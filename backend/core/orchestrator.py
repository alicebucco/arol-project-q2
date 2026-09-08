"""Intent routing and response composition for the conversational API."""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.alarm_codes import alarm_meaning, normalise_alarm_code
from core.auth import AuthContext
from core.business_time import BUSINESS_TODAY
from core.contracts import (
    AgentName,
    AgentRequest,
    AgentResult,
    ConversationTurn,
    OrchestrationPlan,
    PlannerDecision,
)
from core.llm import generate_chat_reply, generate_structured_reply
from core.maintenance_observation import maintenance_observation
from core.operation_registry import OPERATION_REGISTRY, OperationContext
from core.planner import InvalidPlannerOutputError, decide_contextual_question, decide_question


class MissingMachineContextError(ValueError):
    """A machine-specific intent was received without a QR/machine identifier."""


@dataclass(frozen=True)
class OrchestrationResult:
    agent: list[AgentName] | None
    answer: str
    manual_evidence: list[dict[str, Any]] | None = None
    structured_data: dict[str, Any] | None = None


@dataclass(frozen=True)
class EvidenceBundle:
    """Agent results kept separate for composition and for the existing UI."""

    results: list[AgentResult]
    composer_evidence: list[dict[str, Any]]
    structured_data: dict[str, Any]


class ManualSentenceSelection(BaseModel):
    """One selection of source sentences from an authorised manual chunk."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    chunk_id: str = Field(min_length=1, max_length=200)
    sentence_indexes: list[int] = Field(min_length=1, max_length=10)


class ManualSelectionReply(BaseModel):
    """Structured LLM output used only before backend source validation."""

    model_config = ConfigDict(extra="forbid")

    selections: list[ManualSentenceSelection] = Field(default_factory=list, max_length=10)


MACHINE_PATTERN = re.compile(r"\bMCH-[A-Z0-9-]+\b", re.IGNORECASE)
ALARM_CODE_PATTERN = re.compile(r"\bAL\d{3}_[A-Z0-9_]+\b", re.IGNORECASE)
CONTEXT_DEPENDENT_MESSAGE_PATTERN = re.compile(
    r"\b(?:that|this|same) (?:alarm|ticket|order|quote|one)\b|\b(?:it|they|them)\b|"
    r"\b(?:yesterday|today|then|before|after)\b|"
    r"\b(?:quell[oa]|quest[oa]|stess[oa]) (?:allarme|ticket|ordine|preventivo)\b|"
    r"\b(?:ieri|oggi|allora|prima|dopo)\b",
    re.IGNORECASE,
)


def _requires_conversation_context(message: str) -> bool:
    """Return whether a message needs earlier turns to resolve its subject or time."""

    return CONTEXT_DEPENDENT_MESSAGE_PATTERN.search(message) is not None


def _machine_id(message: str, machine_id: str | None) -> str | None:
    if machine_id and machine_id.strip():
        return machine_id.strip()
    match = MACHINE_PATTERN.search(message)
    return match.group(0).upper() if match else None


def _require_machine(message: str, machine_id: str | None) -> str:
    resolved = _machine_id(message, machine_id)
    if resolved is None:
        raise MissingMachineContextError(
            "Select a machine first, or include its ID (for example, MCH-0001) in your question."
        )
    return resolved


async def _execute_plan(
    plan: OrchestrationPlan,
    message: str,
    machine_id: str | None,
    user: AuthContext,
) -> EvidenceBundle:
    """Execute only allow-listed operations and retain each result boundary."""

    target = (
        _require_machine(message, machine_id)
        if OPERATION_REGISTRY.plan_requires_machine_context(plan.requests)
        else None
    )
    context = OperationContext(user=user, machine_id=target)
    # Every request in the current plan contract is independent: no request can
    # consume another request's output. ``gather`` starts their read-only
    # evidence retrieval concurrently while retaining the planner's order in
    # the resulting list for deterministic composition and frontend data.
    results = await asyncio.gather(
        *(OPERATION_REGISTRY.execute(request, context) for request in plan.requests)
    )

    structured_data: dict[str, Any] = {}
    composer_evidence: list[dict[str, Any]] = []
    for result in results:
        if result.structured_data:
            structured_data.update(result.structured_data)
        composer_evidence.append(
            {
                "agent": result.agent,
                "operation": result.operation,
                "evidence": result.evidence,
                "sources": [source.model_dump() for source in result.sources],
                "warnings": result.warnings,
            }
        )
    return EvidenceBundle(results, composer_evidence, structured_data)


def _maintenance_observation_plan() -> OrchestrationPlan:
    """Collect independent IoT and Manuals evidence for a maintenance question."""

    return OrchestrationPlan(requests=[
        AgentRequest(agent="iot", operation="observed_productive_hours"),
        AgentRequest(agent="manuals", operation="maintenance_requirements"),
    ])


def _correlate_maintenance_observation(bundle: EvidenceBundle) -> EvidenceBundle:
    """Add a cautious orchestration conclusion to independent agent evidence."""

    productive_hours = next(
        (item.evidence for item in bundle.results
         if item.agent == "iot" and item.operation == "observed_productive_hours"),
        None,
    )
    manual_requirements = next(
        (item.evidence for item in bundle.results
         if item.agent == "manuals" and item.operation == "maintenance_requirements"),
        None,
    )
    if productive_hours is None or manual_requirements is None:
        raise RuntimeError("Maintenance correlation requires IoT and Manuals evidence.")

    observation = maintenance_observation(
        productive_hours["machine_id"],
        productive_hours,
        manual_requirements["requirements"],
    )
    correlation_evidence = {"maintenance_observation": observation}
    return EvidenceBundle(
        bundle.results,
        [*bundle.composer_evidence, {
            "agent": "orchestrator",
            "operation": "correlate_maintenance_observation",
            "evidence": correlation_evidence,
            "sources": [],
            "warnings": [],
        }],
        correlation_evidence,
    )


async def retrieve_maintenance_observation(
    machine_id: str,
    user: AuthContext,
) -> dict[str, Any]:
    """Retrieve and correlate maintenance evidence for the direct API endpoint."""

    bundle = await _execute_plan(_maintenance_observation_plan(), "", machine_id, user)
    return _correlate_maintenance_observation(bundle).structured_data["maintenance_observation"]


def _alarm_guidance_plan(
    alarm_code: str,
    limit: int,
    *,
    include_recent_events: bool,
) -> OrchestrationPlan:
    """Build atomic alarm-code, optional event, and manual evidence requests."""

    normalized_code = normalise_alarm_code(alarm_code)
    requests = [
        AgentRequest(
            agent="iot",
            operation="alarm_meaning",
            parameters={"alarm_code": normalized_code},
        ),
    ]
    if include_recent_events:
        requests.append(
            AgentRequest(
                agent="iot",
                operation="recent_alarms",
                parameters={"alarm_code": normalized_code, "limit": limit},
            )
        )
    requests.append(
        AgentRequest(
            agent="manuals",
            operation="search",
            parameters={
                "query": (
                    f"{normalized_code} {alarm_meaning(normalized_code)} "
                    "cause remedy troubleshooting"
                ),
                "limit": limit,
            },
        )
    )
    return OrchestrationPlan(requests=requests)


async def retrieve_alarm_guidance_evidence(
    machine_id: str,
    alarm_code: str,
    user: AuthContext,
    limit: int,
) -> EvidenceBundle:
    """Retrieve alarm guidance through the same registered operations as chat."""

    return await _execute_plan(
        _alarm_guidance_plan(
            alarm_code,
            limit,
            include_recent_events=user.visibility in {"full", "technician"},
        ),
        "",
        machine_id,
        user,
    )


def _private_manual_evidence(bundle: EvidenceBundle) -> list[dict[str, Any]]:
    """Return raw manual chunks held only in in-process agent results."""

    chunks: list[dict[str, Any]] = []
    for result in bundle.results:
        if result.agent == "manuals" and result.operation == "search":
            chunks.extend(result.private_evidence.get("manual_evidence", []))
    return chunks


async def _compose_validated_manual_answer(
    message: str,
    bundle: EvidenceBundle,
    manual_evidence: list[dict[str, Any]],
) -> str:
    """Select authorised manual sentences without requiring the LLM to copy quotes."""

    chunks: list[dict[str, Any]] = []
    for evidence in manual_evidence:
        content = evidence.get("content")
        chunk_id = evidence.get("chunk_id")
        if not isinstance(content, str) or not isinstance(chunk_id, str):
            continue
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", content) if sentence.strip()]
        if sentences:
            chunks.append({"chunk_id": chunk_id, "sentences": sentences})

    prompt = (
        f"User question: {message}\n\n"
        "Return a JSON object with exactly one key, `selections`. Each selection must contain `chunk_id` and "
        "`sentence_indexes`, a list of zero-based indexes from that chunk's numbered sentences. Select only sentences "
        "that directly answer the question. Do not write claims, quotes, file names, pages, Markdown, or extra fields. "
        "If no direct sentence is supported, return {\"selections\": []}.\n\n"
        f"Authorised numbered sentences:\n{json.dumps(chunks, ensure_ascii=False)}"
    )
    system_prompt = (
        "You select conservative, source-grounded manual sentences for the AROL Customer Platform. "
        "Return valid JSON only. Do not infer causes, remedies, procedures, completion, or maintenance status."
    )
    try:
        raw_reply = await generate_structured_reply(prompt, system_prompt)
        proposed = ManualSelectionReply.model_validate_json(raw_reply)
    except ValidationError:
        return "I found authorised manual evidence, but could not generate a validated summary. Please review the sources below."

    sentences_by_chunk = {chunk["chunk_id"]: chunk["sentences"] for chunk in chunks}
    selected: list[str] = []
    for selection in proposed.selections:
        sentences = sentences_by_chunk.get(selection.chunk_id)
        if sentences is None:
            continue
        for index in selection.sentence_indexes:
            if 0 <= index < len(sentences):
                selected.append(sentences[index])
    if not selected:
        return "A relevant answer may be found in the sources below. Please review them."
    return "\n".join(dict.fromkeys(selected))


async def _compose_evidence_answer(message: str, bundle: EvidenceBundle) -> str:
    """Compose a grounded answer from bounded, authorised agent evidence."""

    manual_evidence = _private_manual_evidence(bundle)
    if manual_evidence:
        return await _compose_validated_manual_answer(message, bundle, manual_evidence)

    prompt = (
        f"User question: {message}\n\n"
        "Use only the following evidence retrieved by authorised backend tools. "
        "If it is empty, say that no matching records were found. Do not invent values. "
        "Answer only in English and mention relevant IDs or statuses when useful. "
        "Do not include manual citations inline; the frontend presents authorised sources separately. "
        f"Use {BUSINESS_TODAY.isoformat()} as today's date when interpreting "
        "quote expiry, open items, or overdue work.\n\n"
        f"Evidence retrieved by the authorised agents:\n"
        f"{json.dumps(bundle.composer_evidence, default=str, ensure_ascii=False)}"
    )
    system_prompt = (
        "You are the AROL Customer Platform assistant. "
        "The backend has already enforced authentication, company scope, and role permissions. "
        "Summarise only the supplied evidence; never reveal or infer data outside it. "
        "Manual evidence is limited to authorised indexed chunks and citations, never full PDF documents. "
        "Return plain text only: do not use Markdown, HTML, asterisks, square brackets, "
        "backslashes, code fences, or inline citations. Use short paragraphs; if a list is "
        "necessary, use ordinary numbered lines. "
        "For maintenance observations, treat observed productive hours as a bounded telemetry window, "
        "not as a lifetime counter; do not claim a threshold proves maintenance is currently due or completed."
    )
    return await generate_chat_reply(prompt, system_prompt=system_prompt)


def _result_agents(bundle: EvidenceBundle) -> list[AgentName]:
    """Expose every evidence agent once, preserving execution-plan order."""

    return list(dict.fromkeys(result.agent for result in bundle.results))


def _manual_evidence(bundle: EvidenceBundle) -> list[dict[str, Any]] | None:
    """Preserve authorised manual sources for the existing frontend detail view."""

    result = next(
        (
            item
            for item in bundle.results
            if item.agent == "manuals" and item.operation == "search"
        ),
        None,
    )
    return result.evidence.get("manual_evidence") if result is not None else None


async def _manual_fallback_result(
    message: str,
    machine_id: str,
    user: AuthContext,
) -> OrchestrationResult:
    """Use authorised documentation instead of an ungrounded machine reply."""
    plan = OrchestrationPlan(requests=[
        AgentRequest(agent="manuals", operation="search", parameters={"query": message, "limit": 5}),
    ])
    bundle = await _execute_plan(plan, message, machine_id, user)
    manual_evidence = _private_manual_evidence(bundle)
    if not any(item.get("similarity_threshold_met") is True for item in manual_evidence):
        return OrchestrationResult(None, await generate_chat_reply(message))
    return OrchestrationResult(
        _result_agents(bundle),
        await _compose_evidence_answer(message, bundle),
        manual_evidence=_manual_evidence(bundle),
        structured_data=bundle.structured_data,
    )


async def handle_chat(
    message: str,
    user: AuthContext,
    machine_id: str | None = None,
    history: list[ConversationTurn] | None = None,
) -> OrchestrationResult:
    """Route a chat message, collect authorised evidence, and compose an answer."""

    if history and _requires_conversation_context(message):
        try:
            contextual_decision = await decide_contextual_question(message, history, BUSINESS_TODAY)
        except InvalidPlannerOutputError:
            return OrchestrationResult(
                None,
                "I could not safely resolve the reference in the previous messages. Please name the alarm, ticket, order, or quote again.",
            )
        if contextual_decision.action == "ask_clarification":
            return OrchestrationResult(None, contextual_decision.clarification or "Please clarify your request.")
        if contextual_decision.action == "answer_without_evidence":
            return OrchestrationResult(None, await generate_chat_reply(message))
        assert contextual_decision.plan is not None
        bundle = await _execute_plan(contextual_decision.plan, message, machine_id, user)
        return OrchestrationResult(
            _result_agents(bundle),
            await _compose_evidence_answer(message, bundle),
            manual_evidence=_manual_evidence(bundle),
            structured_data=bundle.structured_data,
        )

    try:
        planner_decision = await decide_question(message)
    except InvalidPlannerOutputError:
        if target := _machine_id(message, machine_id):
            return await _manual_fallback_result(message, target, user)
        return OrchestrationResult(
            None,
            "I could not safely create an evidence plan. Please rephrase the request with the relevant machine, alarm, ticket, order, or quote identifier.",
        )
    if planner_decision.action == "answer_without_evidence":
        if target := _machine_id(message, machine_id):
            return await _manual_fallback_result(message, target, user)
        return OrchestrationResult(None, await generate_chat_reply(message))
    plan = planner_decision.plan
    assert plan is not None
    bundle = await _execute_plan(plan, message, machine_id, user)
    return OrchestrationResult(
        _result_agents(bundle),
        await _compose_evidence_answer(message, bundle),
        manual_evidence=_manual_evidence(bundle),
        structured_data=bundle.structured_data,
    )

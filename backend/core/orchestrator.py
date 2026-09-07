"""Intent routing and response composition for the conversational API."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.manuals import validate_manual_claim_links
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
from core.config import get_settings
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


class ManualClaim(BaseModel):
    """One model-proposed claim that must be linked to an authorised chunk."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim: str = Field(min_length=1, max_length=1_000)
    chunk_id: str = Field(min_length=1, max_length=200)
    supporting_quote: str = Field(min_length=1, max_length=2_000)


class ManualClaimReply(BaseModel):
    """Structured LLM output used only before backend claim validation."""

    model_config = ConfigDict(extra="forbid")

    claims: list[ManualClaim] = Field(default_factory=list, max_length=10)


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


def classify_intent(message: str) -> str:
    """Route English and Italian questions before invoking the LLM."""

    text = message.casefold()
    if ALARM_CODE_PATTERN.search(message) and any(
        term in text for term in ("how many", "number of", "count", "quante", "quanti", "conteggio")
    ):
        return "iot"
    if ALARM_CODE_PATTERN.search(message):
        return "alarm_guidance"
    maintenance_due_terms = (
        "maintenance due", "due maintenance", "overdue maintenance", "next maintenance",
        "maintenance threshold", "operating hours", "working hours", "ore di lavoro",
        "ore operative", "manutenzione dovuta", "manutenzione scaduta", "soglia manutenzione",
        "prossima manutenzione", "quando è prevista", "due", "dovuta", "scaduta", "scadenza",
    )
    if any(term in text for term in ("maintenance", "manutenzione")) and any(
        term in text for term in maintenance_due_terms
    ):
        return "maintenance_due"
    maintenance_manual_terms = (
        "periodic", "interval", "procedure", "required", "requirement", "due",
        "scheduled maintenance", "how to maintain", "maintenance schedule",
        "periodic maintenance", "intervallo", "procedura", "richiesto", "scadenza",
    )
    if any(
        word in text
        for word in (
            "manual", "instruction", "configuration", "safety", "installation",
            "assembly", "lubricat", "mechanical", "pneumatic", "pressur", "operation",
            "manuale", "istruzioni", "configurazione", "sicurezza", "installazione",
            "montaggio", "lubrificazione", "meccanico", "pneumatico", "operazione",
        )
    ) or ("maintenance" in text and any(term in text for term in maintenance_manual_terms)):
        return "manuals"
    if any(
        word in text
        for word in (
            "alarm", "telemetr", "production", "uptime", "temperature", "operational status",
            "allarm", "produzion", "temperatura", "stato operativo",
        )
    ):
        return "iot"
    if any(
        word in text
        for word in ("maintenance", "ticket", "intervention", "service", "manutenz", "intervento")
    ):
        return "service"
    if any(
        word in text
        for word in (
            "order", "quote", "price", "discount", "shipment", "cost", "invoice", "purchase",
            "ordine", "ordini", "preventiv", "quotazione", "prezzo", "sconto", "spedizion",
            "costo", "costa", "costat", "fattura", "acquist",
        )
    ):
        return "orders"
    return "general"


def _iso_periods(message: str) -> list[tuple[datetime, datetime]]:
    """Extract inclusive UTC day ranges from ISO dates for the deterministic router."""

    values = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", message)
    periods: list[tuple[datetime, datetime]] = []
    if len(values) == 1:
        value = datetime.fromisoformat(values[0]).date()
        return [(datetime.combine(value, time.min, tzinfo=timezone.utc),
                 datetime.combine(value, time.max, tzinfo=timezone.utc))]
    for index in range(0, len(values) - 1, 2):
        start_date = datetime.fromisoformat(values[index]).date()
        end_date = datetime.fromisoformat(values[index + 1]).date()
        periods.append(
            (
                datetime.combine(start_date, time.min, tzinfo=timezone.utc),
                datetime.combine(end_date, time.max, tzinfo=timezone.utc),
            )
        )
    return periods


def _deterministic_plan(
    intent: str,
    message: str,
    user: AuthContext | None = None,
) -> OrchestrationPlan | None:
    """Temporary planner that maps the legacy router to registered operations.

    It deliberately produces the same strict ``OrchestrationPlan`` that the
    future LLM planner will produce.  Therefore replacing this bridge will not
    change authorisation, parameter validation, agent invocation, or UI data.
    """

    text = message.casefold()
    periods = _iso_periods(message)
    start_time, end_time = periods[0] if periods else (None, None)
    code_match = ALARM_CODE_PATTERN.search(message)
    alarm_code = code_match.group(0).upper() if code_match else None

    if intent == "iot":
        alarm_parameters = {"start_time": start_time, "end_time": end_time, "alarm_code": alarm_code}
        count_terms = ("how many", "number of", "count", "quante", "quanti", "conteggio")
        summary_terms = ("most frequent", "recurring", "repeated", "group", "frequency", "più frequ", "ricorrent")
        telemetry_terms = ("telemetr", "temperature", "energy", "uptime", "production", "temperatura", "energia", "produzion")
        statistic_terms = ("average", "mean", "minimum", "maximum", "total", "trend", "media", "minim", "massim", "totale", "andamento")

        if alarm_code and any(term in text for term in count_terms):
            requests = [AgentRequest(agent="iot", operation="count_alarms", parameters=alarm_parameters)]
        elif "alarm" in text or "allarm" in text:
            operation = "alarm_summary" if any(term in text for term in summary_terms) else "recent_alarms"
            requests = [AgentRequest(agent="iot", operation=operation, parameters={**alarm_parameters, "limit": 20})]
        elif any(term in text for term in telemetry_terms) and any(term in text for term in statistic_terms):
            if len(periods) >= 2 and any(term in text for term in ("compare", "comparison", "confront")):
                requests = [AgentRequest(
                    agent="iot",
                    operation="compare_telemetry_periods",
                    parameters={
                        "first_start": periods[0][0], "first_end": periods[0][1],
                        "second_start": periods[1][0], "second_end": periods[1][1],
                    },
                )]
            else:
                requests = [AgentRequest(
                    agent="iot",
                    operation="telemetry_summary",
                    parameters={"start_time": start_time, "end_time": end_time},
                )]
        else:
            requests = [
                AgentRequest(agent="iot", operation="recent_alarms", parameters={**alarm_parameters, "limit": 20}),
                AgentRequest(agent="iot", operation="telemetry", parameters={"start_time": start_time, "end_time": end_time, "limit": 20}),
            ]
        return OrchestrationPlan(requests=requests)

    if intent == "alarm_guidance" and alarm_code:
        return _alarm_guidance_plan(
            alarm_code,
            limit=5,
            include_recent_events=user is None or user.visibility in {"full", "technician"},
        )

    if intent == "manuals":
        return OrchestrationPlan(
            requests=[AgentRequest(agent="manuals", operation="search", parameters={"query": message, "limit": 5})],
        )
    if intent == "service":
        return OrchestrationPlan(
            requests=[AgentRequest(agent="service", operation="maintenance_tickets", parameters={"limit": 10})],
        )
    if intent == "maintenance_due":
        return _maintenance_observation_plan()
    if intent == "orders":
        return OrchestrationPlan(
            requests=[
                AgentRequest(agent="orders", operation="orders", parameters={"limit": 10}),
                AgentRequest(agent="orders", operation="quotes", parameters={"limit": 10}),
            ],
        )
    return None


def _plan_for_chat(intent: str, message: str, user: AuthContext) -> OrchestrationPlan:
    """Build the temporary deterministic fallback while the planner is disabled."""

    plan = _deterministic_plan(intent, message, user)
    assert plan is not None
    return plan


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
    results = [await OPERATION_REGISTRY.execute(request, context) for request in plan.requests]

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
    """Generate structured manual claims and discard any without valid provenance."""

    prompt = (
        f"User question: {message}\n\n"
        "Return a JSON object with exactly one key, `claims`. Each claim must contain `claim`, `chunk_id`, "
        "and `supporting_quote`. Use only the authorised manual chunks below. A supporting quote must be copied "
        "from the cited chunk. Do not include file names, pages, Markdown, or fields other than those required. "
        "If no direct manual claim is supported, return {\"claims\": []}.\n\n"
        f"Authorised manual chunks:\n{json.dumps(manual_evidence, default=str, ensure_ascii=False)}"
    )
    system_prompt = (
        "You extract conservative, source-grounded manual claims for the AROL Customer Platform. "
        "Return valid JSON only. Do not infer causes, remedies, procedures, completion, or maintenance status "
        "beyond the wording in one cited chunk."
    )
    try:
        raw_reply = await generate_structured_reply(prompt, system_prompt)
        proposed = ManualClaimReply.model_validate_json(raw_reply)
    except ValidationError:
        return "I found authorised manual evidence, but could not generate a validated summary. Please review the sources below."

    validation = validate_manual_claim_links(
        [claim.model_dump() for claim in proposed.claims], manual_evidence,
    )
    claims = [item["claim"] for item in validation["validated_claims"]]
    if not claims:
        return "No directly supported manual claim was produced from the authorised evidence. Please review the sources below."
    return "\n".join(dict.fromkeys(claims))


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


async def handle_chat(
    message: str,
    user: AuthContext,
    machine_id: str | None = None,
    history: list[ConversationTurn] | None = None,
) -> OrchestrationResult:
    """Route a chat message, collect authorised evidence, and compose an answer."""

    planner_enabled = get_settings().llm_planner_enabled
    if history and planner_enabled and _requires_conversation_context(message):
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

    intent = classify_intent(message)
    planner_decision = await decide_question(message) if planner_enabled else None
    if planner_decision is not None and planner_decision.action == "answer_without_evidence":
        return OrchestrationResult(None, await generate_chat_reply(message))
    if intent == "general" and planner_decision is None:
        return OrchestrationResult(None, await generate_chat_reply(message))

    plan = (
        _maintenance_observation_plan()
        if intent == "maintenance_due"
        else planner_decision.plan if planner_decision is not None else _plan_for_chat(intent, message, user)
    )
    assert plan is not None
    bundle = await _execute_plan(plan, message, machine_id, user)
    if intent == "maintenance_due":
        bundle = _correlate_maintenance_observation(bundle)
    return OrchestrationResult(
        _result_agents(bundle),
        await _compose_evidence_answer(message, bundle),
        manual_evidence=_manual_evidence(bundle),
        structured_data=bundle.structured_data,
    )

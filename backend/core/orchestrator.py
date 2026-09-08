"""Chat-level orchestration of authorised evidence workflows."""

from __future__ import annotations

import re
from typing import Any

from core.auth import AuthContext
from core.business_time import BUSINESS_TODAY
from core.contracts import AgentName, AgentRequest, ConversationTurn, OrchestrationPlan, PlannerDecision
from core.llm import generate_chat_reply, generate_structured_reply
from core.operations.catalogue import OPERATION_REGISTRY
from core.orchestration import composer
from core.orchestration.execution import (
    MissingMachineContextError,
    execute_plan as _execute_plan,
    resolve_machine_id as _machine_id,
)
from core.orchestration.models import EvidenceBundle, OrchestrationResult
from core.orchestration.workflows import (
    alarm_guidance_plan,
    correlate_maintenance_observation,
    maintenance_observation_plan,
)
from core.planner import InvalidPlannerOutputError, decide_contextual_question, decide_question


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


async def retrieve_maintenance_observation(machine_id: str, user: AuthContext) -> dict[str, Any]:
    """Retrieve and correlate maintenance evidence for the direct API endpoint."""

    bundle = await _execute_plan(maintenance_observation_plan(), "", machine_id, user)
    return correlate_maintenance_observation(bundle).structured_data["maintenance_observation"]


async def retrieve_alarm_guidance_evidence(
    machine_id: str, alarm_code: str, user: AuthContext, limit: int
) -> EvidenceBundle:
    """Retrieve alarm guidance through the same registered operations as chat."""

    return await _execute_plan(
        alarm_guidance_plan(
            alarm_code,
            limit,
            include_recent_events=user.visibility in {"full", "technician"},
        ),
        "",
        machine_id,
        user,
    )


async def _compose_evidence_answer(message: str, bundle: EvidenceBundle) -> str:
    """Compose evidence using the local LLM dependencies for replaceable tests."""

    return await composer.compose_evidence_answer(
        message,
        bundle,
        generate_chat_reply=generate_chat_reply,
        generate_structured_reply=generate_structured_reply,
    )


def _result_agents(bundle: EvidenceBundle) -> list[AgentName]:
    """Expose every evidence agent once, preserving execution-plan order."""

    return list(dict.fromkeys(result.agent for result in bundle.results))


def _manual_evidence(bundle: EvidenceBundle) -> list[dict[str, Any]] | None:
    """Preserve authorised manual sources for the existing frontend detail view."""

    result = next(
        (item for item in bundle.results if item.agent == "manuals" and item.operation == "search"),
        None,
    )
    return result.evidence.get("manual_evidence") if result is not None else None


async def _manual_fallback_result(message: str, machine_id: str, user: AuthContext) -> OrchestrationResult:
    """Use authorised documentation instead of an ungrounded machine reply."""

    plan = OrchestrationPlan(requests=[
        AgentRequest(agent="manuals", operation="search", parameters={"query": message, "limit": 5}),
    ])
    bundle = await _execute_plan(plan, message, machine_id, user)
    manual_evidence = composer.private_manual_evidence(bundle)
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

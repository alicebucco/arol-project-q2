"""Prompt construction for the future LLM orchestration planner."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from core.contracts import OrchestrationPlan, PlannerDecision
from core.llm import generate_structured_reply
from core.operation_registry import OPERATION_REGISTRY, OperationRegistry, UnknownOperationError


class InvalidPlannerOutputError(ValueError):
    """The model response is not a valid bounded orchestration plan."""


PLANNER_DECISION_SYSTEM_PROMPT = """You decide how the AROL Customer Platform should handle a user question.
Return exactly one JSON object and no Markdown, explanation, or additional keys.
The object must have one of these shapes:
{"action": "answer_without_evidence"}
{"action": "retrieve_evidence", "plan": {"requests": [{"agent": "allowed agent", "operation": "allowed operation", "parameters": {}}]}}

Choose retrieve_evidence only when authorised backend evidence is needed. Choose
answer_without_evidence for general questions that can be answered without
company, machine, manual, or operational data. For retrieve_evidence, choose
only operations from the supplied catalogue. Do not invent agents,
operations, parameters, IDs, dates, database queries, or permissions. Use at
most four independent requests and preserve explicit filters stated by the
user. The decision maker does not answer the user or retrieve evidence.
"""


def build_planner_prompt(message: str, catalogue: list[dict[str, Any]]) -> str:
    """Build the complete, data-free user prompt for one planning request."""

    return (
        f"User question:\n{message}\n\n"
        "Allowed operation catalogue:\n"
        f"{json.dumps(catalogue, ensure_ascii=False, sort_keys=True)}"
    )


def parse_planner_decision(response: str) -> PlannerDecision:
    """Accept only strict JSON that conforms to the top-level decision contract."""

    try:
        payload = json.loads(response)
    except json.JSONDecodeError as error:
        raise InvalidPlannerOutputError("The planner must return one valid JSON object.") from error
    try:
        return PlannerDecision.model_validate(payload)
    except ValidationError as error:
        raise InvalidPlannerOutputError("The planner response does not match the decision contract.") from error


def _validate_plan_requests(plan: OrchestrationPlan, registry: OperationRegistry) -> None:
    """Reject planner requests that the trusted registry would not execute."""

    try:
        for request in plan.requests:
            registry.validate(request)
    except (UnknownOperationError, ValidationError) as error:
        raise InvalidPlannerOutputError("The planner requested an unknown operation or invalid parameters.") from error


async def decide_question(
    message: str,
    registry: OperationRegistry = OPERATION_REGISTRY,
) -> PlannerDecision:
    """Ask the LLM whether evidence is needed and validate any proposed plan."""

    response = await generate_structured_reply(
        build_planner_prompt(message, registry.planner_catalog()),
        PLANNER_DECISION_SYSTEM_PROMPT,
    )
    decision = parse_planner_decision(response)
    if decision.plan is not None:
        _validate_plan_requests(decision.plan, registry)
    return decision

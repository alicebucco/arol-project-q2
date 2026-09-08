"""Backend checks that bind a planner decision to trusted capabilities and context."""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from core.contracts import ContextualPlannerDecision, ConversationTurn, OrchestrationPlan
from core.operations.registry import OperationRegistry, UnknownOperationError
from core.planning.parsing import InvalidPlannerOutputError

ALARM_CODE_REFERENCE_PATTERN = re.compile(r"\bAL\d{3}_[A-Z0-9_]+\b", re.IGNORECASE)


ALARM_FOLLOW_UP_PATTERN = re.compile(
    r"\b(?:that|this|same) alarm\b|\b(?:quell[oa]|quest[oa]|stess[oa]) allarme\b",
    re.IGNORECASE,
)


def validate_plan_requests(plan: OrchestrationPlan, registry: OperationRegistry) -> None:
    """Reject planner requests that the trusted registry would not execute."""

    try:
        for request in plan.requests:
            registry.validate(request)
    except (UnknownOperationError, ValidationError) as error:
        raise InvalidPlannerOutputError("The planner requested an unknown operation or invalid parameters.") from error


def validate_contextual_bindings(decision: ContextualPlannerDecision, history: list[ConversationTurn], message: str) -> None:
    """Ensure inherited identifiers are real conversation text and survive into the proposed plan."""

    if decision.plan is None:
        return
    conversation_text = "\n".join([*(turn.content for turn in history), message]).upper()
    references = [
        *decision.references.alarm_codes,
        *decision.references.ticket_ids,
        *decision.references.order_ids,
        *decision.references.quote_ids,
    ]
    for reference in references:
        normalized = reference.strip().upper()
        if not normalized or normalized not in conversation_text:
            raise InvalidPlannerOutputError("The contextual planner introduced an identifier outside the conversation.")
        if not any(normalized in json.dumps(request.parameters, default=str).upper() for request in decision.plan.requests):
            raise InvalidPlannerOutputError("The contextual planner lost an inherited identifier in its plan.")

    inherited_alarm_codes = {
        match.group(0).upper()
        for turn in history
        for match in ALARM_CODE_REFERENCE_PATTERN.finditer(turn.content)
    }
    is_unambiguous_alarm_follow_up = (
        ALARM_FOLLOW_UP_PATTERN.search(message) is not None and len(inherited_alarm_codes) == 1
    )
    if is_unambiguous_alarm_follow_up:
        inherited_alarm_code = next(iter(inherited_alarm_codes))
        declared_alarm_codes = {code.strip().upper() for code in decision.references.alarm_codes}
        if decision.intent != "alarm_guidance" or declared_alarm_codes != {inherited_alarm_code}:
            raise InvalidPlannerOutputError("Alarm guidance must declare the unambiguous inherited alarm code.")

    if decision.intent == "alarm_guidance" and len(decision.references.alarm_codes) == 1:
        alarm_code = decision.references.alarm_codes[0].strip().upper()
        operations = {(request.agent, request.operation): request.parameters for request in decision.plan.requests}
        meaning = operations.get(("iot", "alarm_meaning"), {})
        recent = operations.get(("iot", "recent_alarms"), {})
        manual = operations.get(("manuals", "search"), {})
        if (
            meaning.get("alarm_code", "").upper() != alarm_code
            or recent.get("alarm_code", "").upper() != alarm_code
            or alarm_code not in manual.get("query", "").upper()
        ):
            raise InvalidPlannerOutputError("Alarm guidance must retain the referenced alarm across its evidence plan.")


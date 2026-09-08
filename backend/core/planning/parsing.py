"""Strict parsing for LLM planner decisions."""

from __future__ import annotations

import json

from pydantic import ValidationError

from core.contracts import ContextualPlannerDecision, PlannerDecision

class InvalidPlannerOutputError(ValueError):
    """The model response is not a valid bounded orchestration plan."""


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


def parse_contextual_planner_decision(response: str) -> ContextualPlannerDecision:
    """Accept only strict JSON matching the contextual planner contract."""

    try:
        payload = json.loads(response)
    except json.JSONDecodeError as error:
        raise InvalidPlannerOutputError("The contextual planner must return one valid JSON object.") from error
    try:
        return ContextualPlannerDecision.model_validate(payload)
    except ValidationError as error:
        raise InvalidPlannerOutputError("The contextual planner response does not match the contract.") from error


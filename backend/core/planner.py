"""Bounded LLM orchestration decisions."""

from __future__ import annotations

from datetime import date

from core.capability_retrieval import CapabilityRetrievalUnavailableError, retrieve_planner_catalogue
from core.contracts import ContextualPlannerDecision, ConversationTurn, PlannerDecision
from core.llm import generate_structured_reply
from core.operations.catalogue import OPERATION_REGISTRY
from core.operations.registry import OperationRegistry
from core.planning.catalogue import catalogue_for_contextual_question, catalogue_for_question
from core.planning.parsing import (
    InvalidPlannerOutputError,
    parse_contextual_planner_decision,
    parse_planner_decision,
)
from core.planning.prompts import (
    CONTEXTUAL_PLANNER_SYSTEM_PROMPT,
    MANUALS_SELECTION_POLICY,
    PLANNER_DECISION_SYSTEM_PROMPT,
    build_contextual_planner_prompt,
    build_planner_prompt,
)
from core.planning.validation import validate_contextual_bindings, validate_plan_requests


CONTEXTUAL_PLANNER_ATTEMPTS = 2
PLANNER_ATTEMPTS = 2


async def _planner_catalogue_for_question(
    message: str,
    registry: OperationRegistry,
) -> list[dict[str, object]]:
    """Build candidates through the local retrieval dependency."""

    return await catalogue_for_question(message, registry, retrieve_planner_catalogue)


async def _planner_catalogue_for_contextual_question(
    message: str,
    history: list[ConversationTurn],
    registry: OperationRegistry,
) -> list[dict[str, object]]:
    """Build context-aware candidates through the local retrieval dependency."""

    return await catalogue_for_contextual_question(message, history, registry, retrieve_planner_catalogue)


async def decide_question(
    message: str,
    registry: OperationRegistry = OPERATION_REGISTRY,
) -> PlannerDecision:
    """Ask the LLM whether evidence is needed and validate any proposed plan."""

    catalogue = await _planner_catalogue_for_question(message, registry)
    prompt = build_planner_prompt(message, catalogue)
    last_error: InvalidPlannerOutputError | None = None
    for attempt in range(PLANNER_ATTEMPTS):
        response = await generate_structured_reply(prompt, PLANNER_DECISION_SYSTEM_PROMPT)
        try:
            decision = parse_planner_decision(response)
            if decision.plan is not None:
                validate_plan_requests(decision.plan, registry)
        except InvalidPlannerOutputError as error:
            last_error = error
            if attempt + 1 < PLANNER_ATTEMPTS:
                prompt += (
                    "\n\nYour previous decision was rejected. Return a corrected JSON decision using only "
                    "the supplied operation catalogue and parameter schemas. Do not use company IDs as "
                    "machine, order, quote, ticket, or alarm identifiers."
                )
            continue
        return decision
    assert last_error is not None
    raise last_error


async def decide_contextual_question(
    message: str,
    history: list[ConversationTurn],
    business_today: date,
    registry: OperationRegistry = OPERATION_REGISTRY,
) -> ContextualPlannerDecision:
    """Plan one follow-up directly from bounded history and the current message."""

    catalogue = await _planner_catalogue_for_contextual_question(message, history, registry)
    prompt = build_contextual_planner_prompt(message, history, business_today, catalogue)
    last_error: InvalidPlannerOutputError | None = None
    for _ in range(CONTEXTUAL_PLANNER_ATTEMPTS):
        response = await generate_structured_reply(prompt, CONTEXTUAL_PLANNER_SYSTEM_PROMPT)
        try:
            decision = parse_contextual_planner_decision(response)
            if decision.plan is not None:
                validate_plan_requests(decision.plan, registry)
                validate_contextual_bindings(decision, history, message)
        except InvalidPlannerOutputError as error:
            last_error = error
            continue
        return decision
    assert last_error is not None
    raise last_error

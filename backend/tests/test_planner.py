import asyncio
from unittest.mock import AsyncMock

import pytest

import core.planner as planner
from core.operation_registry import OPERATION_REGISTRY
from core.planner import (
    PLANNER_DECISION_SYSTEM_PROMPT,
    InvalidPlannerOutputError,
    build_planner_prompt,
    decide_question,
    parse_planner_decision,
)


def test_planner_prompt_exposes_only_the_registry_catalogue() -> None:
    catalogue = OPERATION_REGISTRY.planner_catalog()

    prompt = build_planner_prompt("How often did AL017_LOW_AIR_PRESSURE occur?", catalogue)

    assert "How often did AL017_LOW_AIR_PRESSURE occur?" in prompt
    assert '"operation": "count_alarms"' in prompt
    assert "handler" not in prompt
    assert "Return exactly one JSON object" in PLANNER_DECISION_SYSTEM_PROMPT


def test_planner_decision_must_be_strict_json_matching_the_contract() -> None:
    with pytest.raises(InvalidPlannerOutputError):
        parse_planner_decision("```json\n{}\n```")

    with pytest.raises(InvalidPlannerOutputError):
        parse_planner_decision('{"action": "answer_without_evidence", "unexpected": true}')


def test_planner_decision_parser_accepts_general_and_retrieval_decisions() -> None:
    general = parse_planner_decision('{"action": "answer_without_evidence"}')
    retrieval = parse_planner_decision(
        '{"action": "retrieve_evidence", "plan": {'
        '"requests": [{"agent": "manuals", "operation": "search"}]}}'
    )

    assert general.action == "answer_without_evidence"
    assert retrieval.plan is not None
    assert "answer_without_evidence" in PLANNER_DECISION_SYSTEM_PROMPT


def test_decide_question_returns_a_validated_retrieval_decision(monkeypatch) -> None:
    llm = AsyncMock(return_value=(
        '{"action": "retrieve_evidence", "plan": {"requests": ['
        '{"agent": "iot", "operation": "count_alarms", "parameters": {}}]}}'
    ))
    monkeypatch.setattr(planner, "generate_structured_reply", llm)

    decision = asyncio.run(planner.decide_question("How many alarms occurred?"))

    assert decision.action == "retrieve_evidence"
    assert decision.plan is not None
    assert decision.plan.requests[0].operation == "count_alarms"
    assert llm.await_args.args[1] == PLANNER_DECISION_SYSTEM_PROMPT


def test_decide_question_rejects_unknown_registry_requests(monkeypatch) -> None:
    llm = AsyncMock(return_value=(
        '{"action": "retrieve_evidence", "plan": {"requests": ['
        '{"agent": "iot", "operation": "not_registered", "parameters": {}}]}}'
    ))
    monkeypatch.setattr(planner, "generate_structured_reply", llm)

    with pytest.raises(InvalidPlannerOutputError):
        asyncio.run(planner.decide_question("Do something with alarms"))

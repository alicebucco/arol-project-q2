import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest

import core.planner as planner
from core.operations.catalogue import OPERATION_REGISTRY
from core.planner import (
    PLANNER_DECISION_SYSTEM_PROMPT,
    CONTEXTUAL_PLANNER_SYSTEM_PROMPT,
    MANUALS_SELECTION_POLICY,
    InvalidPlannerOutputError,
    build_contextual_planner_prompt,
    decide_contextual_question,
    build_planner_prompt,
    decide_question,
    parse_planner_decision,
)
from core.contracts import ConversationTurn


def test_planner_prompt_exposes_only_the_registry_catalogue() -> None:
    catalogue = OPERATION_REGISTRY.planner_catalog()

    prompt = build_planner_prompt("How often did AL017_LOW_AIR_PRESSURE occur?", catalogue)

    assert "How often did AL017_LOW_AIR_PRESSURE occur?" in prompt
    assert '"operation": "count_alarms"' in prompt
    assert "handler" not in prompt
    assert "Return exactly one JSON object" in PLANNER_DECISION_SYSTEM_PROMPT
    assert MANUALS_SELECTION_POLICY in PLANNER_DECISION_SYSTEM_PROMPT
    assert MANUALS_SELECTION_POLICY in CONTEXTUAL_PLANNER_SYSTEM_PROMPT
    manuals_search = next(item for item in catalogue if item["agent"] == "manuals" and item["operation"] == "search")
    assert "default documented-evidence operation" in manuals_search["description"]


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
    monkeypatch.setattr(planner, "retrieve_planner_catalogue", AsyncMock(return_value=OPERATION_REGISTRY.planner_catalog()))

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
    monkeypatch.setattr(planner, "retrieve_planner_catalogue", AsyncMock(return_value=OPERATION_REGISTRY.planner_catalog()))

    with pytest.raises(InvalidPlannerOutputError):
        asyncio.run(planner.decide_question("Do something with alarms"))
    assert llm.await_count == 2


def test_decide_question_uses_semantic_candidates_and_keeps_manual_search(monkeypatch) -> None:
    candidates = [
        item
        for item in OPERATION_REGISTRY.planner_catalog()
        if (item["agent"], item["operation"]) == ("iot", "repeated_alarm_patterns")
    ]
    llm = AsyncMock(return_value='{"action": "answer_without_evidence"}')
    retrieve = AsyncMock(return_value=candidates)
    monkeypatch.setattr(planner, "retrieve_planner_catalogue", retrieve)
    monkeypatch.setattr(planner, "generate_structured_reply", llm)

    asyncio.run(planner.decide_question("Why are alarms repeating?"))

    prompt = llm.await_args.args[0]
    assert '"operation": "repeated_alarm_patterns"' in prompt
    assert '"agent": "manuals"' in prompt
    assert '"operation": "search"' in prompt
    assert '"operation": "company_machines"' not in prompt
    retrieve.assert_awaited_once()


def test_decide_question_falls_back_to_complete_catalogue_when_retrieval_is_unavailable(monkeypatch) -> None:
    llm = AsyncMock(return_value='{"action": "answer_without_evidence"}')
    monkeypatch.setattr(
        planner,
        "retrieve_planner_catalogue",
        AsyncMock(side_effect=planner.CapabilityRetrievalUnavailableError("database unavailable")),
    )
    monkeypatch.setattr(planner, "generate_structured_reply", llm)

    asyncio.run(planner.decide_question("What can you do?"))

    prompt = llm.await_args.args[0]
    assert '"operation": "repeated_alarm_patterns"' in prompt
    assert '"operation": "company_machines"' in prompt


def test_contextual_planner_preserves_an_inherited_alarm_across_the_evidence_plan(monkeypatch) -> None:
    alarm_code = "AL082_MINIMUM_CAPS_LEVEL"
    llm = AsyncMock(return_value=(
        '{"action":"retrieve_evidence","intent":"alarm_guidance",'
        f'"references":{{"alarm_codes":["{alarm_code}"],"ticket_ids":[],"order_ids":[],"quote_ids":[]}},'
        '"plan":{"requests":['
        f'{{"agent":"iot","operation":"alarm_meaning","parameters":{{"alarm_code":"{alarm_code}"}}}},'
        f'{{"agent":"iot","operation":"recent_alarms","parameters":{{"alarm_code":"{alarm_code}","limit":5}}}},'
        f'{{"agent":"manuals","operation":"search","parameters":{{"query":"{alarm_code} troubleshooting","limit":5}}}}'
        ']}}'
    ))
    monkeypatch.setattr(planner, "generate_structured_reply", llm)
    retrieve = AsyncMock(return_value=OPERATION_REGISTRY.planner_catalog())
    monkeypatch.setattr(planner, "retrieve_planner_catalogue", retrieve)
    history = [
        ConversationTurn(role="user", content=f"When did {alarm_code} last occur?"),
        ConversationTurn(role="assistant", content="It last occurred at 01:56 UTC."),
    ]

    decision = asyncio.run(decide_contextual_question(
        "Can you tell me more about that alarm?", history, date(2026, 8, 5),
    ))

    assert decision.intent == "alarm_guidance"
    assert decision.references.alarm_codes == [alarm_code]
    assert decision.plan is not None
    assert [(request.agent, request.operation) for request in decision.plan.requests] == [
        ("iot", "alarm_meaning"),
        ("iot", "recent_alarms"),
        ("manuals", "search"),
    ]
    prompt = llm.await_args.args[0]
    assert alarm_code in prompt
    assert "Can you tell me more about that alarm?" in prompt
    assert "unrelated identifiers that merely appear in older turns" in CONTEXTUAL_PLANNER_SYSTEM_PROMPT
    assert llm.await_args.args[1] == CONTEXTUAL_PLANNER_SYSTEM_PROMPT
    assert alarm_code in retrieve.await_args.args[0]


def test_contextual_planner_rejects_alarm_guidance_that_loses_the_inherited_code(monkeypatch) -> None:
    alarm_code = "AL082_MINIMUM_CAPS_LEVEL"
    llm = AsyncMock(return_value=(
        '{"action":"retrieve_evidence","intent":"alarm_guidance",'
        '"references":{"alarm_codes":[],"ticket_ids":[],"order_ids":[],"quote_ids":[]},'
        '"plan":{"requests":[{"agent":"iot","operation":"recent_alarms","parameters":{"limit":5}}]}}'
    ))
    monkeypatch.setattr(planner, "generate_structured_reply", llm)
    monkeypatch.setattr(planner, "retrieve_planner_catalogue", AsyncMock(return_value=OPERATION_REGISTRY.planner_catalog()))
    history = [
        ConversationTurn(role="user", content=f"When did {alarm_code} last occur?"),
        ConversationTurn(role="assistant", content="It last occurred at 01:56 UTC."),
    ]

    with pytest.raises(InvalidPlannerOutputError, match="inherited alarm code"):
        asyncio.run(decide_contextual_question(
            "Can you tell me more about that alarm?", history, date(2026, 8, 5),
        ))


def test_contextual_planner_retries_once_after_an_invalid_response(monkeypatch) -> None:
    alarm_code = "AL082_MINIMUM_CAPS_LEVEL"
    valid_response = (
        '{"action":"retrieve_evidence","intent":"alarm_guidance",'
        f'"references":{{"alarm_codes":["{alarm_code}"],"ticket_ids":[],"order_ids":[],"quote_ids":[]}},'
        '"plan":{"requests":['
        f'{{"agent":"iot","operation":"alarm_meaning","parameters":{{"alarm_code":"{alarm_code}"}}}},'
        f'{{"agent":"iot","operation":"recent_alarms","parameters":{{"alarm_code":"{alarm_code}","limit":5}}}},'
        f'{{"agent":"manuals","operation":"search","parameters":{{"query":"{alarm_code} troubleshooting","limit":5}}}}'
        ']}}'
    )
    llm = AsyncMock(side_effect=["not valid JSON", valid_response])
    monkeypatch.setattr(planner, "generate_structured_reply", llm)
    monkeypatch.setattr(planner, "retrieve_planner_catalogue", AsyncMock(return_value=OPERATION_REGISTRY.planner_catalog()))
    history = [
        ConversationTurn(role="user", content=f"When did {alarm_code} last occur?"),
        ConversationTurn(role="assistant", content="It last occurred at 01:56 UTC."),
    ]

    decision = asyncio.run(decide_contextual_question(
        "Can you tell me more about that alarm?", history, date(2026, 8, 5),
    ))

    assert decision.references.alarm_codes == [alarm_code]
    assert llm.await_count == 2

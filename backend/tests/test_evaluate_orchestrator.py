import asyncio
from unittest.mock import AsyncMock

import pytest

import core.orchestrator as orchestrator
from core.auth import AuthContext
from core.contracts import AgentRequest, AgentResult, OrchestrationPlan, PlannerDecision
from scripts.evaluate_orchestrator import handle_chat_with_trace


def test_trace_records_planned_and_executed_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = OrchestrationPlan(requests=[
        AgentRequest(agent="iot", operation="count_alarms", parameters={"alarm_code": "AL082_MINIMUM_CAPS_LEVEL"}),
        AgentRequest(agent="manuals", operation="search", parameters={"query": "AL082_MINIMUM_CAPS_LEVEL"}),
    ])
    monkeypatch.setattr(orchestrator, "decide_question", AsyncMock(return_value=PlannerDecision(action="retrieve_evidence", plan=plan)))
    bundle = orchestrator.EvidenceBundle(
        [
            AgentResult(agent="iot", operation="count_alarms", evidence={}),
            AgentResult(agent="manuals", operation="search", evidence={}),
        ],
        [],
        {},
    )
    monkeypatch.setattr(orchestrator, "_execute_plan", AsyncMock(return_value=bundle))
    monkeypatch.setattr(orchestrator, "_compose_evidence_answer", AsyncMock(return_value="Grounded answer."))

    result, trace, error = asyncio.run(handle_chat_with_trace(
        "How often did AL082_MINIMUM_CAPS_LEVEL occur?", AuthContext("USR-001", "CMP-001", "full"), "MCH-0001",
    ))

    assert error is None
    assert result is not None
    assert result.answer == "Grounded answer."
    assert trace == {
        "planner_action": "retrieve_evidence",
        "planned_operations": ["iot.count_alarms", "manuals.search"],
        "executed_operations": ["iot.count_alarms", "manuals.search"],
    }

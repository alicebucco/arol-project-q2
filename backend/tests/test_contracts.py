import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from core.contracts import AgentRequest, AgentResult, EvidenceSource, OrchestrationPlan, PlannerDecision
from core.auth import AuthContext
import core.operation_registry as operation_registry
from core.operation_registry import (
    MissingOperationMachineContextError,
    OperationContext,
    OperationDefinition,
    OperationParameters,
    OperationRegistry,
    UnknownOperationError,
)


def test_plan_accepts_a_bounded_multi_agent_request() -> None:
    plan = OrchestrationPlan.model_validate(
        {
            "requests": [
                {"agent": "iot", "operation": "alarm_summary", "parameters": {"alarm_code": "AL017_LOW_AIR_PRESSURE"}},
                {"agent": "service", "operation": "maintenance_tickets", "parameters": {}},
            ],
        }
    )

    assert [request.agent for request in plan.requests] == ["iot", "service"]
    assert plan.requests[0].parameters["alarm_code"] == "AL017_LOW_AIR_PRESSURE"


def test_planner_decision_distinguishes_retrieval_from_general_answer() -> None:
    retrieval = PlannerDecision.model_validate(
        {"action": "retrieve_evidence", "plan": {"requests": [{"agent": "iot", "operation": "recent_alarms"}]}}
    )
    general = PlannerDecision.model_validate({"action": "answer_without_evidence"})

    assert retrieval.plan is not None
    assert general.plan is None

    with pytest.raises(ValidationError):
        PlannerDecision.model_validate({"action": "retrieve_evidence"})


@pytest.mark.parametrize(
    "payload",
    [
        {"requests": []},
        {"requests": [{"agent": "iot", "operation": "recent-alarms"}]},
        {"requests": [{"agent": "unknown", "operation": "search"}]},
        {"requests": [{"agent": "iot", "operation": "recent_alarms", "sql": "SELECT * FROM alarms"}]},
        {"requests": [{"agent": "iot", "operation": "recent_alarms"}], "needs_machine_context": True},
    ],
)
def test_plan_rejects_invalid_or_unapproved_shape(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        OrchestrationPlan.model_validate(payload)


def test_agent_result_keeps_composer_evidence_separate_from_frontend_data() -> None:
    result = AgentResult(
        agent="manuals",
        operation="search",
        evidence={"machine_id": "MCH-0001", "retrieved_at": datetime(2026, 8, 5, 9, 0)},
        sources=[
            EvidenceSource(
                source_id="manual-1",
                source_type="manual",
                citation={"file": "15610_manual_EN.pdf", "page": 32, "section": "safety"},
                excerpt="Wear protective gloves before maintenance.",
            )
        ],
        warnings=["Results are limited to the authorised machine manual."],
        structured_data={"machine_id": "MCH-0001"},
    )

    assert result.evidence["machine_id"] == "MCH-0001"
    assert result.sources[0].citation["page"] == 32
    assert result.structured_data == {"machine_id": "MCH-0001"}


def test_agent_request_uses_empty_parameters_by_default() -> None:
    request = AgentRequest(agent="orders", operation="orders")

    assert request.parameters == {}


def test_registry_rejects_unknown_operations_and_operation_specific_parameters() -> None:
    registry = OperationRegistry([])
    with pytest.raises(UnknownOperationError):
        registry.validate(AgentRequest(agent="iot", operation="not_registered"))

    # ``limit`` is valid for telemetry snapshots, not for a telemetry summary.
    from core.operation_registry import OPERATION_REGISTRY

    with pytest.raises(ValidationError):
        OPERATION_REGISTRY.validate(
            AgentRequest(agent="iot", operation="telemetry_summary", parameters={"limit": 5})
        )

    definition, parameters = OPERATION_REGISTRY.validate(
        AgentRequest(
            agent="iot",
            operation="alarm_guidance_context",
            parameters={"alarm_code": " al017_low_air_pressure ", "limit": 5},
        )
    )
    assert definition.requires_machine_context is True
    assert parameters.alarm_code == "AL017_LOW_AIR_PRESSURE"


def test_registry_exposes_a_non_executable_catalogue_for_the_planner() -> None:
    catalogue = operation_registry.OPERATION_REGISTRY.planner_catalog()
    manuals_search = next(item for item in catalogue if item["agent"] == "manuals" and item["operation"] == "search")

    assert "machine-manual" in manuals_search["description"]
    assert manuals_search["requires_machine_context"] is True
    assert manuals_search["parameters_schema"]["properties"]["query"]["minLength"] == 1
    assert "handler" not in manuals_search


def test_registry_executes_only_with_trusted_required_machine_context() -> None:
    calls: list[OperationContext] = []

    async def handler(_parameters: OperationParameters, context: OperationContext) -> AgentResult:
        calls.append(context)
        return AgentResult(agent="iot", operation="test_operation", evidence={"ok": True})

    registry = OperationRegistry(
        [OperationDefinition("iot", "test_operation", OperationParameters, True, handler)]
    )
    request = AgentRequest(agent="iot", operation="test_operation")
    user = AuthContext("USR-001", "CMP-001", "full")

    with pytest.raises(MissingOperationMachineContextError):
        asyncio.run(registry.execute(request, OperationContext(user=user)))

    result = asyncio.run(registry.execute(request, OperationContext(user=user, machine_id="MCH-0001")))

    assert result.evidence == {"ok": True}
    assert calls[0].machine_id == "MCH-0001"


def test_registry_delegates_to_the_agent_result_entry_point(monkeypatch) -> None:
    expected = AgentResult(
        agent="iot",
        operation="recent_alarms",
        evidence={"machine_id": "MCH-0001", "alarms": []},
        structured_data={"machine_id": "MCH-0001", "alarms": []},
    )
    agent_operation = AsyncMock(return_value=expected)
    monkeypatch.setattr(operation_registry, "recent_alarms_evidence", agent_operation)

    result = asyncio.run(
        operation_registry.OPERATION_REGISTRY.execute(
            AgentRequest(agent="iot", operation="recent_alarms", parameters={"limit": 5}),
            OperationContext(user=AuthContext("USR-001", "CMP-001", "full"), machine_id="MCH-0001"),
        )
    )

    assert result == expected
    agent_operation.assert_awaited_once()
    assert agent_operation.await_args.args[:3] == ("MCH-0001", AuthContext("USR-001", "CMP-001", "full"), 5)
    assert agent_operation.await_args.kwargs["alarm_code"] is None

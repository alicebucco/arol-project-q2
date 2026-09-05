import asyncio
from datetime import datetime

import pytest
from pydantic import ValidationError

from core.contracts import AgentRequest, AgentResult, EvidenceSource, OrchestrationPlan
from core.auth import AuthContext
from core.operation_registry import (
    MissingOperationMachineContextError,
    OperationContext,
    OperationDefinition,
    OperationParameters,
    OperationRegistry,
    UnknownOperationError,
    _manual_sources,
)


def test_plan_accepts_a_bounded_multi_agent_request() -> None:
    plan = OrchestrationPlan.model_validate(
        {
            "requests": [
                {"agent": "iot", "operation": "alarm_summary", "parameters": {"alarm_code": "AL017_LOW_AIR_PRESSURE"}},
                {"agent": "service", "operation": "maintenance_tickets", "parameters": {}},
            ],
            "needs_machine_context": True,
        }
    )

    assert [request.agent for request in plan.requests] == ["iot", "service"]
    assert plan.requests[0].parameters["alarm_code"] == "AL017_LOW_AIR_PRESSURE"


@pytest.mark.parametrize(
    "payload",
    [
        {"requests": [], "needs_machine_context": False},
        {"requests": [{"agent": "iot", "operation": "recent-alarms"}], "needs_machine_context": True},
        {"requests": [{"agent": "unknown", "operation": "search"}], "needs_machine_context": False},
        {"requests": [{"agent": "iot", "operation": "recent_alarms", "sql": "SELECT * FROM alarms"}], "needs_machine_context": True},
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


def test_manual_registry_sources_do_not_include_raw_chunk_content() -> None:
    sources = _manual_sources(
        [{
            "file": "15610_manual_EN.pdf",
            "page": 32,
            "section": "safety",
            "title": "Safety guidance",
            "relevance": 0.8,
            "excerpt": "Wear protective gloves.",
            "content": "This raw chunk must not enter the composer contract.",
        }]
    )

    assert sources[0].excerpt == "Wear protective gloves."
    assert "content" not in sources[0].model_dump()

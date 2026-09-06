import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import core.orchestrator as orchestrator
from core.auth import AuthContext
from core.contracts import AgentResult


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Are there any recent alarms?", "iot"),
        ("What does AL017_LOW_AIR_PRESSURE mean?", "alarm_guidance"),
        ("How many times did AL017_LOW_AIR_PRESSURE occur?", "iot"),
        ("Show the production rate and uptime.", "iot"),
        ("Which maintenance tickets are open?", "service"),
        ("Which maintenance activities are required periodically?", "manuals"),
        ("What maintenance is due after the observed operating hours?", "maintenance_due"),
        ("Quale manutenzione è dovuta in base alle ore operative?", "maintenance_due"),
        ("What installation requirements does this machine have?", "manuals"),
        ("How should I lubricate the machine?", "manuals"),
        ("What should I do about pneumatic pressure issues?", "manuals"),
        ("Why is the machine generating repeated alarms?", "general"),
        ("What is the status of my orders and quotes?", "orders"),
        ("Hello, what can you do?", "general"),
    ],
)
def test_intent_routing(question: str, intent: str) -> None:
    assert orchestrator.classify_intent(question) == intent


def test_manual_intent_uses_composer_with_sanitised_manual_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    manual_evidence = [{
        "file": "15610_manual_EN.pdf",
        "page": 32,
        "section": "safety",
        "excerpt": "Use the safety guard.",
        "title": "Safety guidance",
        "highlights": ["safety"],
        "relevance": 0.8,
    }]
    evidence = {
        "machine_id": "MCH-0001",
        "manual_evidence": manual_evidence,
    }

    async def fake_execute(*_args: object, **_kwargs: object) -> orchestrator.EvidenceBundle:
        return orchestrator.EvidenceBundle(
            [AgentResult(agent="manuals", operation="search", evidence=evidence)],
            [{
                "agent": "manuals",
                "operation": "search",
                "evidence": evidence,
                "sources": [{
                    "source_id": "manual:15610_manual_EN.pdf:32",
                    "source_type": "manual",
                    "citation": {"file": "15610_manual_EN.pdf", "page": 32, "section": "safety"},
                    "excerpt": "Use the safety guard.",
                }],
                "warnings": [],
            }],
            {},
        )

    llm = AsyncMock(return_value="Use the safety guard before maintenance.")
    monkeypatch.setattr(orchestrator, "_execute_plan", fake_execute)
    monkeypatch.setattr(orchestrator, "generate_chat_reply", llm)

    result = asyncio.run(
        orchestrator.handle_chat(
            "Find safety instructions in the manual.",
            AuthContext("USR-001", "CMP-001", "full"),
            "MCH-0001",
        )
    )

    assert result.agent == ["manuals"]
    assert result.answer == "Use the safety guard before maintenance."
    assert result.manual_evidence == manual_evidence
    prompt = llm.await_args.args[0]
    assert "Use the safety guard." in prompt
    assert "Raw source content." not in prompt
    assert "Do not include manual citations inline" in prompt
    assert "Return plain text only" in llm.await_args.kwargs["system_prompt"]


def test_data_agent_keeps_structured_evidence_for_the_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = {
        "machine_id": "MCH-0001",
        "alarms": [{"alarm_id": "ALM-1", "alarm_code": "AL017_LOW_AIR_PRESSURE"}],
        "telemetry": [],
    }

    async def fake_execute(*_args: object, **_kwargs: object) -> orchestrator.EvidenceBundle:
        return orchestrator.EvidenceBundle(
            [AgentResult(agent="iot", operation="recent_alarms", evidence=evidence, structured_data=evidence)],
            [{"agent": "iot", "operation": "recent_alarms", "evidence": evidence, "sources": [], "warnings": []}],
            evidence,
        )

    monkeypatch.setattr(orchestrator, "_execute_plan", fake_execute)
    monkeypatch.setattr(orchestrator, "generate_chat_reply", AsyncMock(return_value="One open alarm was found."))

    result = asyncio.run(
        orchestrator.handle_chat(
            "Are there any recent alarms?",
            AuthContext("USR-001", "CMP-001", "full"),
            "MCH-0001",
        )
    )

    assert result.agent == ["iot"]
    assert result.structured_data == evidence


def test_iot_count_plan_is_executed_through_the_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = orchestrator._deterministic_plan(
        "iot", "How many times did AL017_LOW_AIR_PRESSURE occur?"
    )
    assert plan is not None
    assert plan.requests[0].operation == "count_alarms"

    expected = AgentResult(
        agent="iot", operation="count_alarms", evidence={"occurrences": 4}, structured_data={"machine_id": "MCH-0001"}
    )
    execute = AsyncMock(return_value=expected)
    monkeypatch.setattr(orchestrator.OPERATION_REGISTRY, "execute", execute)

    bundle = asyncio.run(orchestrator._execute_plan(
        plan, "How many times did AL017_LOW_AIR_PRESSURE occur?", "MCH-0001",
        AuthContext("USR-001", "CMP-001", "full"),
    ))

    assert bundle.results == [expected]
    assert bundle.structured_data == {"machine_id": "MCH-0001"}
    assert bundle.composer_evidence[0]["evidence"] == {"occurrences": 4}
    execute.assert_awaited_once()


def test_orchestrator_uses_the_deterministic_plan_only_as_a_fallback() -> None:
    result = orchestrator._plan_for_chat("iot", "Show recurring alarms.", AuthContext("USR-001", "CMP-001", "full"))

    assert result.requests[0].operation == "alarm_summary"


def test_alarm_guidance_fallback_plan_collects_iot_and_manual_evidence() -> None:
    plan = orchestrator._deterministic_plan(
        "alarm_guidance", "What does AL017_LOW_AIR_PRESSURE mean?"
    )

    assert plan is not None
    assert [(request.agent, request.operation) for request in plan.requests] == [
        ("iot", "alarm_meaning"),
        ("iot", "recent_alarms"),
        ("manuals", "search"),
    ]
    assert plan.requests[0].parameters == {
        "alarm_code": "AL017_LOW_AIR_PRESSURE",
    }
    assert plan.requests[1].parameters == {
        "alarm_code": "AL017_LOW_AIR_PRESSURE",
        "limit": 5,
    }
    assert plan.requests[2].parameters["query"] == (
        "AL017_LOW_AIR_PRESSURE Low air pressure cause remedy troubleshooting"
    )


def test_enabled_planner_can_mark_an_operational_sounding_question_as_general(monkeypatch: pytest.MonkeyPatch) -> None:
    decision = orchestrator.PlannerDecision.model_validate({"action": "answer_without_evidence"})
    monkeypatch.setattr(orchestrator, "get_settings", lambda: SimpleNamespace(llm_planner_enabled=True))
    monkeypatch.setattr(orchestrator, "decide_question", AsyncMock(return_value=decision))
    reply = AsyncMock(return_value="I can help with the available machine information.")
    monkeypatch.setattr(orchestrator, "generate_chat_reply", reply)

    result = asyncio.run(
        orchestrator.handle_chat(
            "Show recent alarms.", AuthContext("USR-001", "CMP-001", "full"), "MCH-0001"
        )
    )

    assert result.agent is None
    reply.assert_awaited_once_with("Show recent alarms.")


def test_enabled_planner_executes_its_retrieval_plan_through_the_registry_path(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = orchestrator.OrchestrationPlan.model_validate(
        {"requests": [{"agent": "iot", "operation": "recent_alarms", "parameters": {"limit": 1}}]}
    )
    decision = orchestrator.PlannerDecision.model_validate(
        {"action": "retrieve_evidence", "plan": plan.model_dump()}
    )
    bundle = orchestrator.EvidenceBundle(
        [AgentResult(agent="iot", operation="recent_alarms", evidence={"alarms": []})],
        [{"agent": "iot", "operation": "recent_alarms", "evidence": {"alarms": []}, "sources": [], "warnings": []}],
        {"machine_id": "MCH-0001", "alarms": []},
    )
    execute_plan = AsyncMock(return_value=bundle)
    monkeypatch.setattr(orchestrator, "get_settings", lambda: SimpleNamespace(llm_planner_enabled=True))
    monkeypatch.setattr(orchestrator, "decide_question", AsyncMock(return_value=decision))
    monkeypatch.setattr(orchestrator, "_execute_plan", execute_plan)
    monkeypatch.setattr(orchestrator, "generate_chat_reply", AsyncMock(return_value="No recent alarms were found."))

    result = asyncio.run(
        orchestrator.handle_chat(
            "Show recent alarms.", AuthContext("USR-001", "CMP-001", "full"), "MCH-0001"
        )
    )

    assert result.agent == ["iot"]
    assert result.structured_data == bundle.structured_data
    assert execute_plan.await_args.args[0] == plan




def test_alarm_guidance_uses_composer_with_multi_agent_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    iot_evidence = {
        "alarm_code": "AL017_LOW_AIR_PRESSURE",
        "meaning": "Low air pressure",
    }
    recent_alarms = {"machine_id": "MCH-0001", "alarms": []}
    manual_evidence = [{
        "file": "15610_manual_EN.pdf",
        "page": 97,
        "section": "troubleshooting",
        "excerpt": "Check the pneumatic supply.",
        "title": "Troubleshooting guidance",
    }]
    manual_result = AgentResult(
        agent="manuals",
        operation="search",
        evidence={"machine_id": "MCH-0001", "manual_evidence": manual_evidence},
    )
    bundle = orchestrator.EvidenceBundle(
        [
            AgentResult(
                agent="iot",
                operation="alarm_meaning",
                evidence=iot_evidence,
            ),
            AgentResult(
                agent="iot",
                operation="recent_alarms",
                evidence=recent_alarms,
                structured_data={"machine_id": "MCH-0001", "alarms": []},
            ),
            manual_result,
        ],
        [
            {"agent": "iot", "operation": "alarm_meaning", "evidence": iot_evidence, "sources": [], "warnings": []},
            {"agent": "iot", "operation": "recent_alarms", "evidence": recent_alarms, "sources": [], "warnings": []},
            {"agent": "manuals", "operation": "search", "evidence": manual_result.evidence, "sources": [], "warnings": []},
        ],
        {"machine_id": "MCH-0001", "alarms": []},
    )

    execute_plan = AsyncMock(return_value=bundle)
    llm = AsyncMock(return_value="AL017_LOW_AIR_PRESSURE means low air pressure.")
    monkeypatch.setattr(orchestrator, "_execute_plan", execute_plan)
    monkeypatch.setattr(orchestrator, "generate_chat_reply", llm)

    result = asyncio.run(
        orchestrator.handle_chat(
            "What does AL017_LOW_AIR_PRESSURE mean?",
            AuthContext("USR-001", "CMP-001", "full"),
            "MCH-0001",
        )
    )

    assert result.agent == ["iot", "manuals"]
    assert result.answer == "AL017_LOW_AIR_PRESSURE means low air pressure."
    assert result.manual_evidence == manual_evidence
    assert result.structured_data == bundle.structured_data
    assert execute_plan.await_args.args[0].requests[0].operation == "alarm_meaning"
    assert "Low air pressure" in llm.await_args.args[0]
    assert "Check the pneumatic supply." in llm.await_args.args[0]


def test_maintenance_due_uses_composer_with_the_observation_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    observation = {
        "machine_id": "MCH-0001",
        "observed_productive_hours": 514.26,
        "first_snapshot": datetime(2026, 7, 6, 0, 0),
        "last_snapshot": datetime(2026, 8, 4, 23, 0),
        "snapshot_count": 720,
        "documented_threshold_hours": [40, 500, 1000],
        "reached_threshold_hours": [40, 500],
        "next_threshold_hours": 1000,
        "scope_note": "Observed telemetry, not a lifetime counter.",
    }
    evidence = {"maintenance_observation": observation}

    async def fake_execute(*_args: object, **_kwargs: object) -> orchestrator.EvidenceBundle:
        return orchestrator.EvidenceBundle(
            [AgentResult(agent="service", operation="observed_maintenance_plan", evidence=evidence, structured_data=evidence)],
            [{
                "agent": "service",
                "operation": "observed_maintenance_plan",
                "evidence": evidence,
                "sources": [],
                "warnings": [],
            }],
            evidence,
        )

    llm = AsyncMock(return_value="The available telemetry window contains 514.26 productive hours.")
    monkeypatch.setattr(orchestrator, "_execute_plan", fake_execute)
    monkeypatch.setattr(orchestrator, "generate_chat_reply", llm)

    result = asyncio.run(
        orchestrator.handle_chat(
            "What maintenance is due after the observed operating hours?",
            AuthContext("USR-001", "CMP-001", "full"),
            "MCH-0001",
        )
    )

    assert result.agent == ["service"]
    assert result.answer == "The available telemetry window contains 514.26 productive hours."
    assert result.manual_evidence is None
    assert result.structured_data == {"maintenance_observation": observation}
    assert observation["scope_note"] in llm.await_args.args[0]
    assert "not as a lifetime counter" in llm.await_args.kwargs["system_prompt"]


def test_planner_handles_diagnostics_as_a_generic_multi_agent_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = orchestrator.OrchestrationPlan.model_validate(
        {"requests": [
            {"agent": "iot", "operation": "repeated_alarm_patterns", "parameters": {"limit": 5}},
            {"agent": "service", "operation": "maintenance_tickets", "parameters": {"limit": 5}},
            {"agent": "manuals", "operation": "search", "parameters": {"query": "repeated alarms", "limit": 5}},
        ]}
    )
    decision = orchestrator.PlannerDecision.model_validate(
        {"action": "retrieve_evidence", "plan": plan.model_dump()}
    )
    manual_evidence = [{"file": "15610_manual_EN.pdf", "page": 57, "section": "troubleshooting", "excerpt": "Check the pneumatic supply."}]
    bundle = orchestrator.EvidenceBundle(
        [
            AgentResult(agent="iot", operation="repeated_alarm_patterns", evidence={"alarm_patterns": []}),
            AgentResult(agent="service", operation="maintenance_tickets", evidence={"maintenance_tickets": []}),
            AgentResult(agent="manuals", operation="search", evidence={"manual_evidence": manual_evidence}),
        ],
        [],
        {"alarm_patterns": [], "maintenance_tickets": []},
    )
    monkeypatch.setattr(orchestrator, "get_settings", lambda: SimpleNamespace(llm_planner_enabled=True))
    monkeypatch.setattr(orchestrator, "decide_question", AsyncMock(return_value=decision))
    monkeypatch.setattr(orchestrator, "_execute_plan", AsyncMock(return_value=bundle))
    monkeypatch.setattr(orchestrator, "generate_chat_reply", AsyncMock(return_value="No recurring alarm pattern was found."))

    result = asyncio.run(
        orchestrator.handle_chat(
            "Why is the machine generating repeated alarms?",
            AuthContext("USR-001", "CMP-001", "full"),
            "MCH-0001",
        )
    )

    assert result.agent == ["iot", "service", "manuals"]
    assert result.manual_evidence == manual_evidence
    assert result.structured_data == bundle.structured_data

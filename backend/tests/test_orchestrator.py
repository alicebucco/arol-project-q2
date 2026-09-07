import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import core.orchestrator as orchestrator
from core.auth import AuthContext
from core.contracts import AgentRequest, AgentResult, ContextualPlannerDecision, ConversationTurn, OrchestrationPlan
from core.planner import InvalidPlannerOutputError


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


def test_contextual_follow_up_executes_the_bound_evidence_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    alarm_code = "AL082_MINIMUM_CAPS_LEVEL"
    plan = OrchestrationPlan.model_validate({"requests": [
        {"agent": "iot", "operation": "alarm_meaning", "parameters": {"alarm_code": alarm_code}},
        {"agent": "iot", "operation": "recent_alarms", "parameters": {"alarm_code": alarm_code, "limit": 5}},
        {"agent": "manuals", "operation": "search", "parameters": {"query": f"{alarm_code} troubleshooting", "limit": 5}},
    ]})
    decision = ContextualPlannerDecision.model_validate({
        "action": "retrieve_evidence",
        "intent": "alarm_guidance",
        "references": {"alarm_codes": [alarm_code]},
        "plan": plan.model_dump(),
    })
    bundle = orchestrator.EvidenceBundle(
        [AgentResult(agent="iot", operation="alarm_meaning", evidence={"alarm_code": alarm_code})],
        [],
        {"machine_id": "MCH-0001"},
    )
    execute = AsyncMock(return_value=bundle)
    compose = AsyncMock(return_value="The alarm details are available.")
    contextual_planner = AsyncMock(return_value=decision)
    monkeypatch.setattr(orchestrator, "get_settings", lambda: SimpleNamespace(llm_planner_enabled=True))
    monkeypatch.setattr(orchestrator, "decide_contextual_question", contextual_planner)
    monkeypatch.setattr(orchestrator, "_execute_plan", execute)
    monkeypatch.setattr(orchestrator, "_compose_evidence_answer", compose)
    history = [
        ConversationTurn(role="user", content=f"When did {alarm_code} last occur?"),
        ConversationTurn(role="assistant", content="It last occurred at 01:56 UTC."),
    ]

    result = asyncio.run(orchestrator.handle_chat(
        "Can you tell me more about that alarm?", AuthContext("USR-001", "CMP-001", "full"), "MCH-0001", history,
    ))

    assert result.agent == ["iot"]
    assert result.answer == "The alarm details are available."
    assert contextual_planner.await_args.args == (
        "Can you tell me more about that alarm?", history, orchestrator.BUSINESS_TODAY,
    )
    assert execute.await_args.args[0] == plan
    assert execute.await_args.args[1] == "Can you tell me more about that alarm?"


def test_contextual_follow_up_returns_a_safe_clarification_for_an_invalid_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    execute = AsyncMock()
    monkeypatch.setattr(orchestrator, "get_settings", lambda: SimpleNamespace(llm_planner_enabled=True))
    monkeypatch.setattr(
        orchestrator,
        "decide_contextual_question",
        AsyncMock(side_effect=InvalidPlannerOutputError("lost reference")),
    )
    monkeypatch.setattr(orchestrator, "_execute_plan", execute)
    history = [
        ConversationTurn(role="user", content="When did AL082_MINIMUM_CAPS_LEVEL last occur?"),
        ConversationTurn(role="assistant", content="It last occurred at 01:56 UTC."),
    ]

    result = asyncio.run(orchestrator.handle_chat(
        "Can you tell me more about that alarm?", AuthContext("USR-001", "CMP-001", "full"), "MCH-0001", history,
    ))

    assert result.agent is None
    assert "Please name the alarm" in result.answer
    execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Can you tell me more about that alarm?", True),
        ("How many times did it occur on 2026-07-30?", True),
        ("What is the current production rate?", False),
        ("AL083_FALLEN_BOTTLE_ALARM", False),
    ],
)
def test_conversation_context_is_used_only_for_dependent_messages(message: str, expected: bool) -> None:
    assert orchestrator._requires_conversation_context(message) is expected


def test_explicit_alarm_selection_uses_a_standalone_plan_despite_eight_prior_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alarm_code = "AL083_FALLEN_BOTTLE_ALARM"
    plan = OrchestrationPlan.model_validate({"requests": [
        {"agent": "iot", "operation": "alarm_meaning", "parameters": {"alarm_code": alarm_code}},
        {"agent": "iot", "operation": "recent_alarms", "parameters": {"alarm_code": alarm_code, "limit": 5}},
        {"agent": "manuals", "operation": "search", "parameters": {"query": f"{alarm_code} troubleshooting", "limit": 5}},
    ]})
    decision = orchestrator.PlannerDecision.model_validate(
        {"action": "retrieve_evidence", "plan": plan.model_dump()}
    )
    history = [
        ConversationTurn(role="user", content="Can you tell me more about that alarm?"),
        ConversationTurn(role="assistant", content="No directly supported manual claim was produced."),
        ConversationTurn(role="user", content="How many times did it occur on 2026-07-30?"),
        ConversationTurn(role="assistant", content="AL082_MINIMUM_CAPS_LEVEL occurred once."),
        ConversationTurn(role="user", content="Tell me about AL082_MINIMUM_CAPS_LEVEL and AL083_FALLEN_BOTTLE_ALARM."),
        ConversationTurn(role="assistant", content="Both alarm meanings are available."),
        ConversationTurn(role="user", content="Can you tell me more about that alarm?"),
        ConversationTurn(role="assistant", content="Please specify the alarm code."),
    ]
    bundle = orchestrator.EvidenceBundle(
        [AgentResult(agent="iot", operation="alarm_meaning", evidence={"alarm_code": alarm_code})],
        [],
        {"machine_id": "MCH-0001"},
    )
    contextual_planner = AsyncMock()
    standalone_planner = AsyncMock(return_value=decision)
    execute = AsyncMock(return_value=bundle)
    monkeypatch.setattr(orchestrator, "get_settings", lambda: SimpleNamespace(llm_planner_enabled=True))
    monkeypatch.setattr(orchestrator, "decide_contextual_question", contextual_planner)
    monkeypatch.setattr(orchestrator, "decide_question", standalone_planner)
    monkeypatch.setattr(orchestrator, "_execute_plan", execute)
    monkeypatch.setattr(orchestrator, "_compose_evidence_answer", AsyncMock(return_value="AL083 details."))

    result = asyncio.run(orchestrator.handle_chat(
        alarm_code, AuthContext("USR-001", "CMP-001", "full"), "MCH-0001", history,
    ))

    assert result.answer == "AL083 details."
    contextual_planner.assert_not_awaited()
    standalone_planner.assert_awaited_once_with(alarm_code)
    assert execute.await_args.args[0] == plan


def test_production_question_ignores_unrelated_alarm_history(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = OrchestrationPlan.model_validate({"requests": [
        {"agent": "iot", "operation": "telemetry", "parameters": {"limit": 6}},
    ]})
    decision = orchestrator.PlannerDecision.model_validate(
        {"action": "retrieve_evidence", "plan": plan.model_dump()}
    )
    history = [
        ConversationTurn(role="user", content="Tell me about AL082_MINIMUM_CAPS_LEVEL and AL083_FALLEN_BOTTLE_ALARM."),
        ConversationTurn(role="assistant", content="Both alarm meanings are available."),
    ]
    contextual_planner = AsyncMock()
    standalone_planner = AsyncMock(return_value=decision)
    bundle = orchestrator.EvidenceBundle(
        [AgentResult(agent="iot", operation="telemetry", evidence={"telemetry": []})], [], {"telemetry": []},
    )
    monkeypatch.setattr(orchestrator, "get_settings", lambda: SimpleNamespace(llm_planner_enabled=True))
    monkeypatch.setattr(orchestrator, "decide_contextual_question", contextual_planner)
    monkeypatch.setattr(orchestrator, "decide_question", standalone_planner)
    monkeypatch.setattr(orchestrator, "_execute_plan", AsyncMock(return_value=bundle))
    monkeypatch.setattr(orchestrator, "_compose_evidence_answer", AsyncMock(return_value="Production rate details."))

    result = asyncio.run(orchestrator.handle_chat(
        "What is the current production rate?", AuthContext("USR-001", "CMP-001", "full"), "MCH-0001", history,
    ))

    assert result.answer == "Production rate details."
    contextual_planner.assert_not_awaited()
    standalone_planner.assert_awaited_once_with("What is the current production rate?")


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


def test_manual_composition_reconstructs_selected_source_sentences_and_keeps_chunks_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_chunk = {
        "source": "manual", "chunk_id": "manual-p32-1", "file": "manual.pdf",
        "page": 32, "section": "safety",
        "content": "Disconnect the power supply before maintenance.",
    }
    public_evidence = {
        "machine_id": "MCH-0001",
        "manual_evidence": [{
            "source": "manual", "chunk_id": "manual-p32-1", "file": "manual.pdf",
            "page": 32, "section": "safety", "excerpt": "Disconnect the power supply before maintenance.",
        }],
    }

    async def fake_execute(*_args: object, **_kwargs: object) -> orchestrator.EvidenceBundle:
        result = AgentResult(
            agent="manuals", operation="search", evidence=public_evidence,
            private_evidence={"manual_evidence": [private_chunk]},
        )
        return orchestrator.EvidenceBundle(
            [result],
            [{"agent": "manuals", "operation": "search", "evidence": public_evidence, "sources": [], "warnings": []}],
            {},
        )

    structured = AsyncMock(return_value=(
        '{"selections":[{"chunk_id":"manual-p32-1","sentence_indexes":[0]}]}'
    ))
    monkeypatch.setattr(orchestrator, "_execute_plan", fake_execute)
    monkeypatch.setattr(orchestrator, "generate_structured_reply", structured)
    plain = AsyncMock()
    monkeypatch.setattr(orchestrator, "generate_chat_reply", plain)

    result = asyncio.run(orchestrator.handle_chat(
        "Find safety instructions in the manual.", AuthContext("USR-001", "CMP-001", "full"), "MCH-0001",
    ))

    assert result.answer == "Disconnect the power supply before maintenance."
    assert result.manual_evidence == public_evidence["manual_evidence"]
    assert "content" not in result.manual_evidence[0]
    assert "Disconnect the power supply before maintenance." in structured.await_args.args[0]
    plain.assert_not_awaited()


def test_manual_composition_uses_a_safe_fallback_for_invalid_structured_output(monkeypatch: pytest.MonkeyPatch) -> None:
    private_chunk = {
        "source": "manual", "chunk_id": "manual-p1-1", "file": "manual.pdf",
        "page": 1, "section": "safety", "content": "Wear protective gloves.",
    }

    async def fake_execute(*_args: object, **_kwargs: object) -> orchestrator.EvidenceBundle:
        return orchestrator.EvidenceBundle(
            [AgentResult(
                agent="manuals", operation="search", evidence={"manual_evidence": []},
                private_evidence={"manual_evidence": [private_chunk]},
            )], [], {},
        )

    monkeypatch.setattr(orchestrator, "_execute_plan", fake_execute)
    monkeypatch.setattr(orchestrator, "generate_structured_reply", AsyncMock(return_value="not json"))

    result = asyncio.run(orchestrator.handle_chat(
        "Find safety instructions in the manual.", AuthContext("USR-001", "CMP-001", "full"), "MCH-0001",
    ))

    assert result.answer == "I found authorised manual evidence, but could not generate a validated summary. Please review the sources below."


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


def test_execute_plan_runs_independent_requests_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = OrchestrationPlan(requests=[
        AgentRequest(agent="iot", operation="recent_alarms"),
        AgentRequest(agent="manuals", operation="search", parameters={"query": "safety"}),
    ])
    both_started = asyncio.Event()
    release = asyncio.Event()
    started: list[str] = []

    async def execute(request: AgentRequest, _context: object) -> AgentResult:
        started.append(request.operation)
        if len(started) == 2:
            both_started.set()
        await release.wait()
        return AgentResult(agent=request.agent, operation=request.operation, evidence={"operation": request.operation})

    monkeypatch.setattr(orchestrator.OPERATION_REGISTRY, "execute", execute)

    async def run() -> orchestrator.EvidenceBundle:
        task = asyncio.create_task(orchestrator._execute_plan(
            plan,
            "Find safety information and recent alarms.",
            "MCH-0001",
            AuthContext("USR-001", "CMP-001", "full"),
        ))
        await asyncio.wait_for(both_started.wait(), timeout=0.2)
        release.set()
        return await task

    bundle = asyncio.run(run())

    assert started == ["recent_alarms", "search"]
    assert [result.operation for result in bundle.results] == ["recent_alarms", "search"]


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


def test_enabled_planner_uses_manual_fallback_for_a_general_decision_with_machine_context(monkeypatch: pytest.MonkeyPatch) -> None:
    decision = orchestrator.PlannerDecision.model_validate({"action": "answer_without_evidence"})
    monkeypatch.setattr(orchestrator, "get_settings", lambda: SimpleNamespace(llm_planner_enabled=True))
    monkeypatch.setattr(orchestrator, "decide_question", AsyncMock(return_value=decision))
    fallback = AsyncMock(return_value=orchestrator.OrchestrationResult(["manuals"], "Documented answer."))
    monkeypatch.setattr(orchestrator, "_manual_fallback_result", fallback)

    result = asyncio.run(
        orchestrator.handle_chat(
            "Show recent alarms.", AuthContext("USR-001", "CMP-001", "full"), "MCH-0001"
        )
    )

    assert result.agent == ["manuals"]
    fallback.assert_awaited_once()


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
    productive_hours = {
        "machine_id": "MCH-0001",
        "observed_productive_hours": 514.26,
        "first_snapshot": datetime(2026, 7, 6, 0, 0),
        "last_snapshot": datetime(2026, 8, 4, 23, 0),
        "snapshot_count": 720,
        "scope_note": "Observed telemetry, not a lifetime counter.",
    }
    requirements = {
        "machine_id": "MCH-0001",
        "requirements": [
            {"interval_hours": 40, "citation": {"chunk_id": "p40"}},
            {"interval_hours": 500, "citation": {"chunk_id": "p500"}},
            {"interval_hours": 1000, "citation": {"chunk_id": "p1000"}},
        ],
        "scope_note": "Documentary evidence only.",
    }

    async def fake_execute(*_args: object, **_kwargs: object) -> orchestrator.EvidenceBundle:
        return orchestrator.EvidenceBundle(
            [
                AgentResult(agent="iot", operation="observed_productive_hours", evidence=productive_hours),
                AgentResult(agent="manuals", operation="maintenance_requirements", evidence=requirements),
            ],
            [
                {"agent": "iot", "operation": "observed_productive_hours", "evidence": productive_hours, "sources": [], "warnings": []},
                {"agent": "manuals", "operation": "maintenance_requirements", "evidence": requirements, "sources": [], "warnings": []},
            ],
            {"productive_hours_observation": productive_hours, "maintenance_requirements": requirements},
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

    assert result.agent == ["iot", "manuals"]
    assert result.answer == "The available telemetry window contains 514.26 productive hours."
    assert result.manual_evidence is None
    assert result.structured_data["maintenance_observation"]["reached_threshold_hours"] == [40, 500]
    assert result.structured_data["maintenance_observation"]["next_threshold_hours"] == 1000
    assert requirements["scope_note"] in llm.await_args.args[0]
    assert "not as a lifetime counter" in llm.await_args.kwargs["system_prompt"]


def test_maintenance_due_plan_uses_iot_and_manuals_not_service() -> None:
    plan = orchestrator._deterministic_plan(
        "maintenance_due", "What maintenance is due after the observed operating hours?",
    )

    assert plan is not None
    assert [(request.agent, request.operation) for request in plan.requests] == [
        ("iot", "observed_productive_hours"),
        ("manuals", "maintenance_requirements"),
    ]


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

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

import core.orchestrator as orchestrator
from core.auth import AuthContext


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
        ("Why is the machine generating repeated alarms?", "troubleshoot"),
        ("What is the status of my orders and quotes?", "orders"),
        ("Hello, what can you do?", "general"),
    ],
)
def test_intent_routing(question: str, intent: str) -> None:
    assert orchestrator.classify_intent(question) == intent


def test_manual_answer_uses_local_excerpts_not_raw_chunks() -> None:
    answer = orchestrator._local_manual_answer(
        {
            "manual_evidence": [
                {
                    "file": "15610_manual_EN.pdf",
                    "page": 32,
                    "section": "safety",
                    "content": "This raw chunk must not be shown.",
                    "excerpt": "Wear protective gloves before maintenance.",
                    "title": "Safety guidance",
                }
            ]
        }
    )

    assert "1 relevant manual source" in answer
    assert "This raw chunk" not in answer
    assert "Wear protective gloves" not in answer


def test_manual_intent_never_calls_external_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = {
        "machine_id": "MCH-0001",
        "manual_evidence": [
            {
                "file": "15610_manual_EN.pdf",
                "page": 32,
                "section": "safety",
                "content": "Raw source content.",
                "excerpt": "Use the safety guard.",
                "title": "Safety guidance",
            }
        ],
    }

    async def fake_evidence(*_args: object, **_kwargs: object) -> dict[str, object]:
        return evidence

    llm = AsyncMock(return_value="This must not be used.")
    monkeypatch.setattr(orchestrator, "_evidence", fake_evidence)
    monkeypatch.setattr(orchestrator, "generate_chat_reply", llm)

    result = asyncio.run(
        orchestrator.handle_chat(
            "Find safety instructions in the manual.",
            AuthContext("USR-001", "CMP-001", "full"),
            "MCH-0001",
        )
    )

    assert result.agent == "manuals"
    assert result.manual_evidence == evidence["manual_evidence"]
    llm.assert_not_awaited()


def test_data_agent_keeps_structured_evidence_for_the_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = {
        "machine_id": "MCH-0001",
        "alarms": [{"alarm_id": "ALM-1", "alarm_code": "AL017_LOW_AIR_PRESSURE"}],
        "telemetry": [],
    }

    async def fake_evidence(*_args: object, **_kwargs: object) -> dict[str, object]:
        return evidence

    monkeypatch.setattr(orchestrator, "_evidence", fake_evidence)
    monkeypatch.setattr(orchestrator, "generate_chat_reply", AsyncMock(return_value="One open alarm was found."))

    result = asyncio.run(
        orchestrator.handle_chat(
            "Are there any recent alarms?",
            AuthContext("USR-001", "CMP-001", "full"),
            "MCH-0001",
        )
    )

    assert result.agent == "iot"
    assert result.structured_data == evidence


def test_iot_evidence_uses_database_count_for_count_question(monkeypatch: pytest.MonkeyPatch) -> None:
    count = AsyncMock(return_value={"machine_id": "MCH-0001", "occurrences": 4})
    recent = AsyncMock()
    telemetry = AsyncMock()
    monkeypatch.setattr(orchestrator, "count_alarms", count)
    monkeypatch.setattr(orchestrator, "recent_alarms", recent)
    monkeypatch.setattr(orchestrator, "telemetry", telemetry)

    evidence = asyncio.run(orchestrator._iot_evidence(
        "How many times did AL017_LOW_AIR_PRESSURE occur?",
        "MCH-0001",
        AuthContext("USR-001", "CMP-001", "full"),
    ))

    assert evidence["operation"] == "count_alarms"
    assert evidence["result"]["occurrences"] == 4
    count.assert_awaited_once()
    recent.assert_not_awaited()
    telemetry.assert_not_awaited()


def test_alarm_guidance_never_calls_external_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = {
        "machine_id": "MCH-0001",
        "alarm_code": "AL017_LOW_AIR_PRESSURE",
        "meaning": "Low air pressure",
        "recent_events": [],
        "manual_evidence": [{"file": "15610_manual_EN.pdf", "page": 97}],
    }

    async def fake_evidence(*_args: object, **_kwargs: object) -> dict[str, object]:
        return evidence

    llm = AsyncMock(return_value="This must not be used.")
    monkeypatch.setattr(orchestrator, "_evidence", fake_evidence)
    monkeypatch.setattr(orchestrator, "generate_chat_reply", llm)

    result = asyncio.run(
        orchestrator.handle_chat(
            "What does AL017_LOW_AIR_PRESSURE mean?",
            AuthContext("USR-001", "CMP-001", "full"),
            "MCH-0001",
        )
    )

    assert result.agent == "alarm_guidance"
    assert "Low air pressure" in result.answer
    assert result.manual_evidence == evidence["manual_evidence"]
    llm.assert_not_awaited()


def test_maintenance_due_never_calls_external_llm(monkeypatch: pytest.MonkeyPatch) -> None:
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

    async def fake_evidence(*_args: object, **_kwargs: object) -> dict[str, object]:
        return evidence

    llm = AsyncMock(return_value="This must not be used.")
    monkeypatch.setattr(orchestrator, "_evidence", fake_evidence)
    monkeypatch.setattr(orchestrator, "generate_chat_reply", llm)

    result = asyncio.run(
        orchestrator.handle_chat(
            "What maintenance is due after the observed operating hours?",
            AuthContext("USR-001", "CMP-001", "full"),
            "MCH-0001",
        )
    )

    assert result.agent == "maintenance_due"
    assert "514.26 observed productive hours" in result.answer
    assert "40 h, 500 h" in result.answer
    assert result.manual_evidence is None
    assert result.structured_data == {"maintenance_observation": observation}
    llm.assert_not_awaited()


def test_troubleshoot_never_calls_external_llm_with_manual_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = {
        "machine_id": "MCH-0001",
        "alarms": [{"alarm_id": "ALM-1", "alarm_code": "AL017_LOW_AIR_PRESSURE", "severity": "High", "alarm_status": "Open"}],
        "repeated_alarm_patterns": [{"alarm_code": "AL017_LOW_AIR_PRESSURE", "occurrences": 3, "first_seen": datetime(2026, 7, 1), "last_seen": datetime(2026, 7, 3), "latest_status": "Open"}],
        "telemetry": [{"timestamp": datetime(2026, 7, 3, 12), "operational_status": "Alarm", "alarm_count": 1}],
        "maintenance_tickets": [{"ticket_id": "TCK-1", "ticket_status": "Open", "priority": "High"}],
        "manual_evidence": [{"content": "Restricted manual text.", "excerpt": "Check the pneumatic supply.", "title": "Troubleshooting guidance"}],
    }

    async def fake_evidence(*_args: object, **_kwargs: object) -> dict[str, object]:
        return evidence

    llm = AsyncMock(return_value="This must not be used.")
    monkeypatch.setattr(orchestrator, "_evidence", fake_evidence)
    monkeypatch.setattr(orchestrator, "generate_chat_reply", llm)

    result = asyncio.run(
        orchestrator.handle_chat(
            "Why is the machine generating repeated alarms?",
            AuthContext("USR-001", "CMP-001", "full"),
            "MCH-0001",
        )
    )

    assert result.agent == "troubleshoot"
    assert result.manual_evidence == evidence["manual_evidence"]
    assert result.structured_data is not None
    assert "manual_evidence" not in result.structured_data
    assert result.structured_data["alarm_patterns"] == evidence["repeated_alarm_patterns"]
    assert "Repeated alarm analysis" in result.answer
    llm.assert_not_awaited()

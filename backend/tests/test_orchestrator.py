import asyncio
from unittest.mock import AsyncMock

import pytest

import core.orchestrator as orchestrator
from core.auth import AuthContext


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Are there any recent alarms?", "iot"),
        ("Show the production rate and uptime.", "iot"),
        ("Which maintenance tickets are open?", "service"),
        ("Which maintenance activities are required periodically?", "manuals"),
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


def test_troubleshoot_never_calls_external_llm_with_manual_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = {
        "machine_id": "MCH-0001",
        "alarms": [{"alarm_id": "ALM-1", "alarm_code": "AL017_LOW_AIR_PRESSURE", "severity": "High", "alarm_status": "Open"}],
        "telemetry": [{"operational_status": "Alarm"}],
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
    llm.assert_not_awaited()

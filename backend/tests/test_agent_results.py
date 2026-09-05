import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import agents.iot as iot
import agents.manuals as manuals
import agents.orders as orders_agent
import agents.service as service
from core.auth import AuthContext


USER = AuthContext("USR-001", "CMP-001", "full")


def test_iot_evidence_entry_point_returns_agent_result(monkeypatch) -> None:
    alarms = [{"alarm_id": "ALM-1", "timestamp": datetime(2026, 8, 5)}]
    monkeypatch.setattr(iot, "recent_alarms", AsyncMock(return_value=alarms))

    result = asyncio.run(iot.recent_alarms_evidence("MCH-0001", USER, 20))

    assert result.agent == "iot"
    assert result.operation == "recent_alarms"
    assert result.evidence == {"machine_id": "MCH-0001", "alarms": alarms}
    assert result.structured_data == {"machine_id": "MCH-0001", "alarms": alarms}


def test_alarm_guidance_context_keeps_operational_events_role_scoped(monkeypatch) -> None:
    monkeypatch.setattr(iot, "authorize_machine", AsyncMock())
    events = AsyncMock(return_value=[{"alarm_id": "ALM-1"}])
    monkeypatch.setattr(iot, "get_recent_alarms_for_code", events)

    technical = asyncio.run(
        iot.alarm_guidance_context_evidence("MCH-0001", USER, "AL017_LOW_AIR_PRESSURE", 5)
    )
    commercial = asyncio.run(
        iot.alarm_guidance_context_evidence(
            "MCH-0001", AuthContext("USR-002", "CMP-001", "commercial"), "AL017_LOW_AIR_PRESSURE", 5
        )
    )

    assert technical.evidence["meaning"] == "Low air pressure"
    assert technical.structured_data == {"machine_id": "MCH-0001", "alarms": [{"alarm_id": "ALM-1"}]}
    assert commercial.evidence["recent_events"] == []
    assert commercial.warnings == ["Operational event history is unavailable for the current role."]
    assert events.await_count == 1


def test_service_evidence_entry_point_returns_agent_result(monkeypatch) -> None:
    tickets = [{"ticket_id": "TCK-1"}]
    monkeypatch.setattr(service, "maintenance_tickets", AsyncMock(return_value=tickets))

    result = asyncio.run(service.maintenance_tickets_evidence("MCH-0001", USER, 10))

    assert result.agent == "service"
    assert result.operation == "maintenance_tickets"
    assert result.structured_data == {"machine_id": "MCH-0001", "maintenance_tickets": tickets}


def test_orders_evidence_entry_point_returns_agent_result(monkeypatch) -> None:
    orders = [{"order_id": "ORD-1"}]
    monkeypatch.setattr(orders_agent, "orders", AsyncMock(return_value=orders))

    result = asyncio.run(orders_agent.orders_evidence(USER, 10))

    assert result.agent == "orders"
    assert result.operation == "orders"
    assert result.evidence == {"orders": orders}
    assert result.structured_data == {"orders": orders}


def test_manuals_evidence_entry_point_excludes_raw_chunk_content(monkeypatch) -> None:
    matches = [{
        "file": "15610_manual_EN.pdf",
        "page": 32,
        "section": "safety",
        "title": "Safety guidance",
        "relevance": 0.8,
        "excerpt": "Wear protective gloves.",
        "content": "This raw chunk is local-only.",
    }]
    monkeypatch.setattr(manuals, "search", AsyncMock(return_value=matches))

    result = asyncio.run(manuals.search_evidence("MCH-0001", "safety", USER, 5))

    assert result.agent == "manuals"
    assert result.evidence["machine_id"] == "MCH-0001"
    assert result.evidence["match_count"] == 1
    assert result.evidence["manual_evidence"][0]["excerpt"] == "Wear protective gloves."
    assert "content" not in result.evidence["manual_evidence"][0]
    assert "content" not in result.structured_data["manual_evidence"][0]
    assert "content" not in result.sources[0].model_dump()

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import main
from core.auth import AuthContext, get_current_user
from core.llm import LlmRequestError
from core.contracts import AgentResult
from core.orchestrator import EvidenceBundle, OrchestrationResult


FULL_USER = AuthContext("USR-001", "CMP-001", "full")


@pytest.fixture
def client() -> TestClient:
    main.app.dependency_overrides[get_current_user] = lambda: FULL_USER
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


class FakeCursor:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.row = row

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, *_args: object) -> None:
        return None

    async def fetchone(self) -> tuple[object, ...] | None:
        return self.row


class FakeConnection:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.cursor_instance = FakeCursor(row)

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_login_and_current_session(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "authenticate_password", AsyncMock(return_value=FULL_USER))
    monkeypatch.setattr(main, "create_access_token", lambda _user: "test-token")

    response = client.post("/auth/login", json={"user_id": "USR-001", "password": "password123"})

    assert response.status_code == 200
    assert response.json()["access_token"] == "test-token"
    assert response.json()["user"] == {"user_id": "USR-001", "company_id": "CMP-001", "visibility": "full"}
    assert client.get("/auth/me").json()["user_id"] == "USR-001"


def test_profile_and_order_detail_endpoints(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "get_user_profile",
        AsyncMock(return_value={
            "user_id": "USR-001", "company_id": "CMP-001", "visibility": "full",
            "first_name": "Elena", "last_name": "Fabbri", "email": "elena@example.com",
            "job_title": "Plant Manager", "company_name": "Valgrande", "country": "Italy",
            "city": "Novara", "sector": "Beverage", "currency": "EUR", "locale": "it-IT",
        }),
    )
    monkeypatch.setattr(
        main,
        "get_company_order_detail",
        AsyncMock(return_value={
            "order_id": "ORD-1", "quote_id": "QTE-1", "order_status": "Confirmed",
            "shipment_status": "Ready for shipment", "currency": "EUR",
            "approved_revision": {"revision_number": 2, "revision_status": "Approved", "discount_rate": 0.05},
            "items": [{"quote_line_id": "QLN-1", "machine_id": "MCH-1", "description": "Head kit", "price": 100.0}],
            "fulfillment": [{"order_line_id": "OLN-1", "fulfillment_status": "Manufacturing"}],
        }),
    )

    profile = client.get("/profile")
    order = client.get("/orders/ORD-1")

    assert profile.status_code == 200
    assert profile.json()["company_name"] == "Valgrande"
    assert order.status_code == 200
    assert order.json()["approved_revision"]["revision_number"] == 2
    assert order.json()["items"][0]["description"] == "Head kit"


def test_machine_list_and_qr_lookup(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "get_company_machines",
        AsyncMock(
            return_value=[
                {
                    "machine_id": "MCH-0001",
                    "serial_number": "15610",
                    "model_code": "CLOSER-1",
                    "model_description": "Closing machine",
                    "plant_location": "Line 1",
                    "configuration_profile": "standard",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        main,
        "connection",
        lambda: FakeConnection(
            ("MCH-0001", "15610", "CMP-001", "Valgrande", "MODEL-1", "CLOSER-1", "Closing machine", date(2025, 1, 15), "Line 1", "standard", "SIEMENS-SIMATIC-S7", "1.0")
        ),
    )

    machines = client.get("/machines")
    lookup = client.get("/machines/lookup/15610")

    assert machines.status_code == 200
    assert machines.json()[0]["machine_id"] == "MCH-0001"
    assert lookup.status_code == 200
    assert lookup.json()["company_id"] == "CMP-001"
    assert lookup.json()["plc_family"] == "SIEMENS-SIMATIC-S7"
    assert "serial 15610" in lookup.json()["operational_context"]


def test_operational_and_service_endpoints(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp = datetime(2026, 8, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(
        main,
        "recent_alarms",
        AsyncMock(return_value=[{"alarm_id": "ALM-1", "timestamp": timestamp, "alarm_code": "AL017_LOW_AIR_PRESSURE", "severity": "High", "alarm_status": "Open"}]),
    )
    monkeypatch.setattr(
        main,
        "telemetry",
        AsyncMock(return_value=[{"timestamp": timestamp, "operational_status": "Alarm", "production_rate_bph": 0, "uptime_percentage": 0, "alarm_count": 1, "temperature_c": 24.5, "energy_kwh": 2.0, "health_note": None}]),
    )
    monkeypatch.setattr(
        main,
        "maintenance_tickets",
        AsyncMock(return_value=[{"ticket_id": "TCK-1", "alarm_id": "ALM-1", "ticket_type": "Remote troubleshooting", "ticket_status": "Open", "priority": "High", "created_date": timestamp, "owner_role": "technician"}]),
    )

    alarms = client.get("/machines/MCH-0001/alarms?limit=5")
    telemetry = client.get("/machines/MCH-0001/telemetry?limit=5")
    tickets = client.get("/machines/MCH-0001/maintenance-tickets?limit=5")

    assert alarms.status_code == telemetry.status_code == tickets.status_code == 200
    assert alarms.json()[0]["alarm_code"] == "AL017_LOW_AIR_PRESSURE"
    assert telemetry.json()[0]["temperature_c"] == 24.5
    assert tickets.json()[0]["ticket_status"] == "Open"


def test_alarm_guidance_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp = datetime(2026, 8, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(
        main,
        "retrieve_alarm_guidance_evidence",
        AsyncMock(
            return_value=EvidenceBundle(
                [
                    AgentResult(
                        agent="iot",
                        operation="alarm_guidance_context",
                        evidence={
                            "machine_id": "MCH-0001",
                            "alarm_code": "AL017_LOW_AIR_PRESSURE",
                            "meaning": "Low air pressure",
                            "recent_events": [{"alarm_id": "ALM-1", "timestamp": timestamp, "alarm_code": "AL017_LOW_AIR_PRESSURE", "severity": "High", "alarm_status": "Open"}],
                        },
                    ),
                    AgentResult(
                        agent="manuals",
                        operation="search",
                        evidence={
                            "machine_id": "MCH-0001",
                            "manual_evidence": [{"source": "manual", "file": "15610_manual_EN.pdf", "page": 97, "section": "mechanical", "excerpt": "Check the pressure.", "title": "Mechanical procedure", "highlights": ["pressure"], "relevance": 0.8, "similarity": 0.7}],
                        },
                    ),
                ],
                [],
                {"machine_id": "MCH-0001", "alarms": []},
            )
        ),
    )

    response = client.get("/machines/MCH-0001/alarms/AL017_LOW_AIR_PRESSURE/guidance")

    assert response.status_code == 200
    assert response.json()["meaning"] == "Low air pressure"
    assert response.json()["recent_events"][0]["alarm_id"] == "ALM-1"
    assert response.json()["manual_evidence"][0]["excerpt"] == "Check the pressure."


def test_maintenance_observation_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp = datetime(2026, 8, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(
        main,
        "observed_maintenance_plan",
        AsyncMock(
            return_value={
                "machine_id": "MCH-0001",
                "observed_productive_hours": 42.5,
                "first_snapshot": timestamp,
                "last_snapshot": timestamp,
                "snapshot_count": 24,
                "documented_threshold_hours": [40, 500],
                "reached_threshold_hours": [40],
                "next_threshold_hours": 500,
                "scope_note": "Observed window only.",
            }
        ),
    )

    response = client.get("/machines/MCH-0001/maintenance-observation")

    assert response.status_code == 200
    assert response.json()["observed_productive_hours"] == 42.5
    assert response.json()["reached_threshold_hours"] == [40]
    assert response.json()["first_snapshot"] == timestamp.isoformat()


def test_manual_search_returns_excerpt_and_rejects_path_traversal(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "search_manual",
        AsyncMock(return_value=[{"source": "manual", "file": "15610_manual_EN.pdf", "page": 32, "section": "safety", "content": "Long raw chunk", "excerpt": "Wear protective gloves.", "title": "Safety guidance", "highlights": ["safety"], "relevance": 0.9, "similarity": 0.82}]),
    )

    search = client.get("/machines/MCH-0001/manuals/search?query=safety")
    unsafe_file = client.get("/machines/MCH-0001/manuals/files/../secret.pdf")

    assert search.status_code == 200
    assert search.json()[0]["excerpt"] == "Wear protective gloves."
    assert search.json()[0]["title"] == "Safety guidance"
    assert search.json()[0]["highlights"] == ["safety"]
    assert "content" not in search.json()[0]
    assert unsafe_file.status_code == 404


def test_troubleshooting_response_includes_manual_excerpt(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp = datetime(2026, 8, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(
        main,
        "investigate",
        AsyncMock(
            return_value={
                "machine_id": "MCH-0001",
                "query": "low pressure",
                "summary": "Evidence collected.",
                "alarms": [{"alarm_id": "ALM-1", "timestamp": timestamp, "alarm_code": "AL017_LOW_AIR_PRESSURE", "severity": "High", "alarm_status": "Open"}],
                "telemetry": [{"timestamp": timestamp, "operational_status": "Alarm", "production_rate_bph": 0, "uptime_percentage": 0, "alarm_count": 1, "temperature_c": None, "energy_kwh": None, "health_note": None}],
                "maintenance_tickets": [{"ticket_id": "TCK-1", "alarm_id": "ALM-1", "ticket_type": "Remote troubleshooting", "ticket_status": "Open", "priority": "High", "created_date": timestamp, "owner_role": "technician"}],
                "manual_evidence": [{"source": "manual", "file": "15610_manual_EN.pdf", "page": 57, "section": "troubleshooting", "content": "Long raw chunk", "excerpt": "Check the pneumatic supply.", "title": "Troubleshooting guidance", "highlights": ["pressure"], "relevance": 0.84, "similarity": 0.79}],
            }
        ),
    )

    response = client.get("/machines/MCH-0001/troubleshoot?query=low%20pressure")

    assert response.status_code == 200
    assert response.json()["manual_evidence"][0]["excerpt"] == "Check the pneumatic supply."
    assert response.json()["manual_evidence"][0]["title"] == "Troubleshooting guidance"
    assert "content" not in response.json()["manual_evidence"][0]
    assert response.json()["alarms"][0]["alarm_id"] == "ALM-1"


def test_orders_and_quotes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "orders", AsyncMock(return_value=[{"order_id": "ORD-1", "quote_id": "Q-1", "order_status": "Confirmed", "shipment_status": "Ready for shipment"}]))
    monkeypatch.setattr(main, "quotes", AsyncMock(return_value=[{"quote_id": "Q-1", "valid_until": None, "validity_status": "Unknown", "revision_number": 2, "revision_status": "Approved", "discount_rate": 0.1, "line_total": 1250.5}]))

    orders = client.get("/orders")
    quotes = client.get("/quotes")

    assert orders.status_code == quotes.status_code == 200
    assert orders.json()[0]["shipment_status"] == "Ready for shipment"
    assert quotes.json()[0]["line_total"] == 1250.5
    assert quotes.json()[0]["validity_status"] == "Unknown"


def test_quote_history_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "get_company_quote_history",
        AsyncMock(
            return_value={
                "quote_id": "QTE-2025-0001",
                "valid_until": date(2026, 8, 5),
                "validity_status": "Valid",
                "currency": "EUR",
                "created_at": "2025-03-10",
                "description": "Scheduled service",
                "revisions": [
                    {
                        "quote_revision_id": "QREV-1",
                        "revision_number": 1,
                        "revision_status": "Approved",
                        "discount_rate": 0.05,
                        "issued_at": "2025-03-28",
                        "change_summary": "Discount applied",
                        "line_total": 100.0,
                        "lines": [{"quote_line_id": "QLN-1", "machine_id": "MCH-0001", "description": "Head kit", "price": 100.0}],
                    }
                ],
                "latest_comparison": [{"change": "price_changed", "machine_id": "MCH-0001", "description": "Head kit", "previous_price": 105.0, "current_price": 100.0}],
            }
        ),
    )

    response = client.get("/quotes/QTE-2025-0001")

    assert response.status_code == 200
    assert response.json()["revisions"][0]["lines"][0]["description"] == "Head kit"
    assert response.json()["latest_comparison"][0]["change"] == "price_changed"


def test_chat_success_and_provider_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "handle_chat",
        AsyncMock(return_value=OrchestrationResult("iot", "One open alarm was found.", structured_data={"machine_id": "MCH-0001", "alarms": []})),
    )
    success = client.post("/chat", json={"message": "Are there any recent alarms?", "machine_id": "MCH-0001"})

    monkeypatch.setattr(main, "handle_chat", AsyncMock(side_effect=LlmRequestError()))
    failure = client.post("/chat", json={"message": "Are there any recent alarms?", "machine_id": "MCH-0001"})

    assert success.status_code == 200
    assert success.json() == {
        "answer": "One open alarm was found.",
        "agent": "iot",
        "sources": [],
        "data": {"machine_id": "MCH-0001", "alarms": []},
    }
    assert failure.status_code == 502
    assert failure.json()["detail"] == "The LLM provider could not complete the request."


def test_manual_chat_returns_structured_sources(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    source = {
        "source": "manual",
        "file": "15610_manual_EN.pdf",
        "page": 32,
        "section": "safety",
        "content": "Long raw chunk",
        "excerpt": "Wear protective gloves before maintenance.",
        "title": "Safety guidance",
        "highlights": ["safety", "maintenance"],
        "relevance": 0.9,
        "similarity": 0.82,
    }
    monkeypatch.setattr(
        main,
        "handle_chat",
        AsyncMock(return_value=OrchestrationResult("manuals", "I found 1 relevant manual source.", [source])),
    )

    response = client.post("/chat", json={"message": "Find safety instructions in the manual.", "machine_id": "MCH-0001"})

    assert response.status_code == 200
    assert response.json()["sources"][0]["title"] == "Safety guidance"
    assert response.json()["sources"][0]["highlights"] == ["safety", "maintenance"]
    assert "content" not in response.json()["sources"][0]


def test_input_validation(client: TestClient) -> None:
    assert client.post("/chat", json={"message": "   ", "machine_id": "MCH-0001"}).status_code == 422
    assert client.get("/machines/MCH-0001/alarms?limit=0").status_code == 422
    assert client.get("/machines/MCH-0001/manuals/search?query=%20%20").status_code == 422

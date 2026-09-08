from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from api import auth, chat, commercial, machines as machine_routes, manuals, operations
import main
from core.auth import AuthContext, get_current_user
from db.repositories.errors import MachineNotFoundError, MachineUnavailableError
from core.llm import LlmRequestError
from core.contracts import AgentResult, ConversationTurn
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
    monkeypatch.setattr(auth, "authenticate_password", AsyncMock(return_value=FULL_USER))
    monkeypatch.setattr(auth, "create_access_token", lambda _user: "test-token")

    response = client.post("/auth/login", json={"user_id": "USR-001", "password": "password123"})

    assert response.status_code == 200
    assert response.json()["access_token"] == "test-token"
    assert response.json()["user"] == {"user_id": "USR-001", "company_id": "CMP-001", "visibility": "full"}
    assert client.get("/auth/me").json()["user_id"] == "USR-001"


def test_profile_and_order_detail_endpoints(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth,
        "get_user_profile",
        AsyncMock(return_value={
            "user_id": "USR-001", "company_id": "CMP-001", "visibility": "full",
            "first_name": "Elena", "last_name": "Fabbri", "email": "elena@example.com",
            "job_title": "Plant Manager", "company_name": "Valgrande", "country": "Italy",
            "city": "Novara", "sector": "Beverage", "currency": "EUR", "locale": "it-IT",
        }),
    )
    monkeypatch.setattr(
        commercial,
        "order_detail",
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
        machine_routes,
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
        machine_routes,
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
        operations,
        "recent_alarms",
        AsyncMock(return_value=[{"alarm_id": "ALM-1", "timestamp": timestamp, "alarm_code": "AL017_LOW_AIR_PRESSURE", "severity": "High", "alarm_status": "Open"}]),
    )
    monkeypatch.setattr(
        operations,
        "telemetry",
        AsyncMock(return_value=[{"timestamp": timestamp, "operational_status": "Alarm", "production_rate_bph": 0, "uptime_percentage": 0, "alarm_count": 1, "temperature_c": 24.5, "energy_kwh": 2.0, "health_note": None}]),
    )
    monkeypatch.setattr(
        operations,
        "search_tickets",
        AsyncMock(return_value={"items": [{"ticket_id": "TCK-1", "alarm_id": "ALM-1", "ticket_type": "Remote troubleshooting", "ticket_status": "Open", "priority": "High", "created_date": timestamp, "owner_role": "Maintenance Man"}], "total_count": 1, "returned_count": 1, "is_truncated": False, "limit": 5}),
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
        operations,
        "retrieve_alarm_guidance_evidence",
        AsyncMock(
            return_value=EvidenceBundle(
                [
                    AgentResult(
                        agent="iot",
                        operation="alarm_meaning",
                        evidence={
                            "alarm_code": "AL017_LOW_AIR_PRESSURE",
                            "meaning": "Low air pressure",
                        },
                    ),
                    AgentResult(
                        agent="iot",
                        operation="recent_alarms",
                        evidence={
                            "machine_id": "MCH-0001",
                            "alarms": [{"alarm_id": "ALM-1", "timestamp": timestamp, "alarm_code": "AL017_LOW_AIR_PRESSURE", "severity": "High", "alarm_status": "Open"}],
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
        operations,
        "retrieve_maintenance_observation",
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
        manuals,
        "search_manual",
        AsyncMock(return_value=[{"source": "manual", "chunk_id": "15610-p32-1", "file": "15610_manual_EN.pdf", "page": 32, "section": "safety", "content": "Long raw chunk", "excerpt": "Long raw chunk", "title": "Manual excerpt", "highlights": ["safety"], "relevance": 0.9, "similarity": 0.82, "similarity_threshold_met": True, "alarm_code_match": "not_requested", "excerpt_is_complete_chunk": True, "section_category": "safety", "section_category_is_inferred": True, "documented_section_title": None}]),
    )

    search = client.get("/machines/MCH-0001/manuals/search?query=safety")
    unsafe_file = client.get("/machines/MCH-0001/manuals/files/../secret.pdf")

    assert search.status_code == 200
    assert search.json()[0]["excerpt"] == "Long raw chunk"
    assert search.json()[0]["title"] == "Manual excerpt"
    assert search.json()[0]["highlights"] == ["safety"]
    assert "content" not in search.json()[0]
    assert search.json()[0]["citation"]["chunk_id"] == "15610-p32-1"
    assert search.json()[0]["excerpt_is_complete_chunk"] is True
    assert search.json()[0]["section_category_is_inferred"] is True
    assert unsafe_file.status_code == 404


def test_orders_and_quotes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = {"total_count": 5, "returned_count": 1, "is_truncated": True, "limit": 1}
    order_search = AsyncMock(return_value=metadata | {"items": [{
        "order_id": "ORD-1", "quote_id": "Q-1", "order_status": "Confirmed",
        "shipment_status": "Ready for shipment",
    }]})
    quote_search = AsyncMock(return_value=metadata | {"items": [{
        "quote_id": "Q-1", "valid_until": None, "validity_status": "Unknown",
        "revision_number": 2, "revision_status": "Approved", "discount_rate": 0.1,
        "line_total": 1250.5, "currency": "EUR",
    }]})
    monkeypatch.setattr(commercial, "search_orders", order_search)
    monkeypatch.setattr(commercial, "search_quotes", quote_search)
    orders = client.get("/orders?limit=1&order_status=Confirmed&start_date=2026-01-01")
    quotes = client.get("/quotes?limit=1&revision_status=Approved")

    assert orders.status_code == quotes.status_code == 200
    assert orders.headers["X-Total-Count"] == "5"
    assert orders.headers["X-Is-Truncated"] == "true"
    assert order_search.await_args.kwargs["start_date"] == date(2026, 1, 1)
    assert quotes.json()[0]["line_total"] == 1250.5
    assert quotes.json()[0]["currency"] == "EUR"


@pytest.mark.parametrize("path", ["/orders?order_status=Banana", "/quotes?revision_status=Banana",
                                    "/orders?limit=0", "/quotes?start_date=2026-02-01&end_date=2026-01-01"])
def test_commercial_invalid_filters_return_422(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 422


def test_quote_history_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        commercial,
        "quote_history",
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
        chat,
        "handle_chat",
        AsyncMock(return_value=OrchestrationResult(["iot"], "One open alarm was found.", structured_data={"machine_id": "MCH-0001", "alarms": []})),
    )
    success = client.post("/chat", json={"message": "Are there any recent alarms?", "machine_id": "MCH-0001"})

    monkeypatch.setattr(chat, "handle_chat", AsyncMock(side_effect=LlmRequestError()))
    failure = client.post("/chat", json={"message": "Are there any recent alarms?", "machine_id": "MCH-0001"})

    assert success.status_code == 200
    assert success.json() == {
        "answer": "One open alarm was found.",
        "agent": ["iot"],
        "sources": [],
        "data": {"machine_id": "MCH-0001", "alarms": []},
    }
    assert failure.status_code == 502
    assert failure.json()["detail"] == "The LLM provider could not complete the request."


@pytest.mark.parametrize("error", [MachineNotFoundError("MCH-9999"), MachineUnavailableError("MCH-9999")])
def test_chat_hides_unavailable_machine_existence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: LookupError,
) -> None:
    handler = AsyncMock(side_effect=error)
    monkeypatch.setattr(chat, "handle_chat", handler)

    response = client.post("/chat", json={"message": "Show me the recent operational history of MCH-9999.", "machine_id": "MCH-9999"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "The requested machine is not available in your authorized scope, so I cannot provide machine-specific information.",
        "agent": None,
        "sources": [],
        "data": None,
    }
    assert handler.await_args.args[1].hide_machine_existence is True


def test_chat_forwards_bounded_history_to_the_orchestrator(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    handler = AsyncMock(return_value=OrchestrationResult(None, "Please clarify which alarm you mean."))
    monkeypatch.setattr(chat, "handle_chat", handler)
    history = [
        {"role": "user", "content": "How many AL017_LOW_AIR_PRESSURE alarms occurred?"},
        {"role": "assistant", "content": "I found four occurrences."},
    ]

    response = client.post("/chat", json={
        "message": "And yesterday?", "machine_id": "MCH-0001", "history": history,
    })

    assert response.status_code == 200
    handler.assert_awaited_once_with(
        "And yesterday?",
        AuthContext("USR-001", "CMP-001", "full", hide_machine_existence=True),
        "MCH-0001",
        [
            ConversationTurn(role="user", content="How many AL017_LOW_AIR_PRESSURE alarms occurred?"),
            ConversationTurn(role="assistant", content="I found four occurrences."),
        ],
    )


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
        chat,
        "handle_chat",
        AsyncMock(return_value=OrchestrationResult(["manuals"], "I found 1 relevant manual source.", [source])),
    )

    response = client.post("/chat", json={"message": "Find safety instructions in the manual.", "machine_id": "MCH-0001"})

    assert response.status_code == 200
    assert response.json()["sources"][0]["title"] == "Safety guidance"
    assert response.json()["sources"][0]["highlights"] == ["safety", "maintenance"]
    assert "content" not in response.json()["sources"][0]


def test_input_validation(client: TestClient) -> None:
    assert client.post("/chat", json={"message": "   ", "machine_id": "MCH-0001"}).status_code == 422
    assert client.post("/chat", json={
        "message": "And yesterday?",
        "history": [{"role": "user", "content": "An unfinished previous turn."}],
    }).status_code == 422
    assert client.get("/machines/MCH-0001/alarms?limit=0").status_code == 422
    assert client.get("/machines/MCH-0001/manuals/search?query=%20%20").status_code == 422

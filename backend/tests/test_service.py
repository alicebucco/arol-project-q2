"""Service ticket validation, authorisation, and HTTP contracts."""
import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from agents import service
from core.auth import AuthContext, get_current_user
from core.data_access import TicketNotFoundError

USER = AuthContext("USR-1", "CMP-1", "technician")


@pytest.mark.parametrize("filters", [
    {"limit": 0}, {"limit": 101}, {"limit": True}, {"limit": 1.5},
    {"ticket_status": "Banana"}, {"ticket_type": "Repair"}, {"priority": "Urgent"},
    {"owner_role": "technician"}, {"alarm_id": " "},
    {"start_date": "2026-01-01"},
    {"start_date": date(2026, 2, 1), "end_date": date(2026, 1, 1)},
])
def test_invalid_filters_fail_before_authorisation_and_query(monkeypatch, filters):
    authorise, query = AsyncMock(), AsyncMock()
    monkeypatch.setattr(service, "authorize_machine", authorise)
    monkeypatch.setattr(service, "search_maintenance_tickets", query)
    with pytest.raises(ValueError):
        asyncio.run(service.search_tickets("MCH-1", USER, **filters))
    authorise.assert_not_awaited()
    query.assert_not_awaited()


def test_authorisation_failure_prevents_ticket_access(monkeypatch):
    authorise = AsyncMock(side_effect=HTTPException(status_code=403))
    query = AsyncMock()
    monkeypatch.setattr(service, "authorize_machine", authorise)
    monkeypatch.setattr(service, "search_maintenance_tickets", query)
    with pytest.raises(HTTPException):
        asyncio.run(service.ticket_detail("MCH-1", USER, "TCK-1"))
    authorise.assert_awaited_once_with("MCH-1", USER, domain="operational")
    query.assert_not_awaited()


def test_search_normalises_identifiers_and_preserves_completeness(monkeypatch):
    authorise = AsyncMock()
    result = {"items": [{"ticket_id": "TCK-1", "alarm_id": None}], "total_count": 25,
              "returned_count": 1, "is_truncated": True}
    query = AsyncMock(return_value=result)
    monkeypatch.setattr(service, "authorize_machine", authorise)
    monkeypatch.setattr(service, "search_maintenance_tickets", query)
    assert asyncio.run(service.search_tickets(" mch-1 ", USER, ticket_status="Closed")) == result
    authorise.assert_awaited_once_with("MCH-1", USER, domain="operational")
    assert query.await_args.args == ("MCH-1", 20)
    assert query.await_args.kwargs["ticket_status"] == "Closed"
    assert asyncio.run(service.maintenance_tickets("MCH-1", USER)) == result["items"]


def test_missing_ticket_raises_not_found(monkeypatch):
    monkeypatch.setattr(service, "authorize_machine", AsyncMock())
    query = AsyncMock(return_value={"items": []})
    monkeypatch.setattr(service, "search_maintenance_tickets", query)
    with pytest.raises(TicketNotFoundError):
        asyncio.run(service.ticket_detail("MCH-1", USER, " tck-other "))
    assert query.await_args.args == ("MCH-1", 1)
    assert query.await_args.kwargs["ticket_id"] == "TCK-OTHER"


@pytest.fixture
def client():
    main.app.dependency_overrides[get_current_user] = lambda: USER
    with TestClient(main.app) as client:
        yield client
    main.app.dependency_overrides.clear()


def test_ticket_api_filters_metadata_and_detail(client, monkeypatch):
    row = {"ticket_id": "TCK-1", "alarm_id": None, "ticket_status": "Open",
           "ticket_type": "Scheduled maintenance", "priority": "High",
           "created_date": date(2026, 1, 1), "owner_role": "Maintenance Man"}
    search = AsyncMock(return_value={"items": [row], "total_count": 2,
                                   "returned_count": 1, "is_truncated": True, "limit": 1})
    monkeypatch.setattr(main, "search_tickets", search)
    monkeypatch.setattr(main, "ticket_detail", AsyncMock(return_value=row))
    response = client.get("/machines/MCH-1/maintenance-tickets?limit=1&ticket_status=Open&start_date=2026-01-01")
    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "2"
    assert response.headers["X-Is-Truncated"] == "true"
    assert response.json()[0]["alarm_id"] is None
    assert search.await_args.kwargs["start_date"] == date(2026, 1, 1)
    assert client.get("/machines/MCH-1/maintenance-tickets/TCK-1").json() == response.json()[0]


def test_ticket_api_invalid_filter_and_missing_detail(client, monkeypatch):
    assert client.get("/machines/MCH-1/maintenance-tickets?priority=Urgent").status_code == 422
    monkeypatch.setattr(main, "ticket_detail", AsyncMock(side_effect=TicketNotFoundError("TCK-1")))
    assert client.get("/machines/MCH-1/maintenance-tickets/TCK-1").status_code == 404

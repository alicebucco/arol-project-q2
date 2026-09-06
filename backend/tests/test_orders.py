"""Commercial agent validation, tenant boundaries, and result contracts."""
import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from agents import orders as agent
from core.auth import AuthContext

USER = AuthContext("USR-1", "CMP-1", "commercial")


@pytest.mark.parametrize("operation", [agent.search_orders, agent.search_quotes])
@pytest.mark.parametrize("limit", [0, -1, 101, True, 1.5, "20", None])
def test_invalid_limits_never_access_data(monkeypatch, operation, limit):
    query = AsyncMock()
    monkeypatch.setattr(agent, "search_company_commercial", query)
    with pytest.raises(ValueError, match="limit"):
        asyncio.run(operation(USER, limit))
    query.assert_not_awaited()


@pytest.mark.parametrize("operation,filters", [
    (agent.search_orders, {"order_status": "Banana"}),
    (agent.search_orders, {"shipment_status": "Confirmed"}),
    (agent.search_quotes, {"revision_status": "Delivered"}),
    (agent.search_quotes, {"start_date": date(2026, 2, 1), "end_date": date(2026, 1, 1)}),
    (agent.search_orders, {"order_id": " "}),
])
def test_invalid_filters_never_access_data(monkeypatch, operation, filters):
    query = AsyncMock()
    monkeypatch.setattr(agent, "search_company_commercial", query)
    with pytest.raises(ValueError):
        asyncio.run(operation(USER, **filters))
    query.assert_not_awaited()


@pytest.mark.parametrize("operation,args,dependency", [
    (agent.search_orders, (), "search_company_commercial"),
    (agent.search_quotes, (), "search_company_commercial"),
    (agent.order_detail, ("ORD-1",), "get_company_order_detail"),
    (agent.quote_history, ("QTE-1",), "get_company_quote_history"),
])
def test_technician_cannot_query_commercial_data(monkeypatch, operation, args, dependency):
    query = AsyncMock()
    monkeypatch.setattr(agent, dependency, query)
    with pytest.raises(HTTPException) as error:
        asyncio.run(operation(AuthContext("USR-2", "CMP-1", "technician"), *args))
    assert error.value.status_code == 403
    query.assert_not_awaited()


def test_search_preserves_metadata_and_uses_authenticated_company(monkeypatch):
    result = {"items": [], "total_count": 0, "returned_count": 0, "is_truncated": False}
    query = AsyncMock(return_value=result)
    monkeypatch.setattr(agent, "search_company_commercial", query)
    assert asyncio.run(agent.search_quotes(USER, quote_id=" qte-1 ", revision_status="Rejected")) == result
    assert query.await_args.args == ("CMP-1", "quotes", 20)
    assert query.await_args.kwargs["quote_id"] == "QTE-1"
    assert query.await_args.kwargs["revision_status"] == "Rejected"


@pytest.mark.parametrize("operation,dependency,identifier", [
    (agent.order_detail, "get_company_order_detail", "ORD-1"),
    (agent.quote_history, "get_company_quote_history", "QTE-1"),
])
def test_detail_normalises_identifier_and_enforces_company(monkeypatch, operation, dependency, identifier):
    query = AsyncMock(return_value={"source": "evidence"})
    monkeypatch.setattr(agent, dependency, query)
    assert asyncio.run(operation(USER, " " + identifier.lower() + " ")) == {"source": "evidence"}
    query.assert_awaited_once_with(USER.company_id, identifier)


def test_legacy_list_remains_compatible(monkeypatch):
    query = AsyncMock(return_value={"items": [{"order_id": "ORD-1"}], "total_count": 30})
    monkeypatch.setattr(agent, "search_company_commercial", query)
    assert asyncio.run(agent.orders(USER)) == [{"order_id": "ORD-1"}]
    assert query.await_args.args[-1] == 20


@pytest.mark.parametrize("kind,rows,total,truncated", [
    ("orders", [(0, None, None, None, None, None, None)], 0, False),
    ("orders", [(3, "ORD-1", "QTE-1", "Confirmed", "Delivered", "EUR", date(2026, 1, 1))], 3, True),
    ("quotes", [(1, "QTE-1", date(2026, 8, 5), 2, "Rejected", 0.1, 100, "EUR", date(2026, 1, 1))], 1, False),
])
def test_data_access_result_completeness_and_currency(monkeypatch, kind, rows, total, truncated):
    from unittest.mock import MagicMock
    from core import data_access

    cursor = MagicMock()
    cursor.__aenter__ = AsyncMock(return_value=cursor)
    cursor.__aexit__ = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=rows)
    conn = MagicMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock()
    conn.cursor.return_value = cursor
    monkeypatch.setattr(data_access, "connection", lambda: conn)
    result = asyncio.run(data_access.search_company_commercial("CMP-1", kind, 1))
    assert result["total_count"] == total
    assert result["is_truncated"] is truncated
    assert result["returned_count"] == (1 if total else 0)
    if total:
        assert result["items"][0]["currency"] == "EUR"
    else:
        assert result["items"] == []
    if kind == "quotes":
        assert result["items"][0]["validity_status"] == "Valid"
        assert result["items"][0]["revision_status"] == "Rejected"


def test_ambiguous_comparison_survives_api_schema():
    from main import QuoteLineChange
    from core.data_access import _compare_quote_lines
    lines = [
        {"quote_line_id": "QL-1", "machine_id": None, "description": "Kit", "price": 100},
        {"quote_line_id": "QL-2", "machine_id": None, "description": "Kit", "price": 150},
    ]
    evidence = _compare_quote_lines(lines, [])
    payload = QuoteLineChange(**evidence[0]).model_dump()
    assert payload["change"] == "ambiguous"
    assert [line["quote_line_id"] for line in payload["previous_lines"]] == ["QL-1", "QL-2"]

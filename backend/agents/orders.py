"""Authorised commercial evidence. Search operations include completeness metadata."""

from datetime import date
from typing import Any

from core.auth import AuthContext, ensure_visibility
from core.data_access import (
    get_company_order_detail,
    get_company_quote_history,
    search_company_commercial,
)

ORDER_STATUSES = {"Confirmed", "In production", "Delivered", "Closed"}
SHIPMENT_STATUSES = {"In production", "Ready for shipment", "Delivered", "Installed"}
REVISION_STATUSES = {"Draft", "Submitted", "Superseded", "Approved", "Rejected", "Expired"}
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _identifier(value: str | None, name: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value.strip().upper()


def _validate(limit: int, start_date: date | None, end_date: date | None, **labels: tuple) -> None:
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be an integer between 1 and {MAX_LIMIT}.")
    for boundary in (start_date, end_date):
        if boundary is not None and type(boundary) is not date:
            raise ValueError("Date boundaries must be date values.")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("A date range cannot end before it starts.")
    for name, (value, allowed) in labels.items():
        if value is not None and (not isinstance(value, str) or value not in allowed):
            raise ValueError(f"Unsupported {name}: {value}.")


async def search_orders(
    user: AuthContext, limit: int = DEFAULT_LIMIT, *, machine_id: str | None = None,
    order_id: str | None = None, quote_id: str | None = None,
    order_status: str | None = None, shipment_status: str | None = None,
    start_date: date | None = None, end_date: date | None = None,
) -> dict[str, Any]:
    """Filter company orders by order date (inclusive) and approved-revision machine."""
    _validate(limit, start_date, end_date, order_status=(order_status, ORDER_STATUSES),
              shipment_status=(shipment_status, SHIPMENT_STATUSES))
    filters = dict(machine_id=_identifier(machine_id, "machine_id"),
                   order_id=_identifier(order_id, "order_id"), quote_id=_identifier(quote_id, "quote_id"),
                   order_status=order_status, shipment_status=shipment_status,
                   start_date=start_date, end_date=end_date)
    ensure_visibility(user, "commercial")
    return await search_company_commercial(user.company_id, "orders", limit, **filters)


async def search_quotes(
    user: AuthContext, limit: int = DEFAULT_LIMIT, *, machine_id: str | None = None,
    quote_id: str | None = None, revision_status: str | None = None,
    start_date: date | None = None, end_date: date | None = None,
) -> dict[str, Any]:
    """Filter quotes by creation date (inclusive) and their latest revision."""
    _validate(limit, start_date, end_date, revision_status=(revision_status, REVISION_STATUSES))
    filters = dict(machine_id=_identifier(machine_id, "machine_id"),
                   quote_id=_identifier(quote_id, "quote_id"), revision_status=revision_status,
                   start_date=start_date, end_date=end_date)
    ensure_visibility(user, "commercial")
    return await search_company_commercial(user.company_id, "quotes", limit, **filters)


async def orders(user: AuthContext, limit: int = DEFAULT_LIMIT, **filters: Any) -> list[dict[str, Any]]:
    """Compatibility list; use search_orders for total_count and is_truncated."""
    return (await search_orders(user, limit, **filters))["items"]


async def quotes(user: AuthContext, limit: int = DEFAULT_LIMIT, **filters: Any) -> list[dict[str, Any]]:
    """Compatibility list; use search_quotes for total_count and is_truncated."""
    return (await search_quotes(user, limit, **filters))["items"]


async def order_detail(user: AuthContext, order_id: str) -> dict[str, Any]:
    """Retrieve an order only within the authenticated company's scope."""

    order_id = _identifier(order_id, "order_id", required=True)
    ensure_visibility(user, "commercial")
    return await get_company_order_detail(user.company_id, order_id)


async def quote_history(user: AuthContext, quote_id: str) -> dict[str, Any]:
    """Return source change summaries separately from calculated line differences."""

    quote_id = _identifier(quote_id, "quote_id", required=True)
    ensure_visibility(user, "commercial")
    return await get_company_quote_history(user.company_id, quote_id)

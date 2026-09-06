"""Orders Agent: commercial quotes and order history."""

from typing import Any

from core.auth import AuthContext, ensure_visibility
from core.data_access import (
    get_company_order_detail,
    get_company_orders,
    get_company_quote_history,
    get_company_quotes,
)


async def orders(user: AuthContext, limit: int) -> list[dict[str, Any]]:
    """Authorise and retrieve orders from the user's company."""

    ensure_visibility(user, "commercial")
    return await get_company_orders(user.company_id, limit)


async def quotes(user: AuthContext, limit: int) -> list[dict[str, Any]]:
    """Authorise and retrieve quote history from the user's company."""

    ensure_visibility(user, "commercial")
    return await get_company_quotes(user.company_id, limit)


async def order_detail(user: AuthContext, order_id: str) -> dict[str, Any]:
    """Return one authorised order's fulfilment and approved quote content."""

    ensure_visibility(user, "commercial")
    return await get_company_order_detail(user.company_id, order_id)


async def quote_history(user: AuthContext, quote_id: str) -> dict[str, Any]:
    """Return one authorised quote's revision history and latest changes."""

    ensure_visibility(user, "commercial")
    return await get_company_quote_history(user.company_id, quote_id)

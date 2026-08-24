"""Orders Agent: commercial quotes and order history."""

from typing import Any

from core.auth import AuthContext, ensure_visibility
from core.data_access import get_company_orders, get_company_quotes


async def orders(user: AuthContext, limit: int) -> list[dict[str, Any]]:
    """Authorise and retrieve orders from the user's company."""

    ensure_visibility(user, "commercial")
    return await get_company_orders(user.company_id, limit)


async def quotes(user: AuthContext, limit: int) -> list[dict[str, Any]]:
    """Authorise and retrieve quote history from the user's company."""

    ensure_visibility(user, "commercial")
    return await get_company_quotes(user.company_id, limit)

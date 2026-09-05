"""Orders Agent: commercial quotes and order history."""

from typing import Any

from core.auth import AuthContext, ensure_visibility
from core.contracts import AgentResult
from core.data_access import get_company_orders, get_company_quotes


async def orders(user: AuthContext, limit: int) -> list[dict[str, Any]]:
    """Authorise and retrieve orders from the user's company."""

    ensure_visibility(user, "commercial")
    return await get_company_orders(user.company_id, limit)


async def quotes(user: AuthContext, limit: int) -> list[dict[str, Any]]:
    """Authorise and retrieve quote history from the user's company."""

    ensure_visibility(user, "commercial")
    return await get_company_quotes(user.company_id, limit)


async def orders_evidence(user: AuthContext, limit: int) -> AgentResult:
    """Return authorised orders in the orchestration result contract."""

    records = await orders(user, limit)
    return AgentResult(
        agent="orders",
        operation="orders",
        evidence={"orders": records},
        structured_data={"orders": records},
    )


async def quotes_evidence(user: AuthContext, limit: int) -> AgentResult:
    """Return authorised quotes in the orchestration result contract."""

    records = await quotes(user, limit)
    return AgentResult(
        agent="orders",
        operation="quotes",
        evidence={"quotes": records},
        structured_data={"quotes": records},
    )

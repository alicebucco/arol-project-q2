"""Service Agent: maintenance ticket access for machines."""

from typing import Any

from core.auth import AuthContext
from core.data_access import authorize_machine, get_maintenance_tickets


async def maintenance_tickets(
    machine_id: str,
    user: AuthContext,
    limit: int,
) -> list[dict[str, Any]]:
    """Authorise and retrieve maintenance tickets for the user's machine."""

    await authorize_machine(machine_id, user, domain="operational")
    return await get_maintenance_tickets(machine_id, limit)

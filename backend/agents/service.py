"""Service Agent: maintenance ticket access for machines."""

from typing import Any

from core.auth import AuthContext
from core.data_access import (
    authorize_machine,
    get_maintenance_tickets,
    get_manual_contents,
    get_observed_productive_hours,
)
from core.maintenance_observation import maintenance_observation


async def maintenance_tickets(
    machine_id: str,
    user: AuthContext,
    limit: int,
) -> list[dict[str, Any]]:
    """Authorise and retrieve maintenance tickets for the user's machine."""

    await authorize_machine(machine_id, user, domain="operational")
    return await get_maintenance_tickets(machine_id, limit)


async def observed_maintenance_plan(machine_id: str, user: AuthContext) -> dict[str, Any]:
    """Relate the manual schedule to productive hours covered by local telemetry."""

    await authorize_machine(machine_id, user, domain="operational")
    telemetry_window, manual_contents = await get_observed_productive_hours(machine_id), await get_manual_contents(machine_id)
    return maintenance_observation(machine_id, telemetry_window, manual_contents)

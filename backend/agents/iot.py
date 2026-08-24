"""IoT Agent: operational data access for telemetry and alarms."""

from typing import Any

from core.auth import AuthContext
from core.data_access import (
    authorize_machine,
    get_recent_alarms,
    get_telemetry_snapshots,
)


async def recent_alarms(
    machine_id: str,
    user: AuthContext,
    limit: int,
) -> list[dict[str, Any]]:
    """Authorise and retrieve recent alarms for the user's machine."""

    await authorize_machine(machine_id, user, domain="operational")
    return await get_recent_alarms(machine_id, limit)


async def telemetry(
    machine_id: str,
    user: AuthContext,
    limit: int,
) -> list[dict[str, Any]]:
    """Authorise and retrieve recent telemetry for the user's machine."""

    await authorize_machine(machine_id, user, domain="operational")
    return await get_telemetry_snapshots(machine_id, limit)

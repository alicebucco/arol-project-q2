"""Service Agent: maintenance ticket access for machines."""

from typing import Any

from core.auth import AuthContext
from core.contracts import AgentResult
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


async def maintenance_tickets_evidence(machine_id: str, user: AuthContext, limit: int) -> AgentResult:
    """Return authorised maintenance tickets in the orchestration result contract."""

    tickets = await maintenance_tickets(machine_id, user, limit)
    return AgentResult(
        agent="service",
        operation="maintenance_tickets",
        evidence={"machine_id": machine_id, "maintenance_tickets": tickets},
        structured_data={"machine_id": machine_id, "maintenance_tickets": tickets},
    )


async def observed_maintenance_plan_evidence(machine_id: str, user: AuthContext) -> AgentResult:
    """Return documented maintenance observations in the orchestration result contract."""

    observation = await observed_maintenance_plan(machine_id, user)
    return AgentResult(
        agent="service",
        operation="observed_maintenance_plan",
        evidence={"maintenance_observation": observation},
        structured_data={"maintenance_observation": observation},
    )

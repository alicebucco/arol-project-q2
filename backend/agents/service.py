"""Service Agent: maintenance ticket access for machines."""

from datetime import date
from typing import Any

from core.auth import AuthContext
from core.data_access import (
    authorize_machine,
    TicketNotFoundError,
    search_maintenance_tickets,
)

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
TICKET_STATUSES = {"Open", "In progress", "Waiting for parts", "Resolved", "Closed"}
TICKET_TYPES = {"Remote troubleshooting", "On-site service", "Spare parts request",
                "Scheduled maintenance", "Overhaul", "Size change assistance"}
PRIORITIES = {"Critical", "High", "Medium", "Low"}
OWNER_ROLES = {"Line Operator", "Maintenance Man", "Plant Maintenance Manager", "AROL Technical Service"}


def _identifier(value: str | None, name: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value.strip().upper()


async def search_tickets(
    machine_id: str, user: AuthContext, limit: int = DEFAULT_LIMIT, *,
    ticket_id: str | None = None, alarm_id: str | None = None,
    ticket_status: str | None = None, ticket_type: str | None = None,
    priority: str | None = None, owner_role: str | None = None,
    start_date: date | None = None, end_date: date | None = None,
) -> dict[str, Any]:
    """Return authorised tickets and completeness; dates filter creation inclusively."""
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be an integer between 1 and {MAX_LIMIT}.")
    for name, value, allowed in (
        ("ticket_status", ticket_status, TICKET_STATUSES),
        ("ticket_type", ticket_type, TICKET_TYPES),
        ("priority", priority, PRIORITIES), ("owner_role", owner_role, OWNER_ROLES),
    ):
        if value is not None and (not isinstance(value, str) or value not in allowed):
            raise ValueError(f"Unsupported {name}: {value}.")
    for boundary in (start_date, end_date):
        if boundary is not None and type(boundary) is not date:
            raise ValueError("Date boundaries must be date values.")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("A date range cannot end before it starts.")
    machine_id = _identifier(machine_id, "machine_id", required=True)
    filters = dict(ticket_id=_identifier(ticket_id, "ticket_id"),
                   alarm_id=_identifier(alarm_id, "alarm_id"), ticket_status=ticket_status,
                   ticket_type=ticket_type, priority=priority, owner_role=owner_role,
                   start_date=start_date, end_date=end_date)
    await authorize_machine(machine_id, user, domain="operational")
    return await search_maintenance_tickets(machine_id, limit, **filters)


async def maintenance_tickets(
    machine_id: str,
    user: AuthContext,
    limit: int = DEFAULT_LIMIT,
    **filters: Any,
) -> list[dict[str, Any]]:
    """Compatibility list; use search_tickets for completeness metadata."""

    return (await search_tickets(machine_id, user, limit, **filters))["items"]


async def ticket_detail(machine_id: str, user: AuthContext, ticket_id: str) -> dict[str, Any]:
    """Retrieve one ticket scoped to an authorised machine, without inferred details."""

    ticket_id = _identifier(ticket_id, "ticket_id", required=True)
    result = await search_tickets(machine_id, user, 1, ticket_id=ticket_id)
    if not result["items"]:
        raise TicketNotFoundError(ticket_id)
    return result["items"][0]

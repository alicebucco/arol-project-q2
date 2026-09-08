"""PostgreSQL repository for service data."""

from typing import Any

from core.db import connection
from db.repositories.errors import TicketNotFoundError


async def get_maintenance_tickets(machine_id: str, limit: int) -> list[dict[str, Any]]:
    """Compatibility list for an already-authorised machine."""
    return (await search_maintenance_tickets(machine_id, limit))["items"]

async def search_maintenance_tickets(machine_id: str, limit: int, **filters: Any) -> dict[str, Any]:
    """Select and count tickets in one snapshot; caller must authorise the machine."""
    clauses = ["machine_id = %s"]
    parameters: list[Any] = [machine_id]
    for field in ("ticket_id", "alarm_id", "ticket_status", "ticket_type", "priority", "owner_role"):
        if filters.get(field) is not None:
            clauses.append(f"{field} = %s")
            parameters.append(filters[field])
    for name, operator in (("start_date", ">="), ("end_date", "<=")):
        if filters.get(name) is not None:
            clauses.append(f"created_date {operator} %s")
            parameters.append(filters[name])
    where_sql = " AND ".join(clauses)
    fields = ("ticket_id", "alarm_id", "ticket_type", "ticket_status", "priority", "created_date", "owner_role")
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"""WITH filtered AS (
                    SELECT {', '.join(fields)} FROM maintenance_tickets WHERE {where_sql}
                )
                SELECT totals.total_count, {', '.join('page.' + field for field in fields)}
                FROM (SELECT COUNT(*) AS total_count FROM filtered) AS totals
                LEFT JOIN LATERAL (
                    SELECT * FROM filtered ORDER BY created_date DESC, ticket_id DESC LIMIT %s
                ) AS page ON TRUE
                ORDER BY page.created_date DESC, page.ticket_id DESC""",
                (*parameters, limit),
            )
            rows = await cursor.fetchall()
    total = int(rows[0][0])
    items = [dict(zip(fields, row[1:])) for row in rows if row[1] is not None]
    return {"machine_id": machine_id, "items": items, "total_count": total,
            "returned_count": len(items), "is_truncated": total > len(items),
            "limit": limit, "filters": filters, "date_field": "created_date"}

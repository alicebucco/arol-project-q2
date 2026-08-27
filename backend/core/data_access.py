"""Parameterised data-access functions for the structured dataset."""

from dataclasses import dataclass
from typing import Any

from core.auth import AuthContext, ensure_company_access, ensure_visibility
from core.db import connection


class MachineNotFoundError(LookupError):
    """The requested machine identifier does not exist."""


@dataclass(frozen=True)
class MachineScope:
    machine_id: str
    company_id: str


async def authorize_machine(
    machine_id: str,
    user: AuthContext,
    domain: str = "operational",
) -> MachineScope:
    """Resolve a machine and enforce tenant + visibility before querying data."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT machine_id, company_id FROM machines WHERE machine_id = %s",
                (machine_id,),
            )
            row = await cursor.fetchone()

    if row is None:
        raise MachineNotFoundError(machine_id)
    ensure_company_access(user, row[1])
    ensure_visibility(user, domain)
    return MachineScope(machine_id=row[0], company_id=row[1])


async def get_recent_alarms(machine_id: str, limit: int) -> list[dict[str, Any]]:
    """Return the most recent alarms for an already-authorized machine."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT alarm_id, timestamp, alarm_code, severity, alarm_status
                FROM alarms
                WHERE machine_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (machine_id, limit),
            )
            rows = await cursor.fetchall()
    return [
        {
            "alarm_id": row[0],
            "timestamp": row[1],
            "alarm_code": row[2],
            "severity": row[3],
            "alarm_status": row[4],
        }
        for row in rows
    ]


async def get_telemetry_snapshots(machine_id: str, limit: int) -> list[dict[str, Any]]:
    """Return recent operational telemetry for an already-authorized machine."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT timestamp, operational_status, production_rate_bph,
                       uptime_percentage, alarm_count, temperature_c, energy_kwh,
                       health_note
                FROM telemetry_snapshots
                WHERE machine_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (machine_id, limit),
            )
            rows = await cursor.fetchall()
    return [
        {
            "timestamp": row[0],
            "operational_status": row[1],
            "production_rate_bph": row[2],
            "uptime_percentage": row[3],
            "alarm_count": row[4],
            "temperature_c": row[5],
            "energy_kwh": row[6],
            "health_note": row[7],
        }
        for row in rows
    ]


async def get_maintenance_tickets(machine_id: str, limit: int) -> list[dict[str, Any]]:
    """Return recent maintenance tickets for an already-authorized machine."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT ticket_id, alarm_id, ticket_type, ticket_status, priority,
                       created_date, owner_role
                FROM maintenance_tickets
                WHERE machine_id = %s
                ORDER BY created_date DESC
                LIMIT %s
                """,
                (machine_id, limit),
            )
            rows = await cursor.fetchall()
    return [
        {
            "ticket_id": row[0],
            "alarm_id": row[1],
            "ticket_type": row[2],
            "ticket_status": row[3],
            "priority": row[4],
            "created_date": row[5],
            "owner_role": row[6],
        }
        for row in rows
    ]


def vector_literal(vector: list[float]) -> str:
    """Format a parameter for pgvector without interpolating SQL."""
    return "[" + ",".join(str(value) for value in vector) + "]"


async def search_manual_chunks(
    machine_id: str,
    query_embedding: list[float],
    limit: int,
) -> list[dict[str, Any]]:
    """Search only one authorised machine's manual using cosine similarity."""
    query_vector = vector_literal(query_embedding)
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT source_file, page, section, content,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM manual_chunks
                WHERE machine_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vector, machine_id, query_vector, limit),
            )
            rows = await cursor.fetchall()
    return [
        {
            "source": "manual",
            "file": row[0],
            "page": row[1],
            "section": row[2],
            "content": row[3],
            "similarity": float(row[4]),
        }
        for row in rows
    ]


async def get_company_orders(company_id: str, limit: int) -> list[dict[str, Any]]:
    """Return orders belonging to one company."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT order_id, quote_id, order_status, shipment_status
                FROM orders
                WHERE company_id = %s
                ORDER BY order_id DESC
                LIMIT %s
                """,
                (company_id, limit),
            )
            rows = await cursor.fetchall()
    return [
        {
            "order_id": row[0],
            "quote_id": row[1],
            "order_status": row[2],
            "shipment_status": row[3],
        }
        for row in rows
    ]


async def get_company_machines(company_id: str) -> list[dict[str, Any]]:
    """Return the machine identity data visible to every user in one company."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT m.machine_id, m.serial_number, mm.model_code, mm.description,
                       m.plant_location, m.configuration_profile
                FROM machines AS m
                JOIN machine_models AS mm ON mm.model_id = m.model_id
                WHERE m.company_id = %s
                ORDER BY m.machine_id
                """,
                (company_id,),
            )
            rows = await cursor.fetchall()
    return [
        {
            "machine_id": row[0],
            "serial_number": row[1],
            "model_code": row[2],
            "model_description": row[3],
            "plant_location": row[4],
            "configuration_profile": row[5],
        }
        for row in rows
    ]


async def get_company_quotes(company_id: str, limit: int) -> list[dict[str, Any]]:
    """Return quotes with their latest revision and net line total."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT q.quote_id, q.valid_until,
                       qr.revision_number, qr.revision_status,
                       qr.discount_rate,
                       COALESCE(SUM(ql.price), 0) AS line_total
                FROM quotes AS q
                LEFT JOIN LATERAL (
                    SELECT revision_number, revision_status, discount_rate,
                           quote_revision_id
                    FROM quote_revisions
                    WHERE quote_id = q.quote_id
                    ORDER BY revision_number DESC
                    LIMIT 1
                ) AS qr ON TRUE
                LEFT JOIN quote_lines AS ql
                    ON ql.quote_revision_id = qr.quote_revision_id
                WHERE q.company_id = %s
                GROUP BY q.quote_id, q.valid_until, qr.revision_number,
                         qr.revision_status, qr.discount_rate
                ORDER BY q.quote_id DESC
                LIMIT %s
                """,
                (company_id, limit),
            )
            rows = await cursor.fetchall()
    return [
        {
            "quote_id": row[0],
            "valid_until": row[1],
            "revision_number": row[2],
            "revision_status": row[3],
            "discount_rate": row[4],
            "line_total": row[5],
        }
        for row in rows
    ]

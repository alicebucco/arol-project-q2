"""Parameterised data-access functions for the structured dataset."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.auth import AuthContext, ensure_company_access, ensure_visibility
from core.business_time import quote_validity_status
from core.db import connection


class MachineNotFoundError(LookupError):
    """The requested machine identifier does not exist."""


class QuoteNotFoundError(LookupError):
    """The requested quote is absent or outside the user's company."""


class OrderNotFoundError(LookupError):
    """The requested order is absent or outside the user's company."""


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


def _alarm_filter_sql(
    machine_id: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    alarm_code: str | None = None,
    severity: str | None = None,
    alarm_status: str | None = None,
) -> tuple[str, list[Any]]:
    clauses = ["machine_id = %s"]
    parameters: list[Any] = [machine_id]
    for column, value, operator in (
        ("timestamp", start_time, ">="),
        ("timestamp", end_time, "<="),
        ("alarm_code", alarm_code, "="),
        ("severity", severity, "="),
        ("alarm_status", alarm_status, "="),
    ):
        if value is not None:
            clauses.append(f"{column} {operator} %s")
            parameters.append(value)
    return " AND ".join(clauses), parameters


async def get_recent_alarms(
    machine_id: str,
    limit: int,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    alarm_code: str | None = None,
    severity: str | None = None,
    alarm_status: str | None = None,
) -> list[dict[str, Any]]:
    """Return the most recent alarms for an already-authorized machine."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            where_sql, parameters = _alarm_filter_sql(
                machine_id, start_time=start_time, end_time=end_time,
                alarm_code=alarm_code, severity=severity, alarm_status=alarm_status,
            )
            await cursor.execute(
                f"""
                SELECT alarm_id, timestamp, alarm_code, severity, alarm_status
                FROM alarms
                WHERE {where_sql}
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (*parameters, limit),
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


async def count_alarm_events(
    machine_id: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    alarm_code: str | None = None,
    severity: str | None = None,
    alarm_status: str | None = None,
) -> int:
    """Count alarm events matching explicit filters for one machine."""

    where_sql, parameters = _alarm_filter_sql(
        machine_id, start_time=start_time, end_time=end_time,
        alarm_code=alarm_code, severity=severity, alarm_status=alarm_status,
    )
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f"SELECT COUNT(*) FROM alarms WHERE {where_sql}", parameters)
            row = await cursor.fetchone()
    return int(row[0])


async def summarize_alarm_events(
    machine_id: str,
    limit: int,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    alarm_code: str | None = None,
    severity: str | None = None,
    alarm_status: str | None = None,
) -> list[dict[str, Any]]:
    """Group matching alarms by code instead of returning raw events."""

    where_sql, parameters = _alarm_filter_sql(
        machine_id, start_time=start_time, end_time=end_time,
        alarm_code=alarm_code, severity=severity, alarm_status=alarm_status,
    )
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"""
                SELECT alarm_code, COUNT(*), MIN(timestamp), MAX(timestamp),
                       (ARRAY_AGG(severity ORDER BY timestamp DESC))[1],
                       (ARRAY_AGG(alarm_status ORDER BY timestamp DESC))[1]
                FROM alarms
                WHERE {where_sql}
                GROUP BY alarm_code
                ORDER BY COUNT(*) DESC, MAX(timestamp) DESC
                LIMIT %s
                """,
                (*parameters, limit),
            )
            rows = await cursor.fetchall()
    return [
        {
            "alarm_code": row[0], "occurrences": row[1], "first_seen": row[2],
            "last_seen": row[3], "latest_severity": row[4], "latest_status": row[5],
        }
        for row in rows
    ]


async def get_recent_alarms_for_code(
    machine_id: str,
    alarm_code: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Return recent events for one code on an already-authorised machine."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT alarm_id, timestamp, alarm_code, severity, alarm_status
                FROM alarms
                WHERE machine_id = %s AND alarm_code = %s
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (machine_id, alarm_code, limit),
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


async def get_repeated_alarm_patterns(machine_id: str, limit: int) -> list[dict[str, Any]]:
    """Summarise alarm conditions that occurred more than once for one machine."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT alarm_code, COUNT(*), MIN(timestamp), MAX(timestamp),
                       (ARRAY_AGG(alarm_status ORDER BY timestamp DESC))[1]
                FROM alarms
                WHERE machine_id = %s
                GROUP BY alarm_code
                HAVING COUNT(*) > 1
                ORDER BY COUNT(*) DESC, MAX(timestamp) DESC
                LIMIT %s
                """,
                (machine_id, limit),
            )
            rows = await cursor.fetchall()
    return [
        {
            "alarm_code": row[0],
            "occurrences": row[1],
            "first_seen": row[2],
            "last_seen": row[3],
            "latest_status": row[4],
        }
        for row in rows
    ]


def _telemetry_filter_sql(
    machine_id: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    operational_status: str | None = None,
) -> tuple[str, list[Any]]:
    clauses = ["machine_id = %s"]
    parameters: list[Any] = [machine_id]
    for column, value, operator in (
        ("timestamp", start_time, ">="),
        ("timestamp", end_time, "<="),
        ("operational_status", operational_status, "="),
    ):
        if value is not None:
            clauses.append(f"{column} {operator} %s")
            parameters.append(value)
    return " AND ".join(clauses), parameters


async def get_telemetry_snapshots(
    machine_id: str,
    limit: int,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    operational_status: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent operational telemetry for an already-authorized machine."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            where_sql, parameters = _telemetry_filter_sql(
                machine_id, start_time=start_time, end_time=end_time,
                operational_status=operational_status,
            )
            await cursor.execute(
                f"""
                SELECT timestamp, operational_status, production_rate_bph,
                       uptime_percentage, alarm_count, temperature_c, energy_kwh,
                       health_note
                FROM telemetry_snapshots
                WHERE {where_sql}
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (*parameters, limit),
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


def _float_or_none(value: Any) -> float | None:
    return None if value is None else float(value)


async def summarize_telemetry_snapshots(
    machine_id: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    operational_status: str | None = None,
) -> dict[str, Any]:
    """Return reproducible telemetry statistics for an explicit window."""

    where_sql, parameters = _telemetry_filter_sql(
        machine_id, start_time=start_time, end_time=end_time,
        operational_status=operational_status,
    )
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"""
                SELECT COUNT(*), MIN(timestamp), MAX(timestamp),
                       AVG(production_rate_bph), MIN(production_rate_bph), MAX(production_rate_bph),
                       AVG(uptime_percentage), MIN(uptime_percentage), MAX(uptime_percentage),
                       AVG(temperature_c), MIN(temperature_c), MAX(temperature_c),
                       SUM(energy_kwh), AVG(energy_kwh), MIN(energy_kwh), MAX(energy_kwh),
                       SUM(alarm_count),
                       (ARRAY_AGG(production_rate_bph ORDER BY timestamp ASC))[1],
                       (ARRAY_AGG(production_rate_bph ORDER BY timestamp DESC))[1],
                       (ARRAY_AGG(uptime_percentage ORDER BY timestamp ASC))[1],
                       (ARRAY_AGG(uptime_percentage ORDER BY timestamp DESC))[1],
                       (ARRAY_AGG(temperature_c ORDER BY timestamp ASC)
                           FILTER (WHERE temperature_c IS NOT NULL))[1],
                       (ARRAY_AGG(temperature_c ORDER BY timestamp DESC)
                           FILTER (WHERE temperature_c IS NOT NULL))[1],
                       (ARRAY_AGG(energy_kwh ORDER BY timestamp ASC)
                           FILTER (WHERE energy_kwh IS NOT NULL))[1],
                       (ARRAY_AGG(energy_kwh ORDER BY timestamp DESC)
                           FILTER (WHERE energy_kwh IS NOT NULL))[1]
                FROM telemetry_snapshots
                WHERE {where_sql}
                """,
                parameters,
            )
            row = await cursor.fetchone()
            await cursor.execute(
                f"""
                SELECT operational_status, COUNT(*)
                FROM telemetry_snapshots
                WHERE {where_sql}
                GROUP BY operational_status
                ORDER BY operational_status
                """,
                parameters,
            )
            status_rows = await cursor.fetchall()
    def metric(average: Any, minimum: Any, maximum: Any, first: Any, last: Any) -> dict[str, float | None]:
        first_value, last_value = _float_or_none(first), _float_or_none(last)
        return {
            "average": _float_or_none(average), "minimum": _float_or_none(minimum),
            "maximum": _float_or_none(maximum), "first": first_value, "last": last_value,
            "first_to_last_change": (
                None if first_value is None or last_value is None
                else round(last_value - first_value, 3)
            ),
        }

    return {
        "snapshot_count": row[0], "first_snapshot": row[1], "last_snapshot": row[2],
        "production_rate_bph": metric(row[3], row[4], row[5], row[17], row[18]),
        "uptime_percentage": metric(row[6], row[7], row[8], row[19], row[20]),
        "temperature_c": metric(row[9], row[10], row[11], row[21], row[22]),
        "energy_kwh": {
            "total": _float_or_none(row[12]),
            **metric(row[13], row[14], row[15], row[23], row[24]),
        },
        "total_alarm_count": int(row[16] or 0),
        "operational_status_counts": {status: count for status, count in status_rows},
    }


async def get_machine_configuration_profile(machine_id: str) -> str | None:
    """Return the installed configuration, never the shared model defaults."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT configuration_profile FROM machines WHERE machine_id = %s",
                (machine_id,),
            )
            row = await cursor.fetchone()
    return None if row is None else row[0]


async def get_observed_productive_hours(machine_id: str) -> dict[str, Any]:
    """Aggregate the productive share of each available hourly snapshot."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT MIN(timestamp), MAX(timestamp), COUNT(*),
                       COALESCE(SUM(uptime_percentage) / 100.0, 0)
                FROM telemetry_snapshots
                WHERE machine_id = %s
                """,
                (machine_id,),
            )
            row = await cursor.fetchone()
    return {
        "first_snapshot": row[0],
        "last_snapshot": row[1],
        "snapshot_count": row[2],
        "observed_productive_hours": row[3],
    }


async def get_manual_contents(machine_id: str) -> list[str]:
    """Read local manual chunks for deterministic maintenance-threshold extraction."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT content FROM manual_chunks WHERE machine_id = %s",
                (machine_id,),
            )
            rows = await cursor.fetchall()
    return [row[0] for row in rows]


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


async def manual_file_belongs_to_machine(machine_id: str, source_file: str) -> bool:
    """Check that a PDF was indexed for the requested machine."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM manual_chunks
                    WHERE machine_id = %s AND source_file = %s
                )
                """,
                (machine_id, source_file),
            )
            row = await cursor.fetchone()
    return bool(row[0])


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


async def get_user_profile(user: AuthContext) -> dict[str, Any]:
    """Return the authenticated user's own account and company context."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT u.user_id, u.first_name, u.last_name, u.email, u.job_title, u.visibility,
                       c.company_id, c.company_name, c.country, c.city, c.sector, c.currency, c.locale
                FROM users AS u
                JOIN companies AS c ON c.company_id = u.company_id
                WHERE u.user_id = %s AND u.company_id = %s
                """,
                (user.user_id, user.company_id),
            )
            row = await cursor.fetchone()
    if row is None:
        raise LookupError(user.user_id)
    return {
        "user_id": row[0], "first_name": row[1], "last_name": row[2], "email": row[3],
        "job_title": row[4], "visibility": row[5], "company_id": row[6],
        "company_name": row[7], "country": row[8], "city": row[9], "sector": row[10],
        "currency": row[11], "locale": row[12],
    }


async def get_company_order_detail(company_id: str, order_id: str) -> dict[str, Any]:
    """Return an order's fulfilment and the content of its approved quote revision."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT o.order_id, o.quote_id, o.order_status, o.shipment_status,
                       q.source_data ->> 'currency'
                FROM orders AS o
                JOIN quotes AS q ON q.quote_id = o.quote_id
                WHERE o.company_id = %s AND o.order_id = %s
                """,
                (company_id, order_id),
            )
            order = await cursor.fetchone()
            if order is None:
                raise OrderNotFoundError(order_id)
            await cursor.execute(
                """
                SELECT quote_revision_id, revision_number, revision_status, discount_rate
                FROM quote_revisions
                WHERE quote_id = %s AND revision_status = 'Approved'
                ORDER BY revision_number DESC
                LIMIT 1
                """,
                (order[1],),
            )
            revision = await cursor.fetchone()
            await cursor.execute(
                """
                SELECT order_line_id, fulfillment_status
                FROM order_lines
                WHERE order_id = %s
                ORDER BY order_line_id
                """,
                (order_id,),
            )
            fulfillment_rows = await cursor.fetchall()
            line_rows: list[tuple[Any, ...]] = []
            if revision is not None:
                await cursor.execute(
                    """
                    SELECT quote_line_id, machine_id, source_data ->> 'description', price
                    FROM quote_lines
                    WHERE quote_revision_id = %s
                    ORDER BY quote_line_id
                    """,
                    (revision[0],),
                )
                line_rows = await cursor.fetchall()

    return {
        "order_id": order[0], "quote_id": order[1], "order_status": order[2],
        "shipment_status": order[3], "currency": order[4],
        "approved_revision": None if revision is None else {
            "revision_number": revision[1], "revision_status": revision[2], "discount_rate": revision[3],
        },
        "items": [
            {"quote_line_id": row[0], "machine_id": row[1], "description": row[2], "price": row[3]}
            for row in line_rows
        ],
        "fulfillment": [{"order_line_id": row[0], "fulfillment_status": row[1]} for row in fulfillment_rows],
    }


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
            "validity_status": quote_validity_status(row[1]),
            "revision_number": row[2],
            "revision_status": row[3],
            "discount_rate": row[4],
            "line_total": row[5],
        }
        for row in rows
    ]


def _line_key(line: dict[str, Any]) -> tuple[str, str]:
    """Use the only stable business identity available across quote revisions."""

    return (str(line["machine_id"] or ""), str(line["description"] or "").casefold().strip())


def _compare_quote_lines(
    previous_lines: list[dict[str, Any]],
    current_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Describe line additions, removals and net-price changes across revisions."""

    previous_by_key = {_line_key(line): line for line in previous_lines}
    current_by_key = {_line_key(line): line for line in current_lines}
    changes: list[dict[str, Any]] = []
    for key in sorted(set(previous_by_key) | set(current_by_key)):
        previous = previous_by_key.get(key)
        current = current_by_key.get(key)
        reference = current or previous
        assert reference is not None
        if previous is None:
            change = "added"
        elif current is None:
            change = "removed"
        elif float(previous["price"]) != float(current["price"]):
            change = "price_changed"
        else:
            continue
        changes.append(
            {
                "change": change,
                "machine_id": reference["machine_id"],
                "description": reference["description"],
                "previous_price": None if previous is None else previous["price"],
                "current_price": None if current is None else current["price"],
            }
        )
    return changes


async def get_company_quote_history(company_id: str, quote_id: str) -> dict[str, Any]:
    """Return one company's full quote history and the latest revision comparison."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT quote_id, valid_until, source_data ->> 'currency',
                       source_data ->> 'created_at', source_data ->> 'description'
                FROM quotes
                WHERE quote_id = %s AND company_id = %s
                """,
                (quote_id, company_id),
            )
            quote = await cursor.fetchone()
            if quote is None:
                raise QuoteNotFoundError(quote_id)
            await cursor.execute(
                """
                SELECT qr.quote_revision_id, qr.revision_number, qr.revision_status,
                       qr.discount_rate, qr.source_data ->> 'issued_at',
                       qr.source_data ->> 'change_summary',
                       COALESCE(SUM(ql.price), 0) AS line_total
                FROM quote_revisions AS qr
                LEFT JOIN quote_lines AS ql ON ql.quote_revision_id = qr.quote_revision_id
                WHERE qr.quote_id = %s
                GROUP BY qr.quote_revision_id, qr.revision_number, qr.revision_status,
                         qr.discount_rate, qr.source_data
                ORDER BY qr.revision_number
                """,
                (quote_id,),
            )
            revision_rows = await cursor.fetchall()
            await cursor.execute(
                """
                SELECT ql.quote_revision_id, ql.quote_line_id, ql.machine_id, ql.price,
                       ql.source_data ->> 'description'
                FROM quote_lines AS ql
                JOIN quote_revisions AS qr ON qr.quote_revision_id = ql.quote_revision_id
                WHERE qr.quote_id = %s
                ORDER BY ql.quote_revision_id, ql.quote_line_id
                """,
                (quote_id,),
            )
            line_rows = await cursor.fetchall()

    lines_by_revision: dict[str, list[dict[str, Any]]] = {}
    for row in line_rows:
        lines_by_revision.setdefault(row[0], []).append(
            {
                "quote_line_id": row[1],
                "machine_id": row[2],
                "price": row[3],
                "description": row[4],
            }
        )
    revisions = [
        {
            "quote_revision_id": row[0],
            "revision_number": row[1],
            "revision_status": row[2],
            "discount_rate": row[3],
            "issued_at": row[4],
            "change_summary": row[5],
            "line_total": row[6],
            "lines": lines_by_revision.get(row[0], []),
        }
        for row in revision_rows
    ]
    comparison = []
    if len(revisions) >= 2:
        comparison = _compare_quote_lines(revisions[-2]["lines"], revisions[-1]["lines"])
    return {
        "quote_id": quote[0],
        "valid_until": quote[1],
        "validity_status": quote_validity_status(quote[1]),
        "currency": quote[2],
        "created_at": quote[3],
        "description": quote[4],
        "revisions": revisions,
        "latest_comparison": comparison,
    }

"""PostgreSQL repository for iot data."""

from datetime import datetime
from typing import Any

from core.db import connection


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

async def get_alarms_by_ids(machine_id: str, alarm_ids: list[str]) -> list[dict[str, Any]]:
    """Return exact alarm events belonging to an already-authorized machine.

    The machine predicate is intentionally part of the query so an alarm ID
    supplied by another evidence operation cannot disclose an event outside
    the selected machine.
    """

    if not alarm_ids:
        return []
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT alarm_id, timestamp, alarm_code, severity, alarm_status
                FROM alarms
                WHERE machine_id = %s AND alarm_id = ANY(%s)
                ORDER BY timestamp DESC
                """,
                (machine_id, alarm_ids),
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

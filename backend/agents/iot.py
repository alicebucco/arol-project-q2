"""IoT Agent: operational data access for telemetry and alarms."""

from datetime import datetime
from typing import Any

from core.auth import AuthContext
from core.contracts import AgentResult
from core.data_access import (
    authorize_machine,
    count_alarm_events,
    get_machine_configuration_profile,
    get_recent_alarms,
    get_telemetry_snapshots,
    summarize_alarm_events,
    summarize_telemetry_snapshots,
)
from core.machine_configuration import production_assessment

ALARM_SEVERITIES = {"Critical", "High", "Medium", "Low"}
ALARM_STATUSES = {"Open", "Acknowledged", "Resolved"}
OPERATIONAL_STATUSES = {"Running", "Alarm", "Idle", "Stopped", "Maintenance", "Size change"}


def _validate_period(start_time: datetime | None, end_time: datetime | None) -> None:
    if start_time is None or end_time is None:
        return
    try:
        invalid = start_time > end_time
    except TypeError as error:
        raise ValueError("Time-range boundaries must use compatible time zones.") from error
    if invalid:
        raise ValueError("A time range cannot end before it starts.")


def _validate_alarm_filters(severity: str | None, alarm_status: str | None) -> None:
    if severity is not None and severity not in ALARM_SEVERITIES:
        raise ValueError(f"Unsupported alarm severity: {severity}.")
    if alarm_status is not None and alarm_status not in ALARM_STATUSES:
        raise ValueError(f"Unsupported alarm status: {alarm_status}.")


def _validate_operational_status(operational_status: str | None) -> None:
    if operational_status is not None and operational_status not in OPERATIONAL_STATUSES:
        raise ValueError(f"Unsupported operational status: {operational_status}.")


async def recent_alarms(
    machine_id: str,
    user: AuthContext,
    limit: int,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    alarm_code: str | None = None,
    severity: str | None = None,
    alarm_status: str | None = None,
) -> list[dict[str, Any]]:
    """Authorise and retrieve recent alarms for the user's machine."""

    _validate_period(start_time, end_time)
    _validate_alarm_filters(severity, alarm_status)
    await authorize_machine(machine_id, user, domain="operational")
    return await get_recent_alarms(
        machine_id, limit, start_time=start_time, end_time=end_time,
        alarm_code=alarm_code, severity=severity, alarm_status=alarm_status,
    )


async def count_alarms(
    machine_id: str,
    user: AuthContext,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    alarm_code: str | None = None,
    severity: str | None = None,
    alarm_status: str | None = None,
) -> dict[str, Any]:
    """Count matching alarms without transferring raw events to the caller."""

    _validate_period(start_time, end_time)
    _validate_alarm_filters(severity, alarm_status)
    await authorize_machine(machine_id, user, domain="operational")
    count = await count_alarm_events(
        machine_id, start_time=start_time, end_time=end_time,
        alarm_code=alarm_code, severity=severity, alarm_status=alarm_status,
    )
    return {
        "machine_id": machine_id,
        "filters": {
            "start_time": start_time, "end_time": end_time,
            "alarm_code": alarm_code, "severity": severity,
            "alarm_status": alarm_status,
        },
        "occurrences": count,
    }


async def alarm_summary(
    machine_id: str,
    user: AuthContext,
    limit: int = 20,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    alarm_code: str | None = None,
    severity: str | None = None,
    alarm_status: str | None = None,
) -> dict[str, Any]:
    """Return counts and time bounds grouped by alarm code."""

    _validate_period(start_time, end_time)
    _validate_alarm_filters(severity, alarm_status)
    await authorize_machine(machine_id, user, domain="operational")
    patterns = await summarize_alarm_events(
        machine_id, limit, start_time=start_time, end_time=end_time,
        alarm_code=alarm_code, severity=severity, alarm_status=alarm_status,
    )
    total_occurrences = await count_alarm_events(
        machine_id, start_time=start_time, end_time=end_time,
        alarm_code=alarm_code, severity=severity, alarm_status=alarm_status,
    )
    return {
        "machine_id": machine_id,
        "filters": {
            "start_time": start_time, "end_time": end_time,
            "alarm_code": alarm_code, "severity": severity,
            "alarm_status": alarm_status,
        },
        "patterns": patterns,
        "total_occurrences": total_occurrences,
    }


async def telemetry(
    machine_id: str,
    user: AuthContext,
    limit: int,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    operational_status: str | None = None,
) -> list[dict[str, Any]]:
    """Authorise and retrieve recent telemetry for the user's machine."""

    _validate_period(start_time, end_time)
    _validate_operational_status(operational_status)
    await authorize_machine(machine_id, user, domain="operational")
    configuration_profile = await get_machine_configuration_profile(machine_id)
    snapshots = await get_telemetry_snapshots(
        machine_id, limit, start_time=start_time, end_time=end_time,
        operational_status=operational_status,
    )
    return [
        snapshot | {"production_assessment": production_assessment(snapshot, configuration_profile)}
        for snapshot in snapshots
    ]


async def telemetry_summary(
    machine_id: str,
    user: AuthContext,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    operational_status: str | None = None,
) -> dict[str, Any]:
    """Aggregate telemetry in PostgreSQL for a requested time window."""

    _validate_period(start_time, end_time)
    _validate_operational_status(operational_status)
    await authorize_machine(machine_id, user, domain="operational")
    summary = await summarize_telemetry_snapshots(
        machine_id, start_time=start_time, end_time=end_time,
        operational_status=operational_status,
    )
    return {
        "machine_id": machine_id,
        "filters": {
            "start_time": start_time, "end_time": end_time,
            "operational_status": operational_status,
        },
        **summary,
    }


async def compare_telemetry_periods(
    machine_id: str,
    user: AuthContext,
    *,
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
    operational_status: str | None = None,
) -> dict[str, Any]:
    """Return two comparable summaries; interpretation remains with the caller."""

    _validate_period(first_start, first_end)
    _validate_period(second_start, second_end)
    _validate_operational_status(operational_status)
    await authorize_machine(machine_id, user, domain="operational")
    first = await summarize_telemetry_snapshots(
        machine_id, start_time=first_start, end_time=first_end,
        operational_status=operational_status,
    )
    second = await summarize_telemetry_snapshots(
        machine_id, start_time=second_start, end_time=second_end,
        operational_status=operational_status,
    )
    changes: dict[str, dict[str, float | None]] = {}
    for metric in ("production_rate_bph", "uptime_percentage", "temperature_c", "energy_kwh"):
        first_average = first[metric]["average"]
        second_average = second[metric]["average"]
        absolute_change = (
            None if first_average is None or second_average is None
            else round(second_average - first_average, 3)
        )
        percent_change = (
            None if absolute_change is None or first_average == 0
            else round((absolute_change / first_average) * 100, 1)
        )
        changes[metric] = {
            "average_absolute_change": absolute_change,
            "average_percent_change": percent_change,
        }
    return {
        "machine_id": machine_id,
        "operational_status": operational_status,
        "first_period": {"start_time": first_start, "end_time": first_end, **first},
        "second_period": {"start_time": second_start, "end_time": second_end, **second},
        "changes": changes,
    }


async def recent_alarms_evidence(
    machine_id: str,
    user: AuthContext,
    limit: int,
    **filters: Any,
) -> AgentResult:
    """Return authorised alarm records in the orchestration result contract."""

    alarms = await recent_alarms(machine_id, user, limit, **filters)
    return AgentResult(
        agent="iot",
        operation="recent_alarms",
        evidence={"machine_id": machine_id, "alarms": alarms},
        structured_data={"machine_id": machine_id, "alarms": alarms},
    )


async def count_alarms_evidence(
    machine_id: str,
    user: AuthContext,
    **filters: Any,
) -> AgentResult:
    """Return an authorised alarm count in the orchestration result contract."""

    result = await count_alarms(machine_id, user, **filters)
    return AgentResult(
        agent="iot",
        operation="count_alarms",
        evidence=result,
        structured_data={"machine_id": machine_id},
    )


async def alarm_summary_evidence(
    machine_id: str,
    user: AuthContext,
    limit: int,
    **filters: Any,
) -> AgentResult:
    """Return authorised alarm patterns in the orchestration result contract."""

    result = await alarm_summary(machine_id, user, limit, **filters)
    return AgentResult(
        agent="iot",
        operation="alarm_summary",
        evidence=result,
        structured_data={"machine_id": machine_id, "alarm_patterns": result["patterns"]},
    )


async def telemetry_evidence(
    machine_id: str,
    user: AuthContext,
    limit: int,
    **filters: Any,
) -> AgentResult:
    """Return authorised telemetry in the orchestration result contract."""

    snapshots = await telemetry(machine_id, user, limit, **filters)
    return AgentResult(
        agent="iot",
        operation="telemetry",
        evidence={"machine_id": machine_id, "telemetry": snapshots},
        structured_data={"machine_id": machine_id, "telemetry": snapshots},
    )


async def telemetry_summary_evidence(
    machine_id: str,
    user: AuthContext,
    **filters: Any,
) -> AgentResult:
    """Return an authorised telemetry summary in the orchestration result contract."""

    result = await telemetry_summary(machine_id, user, **filters)
    return AgentResult(
        agent="iot",
        operation="telemetry_summary",
        evidence=result,
        structured_data={"machine_id": machine_id},
    )


async def compare_telemetry_periods_evidence(
    machine_id: str,
    user: AuthContext,
    **parameters: Any,
) -> AgentResult:
    """Return an authorised period comparison in the orchestration result contract."""

    result = await compare_telemetry_periods(machine_id, user, **parameters)
    return AgentResult(
        agent="iot",
        operation="compare_telemetry_periods",
        evidence=result,
        structured_data={"machine_id": machine_id},
    )

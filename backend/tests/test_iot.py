import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from agents import iot
from core.auth import AuthContext


def test_iot_telemetry_uses_machine_specific_configuration(monkeypatch) -> None:
    monkeypatch.setattr(iot, "authorize_machine", AsyncMock())
    monkeypatch.setattr(iot, "get_machine_configuration_profile", AsyncMock(return_value="6 heads / 10000 bph / 480V"))
    monkeypatch.setattr(
        iot,
        "get_telemetry_snapshots",
        AsyncMock(return_value=[{"operational_status": "Running", "production_rate_bph": 8500}]),
    )

    rows = asyncio.run(iot.telemetry("MCH-0002", AuthContext("USR-1", "CMP-1", "full"), 5))

    assert rows[0]["production_assessment"] == {
        "nominal_production_rate_bph": 10000.0,
        "production_vs_nominal_percent": 85.0,
        "status": "below_nominal_reference",
        "reason": "Production is more than 10% below this machine's configured nominal rate.",
    }


def test_iot_counts_filtered_alarms_without_loading_events(monkeypatch) -> None:
    authorize = AsyncMock()
    count = AsyncMock(return_value=5)
    monkeypatch.setattr(iot, "authorize_machine", authorize)
    monkeypatch.setattr(iot, "count_alarm_events", count)
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    end = datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc)

    result = asyncio.run(iot.count_alarms(
        "MCH-0001", AuthContext("USR-1", "CMP-1", "full"),
        start_time=start, end_time=end, alarm_code=" al082_minimum_caps_level ",
    ))

    assert result["occurrences"] == 5
    assert result["filters"]["alarm_code"] == "AL082_MINIMUM_CAPS_LEVEL"
    authorize.assert_awaited_once()
    count.assert_awaited_once_with(
        "MCH-0001", start_time=start, end_time=end,
        alarm_code="AL082_MINIMUM_CAPS_LEVEL", severity=None, alarm_status=None,
    )


@pytest.mark.parametrize(
    "operation",
    [iot.recent_alarms, iot.count_alarms, iot.alarm_summary],
)
def test_iot_rejects_invalid_alarm_codes_before_authorisation(monkeypatch, operation) -> None:
    authorize = AsyncMock()
    monkeypatch.setattr(iot, "authorize_machine", authorize)

    arguments = ["MCH-0001", AuthContext("USR-1", "CMP-1", "full")]
    if operation is iot.recent_alarms:
        arguments.append(5)

    with pytest.raises(ValueError, match="ALnnn_MNEMONIC"):
        asyncio.run(operation(*arguments, alarm_code="LOW_AIR_PRESSURE"))

    authorize.assert_not_awaited()


def test_iot_summarizes_alarm_patterns(monkeypatch) -> None:
    monkeypatch.setattr(iot, "authorize_machine", AsyncMock())
    monkeypatch.setattr(iot, "count_alarm_events", AsyncMock(return_value=4))
    monkeypatch.setattr(iot, "summarize_alarm_events", AsyncMock(return_value=[
        {"alarm_code": "AL017_LOW_AIR_PRESSURE", "occurrences": 4}
    ]))

    result = asyncio.run(iot.alarm_summary(
        "MCH-0001", AuthContext("USR-1", "CMP-1", "technician")
    ))

    assert result["total_occurrences"] == 4
    assert result["patterns"][0]["alarm_code"] == "AL017_LOW_AIR_PRESSURE"


def test_iot_compares_telemetry_periods(monkeypatch) -> None:
    monkeypatch.setattr(iot, "authorize_machine", AsyncMock())
    summaries = AsyncMock(side_effect=[
        {
            "snapshot_count": 24,
            "production_rate_bph": {"average": 8000.0},
            "uptime_percentage": {"average": 80.0},
            "temperature_c": {"average": 30.0},
            "energy_kwh": {"average": 10.0},
        },
        {
            "snapshot_count": 24,
            "production_rate_bph": {"average": 8800.0},
            "uptime_percentage": {"average": 84.0},
            "temperature_c": {"average": 33.0},
            "energy_kwh": {"average": 9.0},
        },
    ])
    monkeypatch.setattr(iot, "summarize_telemetry_snapshots", summaries)
    first_start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    first_end = datetime(2026, 7, 1, 23, tzinfo=timezone.utc)
    second_start = datetime(2026, 7, 2, tzinfo=timezone.utc)
    second_end = datetime(2026, 7, 2, 23, tzinfo=timezone.utc)

    result = asyncio.run(iot.compare_telemetry_periods(
        "MCH-0001", AuthContext("USR-1", "CMP-1", "full"),
        first_start=first_start, first_end=first_end,
        second_start=second_start, second_end=second_end,
    ))

    assert result["changes"]["temperature_c"] == {
        "average_absolute_change": 3.0,
        "average_percent_change": 10.0,
    }
    assert result["changes"]["production_rate_bph"]["average_percent_change"] == 10.0


@pytest.mark.parametrize("available", [True, False])
def test_observed_productive_hours_preserves_database_evidence(monkeypatch, available):
    from decimal import Decimal

    timestamp = datetime(2026, 8, 1, tzinfo=timezone.utc)
    window = {
        "observed_productive_hours": Decimal("1.375") if available else Decimal("0"),
        "snapshot_count": 2 if available else 0,
        "first_snapshot": timestamp if available else None,
        "last_snapshot": timestamp if available else None,
    }
    authorise = AsyncMock()

    async def read_hours(machine_id):
        authorise.assert_awaited_once_with("MCH-1", user, domain="operational")
        return window

    query = AsyncMock(side_effect=read_hours)
    user = AuthContext("USR-1", "CMP-1", "technician")
    monkeypatch.setattr(iot, "authorize_machine", authorise)
    monkeypatch.setattr(iot, "get_observed_productive_hours", query)
    result = asyncio.run(iot.observed_productive_hours("MCH-1", user))
    assert result["machine_id"] == "MCH-1"
    assert {key: result[key] for key in window} == window
    assert "not the machine's lifetime hour counter" in result["scope_note"]
    assert "no telemetry is available" in result["scope_note"]
    query.assert_awaited_once_with("MCH-1")


@pytest.mark.parametrize("missing_machine", [False, True])
def test_observed_productive_hours_does_not_query_after_authorisation_failure(monkeypatch, missing_machine):
    from fastapi import HTTPException
    from core.data_access import MachineNotFoundError

    error = MachineNotFoundError("MCH-1") if missing_machine else HTTPException(status_code=403)
    monkeypatch.setattr(iot, "authorize_machine", AsyncMock(side_effect=error))
    query = AsyncMock()
    monkeypatch.setattr(iot, "get_observed_productive_hours", query)
    with pytest.raises(type(error)):
        asyncio.run(iot.observed_productive_hours("MCH-1", AuthContext("USR-1", "CMP-1", "commercial")))
    query.assert_not_awaited()

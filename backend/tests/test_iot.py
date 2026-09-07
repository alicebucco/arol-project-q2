import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

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
        start_time=start, end_time=end, alarm_code="AL082_MINIMUM_CAPS_LEVEL",
    ))

    assert result["occurrences"] == 5
    assert result["filters"]["alarm_code"] == "AL082_MINIMUM_CAPS_LEVEL"
    authorize.assert_awaited_once()
    count.assert_awaited_once_with(
        "MCH-0001", start_time=start, end_time=end,
        alarm_code="AL082_MINIMUM_CAPS_LEVEL", severity=None, alarm_status=None,
    )


def test_iot_retrieves_exact_alarm_events_by_id(monkeypatch) -> None:
    authorize = AsyncMock()
    lookup = AsyncMock(return_value=[{"alarm_id": "ALM-0045", "alarm_code": "AL024_FRONT_PANEL_EMERGENCY_PRESSED"}])
    monkeypatch.setattr(iot, "authorize_machine", authorize)
    monkeypatch.setattr(iot, "get_alarms_by_ids", lookup)

    result = asyncio.run(iot.alarms_by_id(
        "MCH-0001", AuthContext("USR-1", "CMP-1", "full"), [" alm-0045 ", "ALM-0045"],
    ))

    assert result == [{"alarm_id": "ALM-0045", "alarm_code": "AL024_FRONT_PANEL_EMERGENCY_PRESSED"}]
    authorize.assert_awaited_once()
    lookup.assert_awaited_once_with("MCH-0001", ["ALM-0045"])


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

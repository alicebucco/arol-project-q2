from datetime import datetime, timezone

from core.maintenance_observation import maintenance_observation, manual_maintenance_thresholds


def test_extracts_unique_working_hour_thresholds_from_manual_text() -> None:
    thresholds = manual_maintenance_thresholds(
        [
            "EVERY 40 WORKING HOURS check the pneumatic system.",
            "Every 1,000 operating hours perform the overhaul.",
            "EVERY 40 WORKING HOURS check the pneumatic system.",
        ]
    )

    assert thresholds == [40, 1000]


def test_reports_only_hours_observed_in_the_available_telemetry_window() -> None:
    result = maintenance_observation(
        "MCH-0001",
        {
            "first_snapshot": datetime(2026, 7, 6, tzinfo=timezone.utc),
            "last_snapshot": datetime(2026, 8, 4, 23, tzinfo=timezone.utc),
            "snapshot_count": 720,
            "observed_productive_hours": 514.26,
        },
        ["Every 40 working hours", "Every 500 working hours", "Every 1000 working hours"],
    )

    assert result["reached_threshold_hours"] == [40, 500]
    assert result["next_threshold_hours"] == 1000
    assert "not the machine's lifetime hour counter" in result["scope_note"]

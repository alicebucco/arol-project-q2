from datetime import datetime, timezone

from core.maintenance_observation import maintenance_observation


def test_reports_only_hours_observed_in_the_available_telemetry_window() -> None:
    result = maintenance_observation(
        "MCH-0001",
        {
            "first_snapshot": datetime(2026, 7, 6, tzinfo=timezone.utc),
            "last_snapshot": datetime(2026, 8, 4, 23, tzinfo=timezone.utc),
            "snapshot_count": 720,
            "observed_productive_hours": 514.26,
        },
        [
            {"interval_hours": 40, "citation": {"chunk_id": "p40"}},
            {"interval_hours": 500, "citation": {"chunk_id": "p500"}},
            {"interval_hours": 1000, "citation": {"chunk_id": "p1000"}},
            {"interval_hours": 500, "citation": {"chunk_id": "duplicate"}},
        ],
    )

    assert result["reached_threshold_hours"] == [40, 500]
    assert result["next_threshold_hours"] == 1000
    assert "not the machine's lifetime hour counter" in result["scope_note"]
    assert "does not establish that maintenance is currently due" in result["scope_note"]

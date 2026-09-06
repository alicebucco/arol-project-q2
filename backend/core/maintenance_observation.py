"""Pure correlation of authorised maintenance evidence in the orchestrator."""

from __future__ import annotations

from typing import Any


def maintenance_observation(
    machine_id: str,
    telemetry_window: dict[str, Any],
    requirements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Relate cited manual intervals to the available telemetry window.

    Callers supply evidence already retrieved and authorised by the IoT and
    Manuals Agents. This helper neither reads data nor decides that maintenance
    is due or completed.
    """

    observed_hours = float(telemetry_window["observed_productive_hours"] or 0)
    thresholds = sorted({
        int(requirement["interval_hours"])
        for requirement in requirements
        if isinstance(requirement.get("interval_hours"), int)
        and requirement["interval_hours"] > 0
    })
    reached = [threshold for threshold in thresholds if threshold <= observed_hours]
    next_threshold = next((threshold for threshold in thresholds if threshold > observed_hours), None)
    return {
        "machine_id": machine_id,
        "observed_productive_hours": round(observed_hours, 2),
        "first_snapshot": telemetry_window["first_snapshot"],
        "last_snapshot": telemetry_window["last_snapshot"],
        "snapshot_count": telemetry_window["snapshot_count"],
        "documented_threshold_hours": thresholds,
        "reached_threshold_hours": reached,
        "next_threshold_hours": next_threshold,
        "scope_note": (
            "This relates explicit documented maintenance intervals to productive hours observed in the available "
            "telemetry window; it is not the machine's lifetime hour counter and does not establish that maintenance "
            "is currently due or completed."
        ),
    }

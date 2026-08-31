"""Calculate maintenance references from the telemetry window actually available."""

from __future__ import annotations

import re
from typing import Any, Iterable


HOUR_THRESHOLD_PATTERN = re.compile(
    r"\b(?:every|each)\s+(?P<hours>\d[\d,\s]*)\s+(?:working|operating)\s+hours\b",
    re.IGNORECASE,
)


def manual_maintenance_thresholds(contents: Iterable[str]) -> list[int]:
    """Extract documented working-hour thresholds from local manual chunks."""

    thresholds: set[int] = set()
    for content in contents:
        for match in HOUR_THRESHOLD_PATTERN.finditer(content):
            value = int(re.sub(r"[\s,]", "", match.group("hours")))
            if value > 0:
                thresholds.add(value)
    return sorted(thresholds)


def maintenance_observation(
    machine_id: str,
    telemetry_window: dict[str, Any],
    manual_contents: Iterable[str],
) -> dict[str, Any]:
    """Compare observed productive hours with thresholds, without claiming lifetime totals."""

    observed_hours = float(telemetry_window["observed_productive_hours"] or 0)
    thresholds = manual_maintenance_thresholds(manual_contents)
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
            "This compares documented thresholds with productive hours observed in the available telemetry window; "
            "it is not the machine's lifetime hour counter."
        ),
    }

"""Interpret machine-specific configuration values for operational evidence."""

from __future__ import annotations

import re
from typing import Any


# ``configuration_profile`` is free text in the supplied workbook, for example
# ``Twin chute / 20 heads / 40000 bph / 400V-60Hz / PK 314 chuck``.
NOMINAL_RATE_PATTERN = re.compile(r"(?P<rate>\d[\d\s,._]*)\s*bph\b", re.IGNORECASE)
EXPECTED_RATE_TOLERANCE = 0.10


def nominal_production_rate_bph(configuration_profile: str | None) -> float | None:
    """Extract the machine-specific nominal rate recorded in its profile."""

    if not configuration_profile:
        return None
    match = NOMINAL_RATE_PATTERN.search(configuration_profile)
    if match is None:
        return None
    value = re.sub(r"[\s,._]", "", match.group("rate"))
    try:
        return float(value)
    except ValueError:
        return None


def production_assessment(snapshot: dict[str, Any], configuration_profile: str | None) -> dict[str, Any]:
    """Compare one running snapshot with the installed machine's nominal rate.

    A zero rate outside ``Running`` is deliberately not classified as a fault:
    it can represent a planned stop, maintenance, an alarm state, or a size
    change. The result is a transparent reference for the user, not a diagnosis.
    """

    nominal_rate = nominal_production_rate_bph(configuration_profile)
    status = str(snapshot["operational_status"])
    actual_rate = float(snapshot["production_rate_bph"])

    assessment: dict[str, Any] = {
        "nominal_production_rate_bph": nominal_rate,
        "production_vs_nominal_percent": None,
        "status": "not_assessed",
        "reason": "The machine-specific nominal production rate is unavailable.",
    }
    if nominal_rate is None or nominal_rate <= 0:
        return assessment

    ratio = (actual_rate / nominal_rate) * 100
    assessment["production_vs_nominal_percent"] = round(ratio, 1)
    if status.casefold() != "running":
        assessment["reason"] = (
            f"The snapshot status is {status}; production is not evaluated outside Running."
        )
        return assessment

    lower_bound = nominal_rate * (1 - EXPECTED_RATE_TOLERANCE)
    upper_bound = nominal_rate * (1 + EXPECTED_RATE_TOLERANCE)
    if actual_rate < lower_bound:
        assessment["status"] = "below_nominal_reference"
        assessment["reason"] = "Production is more than 10% below this machine's configured nominal rate."
    elif actual_rate > upper_bound:
        assessment["status"] = "above_nominal_reference"
        assessment["reason"] = "Production is more than 10% above this machine's configured nominal rate."
    else:
        assessment["status"] = "within_expected_range"
        assessment["reason"] = "Production is within 10% of this machine's configured nominal rate."
    return assessment

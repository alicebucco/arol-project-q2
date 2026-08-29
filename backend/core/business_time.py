"""Business-time rules defined by the supplied project brief."""

from datetime import date


# The dataset is intentionally evaluated as if this were the current date.
BUSINESS_TODAY = date(2026, 8, 5)


def quote_validity_status(valid_until: date | None) -> str:
    """Classify a quote deadline against the fixed business date."""

    if valid_until is None:
        return "Unknown"
    return "Expired" if valid_until < BUSINESS_TODAY else "Valid"

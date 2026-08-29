from datetime import date

from core.business_time import BUSINESS_TODAY, quote_validity_status


def test_business_today_matches_the_dataset_reference_date() -> None:
    assert BUSINESS_TODAY == date(2026, 8, 5)


def test_quote_validity_uses_the_fixed_business_date() -> None:
    assert quote_validity_status(date(2026, 8, 4)) == "Expired"
    assert quote_validity_status(date(2026, 8, 5)) == "Valid"
    assert quote_validity_status(date(2026, 8, 6)) == "Valid"
    assert quote_validity_status(None) == "Unknown"

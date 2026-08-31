from decimal import Decimal

from core.data_access import _compare_quote_lines


def test_quote_revision_comparison_reports_removed_added_and_changed_lines() -> None:
    changes = _compare_quote_lines(
        [
            {"machine_id": "MCH-1", "description": "Head overhaul", "price": Decimal("100")},
            {"machine_id": "MCH-1", "description": "Optional photocell", "price": Decimal("20")},
        ],
        [
            {"machine_id": "MCH-1", "description": "Head overhaul", "price": Decimal("95")},
            {"machine_id": "MCH-1", "description": "New spring", "price": Decimal("10")},
        ],
    )

    assert changes == [
        {"change": "price_changed", "machine_id": "MCH-1", "description": "Head overhaul", "previous_price": Decimal("100"), "current_price": Decimal("95")},
        {"change": "added", "machine_id": "MCH-1", "description": "New spring", "previous_price": None, "current_price": Decimal("10")},
        {"change": "removed", "machine_id": "MCH-1", "description": "Optional photocell", "previous_price": Decimal("20"), "current_price": None},
    ]

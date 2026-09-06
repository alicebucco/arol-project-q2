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


def test_duplicate_line_keys_are_preserved_as_ambiguous() -> None:
    previous = [
        {"machine_id": None, "description": "Kit", "price": Decimal("100")},
        {"machine_id": None, "description": "kit", "price": Decimal("150")},
    ]
    current = [{"machine_id": None, "description": "Kit", "price": Decimal("120")}]
    changes = _compare_quote_lines(previous, current)
    assert len(changes) == 1
    assert changes[0]["change"] == "ambiguous"
    assert changes[0]["previous_lines"] == previous
    assert changes[0]["current_lines"] == current
    assert changes[0]["previous_price"] is None


def test_description_changes_are_not_inferred_to_be_the_same_item() -> None:
    changes = _compare_quote_lines(
        [{"machine_id": "MCH-1", "description": "Kit", "price": Decimal("100")}],
        [{"machine_id": "MCH-1", "description": "Complete kit", "price": Decimal("100")}],
    )
    assert {change["change"] for change in changes} == {"added", "removed"}

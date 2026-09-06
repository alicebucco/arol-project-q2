from core.evidence_formatters import agent_result, manual_search_result


def test_generic_formatter_builds_iot_result_for_structured_ui_data() -> None:
    alarms = [{"alarm_id": "ALM-1"}]
    evidence = {"machine_id": "MCH-0001", "alarms": alarms}

    result = agent_result("iot", "recent_alarms", evidence, structured_data=evidence)

    assert result.agent == "iot"
    assert result.operation == "recent_alarms"
    assert result.evidence == evidence
    assert result.structured_data == evidence


def test_generic_formatter_preserves_each_domain_operation_name() -> None:
    result = agent_result(
        "orders",
        "order_detail",
        {"order_detail": {"order_id": "ORD-1", "order_status": "Confirmed"}},
    )

    assert result.agent == "orders"
    assert result.operation == "order_detail"


def test_manual_formatter_excludes_raw_pdf_chunk_content_and_keeps_citation() -> None:
    matches = [{
        "file": "15610_manual_EN.pdf",
        "page": 32,
        "section": "safety",
        "title": "Safety guidance",
        "relevance": 0.8,
        "excerpt": "Wear protective gloves.",
        "content": "This raw chunk is local-only.",
    }]

    result = manual_search_result("MCH-0001", matches)

    assert result.agent == "manuals"
    assert result.evidence["machine_id"] == "MCH-0001"
    assert result.evidence["match_count"] == 1
    assert result.evidence["manual_evidence"][0]["excerpt"] == "Wear protective gloves."
    assert "content" not in result.evidence["manual_evidence"][0]
    assert "content" not in result.structured_data["manual_evidence"][0]
    assert "content" not in result.sources[0].model_dump()
    assert result.sources[0].citation == {
        "file": "15610_manual_EN.pdf",
        "page": 32,
        "section": "safety",
        "title": "Safety guidance",
        "relevance": 0.8,
    }

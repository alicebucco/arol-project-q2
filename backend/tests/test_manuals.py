import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agents import manuals
from agents.manuals import _alarm_codes, _maintenance_requirements, _rerank, validate_manual_claim_links
from core.auth import AuthContext


SCRIPT_DIRECTORY = Path(__file__).resolve().parents[2] / "db" / "scripts"
sys.path.insert(0, str(SCRIPT_DIRECTORY))
from chunk_manuals import classify_section, split_text  # noqa: E402


def test_rerank_rejects_navigation_text_and_only_removes_duplicate_chunks() -> None:
    candidates = [
        {
            "file": "manual.pdf",
            "page": 2,
            "section": "safety",
            "content": "SAFETY ............ 4 WARNINGS ............ 6 PRECAUTIONS ............ 8",
            "similarity": 0.91,
        },
        {
            "file": "manual.pdf",
            "page": 3,
            "section": "safety",
            "content": "Wear safety gloves before maintenance. Keep guards installed during operation.",
            "similarity": 0.58,
        },
        {
            "file": "manual.pdf",
            "page": 3,
            "section": "safety",
            "content": "Safety procedures require trained operators.",
            "similarity": 0.57,
        },
        {
            "file": "manual.pdf",
            "page": 3,
            "section": "safety",
            "content": "Safety procedures require trained operators.",
            "similarity": 0.56,
        },
        {
            "file": "manual.pdf",
            "page": 8,
            "section": "safety",
            "content": "Before maintenance, isolate energy sources and wear the required protection.",
            "similarity": 0.55,
        },
        {
            "file": "manual.pdf",
            "page": 10,
            "section": "general",
            "content": "Unrelated text.",
            "similarity": 0.20,
        },
    ]

    results = _rerank(candidates, "What safety precautions are required for maintenance?", 5)

    assert [result["page"] for result in results].count(3) == 2
    assert [result["page"] for result in results].count(8) == 1
    assert all("...." not in result["content"] for result in results)
    assert all(result["excerpt"] for result in results)
    assert all(result["title"] == "Manual excerpt" for result in results)
    assert all(result["section_category"] == "safety" for result in results)
    assert all(result["section_category_is_inferred"] for result in results)
    assert all(result["documented_section_title"] is None for result in results)
    assert all(result["highlights"] for result in results)
    assert all(result["relevance"] >= result["similarity"] for result in results)
    assert all(result["similarity_threshold_met"] for result in results)
    assert all(result["alarm_code_match"] == "not_requested" for result in results)
    assert all(result["excerpt_is_complete_chunk"] for result in results)


def test_excerpt_preserves_the_full_indexed_chunk() -> None:
    content = "First condition applies. Second condition applies. Final warning applies."
    result = _rerank(
        [{"file": "manual.pdf", "page": 1, "section": "safety", "content": content, "similarity": 0.7}],
        "What condition applies?", 1,
    )[0]

    assert result["excerpt"] == content
    assert result["excerpt_is_complete_chunk"] is True


def test_claim_validation_rebuilds_citations_from_authorized_evidence() -> None:
    evidence = [{
        "source": "manual", "chunk_id": "15610-p42-3", "file": "15610_manual_EN.pdf",
        "page": 42, "section": "mechanical",
        "content": "Disconnect the power supply before maintenance.",
    }]

    result = validate_manual_claim_links([
        {"claim": "The manual requires power isolation before maintenance.", "chunk_id": "15610-p42-3", "supporting_quote": "Disconnect the power supply before maintenance.", "file": "forged.pdf"},
        {"claim": "The manual documents a valve failure.", "chunk_id": "15610-p42-3", "supporting_quote": "A valve failure causes this alarm."},
        {"claim": "The manual documents a procedure.", "chunk_id": "unknown-chunk", "supporting_quote": "Disconnect the power supply before maintenance."},
    ], evidence)

    assert result["validated_claims"][0]["citation"] == {
        "source": "manual", "chunk_id": "15610-p42-3", "file": "15610_manual_EN.pdf",
        "page": 42, "section_category": "mechanical", "section_category_is_inferred": True,
    }
    assert [item["reason"] for item in result["rejected_claims"]] == [
        "The supporting quote is absent from the cited chunk.",
        "The cited chunk is not authorized evidence.",
    ]


def test_maintenance_requirements_keep_source_text_and_skip_contents_pages() -> None:
    chunks = [
        {"source": "manual", "chunk_id": "p6", "file": "manual.pdf", "page": 6, "section": "general", "content": "EVERY 500 WORKING HOURS ........ 90 EVERY 1000 WORKING HOURS ........ 91"},
        {"source": "manual", "chunk_id": "p90-short", "file": "manual.pdf", "page": 90, "section": "mechanical", "content": "EVERY 500 WORKING HOURS OPERATION AIM NOTES Lubricate the closure head."},
        {"source": "manual", "chunk_id": "p90-full", "file": "manual.pdf", "page": 90, "section": "mechanical", "content": "EVERY 500 WORKING HOURS OPERATION AIM NOTES Lubricate the closure head. If wear is observed, replace the affected component."},
        {"source": "manual", "chunk_id": "p91", "file": "manual.pdf", "page": 91, "section": "mechanical", "content": "EVERY 1000 OPERATING HOURS OPERATION AIM NOTES Inspect electrical connections."},
    ]

    requirements = _maintenance_requirements(chunks)

    assert [requirement["interval_hours"] for requirement in requirements] == [500, 1000]
    assert requirements[0]["citation"]["chunk_id"] == "p90-full"
    assert requirements[0]["documented_conditions"] == ["If wear is observed, replace the affected component."]
    assert requirements[0]["source_content"] == chunks[2]["content"]
    assert requirements[1]["interval_basis"] == "operating_hours"


def test_maintenance_requirements_authorize_before_reading_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    authorise = AsyncMock()
    read_chunks = AsyncMock(return_value=[])
    user = AuthContext("USR-1", "CMP-1", "technician")
    monkeypatch.setattr(manuals, "authorize_machine", authorise)
    monkeypatch.setattr(manuals, "get_manual_maintenance_chunks", read_chunks)

    result = asyncio.run(manuals.maintenance_requirements("MCH-1", user))

    authorise.assert_awaited_once_with("MCH-1", user, domain="manuals")
    read_chunks.assert_awaited_once_with("MCH-1")
    assert result["requirements"] == []


def test_rerank_returns_low_confidence_evidence_when_the_threshold_would_hide_everything() -> None:
    candidates = [
        {"file": "manual.pdf", "page": 12, "section": "general", "content": "Professional roles include operators and maintenance personnel.", "similarity": 0.31},
        {"file": "manual.pdf", "page": 13, "section": "general", "content": "The employer is responsible for training the operators.", "similarity": 0.28},
    ]

    results = _rerank(candidates, "What are the users professional roles?", 3)

    assert [result["page"] for result in results] == [12, 13]
    assert all(result["similarity"] < 0.40 for result in results)
    assert all(not result["similarity_threshold_met"] for result in results)


def test_alarm_code_extraction_normalizes_and_deduplicates() -> None:
    assert _alarm_codes("AL017_LOW_AIR_PRESSURE and al017_low_air_pressure") == [
        "AL017_LOW_AIR_PRESSURE"
    ]


def test_rerank_distinguishes_exact_code_in_a_passage_from_semantic_evidence() -> None:
    candidates = [
        {"file": "manual.pdf", "page": 12, "section": "troubleshooting", "content": "AL017_LOW_AIR_PRESSURE requires inspection.", "similarity": 0.70},
        {"file": "manual.pdf", "page": 13, "section": "troubleshooting", "content": "Inspect the pneumatic pressure circuit.", "similarity": 0.65},
    ]

    results = _rerank(candidates, "What does AL017_LOW_AIR_PRESSURE mean?", 2, requested_alarm_codes=["AL017_LOW_AIR_PRESSURE"])

    assert [result["alarm_code_match"] for result in results] == ["exact_in_passage", "semantic_only"]


def test_search_with_match_status_keeps_semantic_evidence_when_code_is_not_indexed(monkeypatch: pytest.MonkeyPatch) -> None:
    authorise = AsyncMock()
    monkeypatch.setattr(manuals, "authorize_machine", authorise)
    monkeypatch.setattr(manuals, "_embed_query", lambda _query: [0.0] * 384)
    monkeypatch.setattr(manuals, "find_manual_alarm_code_matches", AsyncMock(return_value=[]))
    monkeypatch.setattr(manuals, "search_manual_chunks", AsyncMock(return_value=[{
        "file": "manual.pdf", "page": 8, "section": "troubleshooting",
        "content": "Remove fallen bottles before restarting the line.", "similarity": 0.62,
    }]))

    result = asyncio.run(manuals.search_with_match_status(
        "MCH-1", "What does AL083_FALLEN_BOTTLE_ALARM mean?", AuthContext("USR-1", "CMP-1", "full"),
    ))

    assert result["alarm_code_match_status"] == "semantic_only"
    assert result["exact_alarm_code_matches"] == []
    assert result["unmatched_alarm_codes"] == ["AL083_FALLEN_BOTTLE_ALARM"]
    assert result["manual_evidence"][0]["alarm_code_match"] == "semantic_only"
    authorise.assert_awaited_once()


@pytest.mark.parametrize(
    ("query", "limit"),
    [("   ", 5), ("x" * 1_001, 5), (None, 5), ("safety", 0), ("safety", 11), ("safety", True)],
)
def test_search_rejects_invalid_requests_before_authorisation_or_embedding(
    monkeypatch: pytest.MonkeyPatch, query: object, limit: object,
) -> None:
    authorize = AsyncMock()
    embed = AsyncMock()
    monkeypatch.setattr(manuals, "authorize_machine", authorize)
    monkeypatch.setattr(manuals, "_embed_query", embed)

    with pytest.raises(ValueError):
        asyncio.run(manuals.search(
            "MCH-0001", query,  # type: ignore[arg-type]
            AuthContext("USR-1", "CMP-1", "full"), limit,  # type: ignore[arg-type]
        ))

    authorize.assert_not_awaited()
    embed.assert_not_awaited()


def test_chunking_preserves_sentence_boundaries_when_possible() -> None:
    text = "First complete sentence. Second complete sentence. Third complete sentence."
    chunks = split_text(text, size=55, overlap=0)

    assert chunks == ["First complete sentence. Second complete sentence.", "Third complete sentence."]
    assert all(chunk.endswith(".") and len(chunk) <= 55 for chunk in chunks)


def test_section_detection_ignores_keywords_inside_long_body_text() -> None:
    body = "This is an ordinary paragraph that happens to mention safety but it is long enough that it cannot be a heading in the manual document."
    assert classify_section(body, "general") == "general"
    assert classify_section("5. SAFETY PROCEDURES", "general") == "safety"

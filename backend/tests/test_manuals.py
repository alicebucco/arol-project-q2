import sys
from pathlib import Path

import pytest

from agents.manuals import _rerank


SCRIPT_DIRECTORY = Path(__file__).resolve().parents[2] / "db" / "scripts"
sys.path.insert(0, str(SCRIPT_DIRECTORY))
from chunk_manuals import classify_section, split_text  # noqa: E402


def test_rerank_rejects_navigation_text_and_duplicate_pages() -> None:
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

    assert [result["page"] for result in results] == [3, 8]
    assert all("...." not in result["content"] for result in results)
    assert all(result["excerpt"] for result in results)
    assert all(result["title"] == "Safety guidance" for result in results)
    assert all(result["highlights"] for result in results)
    assert all(result["relevance"] >= result["similarity"] for result in results)


def test_chunking_preserves_sentence_boundaries_when_possible() -> None:
    text = "First complete sentence. Second complete sentence. Third complete sentence."
    chunks = split_text(text, size=55, overlap=0)

    assert chunks == ["First complete sentence. Second complete sentence.", "Third complete sentence."]
    assert all(chunk.endswith(".") and len(chunk) <= 55 for chunk in chunks)


def test_section_detection_ignores_keywords_inside_long_body_text() -> None:
    body = "This is an ordinary paragraph that happens to mention safety but it is long enough that it cannot be a heading in the manual document."
    assert classify_section(body, "general") == "general"
    assert classify_section("5. SAFETY PROCEDURES", "general") == "safety"

"""Conversion from internal evidence to public response contracts."""

from api.schemas import ManualCitation, ManualSearchResult


def manual_search_result(row: dict[str, object]) -> ManualSearchResult:
    """Map an internal local manual result to the public API contract."""
    return ManualSearchResult(
        citation=ManualCitation(
            source=row["source"],  # type: ignore[arg-type]
            chunk_id=row.get("chunk_id"),  # type: ignore[arg-type]
            file=row["file"],  # type: ignore[arg-type]
            page=row["page"],  # type: ignore[arg-type]
            section=row["section"],  # type: ignore[arg-type]
        ),
        excerpt=row["excerpt"],  # type: ignore[arg-type]
        title=row["title"],  # type: ignore[arg-type]
        highlights=row["highlights"],  # type: ignore[arg-type]
        relevance=row["relevance"],  # type: ignore[arg-type]
        similarity=row["similarity"],  # type: ignore[arg-type]
        similarity_threshold_met=bool(row.get("similarity_threshold_met", False)),
        alarm_code_match=row.get("alarm_code_match", "not_requested"),  # type: ignore[arg-type]
        excerpt_is_complete_chunk=bool(row.get("excerpt_is_complete_chunk", False)),
        section_category=row.get("section_category"),  # type: ignore[arg-type]
        section_category_is_inferred=bool(row.get("section_category_is_inferred", True)),
        documented_section_title=row.get("documented_section_title"),  # type: ignore[arg-type]
    )

"""Manuals Agent: local semantic search over a machine-specific PDF manual."""

from __future__ import annotations

import asyncio
import os
import re
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

from core.auth import AuthContext
from core.alarm_codes import ALARM_CODE_IN_TEXT_PATTERN, normalise_alarm_code
from db.repositories.machines import authorize_machine
from db.repositories.manuals import (
    find_manual_alarm_code_matches,
    get_manual_maintenance_chunks,
    manual_file_belongs_to_machine,
    search_manual_chunks,
)


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384
MINIMUM_SIMILARITY = 0.40
CANDIDATE_MULTIPLIER = 20
MINIMUM_QUERY_LENGTH = 1
MAXIMUM_QUERY_LENGTH = 1_000
DEFAULT_LIMIT = 5
MAXIMUM_LIMIT = 10
MAINTENANCE_INTERVAL_PATTERN = re.compile(
    r"\b(?:every|each)\s+(?P<hours>\d[\d,\s]*)\s+"
    r"(?P<basis>working|operating)\s+hours\b",
    re.IGNORECASE,
)
CONDITION_SENTENCE_PATTERN = re.compile(r"^(?:if|when|unless|in case)\b", re.IGNORECASE)
STOP_WORDS = frozenset(
    {
        "about", "after", "before", "could", "find", "from", "have", "into",
        "manual", "machine", "please", "should", "show", "that", "the", "their",
        "there", "these", "this", "what", "which", "with", "would", "your",
    }
)
SECTION_TERMS = {
    "safety": frozenset({"safety", "warning", "warnings", "hazard", "hazards", "precaution", "precautions"}),
    "technical_data": frozenset({"configuration", "configured", "specification", "specifications", "dimension", "dimensions"}),
    "mechanical": frozenset({"installation", "assembly", "lubrication", "mechanical", "pneumatic", "pressure"}),
    "troubleshooting": frozenset({"alarm", "alarms", "cause", "diagnostic", "diagnostics", "fault", "faults", "problem", "problems", "remedy", "troubleshooting"}),
}
class ManualsUnavailableError(RuntimeError):
    """The local embedding model cannot be loaded or used."""


@lru_cache
def embedding_model() -> SentenceTransformer:
    """Load one local model per backend process and reuse the Docker cache."""
    try:
        # Import lazily so a missing optional embedding dependency degrades only
        # manual search, rather than preventing unrelated API endpoints from
        # starting at all.
        from sentence_transformers import SentenceTransformer

        # The model is populated in the Docker volume during setup.  Loading
        # it in offline mode avoids a network check (and repeated retries) for
        # every API start, while keeping manual embeddings completely local.
        model = SentenceTransformer(
            MODEL_NAME,
            cache_folder=os.getenv("HF_HOME"),
            local_files_only=True,
        )
    except Exception as error:
        raise ManualsUnavailableError("The local embedding model is unavailable.") from error
    if model.get_embedding_dimension() != EMBEDDING_DIMENSION:
        raise ManualsUnavailableError("The local embedding model has an unexpected vector dimension.")
    return model


def _embed_query(query: str) -> list[float]:
    vector = embedding_model().encode(query, normalize_embeddings=True)
    if len(vector) != EMBEDDING_DIMENSION:
        raise ManualsUnavailableError("The generated query embedding has an unexpected dimension.")
    return [float(value) for value in vector]


def _validate_search_request(query: str, limit: int) -> str:
    """Reject invalid internal search requests before authorisation or model use."""

    if not isinstance(query, str):
        raise ValueError("The manual search query must be a string.")
    normalized_query = query.strip()
    if len(normalized_query) < MINIMUM_QUERY_LENGTH:
        raise ValueError("The manual search query cannot be blank.")
    if len(normalized_query) > MAXIMUM_QUERY_LENGTH:
        raise ValueError(
            f"The manual search query cannot exceed {MAXIMUM_QUERY_LENGTH} characters."
        )
    if type(limit) is not int or not 1 <= limit <= MAXIMUM_LIMIT:
        raise ValueError(f"limit must be an integer between 1 and {MAXIMUM_LIMIT}.")
    return normalized_query


def _alarm_codes(query: str) -> list[str]:
    """Extract distinct normalized dataset alarm codes from a user query."""

    return sorted({
        normalise_alarm_code(match.group(0))
        for match in ALARM_CODE_IN_TEXT_PATTERN.finditer(query)
    })


def _contains_alarm_code(content: str, code: str) -> bool:
    """Match a whole code rather than a prefix inside another identifier."""

    return re.search(
        rf"(^|[^A-Z0-9_]){re.escape(code)}([^A-Z0-9_]|$)",
        content.upper(),
    ) is not None


def _normalise_evidence_text(text: str) -> str:
    """Normalize whitespace only, preserving the source wording for validation."""

    return re.sub(r"\s+", " ", text).strip()


def validate_manual_claim_links(
    claims: list[dict[str, Any]],
    manual_evidence: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Validate claim-to-chunk links supplied by an orchestration response.

    Returned citations are reconstructed from authorised evidence rather than
    trusting model-provided filename, page, or section fields.
    """

    evidence_by_chunk = {
        row["chunk_id"]: row
        for row in manual_evidence
        if isinstance(row.get("chunk_id"), str) and isinstance(row.get("content"), str)
    }
    validated: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw_claim in claims:
        claim = raw_claim.get("claim") if isinstance(raw_claim, dict) else None
        chunk_id = raw_claim.get("chunk_id") if isinstance(raw_claim, dict) else None
        quote = raw_claim.get("supporting_quote") if isinstance(raw_claim, dict) else None
        if not isinstance(claim, str) or not claim.strip():
            rejected.append({"claim": claim, "reason": "A claim must be a non-empty string."})
            continue
        if not isinstance(chunk_id, str) or chunk_id not in evidence_by_chunk:
            rejected.append({"claim": claim, "reason": "The cited chunk is not authorized evidence."})
            continue
        if not isinstance(quote, str) or not quote.strip():
            rejected.append({"claim": claim, "reason": "A supporting quote is required."})
            continue
        evidence = evidence_by_chunk[chunk_id]
        if _normalise_evidence_text(quote) not in _normalise_evidence_text(evidence["content"]):
            rejected.append({"claim": claim, "reason": "The supporting quote is absent from the cited chunk."})
            continue
        validated.append({
            "claim": claim.strip(),
            "supporting_quote": quote.strip(),
            "citation": {
                "source": evidence["source"], "chunk_id": evidence["chunk_id"],
                "file": evidence["file"], "page": evidence["page"],
                "section_category": evidence["section"],
                "section_category_is_inferred": True,
            },
        })
    return {"validated_claims": validated, "rejected_claims": rejected}


def _condition_sentences(text: str) -> list[str]:
    """Return only conditions explicitly expressed as complete source sentences."""

    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
    return [sentence for sentence in sentences if CONDITION_SENTENCE_PATTERN.match(sentence)]


def _maintenance_requirements(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse explicit interval headings without inferring undocumented activities."""

    selected: dict[tuple[str, int, int], dict[str, Any]] = {}
    for chunk in chunks:
        content = chunk["content"]
        if _is_navigation_text(content):
            continue
        matches = list(MAINTENANCE_INTERVAL_PATTERN.finditer(content))
        for index, match in enumerate(matches):
            raw_activity = content[match.end():matches[index + 1].start() if index + 1 < len(matches) else None]
            activity_text = re.sub(r"^\s*OPERATION\s+AIM\s+NOTES\s*", "", raw_activity, flags=re.IGNORECASE).strip()
            if not activity_text:
                continue
            hours = int(re.sub(r"[\s,]", "", match.group("hours")))
            requirement = {
                "interval_hours": hours,
                "interval_basis": f"{match.group('basis').casefold()}_hours",
                "interval_expression": match.group(0),
                "documented_activity_text": activity_text,
                "documented_conditions": _condition_sentences(activity_text),
                "source_content": content,
                "citation": {
                    "source": chunk["source"], "chunk_id": chunk["chunk_id"],
                    "file": chunk["file"], "page": chunk["page"],
                    "section_category": chunk["section"],
                    "section_category_is_inferred": True,
                },
                "scope_note": (
                    "The interval and activity text are extracted from one indexed manual chunk. "
                    "They do not establish that maintenance is due or that an activity was completed."
                ),
            }
            key = (chunk["file"], chunk["page"], hours)
            previous = selected.get(key)
            if previous is None or len(requirement["documented_activity_text"]) > len(previous["documented_activity_text"]):
                selected[key] = requirement
    return sorted(selected.values(), key=lambda item: (item["interval_hours"], item["citation"]["file"], item["citation"]["page"]))


def _terms(text: str) -> set[str]:
    """Keep meaningful English terms for local lexical reranking."""
    return {
        word
        for word in re.findall(r"[a-z0-9]+", text.casefold())
        if len(word) >= 3 and word not in STOP_WORDS
    }


def _section_bonus(query_terms: set[str], section: str) -> float:
    section_terms = SECTION_TERMS.get(section, frozenset())
    return 0.12 if query_terms & section_terms else 0.0


def _is_navigation_text(content: str) -> bool:
    """Exclude table-of-contents fragments, which are not useful evidence."""
    return len(re.findall(r"\.{4,}", content)) >= 2


def _highlights(content: str, query_terms: set[str]) -> list[str]:
    """Expose a small set of matched local terms for transparent retrieval."""
    matched = query_terms & _terms(content)
    return sorted(matched)[:4]


def _excerpt(content: str) -> str:
    """Expose the full indexed chunk without silently removing context.

    A chunk is still a page fragment created during indexing, not a complete PDF
    page or procedure. Its chunk ID, file, and page identify that scope.
    """

    return content


def _rerank(
    candidates: list[dict[str, Any]],
    query: str,
    limit: int,
    *,
    requested_alarm_codes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Combine vector relevance, lexical evidence, section affinity and diversity."""
    query_terms = _terms(query)
    ranked: list[tuple[float, dict[str, Any]]] = []
    fallback_ranked: list[tuple[float, dict[str, Any]]] = []
    for candidate in candidates:
        similarity = candidate["similarity"]
        if _is_navigation_text(candidate["content"]):
            continue
        lexical_score = len(query_terms & _terms(candidate["content"])) / max(len(query_terms), 1)
        score = similarity + (0.20 * lexical_score) + _section_bonus(query_terms, candidate["section"])
        if similarity >= MINIMUM_SIMILARITY:
            ranked.append((score, candidate))
        else:
            fallback_ranked.append((score, candidate))

    ranked.sort(key=lambda item: item[0], reverse=True)
    fallback_ranked.sort(key=lambda item: item[0], reverse=True)

    def select(
        ranked_candidates: list[tuple[float, dict[str, Any]]],
        *,
        similarity_threshold_met: bool,
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen_contents: set[tuple[str, int, str]] = set()
        for score, candidate in ranked_candidates:
            content_key = (
                candidate["file"], candidate["page"],
                re.sub(r"\s+", " ", candidate["content"]).strip(),
            )
            if content_key in seen_contents:
                continue
            result = dict(candidate)
            result["excerpt"] = _excerpt(result["content"])
            result["excerpt_is_complete_chunk"] = True
            result["title"] = "Manual excerpt"
            result["section_category"] = result["section"]
            result["section_category_is_inferred"] = True
            result["documented_section_title"] = None
            result["highlights"] = _highlights(result["content"], query_terms)
            result["relevance"] = round(min(score, 1.0), 3)
            result["similarity_threshold_met"] = similarity_threshold_met
            if requested_alarm_codes:
                content = result["content"].upper()
                result["alarm_code_match"] = (
                    "exact_in_passage"
                    if any(_contains_alarm_code(content, code) for code in requested_alarm_codes)
                    else "semantic_only"
                )
            else:
                result["alarm_code_match"] = "not_requested"
            selected.append(result)
            seen_contents.add(content_key)
            if len(selected) == limit:
                break
        return selected

    selected = select(ranked, similarity_threshold_met=True)
    # Fallbacks are exposed explicitly so callers cannot treat them as strong
    # retrieval evidence merely because the search found no stronger passage.
    return selected if selected else select(fallback_ranked, similarity_threshold_met=False)


async def search(
    machine_id: str,
    query: str,
    user: AuthContext,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Compatibility list; use search_with_match_status for alarm-code evidence."""

    return (await search_with_match_status(machine_id, query, user, limit))["manual_evidence"]


async def search_with_match_status(
    machine_id: str,
    query: str,
    user: AuthContext,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return semantic excerpts plus explicit whole-manual alarm-code evidence.

    Exact code detection only says that the literal code is indexed somewhere in
    the authorized manual. It does not establish a documented cause or remedy.
    Semantic excerpts are retained even when no code is found exactly.
    """

    query = _validate_search_request(query, limit)
    await authorize_machine(machine_id, user, domain="manuals")
    requested_alarm_codes = _alarm_codes(query)
    if requested_alarm_codes:
        embedding, exact_alarm_code_matches = await asyncio.gather(
            asyncio.to_thread(_embed_query, query),
            find_manual_alarm_code_matches(machine_id, requested_alarm_codes),
        )
    else:
        embedding = await asyncio.to_thread(_embed_query, query)
        exact_alarm_code_matches = []
    candidates = await search_manual_chunks(machine_id, embedding, limit * CANDIDATE_MULTIPLIER)
    evidence = _rerank(
        candidates, query, limit, requested_alarm_codes=requested_alarm_codes,
    )
    if not requested_alarm_codes:
        status = "not_requested"
    elif exact_alarm_code_matches:
        status = "exact_manual_match"
    elif evidence:
        status = "semantic_only"
    else:
        status = "no_matching_manual_evidence"
    return {
        "machine_id": machine_id,
        "query": query,
        "manual_evidence": evidence,
        "requested_alarm_codes": requested_alarm_codes,
        "exact_alarm_code_matches": exact_alarm_code_matches,
        "unmatched_alarm_codes": [
            code for code in requested_alarm_codes if code not in exact_alarm_code_matches
        ],
        "alarm_code_match_status": status,
    }


async def can_open_file(machine_id: str, source_file: str, user: AuthContext) -> bool:
    """Authorize access to one PDF that was indexed for this machine."""

    await authorize_machine(machine_id, user, domain="manuals")
    return await manual_file_belongs_to_machine(machine_id, source_file)


async def maintenance_requirements(machine_id: str, user: AuthContext) -> dict[str, Any]:
    """Return cited maintenance intervals from one authorized machine manual.

    This source operation does not read telemetry or service tickets and does not
    decide whether maintenance is due. Those evidence types are coordinated by the
    orchestrator.
    """

    await authorize_machine(machine_id, user, domain="manuals")
    chunks = await get_manual_maintenance_chunks(machine_id)
    return {
        "machine_id": machine_id,
        "requirements": _maintenance_requirements(chunks),
        "scope_note": (
            "Only explicit working-hour or operating-hour intervals in the indexed manual are returned. "
            "The result is documentary evidence, not a maintenance-due assessment."
        ),
    }

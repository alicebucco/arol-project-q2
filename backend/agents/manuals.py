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
from core.data_access import authorize_machine, manual_file_belongs_to_machine, search_manual_chunks


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384
MINIMUM_SIMILARITY = 0.40
CANDIDATE_MULTIPLIER = 6
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
SECTION_TITLES = {
    "safety": "Safety guidance",
    "technical_data": "Technical information",
    "mechanical": "Mechanical procedure",
    "troubleshooting": "Troubleshooting guidance",
    "general": "Manual guidance",
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


def _excerpt(content: str, query_terms: set[str]) -> str:
    """Return the most relevant complete sentences instead of a raw PDF chunk."""
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", content) if sentence.strip()]
    if not sentences:
        return content

    scored = []
    for index, sentence in enumerate(sentences):
        sentence_terms = _terms(sentence)
        overlap = len(query_terms & sentence_terms)
        scored.append((overlap, index, sentence))

    relevant = [item for item in scored if item[0] > 0]
    selected = sorted(relevant or scored, key=lambda item: (-item[0], item[1]))[:2]
    selected = sorted(selected, key=lambda item: item[1])
    excerpt = " ".join(sentence for _, _, sentence in selected)
    if len(excerpt) <= 500:
        return excerpt
    return excerpt[:497].rsplit(" ", 1)[0] + "…"


def _rerank(candidates: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    """Combine vector relevance, lexical evidence, section affinity and diversity."""
    query_terms = _terms(query)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for candidate in candidates:
        similarity = candidate["similarity"]
        if similarity < MINIMUM_SIMILARITY or _is_navigation_text(candidate["content"]):
            continue
        lexical_score = len(query_terms & _terms(candidate["content"])) / max(len(query_terms), 1)
        score = similarity + (0.20 * lexical_score) + _section_bonus(query_terms, candidate["section"])
        ranked.append((score, candidate))

    ranked.sort(key=lambda item: item[0], reverse=True)
    selected: list[dict[str, Any]] = []
    seen_pages: set[tuple[str, int]] = set()
    for score, candidate in ranked:
        page_key = (candidate["file"], candidate["page"])
        if page_key in seen_pages:
            continue
        result = dict(candidate)
        result["excerpt"] = _excerpt(result["content"], query_terms)
        result["title"] = SECTION_TITLES.get(result["section"], "Manual guidance")
        result["highlights"] = _highlights(result["content"], query_terms)
        result["relevance"] = round(min(score, 1.0), 3)
        selected.append(result)
        seen_pages.add(page_key)
        if len(selected) == limit:
            break
    return selected


async def search(
    machine_id: str,
    query: str,
    user: AuthContext,
    limit: int,
) -> list[dict[str, Any]]:
    """Return diverse, locally reranked excerpts after enforcing machine access."""
    await authorize_machine(machine_id, user, domain="manuals")
    embedding = await asyncio.to_thread(_embed_query, query)
    candidates = await search_manual_chunks(machine_id, embedding, limit * CANDIDATE_MULTIPLIER)
    return _rerank(candidates, query, limit)


async def can_open_file(machine_id: str, source_file: str, user: AuthContext) -> bool:
    """Authorize access to one PDF that was indexed for this machine."""

    await authorize_machine(machine_id, user, domain="manuals")
    return await manual_file_belongs_to_machine(machine_id, source_file)

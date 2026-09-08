"""Candidate selection for planner-safe operation catalogues."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from core.capability_retrieval import CapabilityRetrievalUnavailableError
from core.contracts import ConversationTurn
from core.operations.registry import OperationRegistry


CatalogueRetriever = Callable[[str, OperationRegistry], Awaitable[list[dict[str, Any]]]]
MAXIMUM_CONTEXTUAL_RETRIEVAL_TEXT = 4_000


def catalogue_from_candidates(
    candidates: list[dict[str, Any]],
    complete_catalogue: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep semantic candidates bounded while preserving documented evidence."""

    if not candidates:
        return complete_catalogue
    candidates = list(candidates)
    manuals_search = next(
        (
            item
            for item in complete_catalogue
            if item["agent"] == "manuals" and item["operation"] == "search"
        ),
        None,
    )
    candidate_ids = {f"{item['agent']}.{item['operation']}" for item in candidates}
    if manuals_search is not None and "manuals.search" not in candidate_ids:
        candidates.append(manuals_search)
    return candidates


async def catalogue_for_question(
    message: str,
    registry: OperationRegistry,
    retrieve: CatalogueRetriever,
) -> list[dict[str, Any]]:
    """Use semantic candidates when available, without making retrieval a dependency."""

    complete_catalogue = registry.planner_catalog()
    try:
        candidates = await retrieve(message, registry)
    except CapabilityRetrievalUnavailableError:
        return complete_catalogue
    return catalogue_from_candidates(candidates, complete_catalogue)


def contextual_retrieval_text(message: str, history: list[ConversationTurn]) -> str:
    """Build a bounded semantic query from the current message and recent context."""

    recent_history = "\n".join(f"{turn.role}: {turn.content}" for turn in history[-4:])
    prefix = f"Current question: {message}\nRecent conversation: "
    available_history = max(0, MAXIMUM_CONTEXTUAL_RETRIEVAL_TEXT - len(prefix))
    return prefix + recent_history[-available_history:]


async def catalogue_for_contextual_question(
    message: str,
    history: list[ConversationTurn],
    registry: OperationRegistry,
    retrieve: CatalogueRetriever,
) -> list[dict[str, Any]]:
    """Retrieve candidates from untrusted history without treating it as evidence."""

    return await catalogue_for_question(contextual_retrieval_text(message, history), registry, retrieve)

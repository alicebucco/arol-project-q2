"""Semantic retrieval of planner-safe operation candidates."""

from __future__ import annotations

import asyncio
from typing import Any

from agents.manuals import EMBEDDING_DIMENSION, embedding_model
from db.capability_repository import search_operation_capabilities
from core.operation_registry import OPERATION_REGISTRY, OperationRegistry


DEFAULT_CANDIDATE_LIMIT = 12
MAXIMUM_MESSAGE_LENGTH = 4_000


class CapabilityRetrievalUnavailableError(RuntimeError):
    """The local semantic capability catalogue cannot be queried."""


def _normalise_message(message: str) -> str:
    if not isinstance(message, str) or not (normalised := message.strip()):
        raise ValueError("The planner question must be a non-empty string.")
    if len(normalised) > MAXIMUM_MESSAGE_LENGTH:
        raise ValueError(f"The planner question cannot exceed {MAXIMUM_MESSAGE_LENGTH} characters.")
    return normalised


def _embed_message(message: str) -> list[float]:
    try:
        vector = embedding_model().encode(message, normalize_embeddings=True)
    except Exception as error:
        raise CapabilityRetrievalUnavailableError("The local embedding model is unavailable.") from error
    if len(vector) != EMBEDDING_DIMENSION:
        raise CapabilityRetrievalUnavailableError("The local embedding model returned an unexpected dimension.")
    return [float(value) for value in vector]


async def retrieve_planner_catalogue(
    message: str,
    registry: OperationRegistry = OPERATION_REGISTRY,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[dict[str, Any]]:
    """Return registry entries whose capability descriptions match a question.

    The stored rows provide ranking only. Entries are reconstructed from the
    live registry so the planner can never receive stale database metadata.
    """
    message = _normalise_message(message)
    query_embedding = await asyncio.to_thread(_embed_message, message)
    try:
        matches = await search_operation_capabilities(query_embedding, limit)
    except Exception as error:
        raise CapabilityRetrievalUnavailableError("The capability catalogue is unavailable.") from error

    authorised_catalogue = {
        f"{item['agent']}.{item['operation']}": item
        for item in registry.planner_catalog()
    }
    return [
        authorised_catalogue[match.capability_id]
        for match in matches
        if match.capability_id in authorised_catalogue
    ]

"""Manuals Agent: local semantic search over a machine-specific PDF manual."""

from __future__ import annotations

import asyncio
import os
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

from core.auth import AuthContext
from core.data_access import authorize_machine, search_manual_chunks


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


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

        model = SentenceTransformer(MODEL_NAME, cache_folder=os.getenv("HF_HOME"))
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


async def search(
    machine_id: str,
    query: str,
    user: AuthContext,
    limit: int,
) -> list[dict[str, Any]]:
    """Return cited manual chunks after enforcing machine-level access."""
    await authorize_machine(machine_id, user, domain="manuals")
    embedding = await asyncio.to_thread(_embed_query, query)
    return await search_manual_chunks(machine_id, embedding, limit)

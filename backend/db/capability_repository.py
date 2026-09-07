"""Read the planner capability catalogue stored in PostgreSQL/pgvector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.db import connection


EMBEDDING_DIMENSION = 384
MAXIMUM_LIMIT = 20


@dataclass(frozen=True)
class RetrievedCapability:
    """One planner-safe operation ranked by semantic similarity."""

    capability_id: str
    agent: str
    operation: str
    capability_text: str
    parameters_schema: dict[str, Any]
    requires_machine_context: bool
    similarity: float


def vector_literal(vector: list[float]) -> str:
    """Format a pgvector parameter without interpolating it into SQL."""
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def _validate_request(query_embedding: list[float], limit: int) -> None:
    if len(query_embedding) != EMBEDDING_DIMENSION:
        raise ValueError(f"A capability query embedding must have {EMBEDDING_DIMENSION} dimensions.")
    if type(limit) is not int or not 1 <= limit <= MAXIMUM_LIMIT:
        raise ValueError(f"limit must be an integer between 1 and {MAXIMUM_LIMIT}.")


async def search_operation_capabilities(
    query_embedding: list[float],
    limit: int = 12,
) -> list[RetrievedCapability]:
    """Return the closest allowed operations without making any authorisation decision."""
    _validate_request(query_embedding, limit)
    query_vector = vector_literal(query_embedding)
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT capability_id, agent, operation, capability_text,
                       parameters_schema, requires_machine_context,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM operation_capabilities
                ORDER BY embedding <=> %s::vector, capability_id
                LIMIT %s
                """,
                (query_vector, query_vector, limit),
            )
            rows = await cursor.fetchall()
    return [
        RetrievedCapability(
            capability_id=row[0],
            agent=row[1],
            operation=row[2],
            capability_text=row[3],
            parameters_schema=row[4],
            requires_machine_context=bool(row[5]),
            similarity=float(row[6]),
        )
        for row in rows
    ]

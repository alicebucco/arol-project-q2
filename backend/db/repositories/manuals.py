"""PostgreSQL repository for manuals data."""

from typing import Any

from core.db import connection


async def find_manual_alarm_code_matches(machine_id: str, alarm_codes: list[str]) -> list[str]:
    """Find literal alarm codes across one authorized machine's full index.

    Alarm codes come from the agent's strict pattern. The boundary expression
    prevents a shorter code from matching inside a longer alphanumeric token.
    """

    if not alarm_codes:
        return []
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT requested.code
                FROM unnest(%s::text[]) AS requested(code)
                WHERE EXISTS (
                    SELECT 1
                    FROM manual_chunks
                    WHERE machine_id = %s
                      AND UPPER(content) ~ (
                          '(^|[^A-Z0-9_])' || requested.code || '([^A-Z0-9_]|$)'
                      )
                )
                ORDER BY requested.code
                """,
                (alarm_codes, machine_id),
            )
            rows = await cursor.fetchall()
    return [row[0] for row in rows]

async def get_manual_maintenance_chunks(machine_id: str) -> list[dict[str, Any]]:
    """Return indexed chunks that explicitly state a working-hour interval.

    The caller authorizes the machine. Parsing the documented interval and its
    surrounding text remains in the Manuals Agent, where provenance is retained.
    """

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT chunk_id, source_file, page, section, chunk_index, content
                FROM manual_chunks
                WHERE machine_id = %s
                  AND content ~* (
                      '(every|each)[[:space:]]+[0-9][0-9,[:space:]]*'
                      '[[:space:]]+(working|operating)[[:space:]]+hours'
                  )
                ORDER BY source_file, page, chunk_index
                """,
                (machine_id,),
            )
            rows = await cursor.fetchall()
    return [
        {
            "source": "manual",
            "chunk_id": row[0],
            "file": row[1],
            "page": row[2],
            "section": row[3],
            "chunk_index": row[4],
            "content": row[5],
        }
        for row in rows
    ]

def vector_literal(vector: list[float]) -> str:
    """Format a parameter for pgvector without interpolating SQL."""
    return "[" + ",".join(str(value) for value in vector) + "]"

async def search_manual_chunks(
    machine_id: str,
    query_embedding: list[float],
    limit: int,
) -> list[dict[str, Any]]:
    """Search only one authorised machine's manual using cosine similarity."""
    query_vector = vector_literal(query_embedding)
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT chunk_id, source_file, page, section, content,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM manual_chunks
                WHERE machine_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vector, machine_id, query_vector, limit),
            )
            rows = await cursor.fetchall()
    return [
        {
            "source": "manual",
            "chunk_id": row[0],
            "file": row[1],
            "page": row[2],
            "section": row[3],
            "content": row[4],
            "similarity": float(row[5]),
        }
        for row in rows
    ]

async def manual_file_belongs_to_machine(machine_id: str, source_file: str) -> bool:
    """Check that a PDF was indexed for the requested machine."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM manual_chunks
                    WHERE machine_id = %s AND source_file = %s
                )
                """,
                (machine_id, source_file),
            )
            row = await cursor.fetchone()
    return bool(row[0])

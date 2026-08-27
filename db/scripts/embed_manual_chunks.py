"""Generate local embeddings from manual chunks and store them in pgvector."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row
from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    machine_serial_number: str
    source_file: str
    page: int
    section: str
    chunk_index: int
    content: str


def database_url() -> str:
    if value := os.getenv("DATABASE_URL"):
        return value
    required = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise SystemExit(f"Missing variables: {', '.join(missing)}. Set DATABASE_URL or the POSTGRES_* variables.")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}@{host}:{port}/{os.environ['POSTGRES_DB']}"


def read_chunks(path: Path) -> list[Chunk]:
    if not path.is_file():
        raise SystemExit(f"Chunk file not found: {path}. Run chunk_manuals.py first.")
    required = set(Chunk.__annotations__)
    chunks: list[Chunk] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            raw: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from error
        missing = required - set(raw)
        if missing:
            raise ValueError(f"{path}:{line_number}: missing fields {', '.join(sorted(missing))}")
        chunks.append(Chunk(**{field: raw[field] for field in required}))
    if not chunks:
        raise ValueError(f"No chunks found in {path}")
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        raise ValueError("Chunk IDs must be unique")
    return chunks


def batches(items: list[Chunk], size: int) -> Iterable[list[Chunk]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def vector_literal(vector: Any) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def machine_ids_for_serials(connection: psycopg.Connection, serials: set[str]) -> dict[str, str]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT serial_number, machine_id FROM machines WHERE serial_number = ANY(%s)",
            (list(serials),),
        )
        return {row["serial_number"]: row["machine_id"] for row in cursor.fetchall()}


def store_embeddings(connection: psycopg.Connection, chunks: list[Chunk], model: SentenceTransformer, replace: bool, batch_size: int) -> None:
    serial_to_machine = machine_ids_for_serials(connection, {chunk.machine_serial_number for chunk in chunks})
    missing = sorted({chunk.machine_serial_number for chunk in chunks} - set(serial_to_machine))
    if missing:
        raise ValueError(
            "No matching machines found for manual serial numbers: "
            f"{', '.join(missing)}. Import the Excel dataset before embedding manuals."
        )

    with connection.cursor() as cursor:
        cursor.execute("SELECT EXISTS (SELECT 1 FROM manual_chunks)")
        populated = cursor.fetchone()[0]
        if populated and not replace:
            raise ValueError("manual_chunks already contains data. Run again with --replace to rebuild it.")
        if replace:
            cursor.execute("DELETE FROM manual_chunks")

        insert = """
            INSERT INTO manual_chunks
                (chunk_id, machine_id, source_file, page, section, chunk_index, embedding, content)
            VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)
        """
        for number, batch in enumerate(batches(chunks, batch_size), start=1):
            vectors = model.encode(
                [chunk.content for chunk in batch],
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=True,
            )
            if vectors.shape[1] != EMBEDDING_DIMENSION:
                raise ValueError(
                    f"{MODEL_NAME} returned {vectors.shape[1]} dimensions; expected {EMBEDDING_DIMENSION}."
                )
            cursor.executemany(
                insert,
                [
                    (
                        chunk.chunk_id,
                        serial_to_machine[chunk.machine_serial_number],
                        chunk.source_file,
                        chunk.page,
                        chunk.section,
                        chunk.chunk_index,
                        vector_literal(vector),
                        chunk.content,
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ],
            )
            print(f"Embedded batch {number}: {len(batch)} chunks")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate local all-MiniLM embeddings and store them in pgvector.")
    parser.add_argument("chunks", type=Path, help="JSONL output created by chunk_manuals.py")
    parser.add_argument("--replace", action="store_true", help="Replace existing rows in manual_chunks")
    parser.add_argument("--batch-size", type=int, default=32, help="Chunks encoded per batch (default: 32)")
    args = parser.parse_args()
    if args.batch_size <= 0:
        raise SystemExit("batch-size must be positive")

    chunks = read_chunks(args.chunks)
    print(f"Loading local embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME, cache_folder=os.getenv("HF_HOME"))
    if model.get_embedding_dimension() != EMBEDDING_DIMENSION:
        raise ValueError(f"{MODEL_NAME} does not have the expected {EMBEDDING_DIMENSION} dimensions")

    with psycopg.connect(database_url()) as connection:
        store_embeddings(connection, chunks, model, args.replace, args.batch_size)
    print(f"Stored {len(chunks)} embeddings in manual_chunks.")


if __name__ == "__main__":
    main()

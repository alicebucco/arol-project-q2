"""Synchronise registry capability descriptions into the pgvector catalogue.

The rows describe permitted backend operations, never user requests or evidence.
Run this script after changing the operation registry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384
DEFAULT_BACKEND_ROOT = Path("/app") if Path("/app").is_dir() else Path(__file__).resolve().parents[2] / "backend"
BACKEND_ROOT = Path(os.getenv("BACKEND_ROOT", DEFAULT_BACKEND_ROOT))


@dataclass(frozen=True)
class Capability:
    capability_id: str
    agent: str
    operation: str
    capability_text: str
    parameters_schema: dict[str, Any]
    requires_machine_context: bool
    content_hash: str


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


def vector_literal(vector: Any) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def capability_text(item: dict[str, Any]) -> str:
    """Build one stable semantic document from public registry metadata."""
    parameters = json.dumps(item["parameters_schema"], sort_keys=True, separators=(",", ":"))
    machine_context = "required" if item["requires_machine_context"] else "not required"
    return "\n".join(
        (
            "Allowed evidence operation",
            f"Agent: {item['agent']}",
            f"Operation: {item['operation']}",
            f"Purpose: {item['description']}",
            f"Trusted machine context: {machine_context}",
            f"Accepted parameters schema: {parameters}",
        )
    )


def read_registry_capabilities() -> list[Capability]:
    """Read only the planner-safe catalogue exposed by the backend registry."""
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from core.operation_registry import OPERATION_REGISTRY

    capabilities: list[Capability] = []
    for item in OPERATION_REGISTRY.planner_catalog():
        text = capability_text(item)
        capabilities.append(
            Capability(
                capability_id=f"{item['agent']}.{item['operation']}",
                agent=item["agent"],
                operation=item["operation"],
                capability_text=text,
                parameters_schema=item["parameters_schema"],
                requires_machine_context=item["requires_machine_context"],
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return capabilities


def synchronise(connection: psycopg.Connection, capabilities: list[Capability], model: SentenceTransformer) -> tuple[int, int]:
    """Insert new capabilities and re-embed only changed descriptions."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT capability_id, content_hash FROM operation_capabilities")
        existing = dict(cursor.fetchall())
        changed = [item for item in capabilities if existing.get(item.capability_id) != item.content_hash]
        unchanged = len(capabilities) - len(changed)
        if not changed:
            return 0, unchanged

        vectors = model.encode(
            [item.capability_text for item in changed],
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        if vectors.shape[1] != EMBEDDING_DIMENSION:
            raise ValueError(f"{MODEL_NAME} returned {vectors.shape[1]} dimensions; expected {EMBEDDING_DIMENSION}.")

        cursor.executemany(
            """
            INSERT INTO operation_capabilities (
                capability_id, agent, operation, capability_text, parameters_schema,
                requires_machine_context, content_hash, embedding
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s::vector)
            ON CONFLICT (capability_id) DO UPDATE SET
                agent = EXCLUDED.agent,
                operation = EXCLUDED.operation,
                capability_text = EXCLUDED.capability_text,
                parameters_schema = EXCLUDED.parameters_schema,
                requires_machine_context = EXCLUDED.requires_machine_context,
                content_hash = EXCLUDED.content_hash,
                embedding = EXCLUDED.embedding,
                updated_at = now()
            """,
            [
                (
                    item.capability_id,
                    item.agent,
                    item.operation,
                    item.capability_text,
                    json.dumps(item.parameters_schema),
                    item.requires_machine_context,
                    item.content_hash,
                    vector_literal(vector),
                )
                for item, vector in zip(changed, vectors, strict=True)
            ],
        )
    return len(changed), unchanged


def main() -> None:
    parser = argparse.ArgumentParser(description="Index allowed registry operations for planner capability retrieval.")
    parser.add_argument("--dry-run", action="store_true", help="Show capability IDs without writing or loading embeddings.")
    args = parser.parse_args()

    capabilities = read_registry_capabilities()
    if not capabilities:
        raise ValueError("The operation registry did not expose any planner capabilities.")
    if args.dry_run:
        print("Would index:")
        print("\n".join(f"- {item.capability_id}" for item in capabilities))
        return

    print(f"Loading local embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME, cache_folder=os.getenv("HF_HOME"), local_files_only=True)
    if model.get_embedding_dimension() != EMBEDDING_DIMENSION:
        raise ValueError(f"{MODEL_NAME} does not have the expected {EMBEDDING_DIMENSION} dimensions.")

    with psycopg.connect(database_url()) as connection:
        changed, unchanged = synchronise(connection, capabilities, model)
    print(f"Capability catalogue synchronised: {changed} inserted or updated, {unchanged} unchanged.")


if __name__ == "__main__":
    main()

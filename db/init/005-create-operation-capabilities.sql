-- Semantic capability catalogue used to narrow the operations visible to the
-- orchestration planner. This stores descriptions of allowed operations only:
-- it never contains user questions, tenant data, manuals, or agent evidence.
--
-- Embeddings use the same normalised all-MiniLM-L6-v2 vectors as manual_chunks.

CREATE TABLE operation_capabilities (
    capability_id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    operation TEXT NOT NULL,
    capability_text TEXT NOT NULL CHECK (length(capability_text) > 0),
    parameters_schema JSONB NOT NULL,
    requires_machine_context BOOLEAN NOT NULL,
    content_hash TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent, operation)
);

CREATE INDEX idx_operation_capabilities_embedding_hnsw
    ON operation_capabilities USING hnsw (embedding vector_cosine_ops);

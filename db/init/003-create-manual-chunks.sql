-- RAG storage for restricted manuals kept locally under data/manuals/.
-- all-MiniLM-L6-v2 produces 384-dimensional, normalised embeddings.

CREATE TABLE manual_chunks (
    chunk_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL REFERENCES machines(machine_id) ON DELETE CASCADE,
    source_file TEXT NOT NULL,
    page INTEGER NOT NULL CHECK (page > 0),
    section TEXT NOT NULL,
    chunk_index INTEGER NOT NULL CHECK (chunk_index > 0),
    embedding VECTOR(384) NOT NULL,
    content TEXT NOT NULL CHECK (length(content) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_manual_chunks_machine_id ON manual_chunks(machine_id);
CREATE INDEX idx_manual_chunks_embedding_hnsw
    ON manual_chunks USING hnsw (embedding vector_cosine_ops);

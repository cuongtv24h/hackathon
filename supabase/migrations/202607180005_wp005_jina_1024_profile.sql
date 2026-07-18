-- === TASK:WP-005:START ===
-- Forward-only switch to the canonical Jina 1024-dimensional embedding profile.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM knowledge_chunks WHERE embedding IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Existing embeddings must be re-embedded before switching to Jina vector(1024).';
    END IF;
END $$;

DROP INDEX IF EXISTS knowledge_chunks_embedding_idx;

ALTER TABLE knowledge_chunks
    ALTER COLUMN embedding TYPE vector(1024);

CREATE INDEX knowledge_chunks_embedding_idx
    ON knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- === TASK:WP-005:END ===

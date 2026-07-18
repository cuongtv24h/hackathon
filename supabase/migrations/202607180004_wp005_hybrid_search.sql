-- === TASK:WP-005:START ===
-- Additive migration for WP-005 hybrid search.
-- Upgrades vector dimension to 1536 and adds search_document FTS.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM knowledge_chunks WHERE embedding IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Stored embeddings exist. Forward migration unsafe.';
    END IF;
END $$;

-- Drop the old 768-dimensional index
DROP INDEX IF EXISTS knowledge_chunks_embedding_idx;

-- Alter column dimension to 1536
ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1536);

-- Add generated search_document column using simple search configuration
ALTER TABLE knowledge_chunks ADD COLUMN search_document tsvector GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(content, '') || ' ' || coalesce(sub_topic, '') || ' ' || coalesce(source_id, '') || ' ' || coalesce(source_path, ''))
) STORED;

-- Recreate vector index for 1536-dimensional vectors
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Create non-duplicated GIN index for FTS search_document
CREATE INDEX IF NOT EXISTS knowledge_chunks_search_document_idx ON knowledge_chunks USING gin (search_document);

-- === TASK:WP-005:END ===

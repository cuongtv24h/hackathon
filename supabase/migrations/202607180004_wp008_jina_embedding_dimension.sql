-- === TASK:WP-008:START ===
-- Upgrade the Pilot knowledge vector contract from the pre-Pilot 768-d
-- Gemini shape to Jina jina-embeddings-v5-text-small (1024 dimensions).
-- This migration is intentionally fail-safe: vectors must be re-embedded,
-- never silently truncated, padded, or discarded.

DO $$
DECLARE
    current_type text;
BEGIN
    SELECT format_type(attribute.atttypid, attribute.atttypmod)
      INTO current_type
      FROM pg_attribute AS attribute
      JOIN pg_class AS relation ON relation.oid = attribute.attrelid
      JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
     WHERE namespace.nspname = 'public'
       AND relation.relname = 'knowledge_chunks'
       AND attribute.attname = 'embedding'
       AND NOT attribute.attisdropped;

    IF current_type IS NULL THEN
        RAISE EXCEPTION 'knowledge_chunks.embedding does not exist; apply WP-005 schema migration first';
    END IF;

    IF current_type = 'vector(1024)' THEN
        RETURN;
    END IF;

    IF EXISTS (SELECT 1 FROM public.knowledge_chunks WHERE embedding IS NOT NULL) THEN
        RAISE EXCEPTION 'Cannot change knowledge_chunks.embedding from % to vector(1024) while embeddings exist. Re-embed the existing rows through an approved migration first.', current_type;
    END IF;

    DROP INDEX IF EXISTS public.knowledge_chunks_embedding_idx;
    ALTER TABLE public.knowledge_chunks
        ALTER COLUMN embedding TYPE vector(1024)
        USING embedding::vector(1024);
    CREATE INDEX knowledge_chunks_embedding_idx
        ON public.knowledge_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
END
$$;

-- === TASK:WP-008:END ===

-- === TASK:WP-008:START ===
-- Knowledge seed readiness — idempotent check that the WP-005 schema is ready.
-- WP-005 owns knowledge_chunks_embedding_idx. This file does NOT create a
-- duplicate vector index.
--
-- This seed file verifies that the knowledge_chunks table exists and is
-- ready for the WP-008 ingestion pipeline. Actual data insertion is
-- performed programmatically by apps/api/foundation/knowledge/ingestion/.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_tables WHERE tablename = 'knowledge_chunks'
    ) THEN
        RAISE NOTICE 'knowledge_chunks table is ready for WP-008 ingestion pipeline.';
    ELSE
        RAISE WARNING 'knowledge_chunks table does not exist — run WP-005 migration first.';
    END IF;
END $$;

COMMIT;
-- === TASK:WP-008:END ===
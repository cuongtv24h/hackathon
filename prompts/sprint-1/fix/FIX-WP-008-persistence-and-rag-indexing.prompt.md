---
task_id: FIX-WP-008-PERSISTENCE-AND-RAG-INDEXING
work_package: WP-008
sprint: 1
wave: 1
pool: DATA
priority: P0
branch: fix/WP-008-persistence-and-rag-indexing
input_documents:
  - docs/reference-packs/work-packages/wp-008.pack.md
  - docs/spec-registry/task-to-file-contract-map.yaml
  - docs/artifacts/architecture/integration-data-flow.md
  - docs/artifacts/architecture/deployment-resilience.md
  - docs/artifacts/interface/data-contracts.md
  - supabase/migrations/202607180001_wp005_initial_schema.sql
  - data/mvp/seed/knowledge-base.json
  - data/mvp/seed/source-registry.json
---

# Fix Prompt — WP-008 Persistence and RAG Indexing

## Mission

Fix the rejected WP-008 implementation. The completed result must persist approved, answerable RAG chunks into Supabase, generate/store 1024-dimension embeddings from Jina `jina-embeddings-v5-text-small`, be safely repeatable, and make all seven approved BHYT bootstrap sources answerable at runtime. The current implementation only validates JSON and creates a duplicate vector index; that is insufficient.

## Review Findings That Must Be Fixed

1. `process_chunks(..., dry_run=False)` has no persistence side effect.
2. There is no database writer, no upsert and no actual embedding generation.
3. `knowledge_chunks.chunk_id` is `uuid`, while seed IDs are strings such as `KCH-PRICE-001`; direct insertion will fail.
4. `supabase/seed/202607180003_wp008_knowledge_seed.sql` creates a duplicate ivfflat index. WP-005 already owns the canonical `knowledge_chunks_embedding_idx`.
5. Seven approved BHYT sources are registered but have zero chunks. They must not be deferred: the approved documents under `docs/knowledge/bhyt/` must become answerable chunks.
6. Existing tests are static and do not prove transactional persistence, idempotency, approved-only filtering, deterministic ID mapping or embedding/vector shape.
7. Remove type annotations and `from __future__ import annotations` introduced by the rejected implementation unless a mandatory source contract explicitly requires them.

## INPUT DOCUMENTS — MANDATORY READ

1. `docs/reference-packs/work-packages/wp-008.pack.md`
   - Purpose: binding scope, upstream dependencies and acceptance criteria.
2. `docs/spec-registry/task-to-file-contract-map.yaml`
   - Purpose: allowed write zones for WP-008.
3. `docs/artifacts/architecture/integration-data-flow.md`
   - Purpose: Jina 1024-d pgvector RAG flow and approved-chunk-only constraint.
4. `docs/artifacts/architecture/deployment-resilience.md`
   - Purpose: provider/config/secret and degradation constraints.
5. `docs/artifacts/interface/data-contracts.md`
   - Purpose: `KnowledgeChunkDTO` metadata and public-data restrictions.
6. `supabase/migrations/202607180001_wp005_initial_schema.sql`
   - Purpose: actual persistence schema. Do not alter this migration in this fix.
7. `data/mvp/seed/knowledge-base.json`
   - Purpose: canonical seed order, initial chunks, domain/source metadata.
8. `data/mvp/seed/source-registry.json`
   - Purpose: source approval, ingestibility, path and version cross-reference.
9. `docs/knowledge/`
   - Purpose: approved raw documents, including all seven BHYT bootstrap sources.

## REFERENCE DOCUMENTS — OPTIONAL

1. `docs/region-marker-policy.md`
   - Purpose: directory-zone and marker rules.
2. `tests/integration/test_wp_008_knowledge_ingestion.py`
   - Purpose: retain relevant coverage while replacing inadequate assertions.

## Allowed Output File Contract

Only change these paths:

- `apps/api/foundation/knowledge/ingestion/` — UPDATE existing WP-008 files or create WP-008 leaf files only.
- `supabase/seed/202607180003_wp008_knowledge_seed.sql` — UPDATE or DELETE only if its duplicate-index responsibility is removed from the final design.
- `tests/integration/test_wp_008_knowledge_ingestion.py` — UPDATE.

Do not modify:

- `supabase/migrations/202607180001_wp005_initial_schema.sql`.
- `data/mvp/`, `docs/knowledge/`, interface contracts, work-package maps or RLS policies.
- Any file outside the listed zones.

## Required Implementation Behavior

### 1. Preserve the WP-005 schema

- Keep `knowledge_chunks.chunk_id` as UUID.
- Map every canonical external chunk ID deterministically to UUID using a stable namespace-based UUID strategy. The same external ID must always produce the same UUID.
- Store the original external chunk ID and the SHA-256 content hash in `knowledge_chunks.metadata`; retain `source_id`, `source_path`, `source_version`, approval status, effective date, tags and page/section metadata in their canonical schema fields.
- Upsert by the deterministic UUID so rerunning the same import never creates duplicates and refreshes changed content/metadata/embedding.

### 2. Build all approved answerable input

- Process approved, active and answerable canonical chunks from `knowledge-base.json` in their declared seed order.
- For an approved, ingestible source that has no canonical chunks (including the seven BHYT bootstrap sources), load its registered Markdown file under `docs/knowledge/`, split it deterministically into non-empty chunks, and generate deterministic external chunk IDs from source ID plus ordinal/section.
- Do not index draft, rejected, retired, inactive or non-answerable content as answerable runtime knowledge.
- Missing source file, unknown source ID, empty content, invalid metadata or a non-ingestible source must fail the affected import with a clear error and leave its transaction uncommitted.

### 3. Persist and embed safely

- Add a public ingestion entry point that accepts a database connection string and an embedding provider/callable. It must support a dry-run mode that performs no database write.
- The non-dry-run path must use a transaction. If a chunk, embedding or database operation fails, roll back the whole attempted batch and return/raise actionable failure evidence.
- Generate exactly 1024 numeric embedding values per persisted chunk. Reject an embedding of any other dimension before database write.
- Use Jina `jina-embeddings-v5-text-small` through the configured `EMBEDDING_BASE_URL`, with `task: retrieval.passage`, `dimensions: 1024` and normalized output. Read `DATABASE_URL`, `JINA_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` and `EMBEDDING_BASE_URL` from environment only at execution time. Never log, return or write secrets.
- Tests must use an injected fake embedding provider; they must not call a paid/external API.
- After a successful batch, run `ANALYZE public.knowledge_chunks` to refresh planner statistics for the existing WP-005 vector index. Do not rebuild the ivfflat index per import and do not create a second index.

### 4. Remove duplicate index ownership

- WP-005 owns `knowledge_chunks_embedding_idx`.
- Remove the duplicate `idx_knowledge_chunks_embedding` SQL behavior. If the WP-008 SQL file remains, it may only contain an idempotent, clearly scoped seed-readiness action that does not duplicate WP-005 DDL. Delete it if it has no remaining responsibility.

## Required Test Coverage

Update `tests/integration/test_wp_008_knowledge_ingestion.py` to cover at minimum:

1. Existing 50 canonical chunks are validated and prepared deterministically.
2. The seven approved BHYT source paths produce answerable chunks when their registry chunk count is zero.
3. Identical rerun yields identical UUIDs/content hashes and does not create duplicate persistence records.
4. Persisted record mapping matches WP-005 columns and stores source metadata/content hash in the approved locations.
5. Only approved, active, answerable content is persisted for retrieval.
6. Unknown source, non-ingestible source, missing document, empty content and invalid 1023/1025-d embedding fail safely.
7. A database write failure rolls back the batch.
8. Dry-run performs no write.
9. The final SQL does not create the duplicate `idx_knowledge_chunks_embedding` index.

Use temp directories and fake DB/embedding seams for isolated tests. If a local disposable test database is available, add an opt-in integration test that is skipped unless its test-only connection setting is supplied. Do not use the Pilot database for automated tests.

## Mandatory Runtime Validation

After automated tests pass, run an explicit pilot import only if `DATABASE_URL` and embedding configuration are available in the local environment. Report only counts and IDs/hashes; never print the connection string or provider key.

Required evidence:

```text
py -m pytest tests/integration/test_wp_008_knowledge_ingestion.py -q
```

Then report:

- total source chunks discovered;
- total approved/answerable chunks persisted;
- BHYT source count and BHYT chunks persisted;
- inserted versus updated count on first and repeated run;
- vector dimension validation result;
- transaction rollback test result;
- duplicate vector-index check result.

## Acceptance Criteria

- [ ] No schema migration outside WP-008 scope is changed.
- [ ] Canonical `KCH-*` IDs map deterministically to UUID persistence IDs.
- [ ] Every persisted chunk has traceable source, version, approval, effective-date and content-hash metadata.
- [ ] Approved, active and answerable chunks persist idempotently to Supabase.
- [ ] All seven approved BHYT bootstrap sources become answerable runtime chunks.
- [ ] Embeddings are exactly 1024-dimensional from Jina `jina-embeddings-v5-text-small`; malformed vectors are rejected before write.
- [ ] Duplicate vector index is removed; WP-005 remains the sole index owner.
- [ ] Repeated import does not create duplicate rows.
- [ ] Failed batch rolls back; dry-run performs no write.
- [ ] `py -m pytest tests/integration/test_wp_008_knowledge_ingestion.py -q` passes.
- [ ] BUILD RESULT contains counts, command/result and no secrets.

## Response Format

Do not paste code. Return only:

1. Summary
2. Changed paths
3. Automated test evidence
4. Pilot-import evidence (or explicit blocker)
5. Rollback/idempotency evidence
6. Remaining limitations

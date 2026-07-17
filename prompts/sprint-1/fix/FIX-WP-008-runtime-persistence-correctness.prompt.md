---
task_id: FIX-WP-008-RUNTIME-PERSISTENCE-CORRECTNESS
work_package: WP-008
sprint: 1
wave: 1
pool: DATA
priority: P0
branch: fix/WP-008-runtime-persistence-correctness
input_documents:
  - prompts/sprint-1/fix/FIX-WP-008-persistence-and-rag-indexing.prompt.md
  - docs/reference-packs/work-packages/wp-008.pack.md
  - docs/spec-registry/task-to-file-contract-map.yaml
  - supabase/migrations/202607180001_wp005_initial_schema.sql
  - data/mvp/seed/knowledge-base.json
  - data/mvp/seed/source-registry.json
  - requirements.txt
---

# Fix Prompt — WP-008 Runtime Persistence Correctness

## Mission

Fix the remaining runtime blockers in the rejected WP-008 Fix. The prior result passed static/fake tests but cannot successfully persist to the configured Pilot Supabase database. Do not claim completion until the real persistence happy path has run successfully against the Pilot database using a real 768-d embedding provider.

## Verified Findings — Fix in This Exact Order

### Finding 1 — PostgreSQL driver mismatch (P0)

The project dependency is `psycopg[binary]`; `psycopg2` is not installed. Current non-dry-run import fails before connecting.

Required fix:

- Replace runtime use of `psycopg2` with `psycopg` version 3.
- Do not add `psycopg2` to `requirements.txt`.
- Keep the driver import deferred only when that improves test isolation; a real non-dry-run call must work with the installed `psycopg` dependency.

### Finding 2 — Knowledge domains are never seeded (P0)

`knowledge_domains` is empty in the Pilot database. Current code performs a lookup only, so the first valid chunk fails with unknown domain.

Required fix:

- Before chunk upserts, idempotently upsert the seven canonical domains from `data/mvp/seed/knowledge-base.json` into `knowledge_domains`.
- Use the canonical domain code/name and a deterministic non-empty owner value sourced from the seed/registry metadata. Do not hardcode a new domain outside the seven approved codes.
- Resolve `domain_id` only after domain bootstrap succeeds, inside the same transaction as chunk persistence.
- A failed domain or chunk insert must roll back the entire batch.

### Finding 3 — Frozen result mutation (P0)

`IngestionResult` is declared `@dataclass(frozen=True)` but persistence later assigns `total_chunks`, `inserted`, `updated` and `vector_dim`. A successful write would raise `FrozenInstanceError`.

Required fix:

- Choose one consistent design: either return a new immutable result containing all persistence fields, or use a mutable result object.
- `inserted`, `updated` and `vector_dim` must be defined fields with stable values in every result, including dry-run.
- Do not attach undeclared dynamic attributes.

### Finding 4 — Fake embedding must never persist to Pilot (P0)

Current non-dry-run mode silently defaults to a 768-zero fake vector. This is forbidden for Pilot data.

Required fix:

- Fake embeddings are test-only and must be injected explicitly by tests.
- When `dry_run=False`, require a real embedding provider/callable. If it is absent, fail before opening a write transaction with a clear error.
- Retain the exact 768 numeric-value validation before every database upsert.
- Implement or expose a provider factory that reads `GEMINI_API_KEY` and `EMBEDDING_MODEL` from environment only at execution time, using the already approved installed provider dependency. The factory must never log a key or return it in a result.
- An explicit `database_url`/provider parameter may override environment configuration for tests and controlled operations.

### Finding 5 — Runtime configuration claim is incomplete (P1)

The implementation claims to read environment configuration but currently only accepts function parameters.

Required fix:

- If `database_url` is omitted, resolve it from `DATABASE_URL` at runtime.
- If no embedding provider is passed, resolve a real configured provider through the environment-backed factory; if configuration is incomplete, fail safely with an actionable configuration error.
- Never load `.env` directly in library code and never print environment values.

### Finding 6 — Type-hint policy (P2)

The current code still uses dataclass field annotations such as `chunk_id: str` and `tags: list` after claiming none remain.

Required fix:

- Remove type annotations and future-annotations import from WP-008 ingestion files unless a mandatory canonical contract explicitly requires a particular annotation.
- Preserve public behavior; this is a packet-level coding rule, not a reason to redesign DTOs.

### Finding 7 — Tests do not prove the real persistence happy path (P0)

Existing 78 tests do not execute a successful persistence transaction with the supported driver, seeded domains, result statistics and real upsert behavior.

Required fix:

- Add isolated tests using a fake `psycopg` connection/cursor seam that prove:
  1. the supported `psycopg` path is invoked;
  2. seven domains are upserted before chunk lookup/upsert;
  3. a successful batch returns stable `inserted`, `updated` and `vector_dim=768` fields;
  4. the second run is counted as updates, not inserts;
  5. missing provider in non-dry-run fails before any DB write;
  6. a database exception rolls back and closes the connection;
  7. an invalid embedding causes no chunk upsert;
  8. dry-run creates no connection or write.
- Keep all tests offline: no paid provider/network calls in pytest.
- Add an opt-in Pilot smoke test only if it is skipped by default and runs solely when an explicit test-only environment flag is set. Do not make the normal test suite mutate Pilot data.

## INPUT DOCUMENTS — MANDATORY READ

1. `prompts/sprint-1/fix/FIX-WP-008-persistence-and-rag-indexing.prompt.md`
   - Purpose: first-round acceptance constraints that remain binding.
2. `docs/reference-packs/work-packages/wp-008.pack.md`
   - Purpose: canonical WP-008 scope and approved-only/BHYT requirements.
3. `docs/spec-registry/task-to-file-contract-map.yaml`
   - Purpose: allowed write zones.
4. `supabase/migrations/202607180001_wp005_initial_schema.sql`
   - Purpose: existing schema; do not alter it.
5. `data/mvp/seed/knowledge-base.json`
   - Purpose: canonical seven domains and seed order.
6. `data/mvp/seed/source-registry.json`
   - Purpose: source approval and metadata constraints.
7. `requirements.txt`
   - Purpose: approved runtime dependency is `psycopg[binary]`, not `psycopg2`.

## Allowed Output File Contract

Only modify:

- `apps/api/foundation/knowledge/ingestion/`
- `tests/integration/test_wp_008_knowledge_ingestion.py`
- `supabase/seed/202607180003_wp008_knowledge_seed.sql` only if required to retain the existing no-duplicate-index readiness behavior.

Do not modify:

- `requirements.txt`
- `supabase/migrations/202607180001_wp005_initial_schema.sql`
- `.env`, `data/mvp/`, `docs/knowledge/`, RLS policies, contracts or work-package maps.

## Required Pilot Validation

After unit/integration tests pass, run a controlled Pilot import using the configured environment. This is authorized only after all pre-write validation has succeeded.

Report only non-sensitive evidence:

- database connection success/failure without URL/user/password;
- 7 domain rows present after import;
- inserted and updated counts from run 1 and run 2;
- total persisted answerable chunks;
- persisted BHYT chunk count and distinct BHYT source count (must be 7);
- `embedding` non-null count and dimensionality verification (768);
- duplicate vector-index check;
- no secret values.

The second import must not increase the `knowledge_chunks` row count.

## Acceptance Criteria

- [ ] Non-dry-run persistence uses installed `psycopg`, never `psycopg2`.
- [ ] All seven canonical domains are idempotently available before chunk persistence.
- [ ] Result statistics are declared, stable and do not mutate a frozen object.
- [ ] Non-dry-run rejects missing real embedding provider before any write.
- [ ] Pilot persistence never writes the test-only zero-vector embedding.
- [ ] Existing UUID-v5, approved-only, BHYT and no-duplicate-index behavior remains intact.
- [ ] A supported-driver persistence happy path and rollback path are covered by automated tests.
- [ ] `py -m pytest tests/contract/test_wp_007_seed_registry.py tests/integration/test_wp_008_knowledge_ingestion.py -q` passes.
- [ ] Controlled Pilot run succeeds twice without duplicate rows and reports all required non-sensitive counts.

## Response Format

Do not paste code. Return only:

1. Summary
2. Changed paths
3. Automated test evidence
4. Pilot run 1 and run 2 evidence
5. Rollback/idempotency evidence
6. Remaining limitations

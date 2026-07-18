---
task_id: FIX-WP-008-MVP-CHUNKING-SIMPLIFICATION
work_package: WP-008
sprint: 1
wave: 1
pool: DATA
priority: P0
branch: fix/WP-008-mvp-chunking-simplification
input_documents:
  - docs/reference-packs/work-packages/wp-008.pack.md
  - prompts/sprint-1/task-packets/WP-008.packet.md
  - data/mvp/seed/source-registry.json
  - data/mvp/seed/knowledge-base.json
---

# Fix Prompt — WP-008 MVP Chunking Simplification

## Mission

Replace the current H2-only Markdown splitter with the bounded, document-aware MVP strategy defined in the revised WP-008 pack. Keep the existing source-level approval, deterministic ingestion, 768-d embedding and transactional persistence behavior. Do not expand this fix into a production content-governance or advanced retrieval project.

## Current Failure to Correct

`docs/knowledge/bhyt/faq-bhyt.md` currently produces a single chunk of roughly 814,000 characters because most question-answer pairs live below one H2 heading. This mega-chunk is not safe to embed or retrieve. Price/catalog sections can also combine too many independent service rows into one vector.

## Allowed Output File Contract

Only change:

- `apps/api/foundation/knowledge/ingestion/`
- `tests/integration/test_wp_008_knowledge_ingestion.py`

Do not change source documents, canonical seed/registry data, database migrations, API/tool contracts or downstream retrieval code.

## Required MVP Behavior

1. Detect the document form deterministically from registered source metadata/path/content structure.
2. FAQ: create one question-answer pair per chunk; very short adjacent pairs may be grouped only when question boundaries remain explicit.
3. Price/catalog content: keep one service row or a small coherent group per chunk; never separate service name, condition/unit and value.
4. Prose/process content: split by H2/H3, then paragraph or list boundary when a section remains too large. Repeat the minimal heading context required to understand and cite the chunk.
5. Target 300–600 tokens and enforce a hard maximum of 800 tokens. If the model tokenizer is unavailable, use one documented deterministic fallback counter. Only prose chunks split for size may overlap, with at most 50 tokens.
6. External chunk IDs must be deterministic for identical input. Preserve source/version/section/path, approval, effective date and content hash metadata.
7. Source/version approval is inherited. Do not add manual chunk approval, quarantine states or reviewer workflow.
8. Before persistence, require non-empty content, unique deterministic ID, required citation metadata, bounded size and an embedding containing exactly 768 finite numeric values.
9. Persist both the embedding and the lexical-search document/input required by the WP-005 PostgreSQL FTS schema. Query-time vector/FTS retrieval, RRF and reranking belong to WP-102/WP-201.
10. Preserve dry-run, transaction rollback and idempotent upsert behavior. Use the existing WP-005 vector and FTS indexes; do not create or tune another index.

## Explicitly Out of Scope

- Semantic or LLM-based chunking
- Query-time hybrid search, RRF implementation or reranking (owned by WP-102/WP-201)
- Query rewriting or multi-query retrieval
- LLM-as-judge, quality dashboard or advanced near-duplicate detection
- Distributed embedding cache, batching platform or provider failover
- Content-management UI or multi-step approval workflow

## Required Test Evidence

Update `tests/integration/test_wp_008_knowledge_ingestion.py` to prove:

- The BHYT FAQ no longer produces a mega-chunk and question-answer boundaries are retained.
- Every generated chunk is at most 800 tokens under the selected deterministic counter.
- Price rows retain service name, condition/unit and value together.
- Prose heading context and citation metadata survive recursive splitting.
- Identical input produces identical chunk IDs and content hashes.
- Empty/oversized un-splittable content and non-numeric, non-finite, 767-d or 769-d embeddings fail before persistence.
- Dry-run performs no write; a failed batch rolls back; repeated import creates no duplicate row.

Run:

```text
python -m pytest tests/integration/test_wp_008_knowledge_ingestion.py -q
```

## Acceptance Criteria

- [ ] No output chunk exceeds 800 tokens.
- [ ] FAQ, price/catalog and prose use the required MVP strategies.
- [ ] Source-level approval and existing provenance are preserved without chunk-level workflow.
- [ ] Embeddings are exactly 768 finite numeric values.
- [ ] Persisted chunks populate both vector and lexical-search inputs required for downstream hybrid retrieval.
- [ ] Transaction, dry-run and idempotency behavior remain covered.
- [ ] No advanced retrieval/governance feature is introduced.
- [ ] Required pytest command passes or a concrete environment blocker is reported.

## Response Format

Return only: summary, changed paths, selected token counter/fallback, chunk statistics by source, automated test result and remaining limitations. Do not paste code or secrets.

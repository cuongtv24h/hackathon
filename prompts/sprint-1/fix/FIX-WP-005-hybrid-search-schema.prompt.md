---
task_id: FIX-WP-005-HYBRID-SEARCH-SCHEMA
work_package: WP-005
sprint: 1
wave: 1
pool: DATA
priority: P0
branch: fix/WP-005-hybrid-search-schema
input_documents:
  - docs/reference-packs/work-packages/wp-005.pack.md
  - docs/artifacts/architecture/integration-data-flow.md
  - docs/artifacts/interface/data-contracts.md
  - supabase/migrations/202607180001_wp005_initial_schema.sql
---

# Fix Prompt — WP-005 Hybrid Search Schema

## Mission

Extend the existing WP-005 knowledge schema so the MVP supports PostgreSQL full-text candidates alongside pgvector candidates. Preserve the existing vector(768) cosine index and all current metadata/security contracts.

## Allowed Output File Contract

Only change:

- `supabase/migrations/`
- `docs/data-schema/`
- `tests/contract/test_wp_005_schema.py`

Do not implement query-time fusion/reranking here; WP-102 owns vector/FTS retrieval and RRF, and WP-201 owns reranking.

## Required Behavior

- Add a deterministic maintained/generated lexical search document for `knowledge_chunks.content` and citation-relevant text needed for exact codes, abbreviations, service names and prices.
- Add a PostgreSQL GIN full-text index without removing or duplicating the canonical pgvector cosine index.
- Ensure active/approval/effective/domain filters can be applied consistently to vector and lexical lanes.
- Keep the migration safe on a clean database and safe to apply to the existing development schema according to the repository migration policy.
- Use PostgreSQL/Supabase only; do not add Elasticsearch/OpenSearch.

## Required Tests

- Clean migration contains both vector and GIN/FTS index support.
- Lexical search document is updated when chunk content changes.
- Exact terms, codes and numeric price text remain searchable.
- Existing constraints and vector dimension remain intact.
- No duplicate vector index is introduced.

Run `python -m pytest tests/contract/test_wp_005_schema.py -q` and report the exact result.

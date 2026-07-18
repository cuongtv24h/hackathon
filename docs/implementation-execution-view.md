# Implementation Execution View

## Purpose

Human-readable execution guide for the 40 approved work packages. This is a coordination view, not a new work package and not a product-code task.

## Readiness Gates

1. **G0 Base scaffold:** WP-001 → WP-002 → WP-003. No builder coding starts before WP-003 manual readiness review is approved.
2. **G0R Region scaffold:** WP-004 creates region initialization evidence. Human Lead or Reviewer approves the initialization map before the first builder task in a zone.
3. **G1 Data baseline:** WP-005, WP-006, WP-007, WP-008 and WP-009 establish schema, connection, source registry, seed/RAG index and shared contracts.
4. **G2 Foundation baseline:** WP-101–105.
5. **G3 Tool baseline:** WP-201–204.
6. **G4 AI baseline:** WP-301–306.
7. **G5 Capability API baseline:** WP-401–404.
8. **G6 Experience baseline:** WP-501–506.
9. **G7 Release baseline:** WP-601–606.

## Wave Execution

| Wave | Sprint | Work packages | Parallel groups | Entry condition | Exit condition | Primary blockers |
|---|---|---|---|---|---|---|
| 0 | Sprint 0 | WP-001, WP-002, WP-003, WP-004 | Sequential | Normalized specs available | Base + region verification pass | Missing manifests, directory zones or markers |
| 1 | Sprint 1 | WP-005–009 | A: WP-005/WP-007/WP-009; B: WP-006 after WP-005; C: WP-008 after WP-006+007 | G0/G0R pass | Schema, security, source catalog, seed/RAG index and contracts pass | Supabase mapping; RAG source metadata; secret channel |
| 2 | Sprint 1 | WP-101–105 | Five Foundation lanes after their data prerequisites | Wave 1 pass | Foundation contract checks pass | Seed/index missing; Mock HIS unavailable |
| 3 | Sprint 2 | WP-201–204 | Four tool lanes | Wave 2 dependency for each lane | Tool contract, timeout and fallback tests pass | Foundation API contract failures |
| 4 | Sprint 2 | WP-301–306 | WP-301 then WP-302; PC-01..04 pipelines parallel | All tools pass | Provider/guardrail/AI behavior checks pass | Provider config; emergency safety failures |
| 5 | Sprint 2 | WP-401–404 | Four capability API lanes | Matching AI pipeline + Foundation services pass | Capability API contracts pass | AI contract or session/config failures |
| 6 | Sprint 2 | WP-501–506 | WP-501 then capability/admin feature lanes | Required APIs pass | Two-channel and dashboard integration checks pass | API streaming/auth/error behavior |
| 7 | Sprint 3 | WP-601–606 | WP-601 first; WP-602–605 parallel; WP-606 last | Feature paths pass | Integration, safety, NFR and release evidence pass | Unresolved defects, PII, emergency, RAG provenance |

## Data / Schema / API Readiness

- **Data:** `data/mvp/` and `docs/knowledge/` must be reconciled by WP-007, then imported/indexed by WP-008. Approval is source/version-level for MVP; bootstrap BHYT sources are `approved_for_pilot`, while later sources default to `draft` until Human Lead updates the registry. WP-008 uses document-aware bounded chunking and populates both vector and PostgreSQL FTS inputs; WP-102 performs hybrid retrieval + RRF and WP-201 reranks with RRF fallback. Chunk-level approval and multi-step workflow are not ingestion gates.
- **Schema:** WP-005 migration baseline and WP-006 connectivity/RLS must pass before seed import and Foundation services.
- **API:** Foundation APIs must exist before tool adapters; tools before AI; AI pipelines before Capability APIs; APIs before UI and E2E.
- **Test harness:** Every product/data implementation packet has a pytest companion file. A blocked dependency does not remove the obligation to create the test file and report the blocker.

## Coordination Rules

- Dispatch only a packet whose upstream packets are Stable/Done or have approved integration evidence.
- One builder owns one packet and one branch at a time.
- Reviewer capacity is reserved for every packet; Audit runs at the end of Sprint 0, 1, 2 and 3.
- Use `docs/spec-registry/implementation-execution-view.yaml` for scripts/board lookup.

---
artifact_id: ARCH-08
artifact_name: Integration and Data Flow
source_file: docs/3.architecture-design.md
source_sections:
  - "Artifact 8 — Integration & Data Flow"
category: architecture
consumers: [architect, builder, reviewer, auditor]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Integration and Data Flow

## Summary

Trust boundaries và canonical flows giữa browser, backend, AI providers, Supabase và Mock HIS.

## Canonical Content

### RAG query

User query → Jina `jina-embeddings-v5-text-small` API → 1024-d query vector → pgvector cosine search with domain filter/threshold → ranked approved chunks → KnowledgeContext → grounded response + citations.

### Emergency keyword path

User message → local match → local Level 2 protocol → response <100ms → async/immutable audit. Không external dependency.

### Emergency LLM path

Message + caution flags → LLM → `trigger_emergency` → protocol → response ~2–3s → audit.

### Appointment

Multi-turn collection → canonical appointment object → Appointment Service → Mock HIS Adapter → `appointment_id` + `pending` → confirmation. Patient data only crosses Appointment/HIS boundary.

### Conversation logging

Message/response metadata → `detect_pii` → anonymized record → async Analytics Store. Consistency is eventual; raw PII is prohibited.

### External integrations

- LLM/embedding providers through abstraction layer.
- Supabase for pgvector, appointments and analytics.
- Mock HIS REST service local to VPS.
- Browser over HTTPS/SSE.

## Key Constraints

- Approved chunks only.
- Embedding model is `jina-embeddings-v5-text-small`, with exactly 1024 numeric dimensions. Documents use task `retrieval.passage`; user queries use task `retrieval.query` so both vectors share the retrieval space.
- Provider output and tool content are untrusted until validated.
- PII anonymization failure must not result in raw conversation storage.
- Integration errors degrade to configured channel/hotline.

## Dependencies

- `docs/artifacts/architecture/deployment-resilience.md`
- `docs/artifacts/interface/error-contracts.md`
- `docs/artifacts/interface/tool-contracts.md`

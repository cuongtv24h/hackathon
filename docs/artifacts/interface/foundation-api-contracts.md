---
artifact_id: INT-03
artifact_name: Foundation API Contracts
source_file: docs/4.interface-design.md
source_sections:
  - "Artifact 3 — Foundation API Design"
category: interface
consumers: [builder, reviewer, auditor]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Foundation API Contracts

## Summary

Fast, deterministic APIs. They never call LLM or perform AI reasoning.

## Canonical Content

### Session

- `POST /v1/foundation/sessions` → SessionDTO.
- `GET /v1/foundation/sessions/{session_id}` → SessionContextDTO.
- `PATCH /v1/foundation/sessions/{session_id}/context` → SessionContextDTO.

### Knowledge/content

- `POST /v1/foundation/knowledge:search`: vector + PostgreSQL FTS candidates and RRF fusion; returns at most 20 fused candidates for the WP-201 RAG/tool layer to rerank. Foundation does not call LLM/reranker.
- `GET /v1/foundation/knowledge/chunks/{chunk_id}`.
- Draft lifecycle: create, patch, `:submit`, `:review`, `:publish` under `/v1/foundation/knowledge/drafts`.
- Conflict lifecycle: `GET /v1/foundation/knowledge/conflicts`; `POST /v1/foundation/knowledge/conflicts/{conflict_id}:resolve`.

### Emergency

- `GET /v1/foundation/emergency/protocols/{level}`.
- `GET /v1/foundation/emergency/keyword-set`.
- `POST /v1/foundation/emergency/events`.

### Appointment

- `GET /v1/foundation/specialties`.
- `GET /v1/foundation/doctors`.
- `GET /v1/foundation/doctors/{doctor_id}/available-slots`.
- `POST /v1/foundation/appointments`.
- `GET /v1/foundation/appointments/{appointment_id}`.

### Configuration/operations

- `GET /v1/foundation/configuration/channels`.
- `GET /v1/foundation/configuration/chat`.
- `POST /v1/foundation/feedback`.
- `GET /v1/foundation/conversation-history`.
- `GET /v1/foundation/analytics/summary`.

## Key Constraints

- HIS unavailable → `503 INTEGRATION_UNAVAILABLE`; Capability layer converts to channel redirect.
- Appointment writes require idempotency; publish requires approved state/authorized approver.
- Content conflict notification is dashboard-only with 24-hour due date and audit; no Email/Teams/CRM in MVP.
- Raw patient data stays inside Appointment/HIS boundary.
- Emergency APIs return effective, medically approved versions only.
- Foundation APIs may exist and be tested without AI.

## Dependencies

- `docs/artifacts/interface/data-contracts.md`
- `docs/artifacts/interface/interface-guidelines.md`
- `docs/artifacts/architecture/domain-model.md`

---
artifact_id: INT-06
artifact_name: Tool Contracts
source_file: docs/4.interface-design.md
source_sections:
  - "Artifact 6 — Tool Contract"
category: interface
consumers: [builder, reviewer, auditor]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Tool Contracts

## Summary

Tool I/O, dependency, retry and timeout constraints.

## Canonical Content

| Tool | Input → Output | Errors | Retry | Timeout |
|---|---|---|---|---:|
| `search_knowledge_base` | query/domains/top_k/threshold → hybrid + reranked chunks/sufficient/conflict/search metadata | KNOWLEDGE_UNAVAILABLE, NO_GROUNDED_RESULT, CONTENT_CONFLICT | 1 transient; reranker failure falls back to RRF without retry | 1200ms total; rerank budget 400ms |
| `fallback_response` | query/domain/reason → message/channels | CONFIG_UNAVAILABLE | 1, then cache | 100ms |
| `trigger_emergency` | level/reason/session/evidence → protocol/event | PROTOCOL_UNAVAILABLE, AUDIT_DEFERRED | protocol 0/cache; audit 3 async | 100ms critical; 300ms tool |
| `get_specialty_list` | active filter → specialties | INTEGRATION_UNAVAILABLE | 1 | 500ms |
| `get_doctor_list` | optional specialty → doctors | INVALID_SPECIALTY, INTEGRATION_UNAVAILABLE | 1 transient | 700ms |
| `get_available_slots` | doctor/date range → slots | INVALID_DATE_RANGE, INTEGRATION_UNAVAILABLE | 1 | 800ms |
| `create_appointment_draft` | collected appointment data → draft + public confirmation summary | INVALID_STATE, SLOT_UNAVAILABLE | idempotent draft update | 1000ms |
| `submit_appointment_request` | confirmed draft + idempotency → pending staff-review request | CONFIRMATION_REQUIRED, INVALID_STATE, SLOT_UNAVAILABLE, DUPLICATE_REQUEST, INTEGRATION_UNAVAILABLE | 1 same key | 1500ms |
| `get_patient_appointments` / `get_appointment_request_status` | authenticated patient context + optional reference → authorized result/null | UNAUTHENTICATED, FORBIDDEN, INVALID_REFERENCE, INTEGRATION_UNAVAILABLE | 1 transient | 1000ms |
| `detect_pii` | text → anonymized/categories | PII_PROCESSING_FAILED | 1; then no log | 100ms |
| `log_conversation` | anonymized event → receipt | LOG_DEFERRED, LOG_REJECTED | 3 async | 500ms worker |

## Key Constraints

- Versioned tool name/schema; frontend cannot call tools directly.
- Validate inputs outside LLM and validate/sanitize outputs before reuse.
- Visible tools are the intersection of workflow state, user authorization and system policy; they are not selected by an intent router.
- Authorization and workflow state are rechecked immediately before execution. The model cannot unlock tools or grant itself write permission.
- Read tools may auto-execute. Draft creation is workflow-scoped. Request submission requires resumable patient confirmation and idempotency. Staff confirm/reject operations are never visible to the patient agent.
- `detect_pii` before `log_conversation`; failure is fail-closed for raw message storage.
- Timeout/retry cannot exceed capability SLA.
- Knowledge retrieval runs vector and PostgreSQL FTS candidate searches, fuses them with RRF and reranks the fused set. Metadata filters are identical in both lanes.
- If reranking fails or exceeds its budget, return RRF order with an explicit degraded flag. If one retrieval lane fails, the healthy lane may continue; no failure may bypass approval/effective/active filters.

## Dependencies

- `docs/artifacts/architecture/tool-map.md`
- `docs/artifacts/interface/foundation-api-contracts.md`
- `docs/artifacts/interface/error-contracts.md`

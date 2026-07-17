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
| `search_knowledge_base` | query/domains/top_k/threshold → chunks/sufficient/conflict | KNOWLEDGE_UNAVAILABLE, NO_GROUNDED_RESULT, CONTENT_CONFLICT | 1 transient | 800ms |
| `fallback_response` | query/domain/reason → message/channels | CONFIG_UNAVAILABLE | 1, then cache | 100ms |
| `trigger_emergency` | level/reason/session/evidence → protocol/event | PROTOCOL_UNAVAILABLE, AUDIT_DEFERRED | protocol 0/cache; audit 3 async | 100ms critical; 300ms tool |
| `get_specialty_list` | active filter → specialties | INTEGRATION_UNAVAILABLE | 1 | 500ms |
| `get_doctor_list` | optional specialty → doctors | INVALID_SPECIALTY, INTEGRATION_UNAVAILABLE | 1 transient | 700ms |
| `get_available_slots` | doctor/date range → slots | INVALID_DATE_RANGE, INTEGRATION_UNAVAILABLE | 1 | 800ms |
| `create_appointment` | appointment + confirmation/idempotency → appointment | CONFIRMATION_REQUIRED, SLOT_UNAVAILABLE, DUPLICATE_REQUEST, INTEGRATION_UNAVAILABLE | 1 same key | 1500ms |
| `lookup_appointment` | appointment ID → appointment/null | INVALID_REFERENCE, INTEGRATION_UNAVAILABLE | 1 transient | 1000ms |
| `detect_pii` | text → anonymized/categories | PII_PROCESSING_FAILED | 1; then no log | 100ms |
| `log_conversation` | anonymized event → receipt | LOG_DEFERRED, LOG_REJECTED | 3 async | 500ms worker |

## Key Constraints

- Versioned tool name/schema; frontend cannot call tools directly.
- Validate inputs outside LLM and validate/sanitize outputs before reuse.
- `detect_pii` before `log_conversation`; failure is fail-closed for raw message storage.
- Timeout/retry cannot exceed capability SLA.

## Dependencies

- `docs/artifacts/architecture/tool-map.md`
- `docs/artifacts/interface/foundation-api-contracts.md`
- `docs/artifacts/interface/error-contracts.md`

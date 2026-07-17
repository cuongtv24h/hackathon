---
artifact_id: INT-07
artifact_name: Error Contracts
source_file: docs/4.interface-design.md
source_sections:
  - "Artifact 7 — Error Contract"
category: interface
consumers: [builder, reviewer, auditor]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Error Contracts

## Summary

Unified error envelope, categories, retry and fallback behavior.

## Canonical Content

### Envelope

`trace_id` + `error{code, category, message, field_errors, retryable, retry_after_seconds, fallback}`. Never expose stack trace, prompts, provider secrets, raw tool payload or PII.

| Category | HTTP | Canonical codes |
|---|---:|---|
| Validation | 400 | INVALID_REQUEST, FIELD_REQUIRED, INVALID_ENUM, INVALID_DATE_RANGE, MESSAGE_TOO_LONG |
| Authentication | 401 | AUTHENTICATION_REQUIRED, TOKEN_INVALID |
| Authorization | 403 | ACCESS_DENIED, DOMAIN_APPROVER_REQUIRED |
| Business | 409/422 | CONFIRMATION_REQUIRED, SLOT_UNAVAILABLE, CONTENT_NOT_APPROVED, CONTENT_CONFLICT, INVALID_STATE_TRANSITION |
| Not found | 404 | APPOINTMENT_NOT_FOUND, CONTENT_NOT_FOUND |
| AI | 422/503 | NO_GROUNDED_RESULT, OUT_OF_SCOPE, MEDICAL_ADVICE_REFUSED, AI_PROVIDER_UNAVAILABLE, AI_OUTPUT_REJECTED |
| Tool | 502/504 | TOOL_UNAVAILABLE, TOOL_TIMEOUT, TOOL_OUTPUT_INVALID, INTEGRATION_UNAVAILABLE |
| Safety | 200/warning or 503 | EMERGENCY_PROTOCOL_FALLBACK_USED, EMERGENCY_AUDIT_DEFERRED |
| Rate limit | 429 | RATE_LIMIT_EXCEEDED |
| System | 500/503 | INTERNAL_ERROR, CONFIG_UNAVAILABLE, SERVICE_UNAVAILABLE |

### Retry

- Retry only transient/timeouts/429/5xx marked retryable.
- Read-only: max 1 retry within latency budget.
- Write: same idempotency key only.
- Async logs/audit: max 3; no retry validation/business/not-found/refusal/empty grounding.

### Fallback order

Critical local protocol → LLM provider chain → static channel message; knowledge insufficient/conflict → honest fallback; HIS unavailable → configured booking channels; terminal SSE error ends stream.

## Key Constraints

- Emergency response must not wait for deferred audit.
- Appointment not-found must not reveal existence of other patient data.
- User messages are Vietnamese-friendly; machine code is stable.

## Dependencies

- `docs/artifacts/interface/interface-guidelines.md`
- `docs/artifacts/architecture/deployment-resilience.md`


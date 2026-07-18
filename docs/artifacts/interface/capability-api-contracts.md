---
artifact_id: INT-02
artifact_name: Capability API Contracts
source_file: docs/4.interface-design.md
source_sections:
  - "Artifact 2 — AI Capability API Design"
category: interface
consumers: [builder, reviewer, auditor]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Capability API Contracts

## Summary

Primary frontend-facing APIs. Base path `/v1/capabilities`; execution uses POST because operations carry context/orchestration.

## Canonical Content

| Capability | Endpoint | Request | Response | Outcomes |
|---|---|---|---|---|
| PC-01 | `POST /v1/capabilities/information-assistance:execute` | InformationAssistanceRequest | InformationAssistanceResponse | answered, clarification_required, fallback, refused, emergency_rerouted |
| PC-02 | `POST /v1/capabilities/emergency-safety:execute` | EmergencySafetyRequest | EmergencySafetyResponse | emergency_triggered, clarification_required, not_triggered |
| PC-03 | `POST /v1/capabilities/appointment-booking:execute` | AppointmentBookingRequest | AppointmentBookingResponse | collecting_information, confirmation_required, request_pending_staff_review, cancelled, redirected, unavailable |
| PC-04 | `POST /v1/capabilities/appointment-status:execute` | AppointmentStatusRequest | AppointmentStatusResponse | found, not_found, redirected, unavailable |

### Common response

`trace_id`, `capability`, `outcome`, `result`, `explainability`, `warnings`, `errors`, `timestamp`.

### Streaming

`response_mode=stream` uses SSE events: `ack`, `status`, `content_delta`, `tool_status`, `citation`, `action`, `completed`, `error`.

Agent-backed execution may also emit `confirmation_required` with an opaque thread/run reference and public summary. `POST /v1/capabilities/{capability}:resume` accepts that reference plus approve/edit/reject, verifies thread ownership, and resumes the checkpointed LangGraph run. Clients never submit authoritative tool names or hidden arguments.

## Key Constraints

- Request carries `request_id` and session where applicable.
- PC-02 critical path may complete in Gateway but must satisfy the same response DTO.
- PC-03 request submission requires explicit confirmation token and idempotency key; only staff can confirm an appointment.
- PC-04 lookup uses minimal approved reference.
- Frontend never orchestrates tools/Foundation APIs directly.
- Capability APIs apply a profile to the shared LangGraph runtime; they do not implement intent routers or independent orchestration engines.

## Dependencies

- `docs/artifacts/interface/data-contracts.md`
- `docs/artifacts/interface/error-contracts.md`
- `docs/artifacts/interface/interaction-sequences.md`

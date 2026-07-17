---
pack_id: PACK-PC-04
pack_type: capability
capability: Appointment Status
artifact_dependencies: [ARCH-02, ARCH-04, ARCH-08, INT-02, INT-03, INT-04, INT-05, INT-06, INT-07, INT-08, INT-09]
target_audience: [builder, reviewer]
---

# Capability Pack — Appointment Status

## 1. Capability Purpose

Tra cứu lịch bằng định danh tối thiểu và trả trạng thái cùng next step an toàn. Phục vụ JTBD-03 và hỗ trợ JTBD-08.

## 2. Required Domain Concepts

- Appointment references Doctor/Schedule.
- Canonical status: pending, confirmed, cancelled, rejected, completed.
- Conversation stores only context needed for the session; appointment PII remains in Appointment/HIS boundary.

## 3. Required Contracts

### API

`POST /v1/capabilities/appointment-status:execute`

### DTOs

- `AppointmentStatusRequest`: request_id, session_id, appointment_reference.
- `AppointmentStatusResponse`: found/not_found/redirected/unavailable, appointment summary, next_steps.
- `AppointmentDTO`, `SuggestedActionDTO`.

### Tools

- `lookup_appointment(appointment_id)` → appointment/null; timeout 1000ms, max one transient retry.
- `search_knowledge_base` for grounded preparation guidance.
- `fallback_response` for unavailable integration.

### Foundation APIs

`GET /v1/foundation/appointments/{appointment_id}`, Knowledge Search and Channel Configuration.

## 4. Business Flow Summary

Collect/validate appointment code → lookup → map found status to next step. Not found asks user to recheck/contact hotline without exposing data. Unavailable integration returns configured lookup/contact channels.

## 5. AI Behavior Requirements

Must:

- Use the canonical status returned by tool.
- Provide status-specific next step.
- Ground preparation guidance through Knowledge Search.
- Minimize returned patient fields.

Must not:

- Guess status or transform unavailable into not-found.
- Request additional PII unless an approved HIS policy requires it.
- Reveal whether another patient's appointment exists.
- Persist lookup PII in raw analytics.

## 6. Key Constraints

- Appointment ID follows provider contract; IDs are opaque to consumers.
- Not-found is non-retryable; transient integration errors may retry once.
- Real-HIS owner verification is INCOMPLETE; current source supports Mock HIS lookup.

## 7. Artifact Source References

- `docs/artifacts/architecture/domain-model.md`
- `docs/artifacts/architecture/business-sequences.md`
- `docs/artifacts/architecture/integration-data-flow.md`
- `docs/artifacts/interface/capability-api-contracts.md`
- `docs/artifacts/interface/foundation-api-contracts.md`
- `docs/artifacts/interface/data-contracts.md`
- `docs/artifacts/interface/ai-behavior-contracts.md`
- `docs/artifacts/interface/tool-contracts.md`
- `docs/artifacts/interface/error-contracts.md`
- `docs/artifacts/interface/interaction-sequences.md`
- `docs/artifacts/interface/interface-guidelines.md`

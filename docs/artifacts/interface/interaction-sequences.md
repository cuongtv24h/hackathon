---
artifact_id: INT-08
artifact_name: Interaction Sequences
source_file: docs/4.interface-design.md
source_sections:
  - "Artifact 8 — Sequence Contract"
category: interface
consumers: [builder, reviewer, auditor]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Interaction Sequences

## Summary

Execution ordering across frontend, capability, AI, tools, Foundation APIs and external systems.

## Canonical Content

### PC-01

Frontend → Information API → pre-filter → guardrail → Orchestrator → Knowledge tool/Foundation/vector system → validated observation → grounded synthesis or fallback → SSE/complete response → citations/actions.

### PC-02

- Critical: Frontend → Emergency API/Gateway → local pre-filter → cached Level 2 protocol → response → async audit.
- Caution: flags → Orchestrator → `trigger_emergency` → effective protocol → event → response.
- Normal: route to appropriate capability.

### PC-03

Booking API/Orchestrator loops through specialty/doctor/slot/patient fields using tools/Foundation/HIS. It returns `confirmation_required`; after explicit confirmation, `create_appointment` returns `pending`. Unavailable integration returns redirect, never false success.

### PC-04

Appointment ID → Status API → Orchestrator → lookup tool/Foundation/HIS → found/not-found/unavailable → safe next steps.

### Content lifecycle

Content Admin draft/update/submit → Domain Owner approve/request changes → approved publish activates new version/deactivates old → immutable audit.

## Key Constraints

- Every user message is safety-checked first.
- Tool execution is hidden behind Capability layer.
- Write confirmation and idempotency are mandatory.
- Patient data and anonymized analytics follow separate trust boundaries.

## Dependencies

- `docs/artifacts/architecture/business-sequences.md`
- `docs/artifacts/interface/capability-api-contracts.md`
- `docs/artifacts/interface/tool-contracts.md`


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

Frontend → Information API → emergency gate → shared LangGraph agent with authorized visible tools → model-selected knowledge tool → execution policy → Foundation/vector system → validated observation → grounded synthesis or fallback → citation verification → SSE/complete response.

### PC-02

- Critical: Frontend → Emergency API/Gateway → local pre-filter → cached Level 2 protocol → response → async audit.
- Caution/uncertain: flags → restricted safety profile → approved emergency/contact tools only → effective protocol/event → response.
- Normal: shared agent receives the capability profile and authorized tool subset; no intent router is required.

### PC-03

Booking API/shared LangGraph agent loops through read tools, creates a draft, then interrupts with `confirmation_required`. Patient approval resumes the graph and `submit_appointment_request` creates `pending_staff_review`. Only authorized staff can confirm/reject. Unavailable integration returns redirect, never false success.

### PC-04

Authenticated patient context + minimal reference → Status API → shared agent → authorized status tool/Foundation/HIS → found/not-found/unavailable → safe next steps without cross-patient disclosure.

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

---
artifact_id: INT-01
artifact_name: Capability Model
source_file: docs/4.interface-design.md
source_sections:
  - "Artifact 0 — Capability Traceability Matrix"
  - "Artifact 1 — Capability Model"
category: interface
consumers: [architect, builder, reviewer, auditor, lead]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Capability Model

## Summary

Bốn capability sản phẩm, JTBD mapping và primary API ownership.

## Canonical Content

| ID | Capability | JTBD | AI capabilities | Primary API |
|---|---|---|---|---|
| PC-01 | Grounded hospital information assistance | JTBD-01,04,05,06,08; hỗ trợ 02/03 | CAP-1,2,5,6; CAP-4 khi có action | `POST /v1/capabilities/information-assistance:execute` |
| PC-02 | Emergency safety | JTBD-07 | CAP-3 + non-AI pre-filter | `POST /v1/capabilities/emergency-safety:execute` |
| PC-03 | Appointment booking assistance | JTBD-02; hỗ trợ 01/08 | CAP-1,4,5; CAP-2 cho information | `POST /v1/capabilities/appointment-booking:execute` |
| PC-04 | Appointment status assistance | JTBD-03; hỗ trợ 08 | CAP-1,4; CAP-2 cho guidance | `POST /v1/capabilities/appointment-status:execute` |

### Success criteria

- PC-01: 7 domains, important answers cited, correct fallback, multi-turn, TTFT ≤2s/full ≤5s.
- PC-02: recall ≥99%, critical path target <100ms and requirement ≤1s, no treatment advice, all triggers audited.
- PC-03: no create before confirmation; new status pending; redirect on unavailable integration.
- PC-04: canonical status handling, minimal identity, no data leakage, clear fallback.

## Key Constraints

- Product capability, not resource or individual CAP, is the API unit.
- Content/analytics workflows are Foundation functions, not fake AI capabilities.
- All capability APIs share safety, PII, audit and grounding constraints.

## Dependencies

- `docs/artifacts/interface/capability-api-contracts.md`
- `docs/artifacts/interface/foundation-api-contracts.md`
- `docs/artifacts/architecture/ai-capability-mapping.md`


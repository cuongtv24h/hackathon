---
pack_id: PACK-PC-02
pack_type: capability
capability: Emergency Safety
artifact_dependencies: [ARCH-01, ARCH-02, ARCH-03, ARCH-04, ARCH-05, ARCH-09, INT-02, INT-03, INT-04, INT-05, INT-06, INT-07, INT-08]
target_audience: [builder, reviewer]
---

# Capability Pack — Emergency Safety

## 1. Capability Purpose

Phát hiện dấu hiệu nguy hiểm và trả protocol đã phê duyệt, không chẩn đoán. Phục vụ JTBD-07 và là safety constraint cho mọi request.

## 2. Required Domain Concepts

- EmergencyKeywordSet: critical/caution phrases, approval, effective date, version.
- EmergencyProtocol: Level 1/2 template, hotlines, address, approval/effective date.
- EmergencyEvent: session/message, keyword|llm_tool path, evidence, level, latency, time.
- EmergencyContext persists for the session and does not auto-reset after trigger.

## 3. Required Contracts

### API

`POST /v1/capabilities/emergency-safety:execute`

### DTOs

- `EmergencySafetyRequest/Response`.
- `PreFilterResultDTO`: critical|caution|normal, evidence, elapsed_ms.
- `EmergencyKeywordSetDTO`, `EmergencyProtocolDTO`.
- `EmergencyEventCreateRequest/ReceiptDTO`.

### Tool/direct path

- Critical: Gateway Protocol Loader direct; no LLM/tool dependency.
- Caution/indirect: `trigger_emergency(level, reason, session_id, evidence)`.
- `detect_pii` then async `log_conversation`; emergency audit is separate.

### Foundation APIs

Effective protocol, effective keyword set, emergency event creation.

## 4. Business Flow Summary

Every message → local pre-filter. Critical Level 2 → bypass LLM → cached approved protocol → immediate banner/hotline/address → audit. Caution → flags to LLM → conservative evaluation → optional Level 1/2 tool call. Normal → route to intended capability.

## 5. AI Behavior Requirements

Must:

- Treat safety as higher priority than surface appointment/information intent.
- Use protocol text; include emergency channel/address; log detection path/evidence.
- Err on caution for ambiguous dangerous combinations.

Must not:

- Diagnose or grade disease severity.
- Recommend medication/treatment.
- Delay critical response for LLM, database or audit.
- Invent hotline, address or protocol.

## 6. Key Constraints

- Emergency recall target ≥99%.
- Critical keyword path architecture target <100ms; mandatory requirement ≤1s.
- LLM caution path target ≤3s.
- Critical must work without internet/LLM/Supabase.
- Keyword/protocol updates require medical approval and controlled local config deployment.

## 7. Artifact Source References

- `docs/artifacts/architecture/solution-constraints.md`
- `docs/artifacts/architecture/domain-model.md`
- `docs/artifacts/architecture/component-architecture.md`
- `docs/artifacts/architecture/business-sequences.md`
- `docs/artifacts/architecture/ai-capability-mapping.md`
- `docs/artifacts/architecture/deployment-resilience.md`
- `docs/artifacts/interface/capability-api-contracts.md`
- `docs/artifacts/interface/foundation-api-contracts.md`
- `docs/artifacts/interface/data-contracts.md`
- `docs/artifacts/interface/ai-behavior-contracts.md`
- `docs/artifacts/interface/tool-contracts.md`
- `docs/artifacts/interface/error-contracts.md`
- `docs/artifacts/interface/interaction-sequences.md`

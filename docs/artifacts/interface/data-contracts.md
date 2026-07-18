---
artifact_id: INT-04
artifact_name: Data Contracts
source_file: docs/4.interface-design.md
source_sections:
  - "Artifact 4 — Data Contract"
category: interface
consumers: [builder, reviewer, auditor]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Data Contracts

## Summary

Canonical DTO inventory, ownership and validation-critical fields.

## Canonical Content

### Capability DTOs

- `InformationAssistanceRequest`: request_id, session_id, message(1..4000), response_mode, client_context, optional button_context.
- `InformationAssistanceResponse`: outcome, message, citations, suggested_actions, conversation_state, explainability.
- `EmergencySafetyRequest`: request/session/message, prefilter result, matched evidence.
- `EmergencySafetyResponse`: outcome, optional level/path, protocol content, hotline/address/banner, event_id; no medical assessment.
- `AppointmentBookingRequest/Response`: message/selection, flow_state, confirmation; outcome, prompt/options, optional appointment.
- `AppointmentStatusRequest/Response`: appointment reference; found/not-found/redirected/unavailable and minimal summary.
- `ClientContextDTO`, `ButtonContextDTO`, `CapabilityResponseEnvelope`, `CitationDTO`, `SuggestedActionDTO`, `ExplainabilityDTO`.

### Session/context DTOs

- `SessionCreateRequest`, `SessionDTO`, `SessionContextDTO`, `SessionContextPatchRequest`.
- `MessageDTO`: role, content, intent, tools, citations, emergency metadata, time.
- `BookingFlowStateDTO`: flow_id, step, selected IDs, collected/missing fields, version.
- `EmergencyContextDTO`: triggered, level/path/time/banner; Level 2 does not auto-reset.

### Knowledge/content DTOs

- `KnowledgeSearchRequest`: query, domain_filter, top_k 1..20(default 5), threshold 0..1; hybrid retrieval is server-default and not caller-selectable in MVP.
- `KnowledgeSearchResponse`: chunks, result/sufficient/conflict flags, plus search metadata containing strategy, candidate counts, degraded lanes and per-result vector/lexical/fusion/rerank scores or ranks. Internal raw vectors are never exposed.
- `KnowledgeChunkDTO`: content, domain/subtopic/source/version/active + effective/approval metadata; embedding not public.
- `ContentDraftCreateRequest`, `ContentDraftPatchRequest`, `ContentDraftDTO`.
- `ContentSubmitRequest`, `ContentReviewRequest`, `ContentApprovalStateDTO`, `ContentPublishRequest`, `ContentVersionDTO`.
- `ContentConflictDTO`: source chunks, conflicting fields, 24-hour due date, open/investigating/resolved/dismissed state and resolution audit.
- `ContentConflictPageDTO`, `ContentConflictResolveRequest`.

### Emergency DTOs

- `PreFilterResultDTO`: critical|caution|normal, optional Level 2, evidence, elapsed_ms.
- `EmergencyKeywordSetDTO`: critical/caution lists, approval/effective/version.
- `EmergencyProtocolDTO`: level, template, hotlines, address, approval/effective/version.
- `EmergencyEventCreateRequest`, `EmergencyEventReceiptDTO`.

### Appointment DTOs

- `SpecialtyDTO/PageDTO`, `DoctorDTO/PageDTO`, `AvailableSlotDTO/PageDTO`.
- `PatientAppointmentDataDTO`: name, phone, dob, insurance, reason, first_visit|follow_up.
- `AppointmentCreateRequest`: doctor, slot, patient data, confirmation token.
- `AppointmentDTO`: appointment ID, doctor/schedule summary, scoped patient data, canonical status/timestamps/rejection reason.

### Configuration/analytics DTOs

- `ChannelConfigurationDTO`, `ChatConfigurationDTO`.
- `FeedbackCreateRequest`, `FeedbackReceiptDTO`.
- `ConversationHistoryPageDTO`, `AnalyticsSummaryDTO`, `PageMetadataDTO`.

## Key Constraints

- Required unless explicitly optional; ISO 8601 timestamps; `YYYY-MM-DD` dates; opaque IDs.
- JSON fields use canonical interface names; persistence models are not public DTOs.
- PII belongs to Appointment boundary and is forbidden in raw analytics logs.
- Citation requires official source metadata and must not reference drafts.
- Explainability excludes chain-of-thought.

## Dependencies

- `docs/artifacts/architecture/domain-model.md`
- `docs/artifacts/interface/capability-api-contracts.md`
- `docs/artifacts/interface/foundation-api-contracts.md`

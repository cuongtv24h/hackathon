# Phase 4.5 — Normalization Plan

## A1. Source Analysis Summary

### `docs/3.architecture-design.md`

- 11 artifacts, 4 subsections deployment, 6 context types, 10 ADRs, final review và self-review.
- Execution-critical: Domain Model; Component Architecture; Business Sequence; Business→AI Mapping & AI Sequence; Tool Map; Context Design; Integration & Data Flow; Deployment View; các quyết định ADR-001..010 ảnh hưởng runtime.
- Context/narrative không tách riêng: phần lý giải dài trong Solution Summary, review lặp lại và self-review. Các constraint thực thi trong các phần này được nhập vào artifact tương ứng.

### `docs/4.interface-design.md`

- 11 artifacts, 4 capability APIs, 25 Foundation APIs, 7 nhóm DTO, AI behavior contract, 10 tools, unified errors, 5 sequences, 13 nhóm guidelines và 12 IDRs.
- Execution-critical: Capability Model/Traceability; Capability APIs; Foundation APIs; Data Contract; AI Contract; Tool Contract; Error Contract; Sequence Contract; Interface Guidelines.
- Context/narrative không tách riêng: Interface Decision Record và Self Review. Quyết định có ảnh hưởng execution được đưa vào Key Constraints của artifact liên quan; missing contracts được ghi Assumptions/INCOMPLETE.

## A2. Artifact Split Plan

| ID | Artifact | Source | Sections | Category | Target path |
|---|---|---|---|---|---|
| ARCH-01 | Solution Constraints | `docs/3.architecture-design.md` | Artifact 0; Artifact 1; ADR-001..010 | architecture | `docs/artifacts/architecture/solution-constraints.md` |
| ARCH-02 | Domain Model | `docs/3.architecture-design.md` | Artifact 2 | architecture | `docs/artifacts/architecture/domain-model.md` |
| ARCH-03 | Component Architecture | `docs/3.architecture-design.md` | Artifact 3 | architecture | `docs/artifacts/architecture/component-architecture.md` |
| ARCH-04 | Business Sequences | `docs/3.architecture-design.md` | Artifact 4 | architecture | `docs/artifacts/architecture/business-sequences.md` |
| ARCH-05 | AI Capability Mapping | `docs/3.architecture-design.md` | Artifact 5 | architecture | `docs/artifacts/architecture/ai-capability-mapping.md` |
| ARCH-06 | Architecture Tool Map | `docs/3.architecture-design.md` | Artifact 6 | architecture | `docs/artifacts/architecture/tool-map.md` |
| ARCH-07 | Context Design | `docs/3.architecture-design.md` | Artifact 7 | architecture | `docs/artifacts/architecture/context-design.md` |
| ARCH-08 | Integration and Data Flow | `docs/3.architecture-design.md` | Artifact 8 | architecture | `docs/artifacts/architecture/integration-data-flow.md` |
| ARCH-09 | Deployment and Resilience | `docs/3.architecture-design.md` | Artifact 9; ADR-008 | architecture | `docs/artifacts/architecture/deployment-resilience.md` |
| INT-01 | Capability Model | `docs/4.interface-design.md` | Artifact 0; Artifact 1 | interface | `docs/artifacts/interface/capability-model.md` |
| INT-02 | Capability API Contracts | `docs/4.interface-design.md` | Artifact 2 | interface | `docs/artifacts/interface/capability-api-contracts.md` |
| INT-03 | Foundation API Contracts | `docs/4.interface-design.md` | Artifact 3 | interface | `docs/artifacts/interface/foundation-api-contracts.md` |
| INT-04 | Data Contracts | `docs/4.interface-design.md` | Artifact 4 | interface | `docs/artifacts/interface/data-contracts.md` |
| INT-05 | AI Behavior Contracts | `docs/4.interface-design.md` | Artifact 5 | interface | `docs/artifacts/interface/ai-behavior-contracts.md` |
| INT-06 | Tool Contracts | `docs/4.interface-design.md` | Artifact 6 | interface | `docs/artifacts/interface/tool-contracts.md` |
| INT-07 | Error Contracts | `docs/4.interface-design.md` | Artifact 7 | interface | `docs/artifacts/interface/error-contracts.md` |
| INT-08 | Interaction Sequences | `docs/4.interface-design.md` | Artifact 8 | interface | `docs/artifacts/interface/interaction-sequences.md` |
| INT-09 | Interface Guidelines | `docs/4.interface-design.md` | Artifact 9; IDR-001..012 | interface | `docs/artifacts/interface/interface-guidelines.md` |

## A3. Capability Identification

| Capability | Related artifacts | Tools | Primary contracts |
|---|---|---|---|
| PC-01 Information Assistance | ARCH-02,03,04,05,06,07,08; INT-01..09 | `search_knowledge_base`, `fallback_response`, `detect_pii`, `log_conversation` | InformationAssistanceRequest/Response, CitationDTO, ExplainabilityDTO |
| PC-02 Emergency Safety | ARCH-02,03,04,05,06,07,08,09; INT-01..09 | `trigger_emergency`, `detect_pii`, `log_conversation`; critical path dùng Protocol Loader | EmergencySafetyRequest/Response, EmergencyProtocolDTO, EmergencyEvent DTOs |
| PC-03 Appointment Booking | ARCH-02..08; INT-01..09 | `get_specialty_list`, `get_doctor_list`, `get_available_slots`, `create_appointment`, `fallback_response` | AppointmentBookingRequest/Response, BookingFlowStateDTO, AppointmentCreateRequest/DTO |
| PC-04 Appointment Status | ARCH-02..08; INT-01..09 | `lookup_appointment`, `search_knowledge_base`, `fallback_response` | AppointmentStatusRequest/Response, AppointmentDTO |

## A4. Contract Identification

### API contracts

- Capability: Information Assistance, Emergency Safety, Appointment Booking, Appointment Status.
- Foundation: Session (3), Knowledge/Content (7), Emergency (3), Appointment (5), Configuration (2), Feedback (1), Conversation History (1), Analytics (1).

### DTO contract groups

- Capability: InformationAssistance, EmergencySafety, AppointmentBooking, AppointmentStatus, ClientContext, ButtonContext, CapabilityResponseEnvelope, Citation, SuggestedAction, Explainability.
- Session/context: SessionCreateRequest, SessionDTO, SessionContextDTO/Patch, MessageDTO, BookingFlowStateDTO, EmergencyContextDTO.
- Knowledge/content: KnowledgeSearch Request/Response, KnowledgeChunk, Content Draft/Create/Patch/Submit/Review/Approval/Publish/Version.
- Emergency: PreFilterResult, EmergencyKeywordSet, EmergencyProtocol, EmergencyEventCreate/Receipt.
- Appointment: Specialty/Page, Doctor/Page, AvailableSlot/Page, PatientAppointmentData, AppointmentCreateRequest, AppointmentDTO.
- Configuration/analytics: ChannelConfiguration, ChatConfiguration, Feedback Create/Receipt, ConversationHistoryPage, AnalyticsSummary, PageMetadata.

### Tool contracts

`search_knowledge_base`, `fallback_response`, `trigger_emergency`, `get_specialty_list`, `get_doctor_list`, `get_available_slots`, `create_appointment`, `lookup_appointment`, `detect_pii`, `log_conversation`.

### Error and AI behavior contracts

- Error categories: validation, authentication, authorization, business, not-found, AI, tool, safety, rate-limit, system.
- AI behavior: Input, Output, ReasoningResult, PlanningResult, ObservationResult, ConversationResult, ExplainabilityResult, grounding/fallback.

## Assumptions and incomplete items

- Source of truth chỉ gồm hai file đã liệt kê; Requirement/Product docs không được đưa trực tiếp vào packs.
- Không có MCP server; kiến trúc dùng LLM tools. `tool-map.yaml` vẫn được sinh vì project là tool-based architecture.
- Component source ownership đã được chốt tại `docs/3.architecture-design.md`, Section 3.5 và được registry hóa.
- Mock HIS contract, MVP retention/rate-limit, canonical 7 domain codes, Level 1 contact handoff và dashboard-only content conflict đã được chốt tại `docs/4.interface-design.md`, Section 9.13.
- Production HIS identity/consent, production retention/rate-limit và production contact/emergency values vẫn được defer có chủ đích.

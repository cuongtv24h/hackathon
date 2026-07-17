---
pack_id: PACK-PC-03
pack_type: capability
capability: Appointment Booking
artifact_dependencies: [ARCH-02, ARCH-04, ARCH-05, ARCH-08, INT-02, INT-03, INT-04, INT-05, INT-06, INT-07, INT-08, INT-09]
target_audience: [builder, reviewer]
---

# Capability Pack — Appointment Booking

## 1. Capability Purpose

Thu thập dữ liệu đặt lịch theo nhiều lượt, cho người dùng xác nhận và tạo appointment `pending` qua Mock HIS/provider-neutral adapter. Phục vụ JTBD-02, hỗ trợ JTBD-01/08.

## 2. Required Domain Concepts

- Doctor belongs to department/specialty and has schedules.
- Schedule has available/booked status and at most one appointment.
- Appointment references doctor/schedule and contains patient booking data with canonical statuses.
- BookingFlowState holds flow step, selected IDs, collected/missing fields and version.

## 3. Required Contracts

### API

`POST /v1/capabilities/appointment-booking:execute`

### DTOs

- `AppointmentBookingRequest/Response`.
- `BookingFlowStateDTO`.
- `SpecialtyDTO`, `DoctorDTO`, `AvailableSlotDTO` and page contracts.
- `PatientAppointmentDataDTO`.
- `AppointmentCreateRequest`, `AppointmentDTO`.

### Tools

- `get_specialty_list` 500ms.
- `get_doctor_list` 700ms.
- `get_available_slots` 800ms.
- `create_appointment` 1500ms, same idempotency key for allowed retry.
- `fallback_response` for unavailable integration.

### Foundation APIs

Specialty, doctor, available-slot and appointment create APIs; session state and channel configuration.

## 4. Business Flow Summary

Visit type → specialty → doctor → slot → patient data → complete confirmation snapshot → explicit user confirmation → create pending appointment → return appointment code and lookup instruction. Any cancel ends flow. HIS unavailable returns approved redirect.

## 5. AI Behavior Requirements

Must:

- Validate each collected field and preserve session flow state.
- Ask only the next missing field.
- Use tool data for specialty/doctor/slot options.
- Display all consequential fields before confirmation.
- Use grounding for preparation information.

Must not:

- Select doctor based on medical diagnosis.
- Invent slot/doctor/appointment success.
- Create before confirmation.
- Copy booking PII to analytics logs.

## 6. Key Constraints

- New appointment status is `pending`.
- `Idempotency-Key` + valid confirmation token/snapshot required.
- Slot conflict → `SLOT_UNAVAILABLE`; re-query slots.
- Mock HIS is behind adapter; Capability/API contracts remain provider-neutral.
- Real HIS identity/auth details are INCOMPLETE and not assumed.

## 7. Artifact Source References

- `docs/artifacts/architecture/domain-model.md`
- `docs/artifacts/architecture/business-sequences.md`
- `docs/artifacts/architecture/ai-capability-mapping.md`
- `docs/artifacts/architecture/integration-data-flow.md`
- `docs/artifacts/interface/capability-api-contracts.md`
- `docs/artifacts/interface/foundation-api-contracts.md`
- `docs/artifacts/interface/data-contracts.md`
- `docs/artifacts/interface/ai-behavior-contracts.md`
- `docs/artifacts/interface/tool-contracts.md`
- `docs/artifacts/interface/error-contracts.md`
- `docs/artifacts/interface/interaction-sequences.md`
- `docs/artifacts/interface/interface-guidelines.md`

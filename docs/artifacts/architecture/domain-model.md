---
artifact_id: ARCH-02
artifact_name: Domain Model
source_file: docs/3.architecture-design.md
source_sections:
  - "Artifact 2 — Domain Model"
category: architecture
consumers: [architect, builder, reviewer, auditor]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Domain Model

## Summary

Canonical domain objects, relationships và ownership.

## Canonical Content

### Knowledge

- `KnowledgeChunk`: chunk_id, content, domain, sub_topic, source, version, is_active, embedding, metadata(tags, effective_date, page_numbers).
- `KnowledgeDomain`: domain_id, domain_name, domain_code, owner, last_reviewed.
- `ContentVersion`: version_id, chunk_id, content_before/content_after, changed_by, approved_by, changed_at.

### Emergency

- `EmergencyKeywordSet`: keyword_set_id, keywords, caution_keywords, approved_by, effective_date, version.
- `EmergencyProtocol`: protocol_id, level(1|2), response_template, hotline_numbers, emergency_address, approved_by, effective_date.
- `EmergencyEvent`: event_id, session_id, message_id, detection_path(keyword|llm_tool), matched_evidence, level, response_time_ms, triggered_at.

### Appointment

- `Doctor`: doctor_id, full_name, title, specialty, department, is_active.
- `Schedule`: schedule_id, doctor_id, date, time_slot, status(available|booked).
- `Appointment`: appointment_id, doctor_id, schedule_id, patient_name, patient_phone, patient_dob, has_insurance, visit_reason, visit_type, status(pending|confirmed|cancelled|completed|rejected), timestamps.

### Conversation

- `ConversationSession`: session_id, started_at, last_activity, channel(web_widget|web_page), metadata.
- `Message`: message_id, session_id, role, content, intent, tools_called, citations, emergency_triggered, detection_path, created_at.

### Relationships

- ConversationSession 1:N Message.
- Message 0:1 EmergencyEvent; N:M KnowledgeChunk; 0:N Appointment.
- Doctor 1:N Schedule; Schedule 1:0..1 Appointment.
- EmergencyKeywordSet/EmergencyProtocol 1:N EmergencyEvent.

### Ownership

| Domain | Owner | Approver |
|---|---|---|
| Knowledge | Phòng CSKH | Domain owners theo chủ đề |
| Emergency Keyword/Protocol | Hội đồng Y đức | Bác sĩ Khoa Cấp cứu |
| Appointment | Phòng Khám bệnh | IT + CSKH |
| Conversation/Analytics | IT | Product Manager |

## Key Constraints

- Chỉ knowledge content active/approved được dùng.
- Patient data thuộc Appointment boundary; log hội thoại phải ẩn danh.
- Emergency content bắt buộc phê duyệt y tế.

## Dependencies

- `docs/artifacts/interface/data-contracts.md`
- `docs/artifacts/architecture/context-design.md`


---
artifact_id: ARCH-04
artifact_name: Business Sequences
source_file: docs/3.architecture-design.md
source_sections:
  - "Artifact 4 — Business Sequence"
category: architecture
consumers: [architect, builder, reviewer]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Business Sequences

## Summary

Năm business flows canonical, rút gọn cho execution.

## Canonical Content

### Information lookup

1. Người dùng gửi câu hỏi.
2. Kiểm tra dấu hiệu nguy hiểm; có thì chuyển Emergency.
3. Tra nguồn chính thức.
4. Đủ nguồn: trả thông tin + citation; nếu cần, thêm action.
5. Thiếu nguồn: thừa nhận giới hạn + kênh phù hợp.

### Emergency

- Critical: phản hồi ngay, gọi 115/đến Khoa Cấp cứu, hiển thị hotline/address, không tư vấn/đánh giá bệnh, ghi event.
- Possible concern: cảnh báo + thông tin cấp cứu; vẫn có thể hỗ trợ thêm.

### Appointment booking

1. Thu thập visit type → specialty → doctor → slot → patient data.
2. Hiển thị toàn bộ dữ liệu để người dùng xác nhận.
3. Chỉ sau xác nhận mới tạo appointment `pending`.
4. Trả mã `HEN-YYYY-NNNN` và hướng dẫn lookup.

### Appointment lookup

- Input tối thiểu: appointment code.
- Output theo status: pending, confirmed, cancelled, rejected, completed hoặc not-found; mọi nhánh có next step.

### Knowledge update

Draft → Domain Owner review → approve/publish/deactivate old hoặc request changes. Giá cập nhật trong 24h; lịch bác sĩ trước 07:00 ngày áp dụng; BHYT phải được Phòng BHYT xác nhận; content có expiry/review; conflict fallback và resolve trong 24h.

## Key Constraints

- Safety check trước business flow thông thường.
- Không tự quyết định nguồn nào đúng khi conflict.
- Không tạo appointment trước explicit confirmation.
- Content publish cần approval đúng domain.

## Dependencies

- `docs/artifacts/interface/interaction-sequences.md`
- `docs/artifacts/interface/ai-behavior-contracts.md`


# MVP Pilot Data Pack

Bộ dữ liệu canonical phục vụ lập kế hoạch và triển khai MVP Pilot của Trợ lý Thông tin Bệnh viện AI.

## Nguyên tắc

- Đây là dữ liệu giả lập, trừ hai tài liệu Knowledge Base được chủ dự án xác nhận dùng cho pilot.
- Không chứa secret hoặc Supabase connection string.
- Không phải SQL dump và chưa phụ thuộc database schema. Sau khi migration được chốt, importer sẽ ánh xạ các entity trong JSON sang bảng Supabase.
- Hotline, địa chỉ, URL và emergency content đang là mock; phải thay trước pilot với người dùng thật.
- Emergency keyword/protocol chỉ dùng để phát triển và demo; không được coi là nội dung y tế đã phê duyệt.
- Dữ liệu bệnh nhân trong Mock HIS là hư cấu.

## Cấu trúc

| File | Nội dung |
|---|---|
| `manifest.json` | Phiên bản pack, nguồn dữ liệu, giả định và policy pilot |
| `seed/hospital-configuration.json` | Cấu hình bệnh viện, kênh, disclaimer, quick prompts, retention |
| `seed/mock-his.json` | Chuyên khoa, bác sĩ, slot và lịch hẹn giả lập |
| `seed/emergency.json` | Keyword rules, protocol Level 1/2 và negative contexts |
| `seed/knowledge-base.json` | Registry hai nguồn thật và mock content cho các domain còn thiếu |
| `seed/admin-dashboard.json` | Tài khoản full quyền, content workflow và conflict demo |
| `seed/analytics.json` | Conversation/event/feedback aggregate giả lập |
| `tests/mvp-test-cases.json` | Test case capability, safety, booking, lookup, content và analytics |

## Chính sách retention mặc định cho pilot

Các giá trị sau là giả định kỹ thuật bảo thủ, cần được bệnh viện/pháp chế xác nhận trước production:

| Dữ liệu | Retention |
|---|---:|
| Context hội thoại trong bộ nhớ | 30 phút không hoạt động, tối đa 24 giờ |
| Hội thoại đã ẩn danh | 90 ngày |
| Feedback | 180 ngày |
| Appointment mock | 90 ngày sau lần cập nhật cuối |
| Emergency event | 365 ngày |
| Security/content audit | 365 ngày, người dùng thường không được xóa |
| Analytics tổng hợp không PII | 365 ngày |

Retention nghĩa là hệ thống giữ dữ liệu trong bao lâu trước khi tự xóa, archive hoặc anonymize. Nó ảnh hưởng trực tiếp tới dung lượng, quyền riêng tư, khả năng điều tra sự cố và báo cáo lịch sử.

## Khi nào cần Supabase connection?

Chưa cần để tạo hoặc review data pack. Chỉ cần connection sau khi có:

1. Migration/schema được duyệt.
2. Mapping canonical entity → table/column.
3. Importer có dry-run và idempotency.
4. Môi trường đích được xác nhận là development/staging.
5. Backup hoặc phương án reset seed.

Không lưu connection string trong repository. Importer phải nhận secret từ environment/secret manager.


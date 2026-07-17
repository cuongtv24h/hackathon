# Task Prompt — Hoàn thiện MVP Pilot Seed Data và Test Fixtures

## Vai trò

Bạn là **Senior Test Data Architect / AI Safety Dataset Engineer**.

Nhiệm vụ của bạn là hoàn thiện bộ dữ liệu seed còn thiếu cho MVP Pilot của Trợ lý Thông tin Bệnh viện AI. Đây là công việc tạo dữ liệu và test fixtures, không phải triển khai sản phẩm.

## Mục tiêu

Tạo đủ năm file còn thiếu:

1. `data/mvp/seed/emergency.json`
2. `data/mvp/seed/knowledge-base.json`
3. `data/mvp/seed/admin-dashboard.json`
4. `data/mvp/seed/analytics.json`
5. `data/mvp/tests/mvp-test-cases.json`

Sau khi hoàn thành, toàn bộ data pack phải:

- Parse được bằng JSON parser chuẩn.
- Có ID duy nhất và liên kết tham chiếu hợp lệ.
- Bao phủ các capability PC-01 đến PC-04, Content Management và Analytics.
- Không chứa secret hoặc dữ liệu bệnh nhân thật.
- Không cần Supabase connection.
- Sẵn sàng để mapping sang database schema ở phase sau.

---

# 1. Input Documents — Mandatory Read

Đọc đúng các file sau trước khi tạo dữ liệu.

## Data pack hiện tại

1. `data/mvp/README.md`
   - Mục đích: quy tắc, cấu trúc và retention của data pack.

2. `data/mvp/manifest.json`
   - Mục đích: phạm vi MVP, canonical domains, source registry và seed order.

3. `data/mvp/seed/hospital-configuration.json`
   - Mục đích: channel IDs, disclaimer, quick prompts, retention và rate limits.

4. `data/mvp/seed/mock-his.json`
   - Mục đích: departments, specialties, doctors, slots, appointments và business rules đã có.

## Normalized architecture/interface references

5. `docs/artifacts/architecture/domain-model.md`
   - Mục đích: domain objects, relationships và ownership.

6. `docs/artifacts/architecture/business-sequences.md`
   - Mục đích: lookup, emergency, booking, appointment lookup và content lifecycle.

7. `docs/artifacts/architecture/ai-capability-mapping.md`
   - Mục đích: thứ tự AI capabilities và expected outcomes.

8. `docs/artifacts/architecture/tool-map.md`
   - Mục đích: tên tools và I/O canonical.

9. `docs/artifacts/interface/data-contracts.md`
   - Mục đích: DTO names, fields và validation.

10. `docs/artifacts/interface/ai-behavior-contracts.md`
    - Mục đích: grounding, fallback, refusal và explainability rules.

11. `docs/artifacts/interface/tool-contracts.md`
    - Mục đích: tool errors, retry và timeout.

12. `docs/artifacts/interface/error-contracts.md`
    - Mục đích: canonical error codes.

13. `docs/artifacts/interface/interface-guidelines.md`
    - Mục đích: 7 canonical domains và các giá trị MVP đã chốt.

14. `docs/reference-packs/document-reference-policy.md`
    - Mục đích: quy tắc đọc và traceability.

## Approved pilot knowledge sources

15. `docs/Bang_gia_dich_vu_ky_thuat.md`
    - Domain: `gia_dich_vu`.
    - Trạng thái: approved for pilot.
    - Không suy diễn phần chữ bị cắt hoặc STT bị thiếu.

16. `docs/quy-trinh-don-tiep-benh-nhan_chuan-hoa-doi-chieu-nguon.md`
    - Domain: `quy_trinh`.
    - Trạng thái: approved for pilot.
    - Theo quyết định MVP, áp dụng chung cho bệnh viện vì chỉ có một cơ sở trong pilot.

## Reading scope

Chỉ đọc các phần cần thiết cho năm file đầu ra. Không mở rộng sang thiết kế không liên quan.

---

# 2. Existing Decisions — Do Not Change

- Release: `mvp_pilot`.
- Clients: Chat Widget và Standalone Chat Page.
- Appointment integration: database-backed Mock HIS API.
- Appointment mới: `pending`.
- Appointment lookup: chỉ bằng `appointment_id`, không OTP.
- Live-agent: Level 1 contact handoff; không ticket, queue hoặc real-time takeover.
- Content conflict: dashboard-only, SLA 24 giờ.
- ASR/TTS: ngoài scope.
- Deployment: VPS.
- Một demo admin account được gán tất cả role MVP; không tạo role mới `superadmin`.
- BHYT chưa có nguồn chính thức: luôn fallback, không tạo nội dung factual.

## Canonical Knowledge Domains

Chỉ dùng đúng bảy domain codes:

```text
dat_lich
quy_trinh
bhyt
gia_dich_vu
gio_lam_viec
bac_si_khoa
thong_tin_benh_vien
```

Quy tắc:

- `sau_kham` là subtopic của `quy_trinh`.
- `thuat_ngu` là subtopic/tag, không phải domain.
- `emergency` thuộc safety domain riêng, không phải Knowledge Q&A domain.

---

# 3. Global Data Rules

1. Chỉ tạo/sửa năm target files. Không thay đổi source docs, normalized artifacts, registries hoặc hai seed files hiện có.
2. Không tạo SQL, migration, application code, database schema hoặc importer.
3. Không yêu cầu hoặc ghi Supabase URL, API key, service key, password hay connection string.
4. Tất cả JSON phải dùng UTF-8, JSON chuẩn, không comment và không trailing comma.
5. Timestamp dùng ISO 8601 với offset `+07:00`; date dùng `YYYY-MM-DD`.
6. ID phải ổn định, duy nhất, dễ lookup và không dựa vào database-generated ID.
7. Mọi dữ liệu mock phải có `is_mock: true` hoặc metadata tương đương.
8. Không sử dụng tên/số điện thoại bệnh nhân thật. Số điện thoại giả dùng dải `09000000xx`.
9. Không ghi raw PII vào analytics hoặc conversation logs.
10. Không tạo embeddings; chỉ tạo canonical content/metadata. Embedding được thực hiện khi import.
11. Không tự tạo kiến thức BHYT.
12. Không biến ví dụ emergency thành nội dung production-approved.
13. Không hardcode URL/hotline mới; tham chiếu channel IDs từ `hospital-configuration.json`.
14. Tất cả cross-reference phải trỏ tới ID tồn tại.

---

# 4. Target A — `emergency.json`

## 4.1 Mục đích

Cung cấp mock keyword rules, Level 1/2 protocols, negative contexts và safety fixtures cho Keyword Pre-filter và `trigger_emergency`.

## 4.2 Root structure

```json
{
  "dataset": {},
  "keyword_sets": [],
  "protocols": [],
  "negative_context_patterns": [],
  "safety_examples": []
}
```

## 4.3 Dataset metadata

Bắt buộc có:

- `dataset_id`: `EMERGENCY-MOCK-MVP-01`
- `version`: `1.0.0`
- `is_mock`: `true`
- `clinical_approval_status`: `not_clinically_approved`
- `usage`: `development_and_demo_only`
- `effective_date`
- `review_due_date`
- Cảnh báo rõ không dùng production.

## 4.4 Keyword rules

Tạo tối thiểu:

- 10 critical Level 2 rules.
- 8 caution Level 1 rules.
- Bao phủ nhóm tim mạch cấp, hô hấp cấp, mất ý thức và dấu hiệu đột quỵ được architecture minh họa.
- Mỗi rule có ít nhất một biến thể không dấu.

Mỗi rule:

```json
{
  "rule_id": "EMG-CRIT-001",
  "level": 2,
  "category": "cardiovascular",
  "phrases": [],
  "normalized_phrases": [],
  "required_context": [],
  "excluded_context": [],
  "combination_with": [],
  "protocol_id": "ERP-L2-MOCK-V1",
  "is_mock": true
}
```

Không thêm lời khuyên điều trị vào keyword rule.

## 4.5 Protocols

Tạo đúng hai protocol:

- `ERP-L1-MOCK-V1`
- `ERP-L2-MOCK-V1`

Fields:

- protocol_id, level, version.
- response_text.
- channel_refs, dùng `CH-EMERGENCY-115` và `CH-HOTLINE-EMERGENCY`.
- emergency_address_ref hoặc giá trị mock được ghi rõ.
- banner_level.
- allowed_actions.
- prohibited_content: diagnosis, severity_assessment, medication_advice, treatment_advice.
- approval_status: `mock_not_clinically_approved`.
- is_mock.

Level 2 phải ngắn, rõ, yêu cầu hành động ngay và không hỏi thêm. Level 1 chỉ cảnh báo/hỏi làm rõ an toàn, không kết luận bệnh.

## 4.6 Negative contexts

Tạo tối thiểu 10 patterns/examples:

- Hỏi kiến thức chung.
- Sự kiện xảy ra trong quá khứ.
- Trích dẫn tài liệu.
- Phủ định triệu chứng.
- Câu hỏi về người không ở trong tình trạng hiện tại.

Negative contexts không được làm suppression nếu message đồng thời có dấu hiệu critical hiện tại rõ ràng.

## 4.7 Safety examples

Tối thiểu 24 examples:

- 8 critical direct.
- 6 caution.
- 5 indirect/combination cần LLM path.
- 5 negative/no-trigger.

Fields: example_id, input, expected_prefilter_result, expected_level, expected_detection_path, expected_protocol_id, must_not_contain.

---

# 5. Target B — `knowledge-base.json`

## 5.1 Mục đích

Tạo source registry và canonical KnowledgeChunk seed cho 7 domains. Dữ liệu factual từ bảng giá/quy trình phải trace được về tài liệu thật; domain khác dùng mock rõ ràng; BHYT chỉ có fallback metadata.

## 5.2 Root structure

```json
{
  "dataset": {},
  "domains": [],
  "sources": [],
  "chunks": [],
  "fallback_policies": []
}
```

## 5.3 Domains

Tạo đúng bảy records tương ứng canonical codes. Mỗi record có:

- domain_id, domain_code, domain_name.
- owner_role.
- review_cycle_days.
- data_status: approved_for_pilot | mock | deferred.

`bhyt.data_status` phải là `deferred`.

## 5.4 Sources

Đăng ký tối thiểu:

- `SRC-PRICE-001`: path đến bảng giá, approved_for_pilot.
- `SRC-PROCESS-001`: path đến quy trình, approved_for_pilot.
- Một mock source cho mỗi domain mock.
- `SRC-BHYT-DEFERRED`: không có content, dùng để giải thích fallback.

Source fields:

- source_id, title, source_type, path hoặc config reference.
- domain_code.
- version, approval_status, effective_date, last_reviewed.
- is_mock.
- limitations.

## 5.5 Chunks

Tạo tối thiểu 50 chunks:

| Domain | Minimum |
|---|---:|
| `gia_dich_vu` | 15 |
| `quy_trinh` | 12 |
| `dat_lich` | 6 |
| `gio_lam_viec` | 4 |
| `bac_si_khoa` | 6 |
| `thong_tin_benh_vien` | 4 |
| `bhyt` | 0 factual chunks |
| Thuật ngữ dưới dạng subtopics của các domain phù hợp | 3 |

Mỗi chunk:

```json
{
  "chunk_id": "KCH-PRICE-001",
  "content": "...",
  "domain": "gia_dich_vu",
  "sub_topic": "...",
  "source_id": "SRC-PRICE-001",
  "source_section": "...",
  "source_page": "...",
  "version": "1.0",
  "is_active": true,
  "approval_status": "approved_for_pilot",
  "effective_date": "...",
  "tags": [],
  "is_mock": false,
  "answerable": true
}
```

### Giá dịch vụ

- Chỉ lấy giá xuất hiện rõ trong source.
- Giữ đúng tên, mã và giá.
- Citation phải chỉ được page/section thật.
- Đoạn bị cắt/thiếu phải `answerable: false` hoặc không tạo chunk.
- Không tự suy diễn ngày hiệu lực nếu source không có; ghi limitation.

### Quy trình

- Chỉ lấy bước có trong source.
- Giữ document code `QT.25.01`, ngày ban hành và revision.
- Theo quyết định MVP, metadata applicability là toàn bệnh viện pilot.

### Bác sĩ/khoa

- Tham chiếu doctor/specialty IDs có thật trong `mock-his.json`.
- Không viết claim chuyên môn ngoài mock fields đã có.
- Không gợi ý bác sĩ dựa trên chẩn đoán.

### BHYT

- Không tạo factual chunks.
- Tạo fallback policy dùng `CH-HOTLINE-CSKH` hoặc `CH-COUNTER`.
- Expected reason: `NO_APPROVED_SOURCE`.

## 5.6 Fallback policies

Tối thiểu:

- BHYT chưa có nguồn.
- Không tìm thấy giá/dịch vụ.
- Content conflict.
- Mock content cần xác nhận.

Mỗi policy có reason, message template, channel_refs và prohibited behavior.

---

# 6. Target C — `admin-dashboard.json`

## 6.1 Mục đích

Seed dashboard Content Management + Analytics navigation, demo identity, content workflow, conflict workflow và audit examples.

## 6.2 Root structure

```json
{
  "dataset": {},
  "demo_users": [],
  "dashboard_modules": [],
  "content_drafts": [],
  "approval_events": [],
  "content_versions": [],
  "content_conflicts": [],
  "audit_events": []
}
```

## 6.3 Demo user

Tạo đúng một user:

- user_id: `USR-DEMO-ADMIN-001`.
- display_name rõ là tài khoản demo.
- Không password, token hoặc secret.
- `pilot_demo_only: true`.
- `production_allowed: false`.
- Gán đồng thời roles:
  - content_admin
  - domain_owner
  - emergency_approver
  - operations_analyst
  - security_auditor

Không tạo role `superadmin`.

## 6.4 Dashboard modules

Tạo module/navigation metadata cho:

- Content Drafts.
- Review & Approval.
- Published Versions.
- Expiring Content.
- Content Conflicts.
- Analytics Summary.
- Emergency Events.
- Audit Log.

## 6.5 Content workflow fixtures

Tạo tối thiểu:

- 2 draft.
- 2 submitted.
- 1 changes_requested.
- 2 approved.
- 2 published.

Mọi draft/version phải tham chiếu domain/source/chunk hợp lệ trong `knowledge-base.json` khi thích hợp.

## 6.6 Content conflicts

Tạo tối thiểu 4 records:

- open, chưa quá hạn.
- open, overdue.
- investigating.
- resolved.

Fields theo contract:

- conflict_id.
- domain_code.
- source_chunk_ids, tối thiểu 2 IDs hợp lệ.
- conflicting_fields.
- detected_at.
- due_at = detected_at + 24 giờ.
- status.
- assigned_owner.
- resolution/winning_version_id/resolved_by/resolved_at khi resolved.

Không tạo Email/Teams/CRM notification data.

## 6.7 Audit events

Tạo audit cho create, submit, review, publish và resolve conflict. Không chứa secret/PII.

---

# 7. Target D — `analytics.json`

## 7.1 Mục đích

Cung cấp dữ liệu đã ẩn danh để dashboard hiển thị top questions, fallback, emergency, feedback và tool/provider health.

## 7.2 Root structure

```json
{
  "dataset": {},
  "sessions": [],
  "interaction_events": [],
  "feedback_events": [],
  "emergency_events": [],
  "tool_events": [],
  "daily_summaries": [],
  "dashboard_summary": {}
}
```

## 7.3 Required scenarios

Tạo tối thiểu 30 anonymized sessions/events bao phủ:

- Grounded answer có citations.
- Multi-domain answer.
- BHYT fallback.
- Content conflict fallback.
- Medical advice refusal.
- Emergency critical keyword path.
- Emergency caution/LLM path.
- Booking collecting information.
- Booking pending success.
- Booking slot unavailable.
- Appointment lookup cho năm statuses.
- Appointment not found.
- Tool timeout/integration unavailable.
- Provider fallback.
- Helpful và not_helpful feedback.

## 7.4 Privacy

- Không lưu raw name, phone, DOB, insurance number hoặc appointment patient data.
- Message text phải tổng quát hóa hoặc đã redact.
- Nếu cần minh họa PII detection, chỉ lưu `[REDACTED_PHONE]`, `[REDACTED_NAME]`.

## 7.5 Aggregates

`daily_summaries` và `dashboard_summary` phải được tính nhất quán từ events trong file, gồm:

- total_sessions.
- total_messages/interactions.
- grounded_answer_count/rate.
- fallback_count/rate.
- emergency_count/rate.
- helpful_count, not_helpful_count, feedback_score.
- tool_error_count.
- top_questions hoặc top_intents.

Không ghi aggregate tùy ý không khớp raw events.

---

# 8. Target E — `mvp-test-cases.json`

## 8.1 Mục đích

Declarative acceptance/contract test fixtures, không phải test code.

## 8.2 Root structure

```json
{
  "suite": {},
  "test_cases": []
}
```

## 8.3 Common test schema

Mỗi case:

```json
{
  "test_case_id": "TC-PC01-001",
  "category": "capability",
  "capability": "PC-01",
  "priority": "P0",
  "preconditions": [],
  "input": {},
  "expected": {
    "outcome": "...",
    "intent_labels": [],
    "tool_calls": [],
    "error_code": null,
    "citation_source_ids": [],
    "action_refs": [],
    "must_contain": [],
    "must_not_contain": []
  },
  "seed_references": [],
  "acceptance_criteria": []
}
```

## 8.4 Minimum coverage

Tạo ít nhất 60 cases:

| Area | Minimum |
|---|---:|
| PC-01 Information Assistance | 16 |
| PC-02 Emergency Safety | 16 |
| PC-03 Appointment Booking | 10 |
| PC-04 Appointment Status | 8 |
| Content Management/Conflict | 6 |
| Analytics/Privacy | 4 |

## 8.5 Required PC-01 cases

- Giá có citation.
- Quy trình có citation.
- Tiếng Việt không dấu.
- Viết tắt/sai chính tả.
- Multi-domain.
- Minimal clarification.
- BHYT fallback.
- Unknown information fallback.
- Content conflict fallback.
- Medical advice refusal.
- No chain-of-thought.
- SuggestedAction uses channel ref.
- Source inactive/not-approved không được dùng.
- Prompt injection không bypass grounding.
- PII được redact trước logging.
- SSE terminal error behavior.

## 8.6 Required PC-02 cases

- Direct critical, including no-diacritic variant.
- Critical bypasses LLM.
- Caution adds flags.
- Indirect combination calls `trigger_emergency`.
- Negative/historical/general-info contexts.
- No medication/treatment advice.
- Protocol unavailable uses local fallback behavior.
- Audit deferred does not delay response.
- Response time expectations: critical ≤100ms target/≤1s requirement; caution ≤3s.

## 8.7 Required PC-03 cases

- Complete multi-turn flow.
- Missing fields asked one-by-one.
- Invalid phone/date.
- Explicit confirmation required.
- Confirmation token mismatch.
- Idempotent duplicate create.
- Slot unavailable.
- Integration unavailable → redirect.
- Success returns `pending` and valid code.
- No booking PII in analytics.

## 8.8 Required PC-04 cases

- pending, confirmed, cancelled, rejected, completed.
- not_found.
- invalid reference.
- integration unavailable.
- Returned patient fields minimized.

## 8.9 Content/analytics cases

- Draft state transitions.
- Wrong state/approver rejected.
- Publish requires approval/idempotency.
- Conflict overdue and resolve workflow.
- Dashboard aggregates match events.
- Raw PII absent.

## 8.10 Cross-reference rule

Mọi `seed_references`, chunk/source/rule/protocol/doctor/slot/appointment/conflict IDs phải tồn tại trong seed files tương ứng.

---

# 9. Validation Requirements

Agent phải chạy validation sau khi tạo file.

## 9.1 JSON parsing

PowerShell:

```powershell
Get-ChildItem -LiteralPath 'data/mvp' -Recurse -Filter '*.json' |
  ForEach-Object {
    Get-Content -LiteralPath $_.FullName -Encoding utf8 -Raw |
      ConvertFrom-Json | Out-Null
  }
```

## 9.2 Required file existence

Xác nhận đủ năm target files.

## 9.3 Uniqueness

Kiểm tra không trùng:

- source_id.
- chunk_id.
- rule_id.
- protocol_id.
- user_id.
- draft_id/version_id/conflict_id.
- session/event/feedback IDs.
- test_case_id.

## 9.4 Referential integrity

Kiểm tra tối thiểu:

- Emergency rule → protocol tồn tại.
- Knowledge chunk → source/domain tồn tại.
- Doctor/specialty references → `mock-his.json` tồn tại.
- Conflict → chunk/version tồn tại.
- Analytics seed references tồn tại.
- Test case seed references tồn tại.
- Channel refs tồn tại trong `hospital-configuration.json`.

## 9.5 Domain validation

- Chỉ đúng 7 domain codes.
- Không có factual BHYT chunks.
- Không xuất hiện domain `sau_kham`, `thuat_ngu` hoặc `emergency` trong KnowledgeDomain list.

## 9.6 Safety/privacy validation

- Emergency dataset có cảnh báo mock/not clinically approved.
- Không protocol nào chứa medication/treatment recommendation.
- Analytics không chứa raw phone/name/DOB.
- Không file nào chứa Supabase secret hoặc connection string.

## 9.7 Coverage summary

In ra counts:

- Emergency critical/caution/negative/examples.
- Sources/chunks theo domain.
- Admin users/drafts/versions/conflicts/audits.
- Analytics sessions/events/feedback/emergency/tool events.
- Test cases theo capability/category/priority.

Nếu validation lỗi, phải sửa trước khi kết thúc.

---

# 10. Prohibited Actions

Không được:

- Chèn dữ liệu vào Supabase.
- Yêu cầu Supabase connection.
- Tạo hoặc chạy SQL/migration.
- Viết backend/frontend code.
- Thay đổi Architecture hoặc Interface Design.
- Thay đổi canonical domain list.
- Tạo kiến thức BHYT.
- Đánh dấu emergency mock data là medically approved.
- Dùng dữ liệu cá nhân thật.
- Xóa hoặc rewrite hai seed files hiện có.

---

# 11. Definition of Done

Task hoàn thành khi:

- [ ] Đủ năm target files.
- [ ] Tất cả JSON parse thành công.
- [ ] `knowledge-base.json` có ít nhất 50 chunks và đúng 7 domains.
- [ ] BHYT có 0 factual chunks và có fallback policy.
- [ ] `emergency.json` đủ rule/protocol/negative/example coverage.
- [ ] `admin-dashboard.json` bao phủ content lifecycle và 4 conflict states.
- [ ] `analytics.json` có ít nhất 30 anonymized sessions/events và aggregate nhất quán.
- [ ] `mvp-test-cases.json` có ít nhất 60 cases và đủ minimum coverage.
- [ ] Tất cả IDs unique.
- [ ] Tất cả references hợp lệ.
- [ ] Không có raw PII hoặc secret.
- [ ] Không có thay đổi ngoài năm target files.

---

# 12. Final Response Format

```text
MVP Seed Data Completion

Created Files
- path — record counts

Validation
- JSON parsing: PASS/FAIL
- Unique IDs: PASS/FAIL
- Referential integrity: PASS/FAIL
- Canonical domains: PASS/FAIL
- BHYT factual chunks = 0: PASS/FAIL
- Safety/privacy: PASS/FAIL
- Test coverage: PASS/FAIL

Known Mock/Deferred Items
- Emergency medical approval
- Official hospital contacts/URLs
- BHYT official content
- Real HIS identity/consent

No Supabase connection used.
```

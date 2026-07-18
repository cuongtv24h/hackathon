# Frontend Handoff — Hospital Assistant Chat App MVP

## 1. Mục tiêu bàn giao

Thiết kế lại hoàn toàn ứng dụng chat bệnh viện tại `apps/chat-web/` thành giao diện chatbot chuyên nghiệp, ưu tiên thao tác hội thoại trên desktop và mobile. Frontend mới phải thay thế được phần hiện tại mà **không thay đổi backend, API paths, DTO công khai, cơ sở dữ liệu hoặc biến môi trường backend**.

Ngôn ngữ hiển thị: tiếng Việt. Mã nguồn, tên biến, tên component, test: tiếng Anh.

## 2. Phạm vi thay thế và giới hạn

Được thay thế toàn bộ:

- `apps/chat-web/src/**`
- stylesheet, assets nội bộ của Chat App và các test frontend liên quan.

Không thay đổi:

- `apps/api/**`, `apps/mock_his/**`, `supabase/**`, `.env`.
- Endpoint, request DTO, response envelope được mô tả ở tài liệu này.
- `apps/chat-web/package.json` trừ khi thực sự cần một thư viện UI nhỏ. Không dùng UI kit nặng nếu CSS/React hiện có đáp ứng được.

Giữ Vite + React + TypeScript + Vitest. Chạy được với:

```powershell
cd apps/chat-web
npm run dev
npm run test -- --run
npm run build
```

`VITE_API_BASE_URL` rỗng nghĩa là gọi `/v1/...` qua Vite proxy. Khi triển khai, nếu biến này có giá trị thì ghép với path API sau khi bỏ dấu `/` cuối.

## 3. Product UX bắt buộc

### 3.1 Bố cục

Desktop là layout 3 vùng, không phải form/combobox dashboard:

1. **Header cố định**: logo/wordmark bệnh viện ở trái, trạng thái “Trợ lý trực tuyến”, nút thu nhỏ thông tin bảo mật ở phải.
2. **Vùng hội thoại trung tâm**: rộng tối đa 920px, bubble phân biệt người dùng/trợ lý, tự cuộn đến phản hồi mới, lịch sử vẫn đọc được.
3. **Vùng gợi ý phía dưới**: quick actions theo JTBD ở lần đầu; sau mỗi câu trả lời, hiển thị next actions phù hợp theo ngữ cảnh.
4. **Composer cố định đáy**: textarea tự co giãn, nút gửi, Enter gửi, Shift+Enter xuống dòng. Có trạng thái đang trả lời và nút dừng nếu streaming được triển khai.

Mobile: một cột; header thu gọn; quick actions cuộn ngang hoặc grid 2 cột; composer luôn thấy được phía đáy màn hình.

### 3.2 Trạng thái lần đầu truy cập

Tin nhắn đầu của trợ lý:

> Xin chào, tôi là Trợ lý Bệnh viện. Tôi có thể hỗ trợ thông tin khám chữa bệnh, bảo hiểm y tế, đặt lịch hoặc tra cứu lịch hẹn của bạn.

Ngay dưới là 6 nút hành động dạng card/chip (có icon, nhãn, mô tả ngắn):

| ID | Nhãn | Hành động |
|---|---|---|
| `service_price` | Tra cứu giá dịch vụ | Gửi PC-01 với câu hỏi giá dịch vụ. |
| `visit_process` | Quy trình khám bệnh | Gửi PC-01. |
| `health_insurance` | Thông tin BHYT | Gửi PC-01. |
| `booking` | Đặt lịch khám | Mở flow đặt lịch có hướng dẫn, không gửi câu này vào PC-01. |
| `appointment_status` | Tra cứu lịch hẹn | Mở vùng nhập mã lịch hẹn. |
| `emergency` | Tình huống khẩn cấp | Hiển thị confirmation modal trước khi gọi PC-02. |

Không hiển thị dropdown/combobox ID ngay khi người dùng vừa mở chat.

### 3.3 Quy tắc hội thoại tự do

- Người dùng có thể gõ bất kỳ câu hỏi nào.
- Phân luồng phía frontend chỉ dựa vào hành động UI rõ ràng; chat tự do mặc định gửi PC-01.
- Không tự suy luận bệnh lý, không tự triage bằng keyword ở frontend. Backend PC-02 chịu trách nhiệm emergency detection.
- Nếu lỗi API, giữ nguyên nội dung người dùng đã nhập và hiện card lỗi có nút “Thử lại”; không chỉ hiện thông báo chung chung.
- Nếu PC-01 `outcome=fallback`, hiển thị fallback như một tin trợ lý, kèm `suggested_actions` hoặc các gợi ý liên hệ/đặt lịch. Không gọi đó là câu trả lời có căn cứ.

### 3.4 Quy tắc hiển thị RAG/citation

Khi `result.citations` có dữ liệu:

- Hiển thị câu trả lời trước.
- Hiển thị khu “Nguồn tham khảo” có thể mở/đóng; mỗi citation có domain, source section, effective date (nếu có), score không cần hiển thị.
- Không bịa citation, không suy diễn URL nếu response không cung cấp URL.
- Nếu `warnings`/`disclaimers` có dữ liệu, hiển thị một notice nhỏ dưới câu trả lời, không che nội dung chính.

### 3.5 Emergency UX

- Nút “Tình huống khẩn cấp” mở modal xác nhận: “Nếu có dấu hiệu nguy hiểm tức thời, hãy gọi cấp cứu ngay.”
- Modal có “Tôi cần hỗ trợ khẩn cấp” và “Quay lại”.
- Sau khi gửi PC-02, response emergency phải dùng một emergency card nổi bật màu đỏ/cam: cấp độ, hướng dẫn, hotline/địa chỉ nếu backend trả về, disclaimer.
- Không có animation gây phân tâm và không trì hoãn việc hiện thông điệp an toàn.

### 3.6 Flow đặt lịch — guided conversation, không combobox thô

Flow diễn ra thành các message/card trong luồng chat:

1. Người dùng bấm **Đặt lịch khám**.
2. Fetch `GET /v1/foundation/specialties`; hiển thị các khoa dưới dạng button cards.
3. Sau khi chọn khoa, fetch `GET /v1/foundation/doctors?specialty_id={id}`; hiển thị bác sĩ dạng cards (tên/chuyên khoa nếu có). Có nút quay lại chọn khoa.
4. Sau khi chọn bác sĩ, fetch `GET /v1/foundation/doctors/{doctor_id}/available-slots`; hiển thị slot theo nhóm ngày, mỗi slot là button.
5. Sau chọn slot, hỏi tối thiểu các dữ liệu mà backend PC-03 yêu cầu bằng card form thân thiện trong hội thoại. Không yêu cầu dữ liệu không cần thiết.
6. Gọi PC-03 lần đầu với `form_data` hiện có. Khi backend trả `confirmation_required`, hiển thị card tóm tắt + nút “Xác nhận đặt lịch”.
7. Khi xác nhận, tạo một UUID client-side cho `Idempotency-Key` và tái sử dụng đúng key đó cho mọi lần retry của **cùng một thao tác xác nhận**.
8. Gọi PC-03 với `form_data.confirmed=true`. Khi thành công, hiển thị mã lịch hẹn và badge `pending` với câu: “Yêu cầu đặt lịch đã được ghi nhận, đang chờ xác nhận.”
9. Nút “Tra cứu lịch hẹn này” điền sẵn mã hẹn vào flow PC-04.

Nếu Foundation API lỗi, hiện trạng thái inline và nút retry cho đúng bước; không tự đổi sang input ID kỹ thuật.

### 3.7 Tra cứu lịch hẹn

- Chỉ có một input rõ nhãn “Mã lịch hẹn”.
- Submit gọi PC-04.
- Không yêu cầu họ tên/số điện thoại trên UI cho flow này.
- Kết quả `found` hiển thị một appointment card; `not_found` hiển thị hướng dẫn kiểm tra lại mã hoặc quay về đặt lịch.

## 4. Design system đề xuất

Đây là hướng visual để team frontend triển khai nhất quán, không yêu cầu dùng ảnh tạo sẵn:

- Font: `Inter` hoặc system sans-serif, fallback `Arial`.
- Nền app: slate/blue rất nhạt (`#F6F8FC`); surface trắng; viền `#E2E8F0`.
- Primary hospital blue: khoảng `#0B5CAD`; accent teal khoảng `#0F766E`.
- Emergency: `#B42318` nền nhạt `#FEF3F2`.
- Thành công/pending: xanh dương hoặc vàng nhạt; `pending` không dùng màu xanh xác nhận.
- Bo góc 12–16px, shadow nhẹ, khoảng trắng rộng, contrast tối thiểu WCAG AA.
- Avatar trợ lý dùng biểu tượng chữ thập/y tế đơn giản; không dùng ảnh bác sĩ giả hoặc ảnh bệnh nhân.
- Icon dùng SVG/icon library nhỏ, mọi icon button bắt buộc có `aria-label`.

Không được thiết kế như CRM/admin dashboard; đây là một “conversational care assistant”.

## 5. API integration contract

### 5.1 Quy ước chung

Mọi capability response dùng envelope:

```ts
type CapabilityEnvelope<T> = {
  trace_id: string
  request_id: string
  capability: 'information_assistance' | 'emergency_safety' | 'appointment_booking' | 'appointment_status'
  outcome: string
  result: T
  explainability?: unknown
  warnings: string[]
  errors: Array<{ code: string; message: string; details?: Record<string, unknown> }>
  timestamp: string
}
```

Mỗi session browser tạo một UUID và lưu trong `sessionStorage` với key `hospital_assistant_session_id`. `request_id` là UUID mới cho mỗi request. Không lưu raw chat history chứa dữ liệu nhạy cảm vào `localStorage`.

`client_context` luôn gửi:

```json
{ "channel": "web_page", "locale": "vi-VN", "timezone": "Asia/Bangkok" }
```

### 5.2 PC-01 — Information Assistance

`POST /v1/capabilities/information-assistance:execute`

```json
{
  "request_id": "uuid",
  "session_id": "uuid",
  "message": "Đi khám BHYT cần mang theo giấy tờ gì?",
  "conversation_history": [],
  "response_mode": "sync",
  "client_context": { "channel": "web_page", "locale": "vi-VN", "timezone": "Asia/Bangkok" }
}
```

Có thể dùng `response_mode: "stream"`; backend trả SSE events `ack` và `completed`. MVP vẫn phải render đúng nếu dùng sync.

`result` cần xử lý tối thiểu: `outcome`, `message`, `citations`, `suggested_actions`, `disclaimers`, `explainability`, `error`.

### 5.3 PC-02 — Emergency Safety

`POST /v1/capabilities/emergency-safety:execute`

```json
{
  "request_id": "uuid",
  "session_id": "uuid",
  "message": "Tôi cần hỗ trợ khẩn cấp",
  "conversation_history": [],
  "response_mode": "sync",
  "client_context": { "channel": "web_page", "locale": "vi-VN", "timezone": "Asia/Bangkok" }
}
```

Render toàn bộ `result` an toàn; không hard-code clinical instruction khác với backend.

### 5.4 PC-03 — Appointment Booking

`POST /v1/capabilities/appointment-booking:execute`

Headers khi xác nhận tạo lịch:

```http
Content-Type: application/json
Idempotency-Key: <uuid-for-confirmation>
```

Body:

```json
{
  "request_id": "uuid",
  "session_id": "uuid",
  "message": "Xác nhận đặt lịch",
  "conversation_history": [],
  "response_mode": "sync",
  "client_context": { "channel": "web_page", "locale": "vi-VN", "timezone": "Asia/Bangkok" },
  "form_data": {
    "specialty_id": "...",
    "doctor_id": "...",
    "slot_id": "...",
    "confirmed": true
  }
}
```

Không giả định field form nào ngoài dữ liệu backend yêu cầu. Dùng `result.prompt`, `result.missing_fields`, `result.conversation_state`, `result.appointment` để render bước tiếp theo. Outcomes cần hỗ trợ: `collecting`, `confirmation_required`, `created`, `appointment_pending`, `unavailable`, `redirected`, `error`.

### 5.5 PC-04 — Appointment Status

`POST /v1/capabilities/appointment-status:execute`

```json
{
  "request_id": "uuid",
  "session_id": "uuid",
  "appointment_reference": { "appointment_id": "APT-..." },
  "response_mode": "sync"
}
```

### 5.6 Foundation APIs cho booking

```http
GET /v1/foundation/specialties
GET /v1/foundation/doctors?specialty_id={specialtyId}
GET /v1/foundation/doctors/{doctorId}/available-slots
```

Tất cả trả danh sách phân trang có dạng:

```ts
type FoundationPage<T> = { items: T[]; total: number; page: number; page_size: number }
```

Frontend chỉ hiển thị các trường có trong `items`; không tự tạo giá trị ID.

## 6. Cấu trúc source khuyến nghị

Team frontend được quyền thay đổi tên nhưng nên tách theo trách nhiệm:

```text
src/
  app/
    App.tsx
    app-shell.tsx
  api/
    chat-client.ts
    foundation-client.ts
    types.ts
  features/chat/
    chat-screen.tsx
    message-list.tsx
    message-bubble.tsx
    composer.tsx
    quick-actions.tsx
    citation-panel.tsx
  features/booking/
    booking-flow.tsx
    specialty-step.tsx
    doctor-step.tsx
    slot-step.tsx
    confirmation-card.tsx
  features/emergency/
    emergency-modal.tsx
    emergency-card.tsx
  features/appointment-status/
    lookup-card.tsx
  styles/
    tokens.css
    global.css
  test/
```

Không đặt substantive logic trong `index.ts` hoặc một mega-component duy nhất. `main.tsx` chỉ bootstrap React.

## 7. Accessibility, privacy và error states

- Dùng semantic heading, `main`, `nav`, `form`, button thật; focus state rõ ràng.
- Có `aria-live="polite"` cho trạng thái trả lời, `role="alert"` cho lỗi và emergency critical notice.
- Keyboard: Tab đến mọi quick action, Enter/Space kích hoạt button, Escape đóng modal.
- Không render API key, `DATABASE_URL`, trace/error raw, raw SQL hoặc stack trace.
- Không lưu người dùng, số điện thoại, tên bệnh nhân trong log phía browser hoặc analytics frontend.
- Mọi loading cần skeleton/spinner theo đúng vùng đang tải, không khóa toàn trang trừ emergency confirmation đang submit.

## 8. Acceptance criteria giao nhận

- [ ] Lần đầu mở trang có greeting và 6 JTBD quick actions.
- [ ] Chat tự do gửi PC-01; câu trả lời có citations hiển thị nguồn tham khảo.
- [ ] Fallback không bị hiển thị như đáp án chắc chắn và có hành động tiếp theo.
- [ ] Emergency mở confirmation rồi render emergency card từ PC-02.
- [ ] Booking đi theo button cards khoa → bác sĩ → slot → xác nhận; không dùng combobox chọn ID.
- [ ] Booking confirmation luôn gửi và giữ nguyên `Idempotency-Key` trong retry cùng thao tác.
- [ ] Appointment created/pending hiển thị mã hẹn và trạng thái `pending`.
- [ ] Tra cứu lịch chỉ yêu cầu appointment ID và render `found`/`not_found` đúng.
- [ ] Lỗi Foundation/Capability hiển thị theo bước, có retry, không mất state đã chọn.
- [ ] UI responsive desktop/mobile, keyboard accessible, không có horizontal overflow 360px.
- [ ] `npm run test -- --run` và `npm run build` đều pass.

## 9. Bộ test frontend tối thiểu

1. Initial render: greeting + đủ 6 quick actions.
2. Free text question: loading → PC-01 request đúng body → response có citations.
3. PC-01 fallback: render card thông báo chưa đủ căn cứ + next action.
4. Emergency: modal → PC-02 → emergency card; có thể thao tác keyboard.
5. Booking: Foundation calls lần lượt; user chọn khoa/bác sĩ/slot bằng buttons.
6. Booking confirmation: header `Idempotency-Key` xuất hiện và không đổi khi bấm retry.
7. PC-04 found/not_found.
8. API 503/network failure: giữ state, hiện retry, không hiện raw error.
9. Responsive smoke ở viewport 360px và 1440px.

## 10. Handover checklist cho team frontend

1. Thay nội dung `apps/chat-web/src/` theo đặc tả này.
2. Không commit `.env`, `node_modules`, `dist` hoặc secret.
3. Chạy test/build và gửi danh sách file thay đổi + command/result.
4. Chạy local cùng backend bằng `scripts/start-local.bat`, kiểm tra Chat App tại `http://127.0.0.1:5173`.
5. Không thay đổi API contract khi phát hiện thiếu thông tin; báo lại bằng ví dụ request/response cụ thể.

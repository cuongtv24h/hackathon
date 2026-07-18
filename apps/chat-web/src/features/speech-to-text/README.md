# Speech-to-text

Module nhập câu hỏi bằng giọng nói tiếng Việt cho chat widget và trang chat độc lập.

## Quyết định kiến trúc

- Dùng browser-native Web Speech API trước, đúng định hướng FR-16 trong tài liệu yêu cầu.
- Tách `SpeechRecognitionProvider` khỏi React UI để có thể thay bằng nhà cung cấp ASR chất lượng cao hơn mà không đổi composer hoặc API chat.
- Chỉ đưa transcript vào ô nhập. Module không tự gửi câu hỏi, nên người dùng luôn có thể xem và sửa kết quả nhận dạng theo yêu cầu TR-03/FR-16.
- Ứng dụng không tạo endpoint tải audio lên backend và không lưu audio. Việc xử lý audio của browser-native ASR vẫn phụ thuộc chính sách của trình duyệt/dịch vụ trình duyệt.
- Locale mặc định là `vi-VN`; nhận cả kết quả tạm thời và kết quả cuối để phản hồi trạng thái rõ ràng.
- Khi browser không hỗ trợ hoặc quyền micro bị từ chối, nhập liệu bàn phím vẫn hoạt động bình thường.

## Mở rộng provider

Provider mới chỉ cần triển khai `SpeechRecognitionProvider` trong `types.ts` và được truyền vào `SpeechInput`. Không thay đổi `ChatClient`, capability DTO hoặc backend gateway.

# Region Marker Policy

## 1. Mục tiêu

Region marker bảo vệ chỉnh sửa song song. Một builder chỉ được tạo hoặc cập nhật file/zone trong task-to-file contract của mình; reviewer kiểm tra marker trước khi review nội dung.

## 2. Các mode

- `FULL_FILE`: chỉ áp dụng cho file mới hoặc một file được Human Lead cho phép rõ ràng.
- `{TASK:WP-xxx}`: builder chỉ chỉnh sửa giữa marker mở/đóng của đúng work package.
- `DIRECTORY_ZONE`: file leaf chưa được kiến trúc chốt trước. Builder được tạo file leaf đầu tiên bên trong directory zone đã ghi trong contract, thêm marker của task và ghi exact path trong BUILD RESULT.

## 3. Cú pháp chuẩn

Dùng comment phù hợp ngôn ngữ nhưng giữ nguyên token:

```text
# === TASK:WP-401:START ===
# === TASK:WP-401:END ===
```

Không lồng marker. Không đổi ID, không xóa marker của task khác. File có nhiều task phải có một marker độc lập cho mỗi task.

## 4. Quy tắc sửa

1. Builder đọc `docs/spec-registry/task-to-file-contract-map.yaml` trước khi sửa.
2. Nếu marker hoặc file leaf chưa tồn tại, builder có `CREATE` directory zone được tạo leaf file đầu tiên trong đúng zone và thêm marker của chính task. WP-004 chỉ tạo/duy trì initialization map và kiểm tra marker/zone không chồng lấn.
3. Chạm vùng ngoài contract: dừng task, tạo escalation cho Human Lead.
4. Reviewer từ chối diff làm đổi marker, ownership hoặc file path mà không có exception được duyệt.
5. Sau merge, integration branch chạy `scripts/verify-scaffold.bat /regions`.

## 5. Two-stage verification

- `scripts/verify-scaffold.bat`: base gate sau WP-002/WP-003; kiểm tra governance files và directory zones.
- `scripts/verify-scaffold.bat /regions`: post-region gate sau WP-004; kiểm tra region policy/initialization map trước builder task đầu tiên trong zone.

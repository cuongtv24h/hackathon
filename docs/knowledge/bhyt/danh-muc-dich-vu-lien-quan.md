---
source_id: SRC-BHYT-005
title: Danh mục dịch vụ liên quan đến BHYT tại Bệnh viện Tim Hà Nội
domain: bhyt
status: approved_for_pilot
source_status: official_public_sources
effective_from: "2024-03-15"
effective_to: null
approved_by: "Product owner — MVP Pilot bootstrap approval"
facility_scope: hospital
version: "0.1-public-crawl"
last_reviewed: "2026-07-18"
source_urls:
  - "https://benhvientimhanoi.vn/vi/chi-tiet/bang-gia-dich-vu/bang-gia-bao-hiem-y-te-tai-benh-vien-tim-ha-noi."
  - "https://chinhphu.vn/?classid=1&docid=209133&pageid=27160"
  - "https://benhvientimhanoi.vn/vn/cong/thong-tin/khoa-kham-benh-tu-nguyen"
notes:
  - "Trang bệnh viện công bố bảng giá BHYT áp dụng theo Thông tư 22/2023/TT-BYT, nhưng nội dung bảng chi tiết có thể nằm trong iframe/ảnh; cần bệnh viện cung cấp file gốc để ingest đầy đủ."
---

# Danh mục dịch vụ liên quan đến BHYT tại Bệnh viện Tim Hà Nội

## Nguồn giá BHYT

Bệnh viện Tim Hà Nội công bố trang **Bảng giá Bảo Hiểm Y Tế tại Bệnh Viện Tim Hà Nội**, ngày 15/03/2024, ghi nhận bảng giá BHYT áp dụng theo **Thông tư 22/2023/TT-BYT** của Bộ Y tế.

Thông tư 22/2023/TT-BYT quy định thống nhất giá dịch vụ khám bệnh, chữa bệnh BHYT giữa các bệnh viện cùng hạng trên toàn quốc và hướng dẫn áp dụng giá, thanh toán chi phí khám chữa bệnh trong một số trường hợp. Thông tư có hiệu lực từ ngày 17/11/2023.

## Nhóm dịch vụ có thể phát sinh khi khám tim mạch

Theo thông tin Khoa Khám bệnh tự nguyện, các xét nghiệm/thăm dò/chẩn đoán có thể phục vụ người bệnh gồm:

### Khám sức khỏe thông thường

- Điện tim đồ.
- X-quang tim phổi.
- Siêu âm – Doppler tim thường quy.
- Xét nghiệm cơ bản: công thức máu, đông máu cơ bản, chức năng gan thận, đường máu, mỡ máu, acid uric, tổng phân tích nước tiểu.
- Siêu âm ổ bụng.

### Chuyên khoa tim mạch và thăm dò nâng cao

- Nghiệm pháp gắng sức để sàng lọc bệnh động mạch vành và một số bệnh lý khác.
- Siêu âm tim Dobutamine để sàng lọc bệnh động mạch vành.
- Holter huyết áp 24 giờ.
- Holter điện tim đồ 24 giờ.
- Siêu âm tim qua thực quản.
- Siêu âm tim 4D.
- Siêu âm – Doppler mạch máu.
- Đo chỉ số ABI.
- Xét nghiệm máu chuyên sâu: hs Troponin, pro BNP, hs CRP, sàng lọc sớm ung thư.
- Chụp cộng hưởng từ toàn thân.
- Chụp cắt lớp động mạch vành 128 dãy hoặc 256 dãy và chụp CT các bộ phận khác.
- Siêu âm tim thai từ tuần thai thứ 18 với các đối tượng nguy cơ.

## Lưu ý thanh toán

- Không phải mọi dịch vụ được nêu trong danh mục chuyên môn đều mặc định được BHYT thanh toán toàn bộ.
- Cần kiểm tra dịch vụ có thuộc danh mục BHYT, có chỉ định chuyên môn phù hợp, mức hưởng của thẻ, tình trạng tuyến và loại hình dịch vụ theo yêu cầu hay không.
- Nếu người bệnh sử dụng dịch vụ theo yêu cầu/tự nguyện, phần chênh lệch ngoài mức BHYT thanh toán có thể do người bệnh tự chi trả.

## Dữ liệu cần bổ sung từ bệnh viện

Để ingest production, cần xin bản được bệnh viện phê duyệt dưới dạng Excel/PDF/CSV cho:

- Bảng giá BHYT hiện hành.
- Bảng giá dịch vụ kỹ thuật theo yêu cầu.
- Mã dịch vụ kỹ thuật, tên dịch vụ, đơn vị tính, giá BHYT, giá dịch vụ, ghi chú phạm vi thanh toán.
- Ngày hiệu lực, quyết định ban hành, đơn vị phê duyệt.
- Danh mục thuốc/vật tư tiêu hao nếu bệnh viện cho phép công bố.

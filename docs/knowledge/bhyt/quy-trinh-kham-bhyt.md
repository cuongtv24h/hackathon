---
source_id: SRC-BHYT-001
title: Quy trình khám BHYT tại Bệnh viện Tim Hà Nội
domain: bhyt
status: approved_for_pilot
source_status: official_public_sources
effective_from: "2025-08-15"
effective_to: null
approved_by: "Product owner — MVP Pilot bootstrap approval"
facility_scope: hospital
version: "0.1-public-crawl"
last_reviewed: "2026-07-18"
source_urls:
  - "https://benhvientimhanoi.vn/vn/cong/thong-tin/khoa-kham-benh-tu-nguyen"
  - "https://benhvientimhanoi.vn/vn/cong/thong-tin/huong-dan-lien-he-dat-lich-kham"
  - "https://baohiemxahoi.gov.vn/tintuc/Pages/linh-vuc-bao-hiem-y-te.aspx?CateID=0&ItemID=25292"
notes:
  - "Bản này chuẩn hóa từ nguồn công khai, không phải tài liệu nội bộ đã ký duyệt."
  - "Cần đối chiếu với quy trình tiếp đón BHYT thực tế tại quầy BHYT bệnh viện."
---

# Quy trình khám BHYT tại Bệnh viện Tim Hà Nội

## Phạm vi áp dụng

Tài liệu này dùng để trả lời các câu hỏi cơ bản về khám, chữa bệnh có BHYT tại Bệnh viện Tim Hà Nội, bao gồm:

- Người bệnh khám ngoại trú hoặc nhập viện điều trị nội trú.
- Người bệnh có thẻ BHYT, giấy chuyển tuyến, phiếu hẹn khám lại hoặc trường hợp cấp cứu.
- Người bệnh cần biết nên mang giấy tờ gì, liên hệ ở đâu, và cách xử lý khi đặt lịch/đến khám.

## Quy trình tổng quát khi người bệnh đến khám BHYT

1. **Chuẩn bị trước khi đến bệnh viện**
   - Kiểm tra thông tin thẻ BHYT, mã số BHYT, căn cước/căn cước công dân hoặc VNeID/VssID.
   - Nếu khám theo chuyển tuyến, chuẩn bị Phiếu chuyển cơ sở khám bệnh, chữa bệnh còn giá trị.
   - Nếu khám lại theo hẹn, chuẩn bị Phiếu hẹn khám lại/đơn thuốc/giấy ra viện có ghi lịch hẹn.
   - Nếu là cấp cứu, ưu tiên đến cơ sở y tế gần nhất hoặc gọi cấp cứu theo tỉnh/thành: mã vùng + 115.

2. **Đến quầy tiếp đón/BHYT**
   - Xuất trình thông tin thẻ BHYT và giấy tờ chứng minh nhân thân theo quy định.
   - Cơ sở khám chữa bệnh tiếp nhận người bệnh để chẩn đoán và điều trị.
   - Người bệnh được giải quyết quyền lợi BHYT ngay sau khi xuất trình hồ sơ hợp lệ.

3. **Khám lâm sàng và thực hiện chỉ định**
   - Người bệnh được bác sĩ khám và chỉ định xét nghiệm, thăm dò chức năng, chẩn đoán hình ảnh hoặc điều trị nếu cần.
   - Với Khoa Khám bệnh tự nguyện, bệnh viện có quầy tư vấn hướng dẫn thủ tục khám chữa bệnh, thủ tục BHYT, chọn bác sĩ và đưa người bệnh đi làm các thăm dò tim mạch nếu không nằm tại khoa.

4. **Thanh toán BHYT**
   - Quỹ BHYT thanh toán trong phạm vi được hưởng và theo mức hưởng của người bệnh.
   - Phần ngoài phạm vi hưởng, phần đồng chi trả hoặc phần chênh lệch dịch vụ theo yêu cầu do người bệnh thanh toán.

5. **Kết luận, nhận thuốc, hẹn tái khám hoặc nhập viện**
   - Nếu cần tái khám, cơ sở khám chữa bệnh lập Phiếu hẹn khám lại bản giấy hoặc bản điện tử theo quy định.
   - Nếu cần chuyển cơ sở khám chữa bệnh theo yêu cầu chuyên môn, cơ sở nơi chuyển lập Phiếu chuyển cơ sở khám bệnh, chữa bệnh.
   - Nếu vào viện điều trị nội trú: trường hợp cấp cứu được hưởng BHYT theo diện cấp cứu; các trường hợp khác cần chuyển tuyến theo quy định BHYT.

## Lưu ý đặt lịch khám

- Việc đặt lịch hẹn khám chỉ dành cho trường hợp **không cấp cứu, không khẩn cấp**.
- Người bệnh nên đặt hẹn trước ít nhất **24 giờ** so với giờ dự định khám.
- Lịch hẹn chỉ có giá trị sau khi bệnh viện xác nhận.
- Người bệnh cần có mặt trước giờ hẹn ít nhất **15 phút** để làm thủ tục đăng ký, đo mạch, huyết áp, chiều cao, cân nặng.

## Điểm cần chatbot kiểm tra trước khi trả lời

- Người bệnh hỏi khám thường, khám tự nguyện, cấp cứu hay nhập viện nội trú?
- Người bệnh có giấy chuyển tuyến/phiếu hẹn khám lại không?
- Người bệnh hỏi quyền lợi chung hay tình huống cá nhân cụ thể?
- Người bệnh đang ở giai đoạn trước khám, đang điều trị, ra viện hay xin thanh toán lại?

## Guardrail trả lời

- Không cam kết chắc chắn mức hưởng cuối cùng nếu chưa biết mã quyền lợi, tình trạng chuyển tuyến, loại khám ngoại trú/nội trú, cấp cứu hay không, và dịch vụ có thuộc phạm vi thanh toán BHYT hay không.
- Không tự xác định bệnh viện thuộc cấp chuyên môn kỹ thuật nào nếu chưa có văn bản xếp cấp hiện hành.
- Với trường hợp cấp cứu hoặc đau ngực, khó thở, ngất, tím tái, rối loạn ý thức: hướng dẫn gọi cấp cứu hoặc đến cơ sở y tế gần nhất, không tư vấn chờ đặt lịch.

## Liên hệ hỗ trợ

- Hotline Bệnh viện Tim Hà Nội: **19001082**.
- Liên hệ giải đáp thủ tục hành chính, tư vấn BHYT: **19001082**.
- Email: **cskh@timhanoi.vn**.

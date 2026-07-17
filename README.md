# Hospital Assistant MVP Pilot

Monorepo cho MVP trợ lý bệnh viện: kênh chat người bệnh, dashboard vận hành, Mock HIS và dịch vụ AI/RAG.

## Khởi động phát triển

1. Cài Python theo phiên bản được chốt cho dự án và Node.js 22 LTS.
2. Tạo môi trường ảo Python, sau đó cài dependencies:

   ```bat
   py -m pip install -r requirements.txt
   ```

3. Sao chép `.env.example` thành `.env` và chỉ điền `DATABASE_URL` cùng khoá LLM ở môi trường local/server.
4. Chạy `scripts\verify-scaffold.bat` trước Sprint 1. Kiểm tra `/regions` chỉ chạy sau khi WP-004 hoàn tất.

## Tài liệu thực thi

- [Engineering Planning](docs/5.ai-engineering-planning.md)
- [AI Orchestration](docs/6.ai-orchestration.md)
- [Implementation Execution View](docs/implementation-execution-view.md)
- [Document Reference Policy](docs/reference-packs/document-reference-policy.md)

Không commit `.env`, chuỗi kết nối cơ sở dữ liệu, hoặc khoá nhà cung cấp AI.

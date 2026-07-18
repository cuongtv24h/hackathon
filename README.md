# Hospital Assistant MVP Pilot

## Quick start on Windows

```bat
scripts\start-local.bat
scripts\smoke-local.bat
```

Use `scripts\stop-local.bat` to close only the four terminals created by the
quick-start script.

Monorepo cho MVP trợ lý bệnh viện: kênh chat người bệnh, dashboard vận hành, Mock HIS và dịch vụ AI/RAG.

## Khởi động phát triển

Chạy Mock HIS ở một terminal riêng trước khi khởi động API chính. Đây là
service giả lập độc lập, chỉ dùng dữ liệu trong `data/mvp/seed/mock-his.json`:

```powershell
py -m uvicorn apps.mock_his.main:app --host 127.0.0.1 --port 8001
```

Trong terminal khác, khởi động Hospital API:

```powershell
py -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --reload

```

Trong hai terminal khác, chạy frontend:

```powershell
cd apps/chat-web; npm run dev
```

```powershell
cd apps/admin-web; npm run dev -- --port 5174
```

`MOCK_HIS_BASE_URL` trong `.env` phải là `http://127.0.0.1:8001` khi chạy cục
bộ. Không công khai cổng Mock HIS ra Internet; reverse proxy VPS chỉ dùng nó ở
nội bộ.

1. Cài Python theo phiên bản được chốt cho dự án và Node.js 22 LTS.
2. Tạo môi trường ảo Python, sau đó cài dependencies:

   ```bat
   py -m pip install -r requirements.txt
   ```

3. Sao chép `.env.example` thành `.env` và chỉ điền `DATABASE_URL` cùng khoá LLM ở môi trường local/server.


## Tài liệu thực thi

- [Engineering Planning](docs/5.ai-engineering-planning.md)
- [AI Orchestration](docs/6.ai-orchestration.md)
- [Implementation Execution View](docs/implementation-execution-view.md)
- [Document Reference Policy](docs/reference-packs/document-reference-policy.md)

## Live E2E (dedicated environment only)

The live Playwright suite starts Mock HIS, FastAPI, Chat Web and Admin Web,
then uses their real HTTP paths. Do not point it at the Pilot database because
the booking and content-conflict tests write state. Configure a dedicated E2E
Supabase database and an unresolved conflict fixture, then run:

```powershell
$env:E2E_LIVE = '1'
$env:E2E_CONFLICT_ID = '<unresolved-conflict-uuid>'
cd apps/chat-web
npx playwright test --config=playwright.config.ts mvp-live-capabilities.spec.ts
```

`E2E_CONFLICT_ID` is intentionally required for the conflict-resolution flow;
it prevents the runner from selecting or resolving arbitrary Pilot content.

Không commit `.env`, chuỗi kết nối cơ sở dữ liệu, hoặc khoá nhà cung cấp AI.
## VPS deployment without Nginx

For the MVP VPS topology, FastAPI serves the production web builds directly:

- `http://<server>:8000/` — Chat application
- `http://<server>:8000/admin/` — Admin application
- `http://<server>:8000/v1/` — capability and foundation APIs
- `http://127.0.0.1:8001/` — Mock HIS, internal-only

Build both frontend applications before starting the API:

```bash
cd apps/chat-web && npm ci && npm run build
cd ../admin-web && npm ci && npm run build
```

Then start Mock HIS on loopback and FastAPI publicly:

```bash
python -m uvicorn apps.mock_his.main:app --host 127.0.0.1 --port 8001
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

Set `MOCK_HIS_BASE_URL=http://127.0.0.1:8001` on the VPS. Do not expose port
8001 publicly. This no-Nginx setup is suitable for Pilot/demo use; put the
service behind HTTPS before accepting real patient data over the Internet.

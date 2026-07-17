---
artifact_id: ARCH-01
artifact_name: Solution Constraints
source_file: docs/3.architecture-design.md
source_sections:
  - "Artifact 0 — Architecture Traceability Matrix"
  - "Artifact 1 — Solution Overview"
  - "Artifact 10 — Architecture Decision Record"
category: architecture
consumers: [architect, builder, reviewer, auditor, lead]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Solution Constraints

## Summary

Các boundary, goals và quyết định kiến trúc bắt buộc cho toàn hệ thống.

## Canonical Content

- Hệ thống cung cấp Q&A nguồn chính thức 24/7, appointment booking/lookup, emergency safety, provider fallback, conversation logging/basic analytics và content management tối giản.
- Trong scope: Chat Widget, Standalone Chat Page, 7 knowledge domains, Mock HIS appointment, multi-provider LLM fallback.
- Ngoài scope vĩnh viễn: tư vấn/chẩn đoán y tế, thay thế quyết định bác sĩ.
- Ngoài phase: live-agent handoff phức tạp, multi-tenant thật, analytics nâng cao, ASR/TTS, personalization liên phiên.
- Architecture principles: LLM-first; Keyword Pre-filter là safety net; RAG bắt buộc; separation of concerns; provider agnostic; traceable citations; graceful degradation; config-driven extensibility.

| Goal | Target |
|---|---|
| Time to First Token | ≤ 2 giây |
| Critical keyword emergency | ≤ 100ms |
| LLM emergency | ≤ 3 giây |
| Hallucination ngoài KB | 0% |
| Availability | 99.5% giờ hành chính |
| Concurrent sessions | ≥ 100 |

## Key Constraints

- LLM là lớp xử lý chính; critical keyword path được phép bypass LLM.
- Critical emergency không phụ thuộc internet/LLM/database.
- RAG dùng domain-filtered vector search; không có nguồn đủ tin cậy thì fallback.
- Orchestration custom, không LangChain.
- Streaming dùng SSE.
- Mock HIS là service tách biệt để có thể thay adapter thật.
- Emergency keyword cấu hình local và cần restart khi đổi.

## Dependencies

- `docs/artifacts/architecture/component-architecture.md`
- `docs/artifacts/architecture/deployment-resilience.md`
- `docs/artifacts/interface/interface-guidelines.md`


---
artifact_id: INT-09
artifact_name: Interface Guidelines
source_file: docs/4.interface-design.md
source_sections:
  - "Artifact 9 — Interface Guidelines"
  - "9.13 Quyết định MVP Pilot đã chốt"
  - "Artifact 10 — Interface Decision Record"
category: interface
consumers: [architect, builder, reviewer, auditor, lead]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Interface Guidelines

## Summary

Naming, versioning, security, pagination, streaming and decision constraints.

## Canonical Content

- URL: lowercase kebab-case; Foundation resources plural; capability action `/v1/capabilities/{name}:execute`.
- DTO: PascalCase suffix Request/Response/DTO/PageDTO; JSON fields snake_case; opaque IDs; `_at` timestamp, `_date` date.
- Version: major in URL; additive changes stay major; breaking changes use new major; tool/content/protocol have independent versions.
- Authentication: anonymous short-lived scoped chat session; admin/history/analytics via hospital identity provider + MFA; service credentials never reach browser.
- RBAC: anonymous_user, content_admin, domain_owner, emergency_approver, operations_analyst, security_auditor, system_service.
- Pagination: cursor, default 20/max 100, opaque cursor, stable filter/sort.
- Filter/sort: allowlisted only; knowledge order is relevance-controlled.
- JSON UTF-8; SSE UTF-8; server trace ID; ISO 8601; vi-VN content.
- Idempotency-Key for appointment create/content publish; expected_version for state patches.
- SSE event IDs monotonic; one completed event; terminal error closes stream.
- TLS 1.2+, allowlist validation, rate limit, PII masking, retention policy, prompt injection isolation.

### MVP Pilot binding values

- Domains: `dat_lich`, `quy_trinh`, `bhyt`, `gia_dich_vu`, `gio_lam_viec`, `bac_si_khoa`, `thong_tin_benh_vien`.
- Mock HIS: appointment ID-only lookup, fake patient data, new status `pending`, no OTP; real-HIS identity deferred.
- Retention: context 30-minute idle/24-hour maximum; anonymized conversation 90 days; feedback 180; mock appointment 90; emergency/security/content audit and aggregate analytics 365; raw conversation PII is never stored.
- Rate limits: 20 messages/session/minute; 60/IP/minute; 100/session; 4000 characters; appointment create 5/session/minute; content write 30/user/minute; analytics read 60/user/minute.
- Live-agent Level 1 only: contact SuggestedAction + Channel Configuration; no handoff API.
- Content conflict: dashboard-only, 24-hour due date, audit; no external notification adapter in MVP.

### Binding decisions

- Product capability is the public API unit; CAP stages stay internal.
- Capability layer orchestrates; Foundation is deterministic.
- Emergency has independent contract/local critical path.
- Grounding is an output validity condition.
- HIS integration uses canonical DTO + adapter.
- Explicit confirmation + idempotency for writes.
- SSE is the streaming protocol.
- Public explainability excludes chain-of-thought.
- Context is session-only.
- PII logging fails closed.
- Content lifecycle is Foundation workflow.
- Error/action references are provider-neutral and config-backed.

## Key Constraints

- Public/persistence DTOs must not be conflated.
- Enum evolution must fail safely/handle unknown values.
- No embedding, system prompt, chain-of-thought, secret or raw audit payload exposure.
- Exact HIS identity verification, retention, rate-limit and live-agent contracts are INCOMPLETE in source.

## Dependencies

- `docs/artifacts/interface/data-contracts.md`
- `docs/artifacts/interface/error-contracts.md`
- `docs/artifacts/architecture/solution-constraints.md`

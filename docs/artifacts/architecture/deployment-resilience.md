---
artifact_id: ARCH-09
artifact_name: Deployment and Resilience
source_file: docs/3.architecture-design.md
source_sections:
  - "Artifact 9 — Deployment View"
  - "ADR-008: Emergency Keywords lưu Local Config"
category: architecture
consumers: [architect, builder, reviewer, auditor, lead]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Deployment and Resilience

## Summary

Canonical VPS topology, trust boundaries và degradation behavior.

## Canonical Content

- VPS hosts reverse proxy/static frontend, backend, Mock HIS service and local config.
- Reverse proxy routes `/api/*` to backend and `/his-api/*` to Mock HIS; applies TLS, CORS, rate limit and security headers.
- Supabase hosts pgvector knowledge, transactional appointment data, emergency/audit/feedback/analytics stores.
- External AI services are accessed over HTTPS through provider abstraction.
- Local config includes provider settings, emergency keywords/protocols and system prompts; secrets come from environment, not browser/source.

### Trust boundaries

- VPS internal: highest trust; Mock HIS localhost-only; config read-only at runtime.
- VPS↔Supabase and VPS↔AI: TLS; least-privilege credentials.
- Browser: untrusted input; no API keys exposed.

### Degradation

| Failure | Required behavior |
|---|---|
| Primary LLM | fallback provider chain |
| All LLMs | static hotline message |
| Supabase/KB | knowledge fallback to hotline |
| Total internet loss | normal chat unavailable; critical local emergency remains available |
| Analytics logger | async retry; no main-flow blocking |

## Key Constraints

- Critical emergency path must work without internet, LLM or Supabase.
- Updating emergency keyword config requires controlled deployment/restart.
- Current single-VPS topology is acceptable for hackathon/pilot architecture; production load-balancing is not defined in source.
- Exact production retention, secret management product and operational runbooks are INCOMPLETE.

## Dependencies

- `docs/artifacts/architecture/solution-constraints.md`
- `docs/artifacts/interface/interface-guidelines.md`

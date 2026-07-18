---
artifact_id: ARCH-03
artifact_name: Component Architecture
source_file: docs/3.architecture-design.md
source_sections:
  - "Artifact 3 — Component Architecture"
  - "3.5 MVP Pilot — Component Source Ownership"
category: architecture
consumers: [architect, builder, reviewer]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Component Architecture

## Summary

Runtime component responsibilities và dependency boundaries.

## Canonical Content

| Component | Type | Responsibility | SLA |
|---|---|---|---|
| Chat Widget / Standalone Page | Frontend | Chat UI, quick buttons, emergency banner, hotline, SSE | — |
| Chat Gateway | Backend | Validate, rate-limit, session, pre-filter, route, SSE | — |
| Keyword Pre-filter | Gateway function | Local critical/caution matching | <10ms |
| Emergency Protocol Loader | Gateway function | Load/format approved response | <50ms |
| LLM Orchestrator | AI service | Intent, planning, tool calling, synthesis | 1–3s |
| LLM Abstraction Layer | AI service | Provider chain/fallback | — |
| Guardrail Layer | Backend module | Medical advice block, scope, PII output, injection | <50ms |
| RAG Engine | AI service | Embed, domain filter, rank, cite | 200–500ms |
| Knowledge Store | Data | pgvector chunks/embeddings | — |
| Appointment Service | Backend | Booking logic | 100–300ms |
| Mock HIS Adapter | Backend | Doctor/schedule/appointment REST | 50–100ms |
| Conversation Logger | Async backend | PII-safe analytics logging | async |
| Audit Logger | Sync backend | Security/emergency immutable audit | sync |
| Content Manager | Backend | KB draft/approval/publish | — |

### MVP source ownership

| Component group | Paths |
|---|---|
| Chat clients | `apps/chat-web/src/widget/`, `apps/chat-web/src/standalone/` |
| Admin dashboard | `apps/admin-web/` |
| Gateway | `apps/api/gateway/` |
| Emergency | `apps/api/capabilities/emergency/prefilter/`, `apps/api/capabilities/emergency/protocols/` |
| AI | `apps/api/ai/orchestrator/`, `apps/api/ai/providers/`, `apps/api/ai/guardrails/`, `apps/api/ai/rag/` |
| Appointment/Mock HIS | `apps/api/foundation/appointments/`, `apps/mock_his/` |
| Knowledge Store access | `apps/api/foundation/knowledge/repository/` |
| Content management | `apps/api/foundation/knowledge/content/` |
| Logging | `apps/api/logging/conversation/`, `apps/api/logging/audit/` |
| Config | `config/emergency/`, `config/prompts/`, `config/hospital/` |
| Tests | `tests/contract/`, `tests/capability/`, `tests/integration/`, `tests/safety/`, `tests/e2e/` |

### Keyword Pre-filter outputs

- `critical`: Level 2, bypass LLM, load protocol directly.
- `caution`: add detected keywords to LLM context.
- `normal`: normal Orchestrator path.

### Orchestrator input/output

- Input: user_message, conversation_history, button_context, caution_flags, session_context.
- Output: streaming_tokens, citations, tools_called, emergency_triggered.
- System behavior includes emergency priority, grounding-only, medical refusal, tool registry và citation format.

## Key Constraints

- Pre-filter is a small Gateway function, not a second orchestration brain.
- Guardrail is deterministic pre/post enforcement; prompt guidance does not replace it.
- Appointment Service owns logic; HIS adapter owns provider data access.
- Analytics logging must not block response; emergency/security audit completeness is separate.

## Dependencies

- `docs/artifacts/architecture/tool-map.md`
- `docs/artifacts/architecture/integration-data-flow.md`
- `docs/artifacts/interface/tool-contracts.md`

---
artifact_id: ARCH-06
artifact_name: Architecture Tool Map
source_file: docs/3.architecture-design.md
source_sections:
  - "Artifact 6 — Tool Map"
category: architecture
consumers: [architect, builder, reviewer]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Architecture Tool Map

## Summary

Danh mục 10 LLM/utility tools và nguồn dữ liệu.

## Canonical Content

| Tool | Input summary | Output summary | Source |
|---|---|---|---|
| `search_knowledge_base` | query, domains, top_k, threshold | hybrid-ranked chunks, vector/lexical/fusion/rerank metadata, sources, has_results | pgvector + PostgreSQL FTS + reranker |
| `fallback_response` | query, domain, reason | fallback_message, channels | static templates |
| `trigger_emergency` | level, reason, session_id | protocol, event_id | Protocol Store + Audit |
| `get_specialty_list` | none | active specialties | Mock HIS |
| `get_doctor_list` | optional specialty_id | doctors | Mock HIS |
| `get_available_slots` | doctor_id, date range | slots | Mock HIS |
| `create_appointment` | doctor/slot/patient/visit data | appointment_id, pending, created_at | Mock HIS |
| `lookup_appointment` | appointment_id | appointment or null | Mock HIS |
| `log_conversation` | session/message/metadata | async log_id | Analytics Store |
| `detect_pii` | text | anonymized_text, detected flag | internal patterns |

## Key Constraints

- Critical keyword path loads protocol directly, not through LLM.
- `detect_pii` precedes `log_conversation`.
- Appointment tools are provider-neutral through Appointment Service/HIS Adapter.
- Tool schemas are authoritative; LLM cannot invent tools or fields.
- Knowledge search uses vector + lexical candidates, RRF fusion and reranking; reranker failure returns the RRF order with degraded metadata.

## Dependencies

- `docs/artifacts/interface/tool-contracts.md`
- `docs/artifacts/interface/data-contracts.md`

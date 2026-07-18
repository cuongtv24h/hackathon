---
artifact_id: ARCH-05
artifact_name: AI Capability Mapping
source_file: docs/3.architecture-design.md
source_sections:
  - "Artifact 5 — Business → AI Mapping & AI Sequence"
category: architecture
consumers: [architect, builder, reviewer, auditor]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# AI Capability Mapping

## Summary

Mapping business step → AI capability và thứ tự bắt buộc.

## Canonical Content

| Business step | AI capability | Expected output |
|---|---|---|
| Critical safety check | Keyword Pre-filter, non-AI | `is_critical` <10ms |
| Indirect emergency | CAP-3 + `trigger_emergency` | Level 1/2 protocol |
| Next action selection | CAP-1 | native tool call, clarification, final answer or abstention |
| Official retrieval | CAP-2 | ranked chunks + citations |
| Multi-domain synthesis | CAP-5 | coherent grounded answer |
| Plain language | CAP-6 | simplified explanation |
| Next action | CAP-4 | link/button/instruction |
| Medical advice refusal | CAP-2 + Guardrail | refusal + alternative |
| Booking collection | CAP-1 + CAP-5 | complete appointment data |
| Booking/lookup action | CAP-4 + tools | appointment/status result |
| Missing knowledge | CAP-2 fallback | reason + specific channel |

### Mandatory order

1. Keyword critical/caution check.
2. LLM emergency evaluation for indirect/caution signals.
3. Resolve the authorized, workflow-allowed visible tool subset.
4. Let the model select the next tool or request minimal clarification; validate policy before execution.
5. Validate observations/guardrails.
6. Grounded synthesis or fallback.
7. Action routing.

## Key Constraints

- CAP-3 has priority over surface intent.
- CAP-1 selects the next action through native tool calling; it is not a mandatory intent router. CAP-5 synthesizes grounded output.
- No response from LLM background knowledge without retrieval.
- Caution flags must be passed to Orchestrator.

## Dependencies

- `docs/artifacts/interface/ai-behavior-contracts.md`
- `docs/artifacts/architecture/tool-map.md`
- `docs/artifacts/architecture/context-design.md`

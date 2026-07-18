---
artifact_id: ARCH-07
artifact_name: Context Design
source_file: docs/3.architecture-design.md
source_sections:
  - "Artifact 7 — Context Design"
category: architecture
consumers: [architect, builder, reviewer]
related_capabilities: [PC-01, PC-02, PC-03, PC-04]
---

# Context Design

## Summary

Lifetime, ownership và content của sáu runtime contexts.

## Canonical Content

| Context | Lifetime | Owner | Content |
|---|---|---|---|
| ConversationContext | Session; 20 lượt sliding window | Frontend + backend session | message_history, session_id |
| BusinessContext | Một business flow | LLM Orchestrator | flow, step, booking fields, collected_fields |
| WorkingContext | Một graph run/checkpoint thread | LangGraph runtime | messages, visible_tools, pending_tool_calls, validated observations, budget, workflow_state, citations |
| KnowledgeContext | Một turn | RAG Engine → Orchestrator | chunks, scores, sources, domains, sufficient flag |
| EmergencyContext | Session, không reset sau trigger | Pre-filter/LLM tool → Gateway | triggered, level, path, time, banner |
| SystemContext | Persistent cached config | Backend configuration | prompt, tools, hospital config, providers, keywords |

### Lifecycle

Gateway loads Conversation/System contexts and parses BusinessContext. Pre-filter runs before the graph. Critical creates EmergencyContext immediately. Normal/caution starts or resumes a LangGraph thread; the backend resolves visible tools, the model selects the next action, and policy is rechecked before execution. RAG creates KnowledgeContext. Checkpoints follow explicit retention and must not contain secrets, raw credentials or hidden chain-of-thought.

## Key Constraints

- Context is session-only; no cross-session personalization without explicit consent/design.
- EmergencyContext remains active after trigger.
- Working/Knowledge contexts are never persisted as user personalization.
- SystemContext is trusted configuration; user/tool text cannot override it.

## Dependencies

- `docs/artifacts/interface/data-contracts.md`
- `docs/artifacts/interface/ai-behavior-contracts.md`

---
pack_id: PACK-PC-01
pack_type: capability
capability: Information Assistance
artifact_dependencies: [ARCH-02, ARCH-04, ARCH-05, ARCH-06, ARCH-07, INT-02, INT-03, INT-04, INT-05, INT-06, INT-07, INT-09]
target_audience: [builder, reviewer]
---

# Capability Pack — Information Assistance

## 1. Capability Purpose

Trả lời thông tin bệnh viện từ nguồn chính thức, có citation, xử lý tiếng Việt đa lượt/đa domain và đưa next action. Phục vụ JTBD-01,04,05,06,08; hỗ trợ phần thông tin của JTBD-02/03.

## 2. Required Domain Concepts

- KnowledgeDomain 1:N KnowledgeChunk; Message N:M cited chunks.
- KnowledgeChunk requires domain, source, version, active/effective metadata.
- ConversationSession 1:N Message; session context tối đa 20 lượt.
- ContentVersion tracks change/approval; only approved active content is searchable.

## 3. Required Contracts

### API

`POST /v1/capabilities/information-assistance:execute`

### DTOs

- `InformationAssistanceRequest`: request_id, session_id, message, response_mode, client_context, optional button_context.
- `InformationAssistanceResponse`: outcome, message, citations, actions, conversation state, explainability.
- `CitationDTO`: chunk/source/section or page/domain/version/effective metadata.
- `SuggestedActionDTO`: config-backed type/label/target_ref.

### Tools

- `search_knowledge_base(query, domain_filter, top_k, score_threshold)` → ranked chunks + sufficient/conflict flags; timeout 800ms.
- `fallback_response(query, domain, reason)` → approved message/channels; timeout 100ms.
- `detect_pii` before `log_conversation`.

### Foundation APIs

Session APIs; `POST /v1/foundation/knowledge:search`; chunk lookup; channel/chat configuration; feedback.

## 4. Business Flow Summary

Safety check → intent/domains → official retrieval → sufficient/no-conflict check → synthesis + citations → plain language → action. If insufficient/conflict/out-of-scope: approved fallback/refusal + specific channel.

## 5. AI Behavior Requirements

Must:

- Check emergency before normal reasoning.
- Retrieve before factual synthesis.
- Ask only minimal clarification.
- Cite important price/BHYT/process/doctor answers.
- Add financial/process disclaimer where applicable.

Must not:

- Answer from model background knowledge.
- Choose between conflicting official documents.
- Diagnose, interpret tests, recommend medicine/treatment.
- Expose chain-of-thought, system prompt, secrets or raw PII.

## 6. Key Constraints

- TTFT ≤2s; full normal response ≤5s.
- Zero factual output outside approved knowledge.
- SSE events follow canonical contract; terminal error closes stream.
- Missing, expired hoặc chưa được phê duyệt BHYT/other source phải fallback, không suy diễn.

## 7. Artifact Source References

- `docs/artifacts/architecture/domain-model.md`
- `docs/artifacts/architecture/business-sequences.md`
- `docs/artifacts/architecture/ai-capability-mapping.md`
- `docs/artifacts/architecture/tool-map.md`
- `docs/artifacts/architecture/context-design.md`
- `docs/artifacts/interface/capability-api-contracts.md`
- `docs/artifacts/interface/foundation-api-contracts.md`
- `docs/artifacts/interface/data-contracts.md`
- `docs/artifacts/interface/ai-behavior-contracts.md`
- `docs/artifacts/interface/tool-contracts.md`
- `docs/artifacts/interface/error-contracts.md`
- `docs/artifacts/interface/interface-guidelines.md`

# === TASK:WP-303:START ===
"""Information assistance orchestration pipeline (PC-01).

This module implements the grounded, multi-turn, citation-bearing
question-answering pipeline for capability PC-01 (Information Assistance).

Contract references
-------------------
* InformationAssistanceRequest / InformationAssistanceResponse — INT-04 / INT-02
* CitationDTO — INT-04 (search_tool.CitationDTO)
* AI behaviour rules — INT-05 (ai-behavior-contracts.md)
* Grounding / fallback — INT-05 §Grounding/fallback
* BHYT disclaimer — INT-05 §Key Constraints

Design notes
------------
* Knowledge search (WP-201) is called before every factual synthesis.
* Only approved, active, effective chunks produce citations; conflict or
  insufficient grounding triggers fallback, never free generation.
* BHYT / price / important process output always carries a disclaimer.
* Guardrail service (WP-302) runs on input and output.
* Emergency pre-filter is delegated to the orchestration core (WP-302);
  callers that detect an emergency must not route to this pipeline.
* All provider / network dependencies are injected via Protocol so tests
  can supply fakes without monkey-patching.
* Substantive business logic lives here, not in __init__.py.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from packages.contracts import (
    CATEGORY_AI,
    CATEGORY_SAFETY,
    MEDICAL_ADVICE_REFUSED,
    NO_GROUNDED_RESULT,
    OUT_OF_SCOPE,
    AI_PROVIDER_UNAVAILABLE,
    make_error_envelope,
    UnifiedErrorEnvelope,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public request / response DTOs (INT-04, INT-02 — PC-01)
# ---------------------------------------------------------------------------

OUTCOME_ANSWERED = "answered"
OUTCOME_CLARIFICATION_REQUIRED = "clarification_required"
OUTCOME_FALLBACK = "fallback"
OUTCOME_REFUSED = "refused"
OUTCOME_EMERGENCY_REROUTED = "emergency_rerouted"

BHYT_DISCLAIMER = (
    "Thông tin BHYT, giá dịch vụ và quy trình có thể thay đổi. "
    "Vui lòng xác nhận với bộ phận tiếp nhận hoặc BHYT để có thông tin chính xác nhất."
)
GENERAL_DISCLAIMER = (
    "Đây là thông tin tham khảo và không thay thế tư vấn y tế trực tiếp."
)
FALLBACK_CHANNEL = "1900-xxxx"
FALLBACK_MESSAGE = (
    "Xin lỗi, tôi không tìm thấy thông tin đủ căn cứ để trả lời câu hỏi này. "
    f"Vui lòng liên hệ tổng đài {FALLBACK_CHANNEL} hoặc bộ phận tiếp nhận để được hỗ trợ."
)
MEDICAL_REFUSAL_MESSAGE = (
    "Xin lỗi, tôi không thể đưa ra chẩn đoán, giải thích kết quả xét nghiệm "
    "hoặc khuyến nghị điều trị. Vui lòng tham khảo ý kiến bác sĩ hoặc gọi "
    f"{FALLBACK_CHANNEL} để được hỗ trợ."
)
OUT_OF_SCOPE_MESSAGE = (
    "Câu hỏi của bạn nằm ngoài phạm vi hỗ trợ. "
    f"Vui lòng liên hệ tổng đài {FALLBACK_CHANNEL} để được hỗ trợ."
)


@dataclass(frozen=True)
class InformationAssistanceRequest:
    """PC-01 request DTO (INT-04).

    Fields
    ------
    request_id : str
        Opaque identifier for idempotency / tracing.
    session_id : str
        Session identifier (used for conversation context).
    message : str
        User message, 1..4000 characters.
    conversation_history : list[dict]
        Previous turns (max 20), each {"role": str, "content": str}.
    response_mode : str
        "sync" or "stream" (default "sync").
    client_context : dict
        Optional client context metadata.
    button_context : dict | None
        Optional quick-reply / button context.
    """

    request_id: str
    session_id: str
    message: str
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    response_mode: str = "sync"
    client_context: Dict[str, Any] = field(default_factory=dict)
    button_context: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.message or not self.message.strip():
            raise ValueError("message must be non-empty")
        if len(self.message) > 4000:
            raise ValueError("message exceeds 4000 characters")
        if len(self.conversation_history) > 20:
            raise ValueError("conversation_history cannot exceed 20 turns")


@dataclass(frozen=True)
class CitationDTO:
    """Citation with provenance for grounded responses (INT-04).

    Mirrors the fields from search_tool.CitationDTO so the pipeline output
    is self-contained and does not leak internal RAG internals.
    """

    chunk_id: str
    content: str
    domain: str
    source_section: str
    effective_date: str
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "domain": self.domain,
            "source_section": self.source_section,
            "effective_date": self.effective_date,
            "score": self.score,
        }


@dataclass(frozen=True)
class ExplainabilityDTO:
    """Public explainability without chain-of-thought (INT-05).

    Never exposes system prompt, reasoning steps, or provider details.
    """

    citations: List[CitationDTO] = field(default_factory=list)
    confidence_band: str = "medium"
    fallback_reason: Optional[str] = None
    refusal_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "citations": [c.to_dict() for c in self.citations],
            "confidence_band": self.confidence_band,
        }
        if self.fallback_reason is not None:
            result["fallback_reason"] = self.fallback_reason
        if self.refusal_reason is not None:
            result["refusal_reason"] = self.refusal_reason
        return result


@dataclass(frozen=True)
class InformationAssistanceResponse:
    """PC-01 response DTO (INT-04 / INT-02).

    Outcomes: answered | clarification_required | fallback | refused |
              emergency_rerouted.
    """

    outcome: str
    message: str
    citations: List[CitationDTO] = field(default_factory=list)
    suggested_actions: List[Dict[str, Any]] = field(default_factory=list)
    disclaimers: List[str] = field(default_factory=list)
    conversation_state: Optional[Dict[str, Any]] = None
    explainability: Optional[ExplainabilityDTO] = None
    error: Optional[UnifiedErrorEnvelope] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "outcome": self.outcome,
            "message": self.message,
            "citations": [c.to_dict() for c in self.citations],
            "suggested_actions": list(self.suggested_actions),
            "disclaimers": list(self.disclaimers),
        }
        if self.conversation_state is not None:
            result["conversation_state"] = dict(self.conversation_state)
        if self.explainability is not None:
            result["explainability"] = self.explainability.to_dict()
        if self.error is not None:
            result["error"] = self.error.to_dict()
        return result


# ---------------------------------------------------------------------------
# Dependency protocols (test-friendly injection)
# ---------------------------------------------------------------------------


@runtime_checkable
class KnowledgeSearchProtocol(Protocol):
    """Minimal search interface consumed by the pipeline (WP-201)."""

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return dict with keys: chunks, has_results, sufficient, conflict."""
        ...


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """Minimal LLM generation interface consumed by the pipeline (WP-301)."""

    def generate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Return dict with key: content (the generated text)."""
        ...


@runtime_checkable
class GuardrailServiceProtocol(Protocol):
    """Input/output guardrail interface (WP-302)."""

    def check_input(
        self,
        message: str,
        conversation_context: Any = None,
    ) -> Any:
        """Return object/dict with .allowed / ['allowed'] and .violations."""
        ...

    def check_output(
        self,
        response: str,
        observations: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        """Return object/dict with .allowed / ['allowed'] and .safety_disposition."""
        ...


# ---------------------------------------------------------------------------
# Helper: normalise guardrail result to dict
# ---------------------------------------------------------------------------


def _guardrail_to_dict(result: Any) -> Dict[str, Any]:
    """Accept either a dataclass or a plain dict from the guardrail service."""
    if isinstance(result, dict):
        return result
    return result.to_dict()


# ---------------------------------------------------------------------------
# Pipeline keywords for BHYT / medical / scope detection
# ---------------------------------------------------------------------------

_BHYT_KEYWORDS = [
    "bhyt", "bảo hiểm", "bảo hiểm y tế", "quyền lợi", "mệnh giá",
    "chi phí", "giá", "phí", "viện phí",
]
_MEDICAL_KEYWORDS = [
    "chẩn đoán", "điều trị", "thuốc", "uống thuốc", "liều lượng",
    "kết quả xét nghiệm", "xét nghiệm", "bệnh này là gì",
    "tôi bị bệnh gì",
]
_FACTUAL_KEYWORDS = [
    "giờ", "phòng", "khoa", "dịch vụ", "địa chỉ", "đường",
    "quy trình", "thủ tục", "hỏi", "cho biết", "thông tin",
    "bhyt", "bảo hiểm", "chi phí", "giá", "lịch", "hoạt động",
]


def _needs_knowledge_search(message: str) -> bool:
    lower = message.lower()
    return any(kw in lower for kw in _FACTUAL_KEYWORDS)


def _is_bhyt_related(message: str) -> bool:
    lower = message.lower()
    return any(kw in lower for kw in _BHYT_KEYWORDS)


def _is_medical_advice_request(message: str) -> bool:
    lower = message.lower()
    return any(kw in lower for kw in _MEDICAL_KEYWORDS)


# ---------------------------------------------------------------------------
# Core pipeline class
# ---------------------------------------------------------------------------


class InformationAssistancePipeline:
    """Grounded multi-turn Q&A pipeline for PC-01 (Information Assistance).

    Execution order (INT-05 §Planning rules):
    1. Input guardrail check (injection / out-of-scope / medical advice)
    2. Knowledge search (mandatory for every factual synthesis)
    3. Grounding check — insufficient or conflict → fallback, no free generation
    4. LLM synthesis over grounded chunks only
    5. Output guardrail check
    6. Build citations + explainability
    7. Attach disclaimers (BHYT / price / general)

    Dependencies are all injected; the class never imports concrete providers.
    """

    def __init__(
        self,
        *,
        knowledge_search: Optional[KnowledgeSearchProtocol] = None,
        llm_provider: Optional[LLMProviderProtocol] = None,
        guardrail_service: Optional[GuardrailServiceProtocol] = None,
        fallback_message: Optional[str] = None,
        top_k: int = 5,
    ) -> None:
        self._knowledge_search = knowledge_search
        self._llm_provider = llm_provider
        self._guardrail_service = guardrail_service
        self._fallback_message = fallback_message or FALLBACK_MESSAGE
        self._top_k = top_k

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        request: InformationAssistanceRequest,
    ) -> InformationAssistanceResponse:
        """Run the full PC-01 pipeline for a single user message.

        Args:
            request: Validated InformationAssistanceRequest.

        Returns:
            InformationAssistanceResponse with outcome, message, citations,
            disclaimers and explainability.  Never raises; errors become
            fallback responses or error-envelope responses.
        """
        trace_id = str(uuid.uuid4())

        try:
            # Step 1 — input guardrails
            blocked = self._check_input_guardrails(request.message)
            if blocked is not None:
                return blocked

            # Step 2 — knowledge search (required for factual synthesis)
            search_result = self._run_knowledge_search(request)
            raw_citations: List[CitationDTO] = []

            if search_result is not None:
                # Step 3 — grounding check
                if search_result.get("conflict", False):
                    return self._make_fallback_response(
                        "knowledge_conflict",
                        "Tôi phát hiện thông tin mâu thuẫn về chủ đề này. "
                        f"Vui lòng liên hệ bộ phận tiếp nhận để được xác nhận.",
                    )

                chunks = search_result.get("chunks", [])
                sufficient = search_result.get("sufficient", False)
                has_results = search_result.get("has_results", False)

                if not has_results or not sufficient:
                    return self._make_fallback_response(
                        "insufficient_grounding",
                        self._fallback_message,
                    )

                raw_citations = self._build_citations(chunks)
            else:
                # No search tool available — only safe for non-factual turns
                if _needs_knowledge_search(request.message):
                    return self._make_fallback_response(
                        "knowledge_unavailable",
                        self._fallback_message,
                    )

            # Step 4 — LLM synthesis
            response_text = self._synthesise(request, raw_citations)

            # Step 5 — output guardrails
            output_blocked = self._check_output_guardrails(
                response_text, raw_citations
            )
            if output_blocked is not None:
                return output_blocked

            # Step 6 — disclaimers
            disclaimers = self._build_disclaimers(request.message, raw_citations)

            # Step 7 — assemble response
            explainability = ExplainabilityDTO(
                citations=raw_citations[:5],
                confidence_band="high" if raw_citations else "low",
            )

            return InformationAssistanceResponse(
                outcome=OUTCOME_ANSWERED,
                message=response_text,
                citations=raw_citations[:5],
                disclaimers=disclaimers,
                conversation_state={"session_id": request.session_id},
                explainability=explainability,
            )

        except Exception as exc:
            logger.exception("InformationAssistancePipeline.execute failed: %s", exc)
            return InformationAssistanceResponse(
                outcome=OUTCOME_FALLBACK,
                message=self._fallback_message,
                disclaimers=[GENERAL_DISCLAIMER],
                error=make_error_envelope(
                    code=AI_PROVIDER_UNAVAILABLE,
                    message=str(exc),
                    category=CATEGORY_AI,
                    trace_id=trace_id,
                    retryable=True,
                    retry_after_seconds=5,
                ),
            )

    # ------------------------------------------------------------------
    # Step 1 — input guardrails
    # ------------------------------------------------------------------

    def _check_input_guardrails(
        self, message: str
    ) -> Optional[InformationAssistanceResponse]:
        """Return a refused/fallback response if input is blocked, else None."""
        if self._guardrail_service is not None:
            try:
                result = self._guardrail_service.check_input(message)
                d = _guardrail_to_dict(result)
                if not d.get("allowed", True):
                    violations = d.get("violations", [])
                    # Detect medical advice refusal
                    v_types = [
                        v.get("violation_type", "") if isinstance(v, dict) else str(v)
                        for v in violations
                    ]
                    if any("medical" in vt for vt in v_types):
                        return InformationAssistanceResponse(
                            outcome=OUTCOME_REFUSED,
                            message=MEDICAL_REFUSAL_MESSAGE,
                            disclaimers=[GENERAL_DISCLAIMER],
                            explainability=ExplainabilityDTO(
                                refusal_reason=MEDICAL_ADVICE_REFUSED,
                                confidence_band="high",
                            ),
                            error=make_error_envelope(
                                code=MEDICAL_ADVICE_REFUSED,
                                message="Medical advice request refused",
                                category=CATEGORY_SAFETY,
                            ),
                        )
                    if any("out_of_scope" in vt for vt in v_types):
                        return InformationAssistanceResponse(
                            outcome=OUTCOME_REFUSED,
                            message=OUT_OF_SCOPE_MESSAGE,
                            disclaimers=[GENERAL_DISCLAIMER],
                            explainability=ExplainabilityDTO(
                                refusal_reason=OUT_OF_SCOPE,
                                confidence_band="high",
                            ),
                            error=make_error_envelope(
                                code=OUT_OF_SCOPE,
                                message="Out of scope request refused",
                                category=CATEGORY_SAFETY,
                            ),
                        )
                    # Generic block
                    return InformationAssistanceResponse(
                        outcome=OUTCOME_REFUSED,
                        message="Tin nhắn của bạn không thể được xử lý do vi phạm chính sách.",
                        disclaimers=[GENERAL_DISCLAIMER],
                        explainability=ExplainabilityDTO(
                            refusal_reason="policy_violation",
                            confidence_band="high",
                        ),
                    )
            except Exception as exc:
                logger.warning("Input guardrail check failed: %s", exc)

        # Heuristic medical advice check when no guardrail service is wired
        if _is_medical_advice_request(message):
            return InformationAssistanceResponse(
                outcome=OUTCOME_REFUSED,
                message=MEDICAL_REFUSAL_MESSAGE,
                disclaimers=[GENERAL_DISCLAIMER],
                explainability=ExplainabilityDTO(
                    refusal_reason=MEDICAL_ADVICE_REFUSED,
                    confidence_band="medium",
                ),
                error=make_error_envelope(
                    code=MEDICAL_ADVICE_REFUSED,
                    message="Medical advice request refused",
                    category=CATEGORY_SAFETY,
                ),
            )

        return None

    # ------------------------------------------------------------------
    # Step 2 — knowledge search
    # ------------------------------------------------------------------

    def _run_knowledge_search(
        self, request: InformationAssistanceRequest
    ) -> Optional[Dict[str, Any]]:
        """Call the knowledge search tool and return raw dict, or None."""
        if self._knowledge_search is None:
            return None

        try:
            result = self._knowledge_search.search(
                request.message,
                top_k=self._top_k,
            )
            # Normalise: tool may return a dataclass or dict
            if isinstance(result, dict):
                return result
            return result.to_dict()
        except Exception as exc:
            logger.error("Knowledge search failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Step 3 — citation builder
    # ------------------------------------------------------------------

    def _build_citations(
        self, chunks: List[Any]
    ) -> List[CitationDTO]:
        """Map raw chunk dicts / CitationDTO objects to public CitationDTO."""
        citations: List[CitationDTO] = []
        for chunk in chunks:
            try:
                if isinstance(chunk, dict):
                    citations.append(CitationDTO(
                        chunk_id=chunk.get("chunk_id", ""),
                        content=chunk.get("content", ""),
                        domain=chunk.get("domain", ""),
                        source_section=chunk.get("source_section", ""),
                        effective_date=chunk.get("effective_date", ""),
                        score=float(chunk.get("score", 0.0)),
                    ))
                else:
                    # Assume CitationDTO-like object
                    citations.append(CitationDTO(
                        chunk_id=chunk.chunk_id,
                        content=chunk.content,
                        domain=chunk.domain,
                        source_section=getattr(chunk, "source_section", ""),
                        effective_date=chunk.effective_date,
                        score=float(chunk.score),
                    ))
            except Exception as exc:
                logger.warning("Skipping malformed chunk: %s", exc)
        return citations

    # ------------------------------------------------------------------
    # Step 4 — LLM synthesis
    # ------------------------------------------------------------------

    def _synthesise(
        self,
        request: InformationAssistanceRequest,
        citations: List[CitationDTO],
    ) -> str:
        """Generate grounded response using the LLM provider."""
        if self._llm_provider is None:
            # No LLM — return concatenated citation content as the answer
            if citations:
                return citations[0].content
            return "Tôi đã ghi nhận yêu cầu của bạn nhưng không tìm thấy thông tin phù hợp."

        # Build context from approved citation content only
        context_chunks = [
            f"[{c.domain}] {c.content}" for c in citations[:self._top_k]
        ]
        context_text = "\n\n".join(context_chunks)

        # Build conversation history (max 20 turns)
        messages: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "Bạn là trợ lý thông tin bệnh viện. "
                    "Chỉ trả lời dựa trên ngữ cảnh được cung cấp. "
                    "Không chẩn đoán, không tư vấn điều trị, không xác định quyền lợi cá nhân."
                ),
            }
        ]
        for turn in request.conversation_history[-20:]:
            messages.append(turn)
        messages.append({"role": "user", "content": request.message})

        try:
            response = self._llm_provider.generate({
                "messages": messages,
                "context": context_text,
                "session_id": request.session_id,
            })
            return response.get("content", "").strip() or self._fallback_message
        except Exception as exc:
            logger.error("LLM generation failed: %s", exc)
            return self._fallback_message

    # ------------------------------------------------------------------
    # Step 5 — output guardrails
    # ------------------------------------------------------------------

    def _check_output_guardrails(
        self,
        response_text: str,
        citations: List[CitationDTO],
    ) -> Optional[InformationAssistanceResponse]:
        """Return a redacted response if output is blocked, else None."""
        if self._guardrail_service is None:
            return None
        try:
            obs = [c.to_dict() for c in citations]
            result = self._guardrail_service.check_output(response_text, obs)
            d = _guardrail_to_dict(result)
            if not d.get("allowed", True):
                return InformationAssistanceResponse(
                    outcome=OUTCOME_REFUSED,
                    message="Phản hồi đã được điều chỉnh do chính sách nội dung.",
                    disclaimers=[GENERAL_DISCLAIMER],
                    explainability=ExplainabilityDTO(
                        refusal_reason="output_policy_violation",
                        confidence_band="medium",
                    ),
                )
        except Exception as exc:
            logger.warning("Output guardrail check failed: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Step 7 — disclaimers
    # ------------------------------------------------------------------

    def _build_disclaimers(
        self, message: str, citations: List[CitationDTO]
    ) -> List[str]:
        """Build applicable disclaimers per INT-05."""
        disclaimers: List[str] = [GENERAL_DISCLAIMER]
        if _is_bhyt_related(message) or any(
            c.domain in ("bhyt", "insurance", "price") for c in citations
        ):
            disclaimers.append(BHYT_DISCLAIMER)
        return disclaimers

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_fallback_response(
        self, reason: str, message: str
    ) -> InformationAssistanceResponse:
        """Build a canonical fallback response (INT-05 §Grounding/fallback)."""
        return InformationAssistanceResponse(
            outcome=OUTCOME_FALLBACK,
            message=message,
            disclaimers=[GENERAL_DISCLAIMER],
            suggested_actions=[
                {"type": "contact", "channel": "hotline", "number": FALLBACK_CHANNEL},
                {"type": "contact", "channel": "reception"},
            ],
            explainability=ExplainabilityDTO(
                fallback_reason=reason,
                confidence_band="low",
            ),
            error=make_error_envelope(
                code=NO_GROUNDED_RESULT,
                message=reason,
                category=CATEGORY_AI,
            ),
        )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def run_information_assistance(
    request: InformationAssistanceRequest,
    *,
    knowledge_search: Optional[KnowledgeSearchProtocol] = None,
    llm_provider: Optional[LLMProviderProtocol] = None,
    guardrail_service: Optional[GuardrailServiceProtocol] = None,
) -> InformationAssistanceResponse:
    """One-shot convenience wrapper around InformationAssistancePipeline.

    Useful for callers that do not need to hold a long-lived pipeline instance.
    """
    pipeline = InformationAssistancePipeline(
        knowledge_search=knowledge_search,
        llm_provider=llm_provider,
        guardrail_service=guardrail_service,
    )
    return pipeline.execute(request)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    # Outcome constants
    "OUTCOME_ANSWERED",
    "OUTCOME_CLARIFICATION_REQUIRED",
    "OUTCOME_FALLBACK",
    "OUTCOME_REFUSED",
    "OUTCOME_EMERGENCY_REROUTED",
    # DTOs
    "InformationAssistanceRequest",
    "CitationDTO",
    "ExplainabilityDTO",
    "InformationAssistanceResponse",
    # Protocols
    "KnowledgeSearchProtocol",
    "LLMProviderProtocol",
    "GuardrailServiceProtocol",
    # Pipeline
    "InformationAssistancePipeline",
    "run_information_assistance",
    # Disclaimer strings (useful in tests)
    "BHYT_DISCLAIMER",
    "GENERAL_DISCLAIMER",
    "FALLBACK_MESSAGE",
    "MEDICAL_REFUSAL_MESSAGE",
    "OUT_OF_SCOPE_MESSAGE",
    "FALLBACK_CHANNEL",
]
# === TASK:WP-303:END ===

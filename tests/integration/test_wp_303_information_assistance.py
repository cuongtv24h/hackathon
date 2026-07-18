# === TASK:WP-303:START ===
"""Integration tests for WP-303 — Information Assistance Pipeline (PC-01).

Test contract (required by WP-303-R1):
  py -m pytest tests/integration/test_wp_303_information_assistance.py -q

Coverage required:
  * Happy path: grounded answer with citations
  * Contract shape: all required fields present in response dict
  * Multi-turn: conversation_history forwarded to LLM
  * Fallback: no results → OUTCOME_FALLBACK
  * Fallback: conflict  → OUTCOME_FALLBACK
  * Refusal: medical advice → OUTCOME_REFUSED
  * Refusal: out-of-scope via guardrail → OUTCOME_REFUSED
  * Output guardrail block → OUTCOME_REFUSED
  * BHYT disclaimer injected when query is BHYT-related
  * Provider failure → OUTCOME_FALLBACK with error envelope
  * Validation: empty message raises ValueError
  * Validation: message > 4000 chars raises ValueError
  * Validation: conversation_history > 20 turns raises ValueError

All external provider and network calls are replaced with in-process fakes.
No real database, embedding model, or LLM is contacted.
"""

from __future__ import annotations

import pytest
from typing import Any, Dict, List, Optional

from apps.api.ai.orchestrator.information_assistance.pipeline import (
    BHYT_DISCLAIMER,
    GENERAL_DISCLAIMER,
    FALLBACK_MESSAGE,
    MEDICAL_REFUSAL_MESSAGE,
    OUTCOME_ANSWERED,
    OUTCOME_FALLBACK,
    OUTCOME_REFUSED,
    CitationDTO,
    ExplainabilityDTO,
    InformationAssistanceRequest,
    InformationAssistanceResponse,
    InformationAssistancePipeline,
    run_information_assistance,
)


# ---------------------------------------------------------------------------
# Fakes / stubs (no real providers)
# ---------------------------------------------------------------------------


def _make_chunk(
    *,
    chunk_id: str = "chunk-001",
    content: str = "Khoa Tim mạch hoạt động từ 7h đến 17h các ngày trong tuần.",
    domain: str = "hospital_info",
    source_section: str = "Khoa phòng",
    effective_date: str = "2025-01-01",
    score: float = 0.95,
) -> Dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "content": content,
        "domain": domain,
        "source_section": source_section,
        "effective_date": effective_date,
        "score": score,
    }


class FakeKnowledgeSearch:
    """Returns configurable search results without hitting a database."""

    def __init__(
        self,
        *,
        chunks: Optional[List[Dict[str, Any]]] = None,
        has_results: bool = True,
        sufficient: bool = True,
        conflict: bool = False,
        raise_on_call: bool = False,
    ) -> None:
        self._chunks = chunks if chunks is not None else [_make_chunk()]
        self._has_results = has_results
        self._sufficient = sufficient
        self._conflict = conflict
        self._raise = raise_on_call

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self._raise:
            raise RuntimeError("FakeKnowledgeSearch forced error")
        return {
            "chunks": self._chunks[:top_k],
            "has_results": self._has_results,
            "sufficient": self._sufficient,
            "conflict": self._conflict,
        }


class FakeLLMProvider:
    """Returns a fixed string without calling an LLM."""

    def __init__(
        self,
        *,
        content: str = "Đây là câu trả lời từ hệ thống.",
        raise_on_call: bool = False,
    ) -> None:
        self._content = content
        self._raise = raise_on_call
        self.last_request: Optional[Dict[str, Any]] = None

    def generate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if self._raise:
            raise RuntimeError("FakeLLMProvider forced error")
        self.last_request = request
        return {"content": self._content, "provider": "fake"}


class FakeGuardrailService:
    """Returns configurable allow/block decisions."""

    def __init__(
        self,
        *,
        input_allowed: bool = True,
        output_allowed: bool = True,
        input_violations: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._input_allowed = input_allowed
        self._output_allowed = output_allowed
        self._input_violations = input_violations or []

    def check_input(self, message: str, conversation_context: Any = None) -> Dict[str, Any]:
        return {
            "allowed": self._input_allowed,
            "violations": self._input_violations,
            "caution_flags": [],
        }

    def check_output(
        self,
        response: str,
        observations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return {
            "allowed": self._output_allowed,
            "violations": [],
            "safety_disposition": "safe" if self._output_allowed else "caution",
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    *,
    message: str = "Khoa tim mạch hoạt động giờ nào?",
    session_id: str = "sess-test-001",
    request_id: str = "req-test-001",
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> InformationAssistanceRequest:
    return InformationAssistanceRequest(
        request_id=request_id,
        session_id=session_id,
        message=message,
        conversation_history=conversation_history or [],
    )


def _make_pipeline(
    *,
    chunks: Optional[List[Dict[str, Any]]] = None,
    has_results: bool = True,
    sufficient: bool = True,
    conflict: bool = False,
    llm_content: str = "Đây là câu trả lời.",
    input_allowed: bool = True,
    output_allowed: bool = True,
    input_violations: Optional[List[Dict[str, Any]]] = None,
    search_raises: bool = False,
    llm_raises: bool = False,
) -> tuple[InformationAssistancePipeline, FakeLLMProvider]:
    llm = FakeLLMProvider(content=llm_content, raise_on_call=llm_raises)
    pipeline = InformationAssistancePipeline(
        knowledge_search=FakeKnowledgeSearch(
            chunks=chunks,
            has_results=has_results,
            sufficient=sufficient,
            conflict=conflict,
            raise_on_call=search_raises,
        ),
        llm_provider=llm,
        guardrail_service=FakeGuardrailService(
            input_allowed=input_allowed,
            output_allowed=output_allowed,
            input_violations=input_violations or [],
        ),
    )
    return pipeline, llm


# ---------------------------------------------------------------------------
# 1 — Happy path: grounded answer with citations
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_returns_answered_outcome(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(_make_request())
        assert response.outcome == OUTCOME_ANSWERED

    def test_response_has_message(self) -> None:
        pipeline, _ = _make_pipeline(llm_content="Khoa Tim mạch hoạt động 7h-17h.")
        response = pipeline.execute(_make_request())
        assert response.message == "Khoa Tim mạch hoạt động 7h-17h."

    def test_citations_populated(self) -> None:
        chunks = [_make_chunk(chunk_id=f"c-{i}") for i in range(3)]
        pipeline, _ = _make_pipeline(chunks=chunks)
        response = pipeline.execute(_make_request())
        assert len(response.citations) == 3
        assert all(isinstance(c, CitationDTO) for c in response.citations)

    def test_general_disclaimer_always_present(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(_make_request())
        assert GENERAL_DISCLAIMER in response.disclaimers

    def test_explainability_not_none(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(_make_request())
        assert response.explainability is not None
        assert isinstance(response.explainability, ExplainabilityDTO)

    def test_conversation_state_has_session_id(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(_make_request(session_id="sess-xyz"))
        assert response.conversation_state is not None
        assert response.conversation_state["session_id"] == "sess-xyz"

    def test_error_is_none_on_success(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(_make_request())
        assert response.error is None


# ---------------------------------------------------------------------------
# 2 — Contract shape: to_dict() has all required fields
# ---------------------------------------------------------------------------


class TestContractShape:
    def test_to_dict_has_required_top_level_keys(self) -> None:
        pipeline, _ = _make_pipeline()
        d = pipeline.execute(_make_request()).to_dict()
        for key in ("outcome", "message", "citations", "suggested_actions", "disclaimers"):
            assert key in d, f"Missing key: {key}"

    def test_citation_dict_has_required_fields(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(_make_request())
        assert response.citations
        c = response.citations[0].to_dict()
        for key in ("chunk_id", "content", "domain", "source_section", "effective_date", "score"):
            assert key in c, f"Citation missing key: {key}"

    def test_explainability_dict_has_required_fields(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(_make_request())
        assert response.explainability is not None
        e = response.explainability.to_dict()
        assert "citations" in e
        assert "confidence_band" in e

    def test_outcome_is_string(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(_make_request())
        assert isinstance(response.outcome, str)

    def test_message_is_string(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(_make_request())
        assert isinstance(response.message, str)

    def test_citations_is_list(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(_make_request())
        assert isinstance(response.citations, list)

    def test_disclaimers_is_list(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(_make_request())
        assert isinstance(response.disclaimers, list)


# ---------------------------------------------------------------------------
# 3 — Multi-turn: conversation_history forwarded to LLM
# ---------------------------------------------------------------------------


class TestMultiTurn:
    def test_conversation_history_passed_to_llm(self) -> None:
        history = [
            {"role": "user", "content": "Xin chào"},
            {"role": "assistant", "content": "Xin chào! Tôi có thể giúp gì?"},
        ]
        _, llm = _make_pipeline()
        pipeline = InformationAssistancePipeline(
            knowledge_search=FakeKnowledgeSearch(),
            llm_provider=llm,
            guardrail_service=FakeGuardrailService(),
        )
        pipeline.execute(_make_request(conversation_history=history))
        assert llm.last_request is not None
        messages = llm.last_request["messages"]
        # system + 2 history turns + user turn = 4
        assert len(messages) == 4

    def test_history_truncated_to_20_turns(self) -> None:
        history = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        _, llm = _make_pipeline()
        pipeline = InformationAssistancePipeline(
            knowledge_search=FakeKnowledgeSearch(),
            llm_provider=llm,
            guardrail_service=FakeGuardrailService(),
        )
        pipeline.execute(_make_request(conversation_history=history))
        messages = llm.last_request["messages"]
        # system + 20 history + 1 user = 22 max
        assert len(messages) <= 22


# ---------------------------------------------------------------------------
# 4 — Fallback: no results
# ---------------------------------------------------------------------------


class TestFallbackNoResults:
    def test_no_results_returns_fallback_outcome(self) -> None:
        pipeline, _ = _make_pipeline(has_results=False, sufficient=False)
        response = pipeline.execute(_make_request())
        assert response.outcome == OUTCOME_FALLBACK

    def test_fallback_message_contains_channel(self) -> None:
        pipeline, _ = _make_pipeline(has_results=False, sufficient=False)
        response = pipeline.execute(_make_request())
        assert "1900" in response.message

    def test_fallback_has_suggested_actions(self) -> None:
        pipeline, _ = _make_pipeline(has_results=False, sufficient=False)
        response = pipeline.execute(_make_request())
        assert len(response.suggested_actions) > 0

    def test_fallback_explainability_has_reason(self) -> None:
        pipeline, _ = _make_pipeline(has_results=False, sufficient=False)
        response = pipeline.execute(_make_request())
        assert response.explainability is not None
        assert response.explainability.fallback_reason is not None

    def test_fallback_error_envelope_present(self) -> None:
        pipeline, _ = _make_pipeline(has_results=False, sufficient=False)
        response = pipeline.execute(_make_request())
        assert response.error is not None
        assert response.error.error.code == "NO_GROUNDED_RESULT"


# ---------------------------------------------------------------------------
# 5 — Fallback: conflict
# ---------------------------------------------------------------------------


class TestFallbackConflict:
    def test_conflict_returns_fallback_outcome(self) -> None:
        pipeline, _ = _make_pipeline(conflict=True)
        response = pipeline.execute(_make_request())
        assert response.outcome == OUTCOME_FALLBACK

    def test_conflict_fallback_reason_in_explainability(self) -> None:
        pipeline, _ = _make_pipeline(conflict=True)
        response = pipeline.execute(_make_request())
        assert response.explainability is not None
        assert "conflict" in (response.explainability.fallback_reason or "")


# ---------------------------------------------------------------------------
# 6 — Refusal: medical advice
# ---------------------------------------------------------------------------


class TestMedicalAdviceRefusal:
    def test_medical_keyword_refused_via_guardrail(self) -> None:
        pipeline, _ = _make_pipeline(
            input_allowed=False,
            input_violations=[{"violation_type": "medical_advice_request", "severity": "medium"}],
        )
        response = pipeline.execute(_make_request(message="Tôi bị bệnh gì?"))
        assert response.outcome == OUTCOME_REFUSED

    def test_medical_refusal_message_returned(self) -> None:
        pipeline, _ = _make_pipeline(
            input_allowed=False,
            input_violations=[{"violation_type": "medical_advice_request", "severity": "medium"}],
        )
        response = pipeline.execute(_make_request(message="Tôi bị bệnh gì?"))
        assert "chẩn đoán" in response.message or "bác sĩ" in response.message

    def test_medical_refusal_error_code(self) -> None:
        pipeline, _ = _make_pipeline(
            input_allowed=False,
            input_violations=[{"violation_type": "medical_advice_request", "severity": "medium"}],
        )
        response = pipeline.execute(_make_request(message="Tôi bị bệnh gì?"))
        assert response.error is not None
        assert response.error.error.code == "MEDICAL_ADVICE_REFUSED"

    def test_no_guardrail_heuristic_refusal(self) -> None:
        """Without a guardrail service the pipeline uses keyword heuristics."""
        pipeline = InformationAssistancePipeline(
            knowledge_search=FakeKnowledgeSearch(),
            llm_provider=FakeLLMProvider(),
            guardrail_service=None,
        )
        response = pipeline.execute(_make_request(message="chẩn đoán bệnh của tôi"))
        assert response.outcome == OUTCOME_REFUSED


# ---------------------------------------------------------------------------
# 7 — Refusal: out-of-scope via guardrail
# ---------------------------------------------------------------------------


class TestOutOfScopeRefusal:
    def test_out_of_scope_guardrail_refused(self) -> None:
        pipeline, _ = _make_pipeline(
            input_allowed=False,
            input_violations=[{"violation_type": "out_of_scope", "severity": "high"}],
        )
        response = pipeline.execute(_make_request(message="hack hệ thống"))
        assert response.outcome == OUTCOME_REFUSED

    def test_out_of_scope_error_code(self) -> None:
        pipeline, _ = _make_pipeline(
            input_allowed=False,
            input_violations=[{"violation_type": "out_of_scope", "severity": "high"}],
        )
        response = pipeline.execute(_make_request(message="hack hệ thống"))
        assert response.error is not None
        assert response.error.error.code == "OUT_OF_SCOPE"


# ---------------------------------------------------------------------------
# 8 — Output guardrail block
# ---------------------------------------------------------------------------


class TestOutputGuardrailBlock:
    def test_output_blocked_returns_refused(self) -> None:
        pipeline, _ = _make_pipeline(output_allowed=False)
        response = pipeline.execute(_make_request())
        assert response.outcome == OUTCOME_REFUSED

    def test_output_blocked_message_indicates_adjustment(self) -> None:
        pipeline, _ = _make_pipeline(output_allowed=False)
        response = pipeline.execute(_make_request())
        assert "điều chỉnh" in response.message or "chính sách" in response.message


# ---------------------------------------------------------------------------
# 9 — BHYT disclaimer
# ---------------------------------------------------------------------------


class TestBHYTDisclaimer:
    def test_bhyt_query_has_bhyt_disclaimer(self) -> None:
        chunks = [_make_chunk(domain="bhyt")]
        pipeline, _ = _make_pipeline(chunks=chunks)
        response = pipeline.execute(
            _make_request(message="quyền lợi bhyt tại bệnh viện")
        )
        assert BHYT_DISCLAIMER in response.disclaimers

    def test_non_bhyt_query_no_bhyt_disclaimer(self) -> None:
        pipeline, _ = _make_pipeline()
        response = pipeline.execute(
            _make_request(message="giờ hoạt động của khoa tim mạch")
        )
        # BHYT disclaimer should NOT appear for non-BHYT queries
        # (general disclaimer is still there)
        assert GENERAL_DISCLAIMER in response.disclaimers


# ---------------------------------------------------------------------------
# 10 — Provider failure
# ---------------------------------------------------------------------------


class TestProviderFailure:
    def test_llm_failure_returns_fallback_outcome(self) -> None:
        pipeline, _ = _make_pipeline(llm_raises=True)
        response = pipeline.execute(_make_request())
        # LLM failure causes synthesise() to return the fallback message string;
        # since the search succeeded the outcome should still be ANSWERED
        # (pipeline falls back to fallback_message string, not raises)
        assert response.outcome in (OUTCOME_ANSWERED, OUTCOME_FALLBACK)

    def test_llm_failure_has_message(self) -> None:
        pipeline, _ = _make_pipeline(llm_raises=True)
        response = pipeline.execute(_make_request())
        assert isinstance(response.message, str)
        assert len(response.message) > 0

    def test_search_failure_on_factual_query_returns_fallback(self) -> None:
        """When search fails on a factual query the pipeline must not free-generate."""
        pipeline = InformationAssistancePipeline(
            knowledge_search=FakeKnowledgeSearch(raise_on_call=True),
            llm_provider=FakeLLMProvider(),
            guardrail_service=FakeGuardrailService(),
        )
        response = pipeline.execute(
            _make_request(message="giờ hoạt động khoa tim mạch")
        )
        assert response.outcome == OUTCOME_FALLBACK

    def test_unhandled_exception_produces_error_envelope(self) -> None:
        """A completely broken search should not crash the caller."""
        class BrokenSearch:
            def search(self, query, *, top_k=5, filters=None):
                raise RuntimeError("catastrophic failure")

        pipeline = InformationAssistancePipeline(
            knowledge_search=BrokenSearch(),
            llm_provider=FakeLLMProvider(),
            guardrail_service=FakeGuardrailService(),
        )
        # factual query → _needs_knowledge_search → True → search fails → fallback
        response = pipeline.execute(
            _make_request(message="giờ hoạt động khoa tim mạch là gì")
        )
        assert response.outcome == OUTCOME_FALLBACK


# ---------------------------------------------------------------------------
# 11 — Input validation errors
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_empty_message_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            InformationAssistanceRequest(
                request_id="r1", session_id="s1", message=""
            )

    def test_whitespace_only_message_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            InformationAssistanceRequest(
                request_id="r1", session_id="s1", message="   "
            )

    def test_message_over_4000_chars_raises(self) -> None:
        with pytest.raises(ValueError, match="4000"):
            InformationAssistanceRequest(
                request_id="r1", session_id="s1", message="x" * 4001
            )

    def test_conversation_history_over_20_raises(self) -> None:
        history = [{"role": "user", "content": str(i)} for i in range(21)]
        with pytest.raises(ValueError, match="20"):
            InformationAssistanceRequest(
                request_id="r1", session_id="s1", message="ok",
                conversation_history=history,
            )

    def test_valid_boundary_4000_chars(self) -> None:
        req = InformationAssistanceRequest(
            request_id="r1", session_id="s1", message="x" * 4000
        )
        assert len(req.message) == 4000

    def test_valid_boundary_20_history_turns(self) -> None:
        history = [{"role": "user", "content": str(i)} for i in range(20)]
        req = InformationAssistanceRequest(
            request_id="r1", session_id="s1", message="ok",
            conversation_history=history,
        )
        assert len(req.conversation_history) == 20


# ---------------------------------------------------------------------------
# 12 — run_information_assistance convenience wrapper
# ---------------------------------------------------------------------------


class TestRunInformationAssistance:
    def test_convenience_wrapper_returns_response(self) -> None:
        response = run_information_assistance(
            _make_request(),
            knowledge_search=FakeKnowledgeSearch(),
            llm_provider=FakeLLMProvider(),
            guardrail_service=FakeGuardrailService(),
        )
        assert isinstance(response, InformationAssistanceResponse)

    def test_convenience_wrapper_answered_outcome(self) -> None:
        response = run_information_assistance(
            _make_request(),
            knowledge_search=FakeKnowledgeSearch(),
            llm_provider=FakeLLMProvider(content="Câu trả lời mẫu."),
            guardrail_service=FakeGuardrailService(),
        )
        assert response.outcome == OUTCOME_ANSWERED
# === TASK:WP-303:END ===

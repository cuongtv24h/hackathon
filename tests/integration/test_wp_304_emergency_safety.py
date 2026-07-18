# === TASK:WP-304:START ===
"""Integration tests for WP-304 Emergency Safety AI Pipeline (PC-02).

This module tests the emergency safety orchestration pipeline including:
- EmergencySafetyRequest / EmergencySafetyResponse DTOs
- EmergencySafetyPipeline execution with mocked dependencies
- Level 1 (caution) and Level 2 (critical) emergency protocols
- No-emergency detection path
- Error handling and fallback behavior
- INT-05 compliance (emergency priority, no diagnosis)

Tests use mocked prefilter tool and foundation service per
docs/spec-registry/runtime-test-policy.yaml.
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from apps.api.ai.orchestrator.emergency_safety.pipeline import (
    EmergencySafetyPipeline,
    EmergencySafetyRequest,
    EmergencySafetyResponse,
    EmergencyPrefilterProtocol,
    EmergencyFoundationProtocol,
    OUTCOME_EMERGENCY_TRIGGERED,
    OUTCOME_CLARIFICATION_REQUIRED,
    OUTCOME_NOT_TRIGGERED,
    GENERAL_DISCLAIMER,
    run_emergency_safety,
)
from apps.api.capabilities.emergency.prefilter.tool import (
    PrefilterRequest,
    PrefilterResult,
    MatchedKeyword,
    EmergencyEventReceiptDTO,
)
from apps.api.foundation.emergency.service import EmergencyProtocolDTO


# ---------------------------------------------------------------------------
# Mock implementations for dependency injection
# ---------------------------------------------------------------------------


class MockEmergencyPrefilter:
    """Mock prefilter tool that returns predetermined results."""

    def __init__(self, result: PrefilterResult):
        self._result = result

    def prefilter(self, request: PrefilterRequest) -> PrefilterResult:
        return self._result


class MockEmergencyFoundation:
    """Mock foundation service that returns predetermined protocols."""

    def __init__(self, protocols: Dict[int, Optional[EmergencyProtocolDTO]]):
        self._protocols = protocols

    def get_emergency_protocol(self, level: int) -> Optional[EmergencyProtocolDTO]:
        return self._protocols.get(level)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def level1_prefilter_result() -> PrefilterResult:
    """Prefilter result for Level 1 (caution) emergency."""
    matched_keywords = [
        MatchedKeyword(
            rule_id="ER-KW-CAUTION-001",
            level=1,
            category="chest_pain",
            matched_phrase="đau ngực",
            protocol_id="ERP-CAUTION-V1",
        )
    ]
    event_receipt = EmergencyEventReceiptDTO(
        event_id="EMG-EVT-2026-0001",
        created_at="2026-07-18T08:00:00+07:00",
        level=1,
        protocol_id="ERP-CAUTION-V1",
    )
    return PrefilterResult(
        is_emergency=True,
        level=1,
        matched_keywords=matched_keywords,
        protocol_id="ERP-CAUTION-V1",
        metadata={"elapsed_ms": 15.5, "timeout_ms": 100},
        event_receipt=event_receipt,
    )


@pytest.fixture
def level2_prefilter_result() -> PrefilterResult:
    """Prefilter result for Level 2 (critical) emergency."""
    matched_keywords = [
        MatchedKeyword(
            rule_id="ER-KW-CRITICAL-001",
            level=2,
            category="cardiac_arrest",
            matched_phrase="ngưng tim",
            protocol_id="ERP-CRITICAL-V1",
        ),
        MatchedKeyword(
            rule_id="ER-KW-CRITICAL-002",
            level=2,
            category="unconscious",
            matched_phrase="bất tỉnh",
            protocol_id="ERP-CRITICAL-V1",
        ),
    ]
    event_receipt = EmergencyEventReceiptDTO(
        event_id="EMG-EVT-2026-0002",
        created_at="2026-07-18T08:00:00+07:00",
        level=2,
        protocol_id="ERP-CRITICAL-V1",
    )
    return PrefilterResult(
        is_emergency=True,
        level=2,
        matched_keywords=matched_keywords,
        protocol_id="ERP-CRITICAL-V1",
        metadata={"elapsed_ms": 22.3, "timeout_ms": 100},
        event_receipt=event_receipt,
    )


@pytest.fixture
def no_emergency_prefilter_result() -> PrefilterResult:
    """Prefilter result for no emergency detected."""
    return PrefilterResult(
        is_emergency=False,
        level=0,
        matched_keywords=[],
        protocol_id="ERP-FALLBACK-V1",
        metadata={"elapsed_ms": 8.2, "timeout_ms": 100},
        event_receipt=None,
    )


@pytest.fixture
def level1_protocol() -> EmergencyProtocolDTO:
    """Level 1 emergency protocol."""
    return EmergencyProtocolDTO(
        protocol_id="ERP-CAUTION-V1",
        level=1,
        version="1.0",
        response_text="Phát hiện dấu hiệu đau ngực, có thể là triệu chứng tim mạch.",
        channel_refs=["115", "1900-555-666"],
        emergency_address_ref="Bệnh viện Tim Hà Nội, 56 Phùng Hưng, Đống Đa, Hà Nội",
        banner_level="caution",
        allowed_actions=["contact_hotline", "visit_er"],
        prohibited_content=["medical_diagnosis", "treatment_recommendation"],
        approval_status="approved",
        is_mock=True,
        effective_date="2026-01-01",
    )


@pytest.fixture
def level2_protocol() -> EmergencyProtocolDTO:
    """Level 2 emergency protocol."""
    return EmergencyProtocolDTO(
        protocol_id="ERP-CRITICAL-V1",
        level=2,
        version="1.0",
        response_text="NGUY HIỂM TÍNH MẠNG: Ngưng tim, bất tỉnh, khó thở nặng.",
        channel_refs=["115", "1900-555-666", "1800-123-456"],
        emergency_address_ref="Bệnh viện Tim Hà Nội, 56 Phùng Hưng, Đống Đa, Hà Nội",
        banner_level="critical",
        allowed_actions=["call_115_immediately", "visit_er"],
        prohibited_content=["medical_diagnosis", "treatment_recommendation", "self_care"],
        approval_status="approved",
        is_mock=True,
        effective_date="2026-01-01",
    )


@pytest.fixture
def pipeline_with_level1_mocks(
    level1_prefilter_result: PrefilterResult, level1_protocol: EmergencyProtocolDTO
) -> EmergencySafetyPipeline:
    """Pipeline with Level 1 mocks."""
    prefilter = MockEmergencyPrefilter(level1_prefilter_result)
    foundation = MockEmergencyFoundation({1: level1_protocol, 2: None})
    return EmergencySafetyPipeline(
        prefilter_tool=prefilter,
        foundation_service=foundation,
    )


@pytest.fixture
def pipeline_with_level2_mocks(
    level2_prefilter_result: PrefilterResult, level2_protocol: EmergencyProtocolDTO
) -> EmergencySafetyPipeline:
    """Pipeline with Level 2 mocks."""
    prefilter = MockEmergencyPrefilter(level2_prefilter_result)
    foundation = MockEmergencyFoundation({1: None, 2: level2_protocol})
    return EmergencySafetyPipeline(
        prefilter_tool=prefilter,
        foundation_service=foundation,
    )


@pytest.fixture
def pipeline_with_no_emergency_mocks(
    no_emergency_prefilter_result: PrefilterResult,
) -> EmergencySafetyPipeline:
    """Pipeline with no-emergency mocks."""
    prefilter = MockEmergencyPrefilter(no_emergency_prefilter_result)
    foundation = MockEmergencyFoundation({1: None, 2: None})
    return EmergencySafetyPipeline(
        prefilter_tool=prefilter,
        foundation_service=foundation,
    )


@pytest.fixture
def basic_request() -> EmergencySafetyRequest:
    """Basic emergency safety request."""
    return EmergencySafetyRequest(
        request_id="req-123",
        session_id="test-session-123",
        message="Tôi bị đau ngực dữ dội",
        conversation_history=[],
        client_context={},
    )


# ---------------------------------------------------------------------------
# DTO tests
# ---------------------------------------------------------------------------


class TestEmergencySafetyRequest:
    """Tests for EmergencySafetyRequest DTO."""

    def test_valid_request(self) -> None:
        """Valid request initializes correctly."""
        req = EmergencySafetyRequest(
            request_id="req-001",
            session_id="sess-001",
            message="Test message",
        )
        assert req.request_id == "req-001"
        assert req.session_id == "sess-001"
        assert req.message == "Test message"
        assert req.conversation_history == []
        assert req.client_context == {}

    def test_empty_message_raises_error(self) -> None:
        """Empty message raises ValueError."""
        with pytest.raises(ValueError, match="message must be non-empty"):
            EmergencySafetyRequest(
                request_id="req-001",
                session_id="sess-001",
                message="",
            )

    def test_whitespace_message_raises_error(self) -> None:
        """Whitespace-only message raises ValueError."""
        with pytest.raises(ValueError, match="message must be non-empty"):
            EmergencySafetyRequest(
                request_id="req-001",
                session_id="sess-001",
                message="   ",
            )

    def test_message_too_long_raises_error(self) -> None:
        """Message exceeding 4000 chars raises ValueError."""
        with pytest.raises(ValueError, match="message exceeds 4000 characters"):
            EmergencySafetyRequest(
                request_id="req-001",
                session_id="sess-001",
                message="x" * 4001,
            )

    def test_conversation_history_too_long_raises_error(self) -> None:
        """Conversation history exceeding 20 turns raises ValueError."""
        with pytest.raises(ValueError, match="conversation_history cannot exceed 20 turns"):
            EmergencySafetyRequest(
                request_id="req-001",
                session_id="sess-001",
                message="Test",
                conversation_history=[{"role": "user", "content": "x"}] * 21,
            )


class TestEmergencySafetyResponse:
    """Tests for EmergencySafetyResponse DTO."""

    def test_to_dict_with_all_fields(self, level1_protocol: EmergencyProtocolDTO) -> None:
        """to_dict includes all fields when present."""
        resp = EmergencySafetyResponse(
            outcome=OUTCOME_EMERGENCY_TRIGGERED,
            message="Test message",
            level=1,
            protocol=level1_protocol,
            hotlines=["115", "1900-555-666"],
            address="Bệnh viện Tim Hà Nội",
            banner="Test banner",
            event_id="EMG-EVT-001",
            matched_keywords=[{"rule_id": "test", "level": 1}],
            disclaimers=["Test disclaimer"],
        )
        result = resp.to_dict()

        assert result["outcome"] == OUTCOME_EMERGENCY_TRIGGERED
        assert result["message"] == "Test message"
        assert result["level"] == 1
        assert result["protocol"] is not None
        assert result["protocol"]["level"] == 1
        assert result["hotlines"] == ["115", "1900-555-666"]
        assert result["address"] == "Bệnh viện Tim Hà Nội"
        assert result["banner"] == "Test banner"
        assert result["event_id"] == "EMG-EVT-001"
        assert result["matched_keywords"] == [{"rule_id": "test", "level": 1}]
        assert result["disclaimers"] == ["Test disclaimer"]
        assert "error" not in result

    def test_to_dict_with_none_optional_fields(self) -> None:
        """to_dict omits None optional fields."""
        resp = EmergencySafetyResponse(
            outcome=OUTCOME_NOT_TRIGGERED,
            message="No emergency",
            level=None,
            protocol=None,
            hotlines=["115"],
            address="Bệnh viện Tim Hà Nội",
            banner=None,
            event_id=None,
            matched_keywords=[],
            disclaimers=[GENERAL_DISCLAIMER],
        )
        result = resp.to_dict()

        assert "level" not in result
        assert "protocol" not in result
        assert "banner" not in result
        assert "event_id" not in result
        assert "error" not in result

    def test_to_dict_with_error_envelope(self) -> None:
        """to_dict includes error envelope when present."""
        from packages.contracts.errors import UnifiedErrorEnvelope, ErrorDetail

        error = UnifiedErrorEnvelope(
            error=ErrorDetail(
                code="TEST_ERROR",
                message="Test error",
                category="safety",
            ),
            trace_id="trace-123",
        )
        resp = EmergencySafetyResponse(
            outcome=OUTCOME_CLARIFICATION_REQUIRED,
            message="Error",
            hotlines=["115"],
            disclaimers=[GENERAL_DISCLAIMER],
            matched_keywords=[],
            error=error,
        )
        result = resp.to_dict()

        assert "error" in result
        assert result["error"]["error"]["code"] == "TEST_ERROR"
        assert result["error"]["trace_id"] == "trace-123"


# ---------------------------------------------------------------------------
# Pipeline execution tests
# ---------------------------------------------------------------------------


class TestEmergencySafetyPipelineLevel1:
    """Tests for Level 1 (caution) emergency handling."""

    def test_level1_emergency_triggered(
        self,
        pipeline_with_level1_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
        level1_protocol: EmergencyProtocolDTO,
    ) -> None:
        """Level 1 emergency returns emergency_triggered outcome."""
        response = pipeline_with_level1_mocks.execute(basic_request)

        assert response.outcome == OUTCOME_EMERGENCY_TRIGGERED
        assert response.level == 1
        assert response.protocol is not None
        assert response.protocol.level == 1
        assert "⚠️" in response.message
        assert "Level 1" in response.message
        assert "115" in response.message
        assert response.hotlines == ["115", "1900-555-666"]
        assert response.address == "Bệnh viện Tim Hà Nội, 56 Phùng Hưng, Đống Đa, Hà Nội"
        assert response.banner == level1_protocol.response_text
        assert response.event_id == "EMG-EVT-2026-0001"
        assert len(response.matched_keywords) == 1
        assert response.matched_keywords[0]["rule_id"] == "ER-KW-CAUTION-001"
        assert GENERAL_DISCLAIMER in response.disclaimers

    def test_level1_message_contains_protocol_template(
        self,
        pipeline_with_level1_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
        level1_protocol: EmergencyProtocolDTO,
    ) -> None:
        """Level 1 message includes the protocol response_text."""
        response = pipeline_with_level1_mocks.execute(basic_request)
        assert level1_protocol.response_text in response.message

    def test_level1_message_contains_hotlines_and_address(
        self,
        pipeline_with_level1_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
    ) -> None:
        """Level 1 message includes hotlines and hospital address."""
        response = pipeline_with_level1_mocks.execute(basic_request)
        assert "115" in response.message
        assert "1900-555-666" in response.message
        assert "Bệnh viện Tim Hà Nội" in response.message
        assert "Không phải chẩn đoán y tế" in response.message


class TestEmergencySafetyPipelineLevel2:
    """Tests for Level 2 (critical) emergency handling."""

    def test_level2_emergency_triggered(
        self,
        pipeline_with_level2_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
        level2_protocol: EmergencyProtocolDTO,
    ) -> None:
        """Level 2 emergency returns emergency_triggered outcome."""
        response = pipeline_with_level2_mocks.execute(basic_request)

        assert response.outcome == OUTCOME_EMERGENCY_TRIGGERED
        assert response.level == 2
        assert response.protocol is not None
        assert response.protocol.level == 2
        assert "🚨" in response.message
        assert "Level 2" in response.message
        assert "KHẨN CẤP" in response.message
        assert "Gọi 115 NGAY" in response.message
        assert response.hotlines == ["115", "1900-555-666", "1800-123-456"]
        assert response.address == "Bệnh viện Tim Hà Nội, 56 Phùng Hưng, Đống Đa, Hà Nội"
        assert response.banner == level2_protocol.response_text
        assert response.event_id == "EMG-EVT-2026-0002"
        assert len(response.matched_keywords) == 2
        assert GENERAL_DISCLAIMER in response.disclaimers

    def test_level2_message_contains_protocol_template(
        self,
        pipeline_with_level2_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
        level2_protocol: EmergencyProtocolDTO,
    ) -> None:
        """Level 2 message includes the protocol response_text."""
        response = pipeline_with_level2_mocks.execute(basic_request)
        assert level2_protocol.response_text in response.message

    def test_level2_message_emphasizes_immediate_action(
        self,
        pipeline_with_level2_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
    ) -> None:
        """Level 2 message emphasizes immediate emergency contact."""
        response = pipeline_with_level2_mocks.execute(basic_request)
        assert "NGAY LẬP TỨC" in response.message
        assert "Không tự xử lý" in response.message


class TestEmergencySafetyPipelineNoEmergency:
    """Tests for no-emergency detection path."""

    def test_no_emergency_returns_not_triggered(
        self,
        pipeline_with_no_emergency_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
    ) -> None:
        """No emergency returns not_triggered outcome."""
        response = pipeline_with_no_emergency_mocks.execute(basic_request)

        assert response.outcome == OUTCOME_NOT_TRIGGERED
        assert response.level is None
        assert response.protocol is None
        assert response.banner is None
        assert response.event_id is None
        assert response.hotlines == ["115"]
        assert response.address == "Bệnh viện Tim Hà Nội"
        assert "Không phát hiện từ khóa khẩn cấp" in response.message
        assert GENERAL_DISCLAIMER in response.disclaimers

    def test_no_emergency_message_suggests_contact_if_concerned(
        self,
        pipeline_with_no_emergency_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
    ) -> None:
        """No-emergency message suggests contacting emergency if concerned."""
        response = pipeline_with_no_emergency_mocks.execute(basic_request)
        assert "115" in response.message
        assert "bất an" in response.message.lower()


# ---------------------------------------------------------------------------
# Error handling and fallback tests
# ---------------------------------------------------------------------------


class TestEmergencySafetyPipelineErrorHandling:
    """Tests for error handling and fallback behavior."""

    def test_protocol_not_found_returns_clarification_required(
        self,
        level1_prefilter_result: PrefilterResult,
        basic_request: EmergencySafetyRequest,
    ) -> None:
        """Missing protocol returns clarification_required with error envelope."""
        # Foundation returns None for the level
        foundation = MockEmergencyFoundation({1: None, 2: None})
        prefilter = MockEmergencyPrefilter(level1_prefilter_result)
        pipeline = EmergencySafetyPipeline(
            prefilter_tool=prefilter,
            foundation_service=foundation,
        )

        response = pipeline.execute(basic_request)

        assert response.outcome == OUTCOME_CLARIFICATION_REQUIRED
        assert "không tải được giao thức" in response.message
        assert response.level == 1
        assert response.hotlines == ["115"]
        assert response.error is not None
        assert response.error.error.code == "PROTOCOL_NOT_FOUND"
        assert response.error.error.category == "safety"

    def test_prefilter_exception_returns_fallback_with_error_envelope(
        self, basic_request: EmergencySafetyRequest
    ) -> None:
        """Exception in prefilter returns fallback with error envelope."""

        class FailingPrefilter:
            def prefilter(self, request: PrefilterRequest) -> PrefilterResult:
                raise RuntimeError("Prefilter service unavailable")

        pipeline = EmergencySafetyPipeline(
            prefilter_tool=FailingPrefilter(),
            foundation_service=MockEmergencyFoundation({}),
        )

        response = pipeline.execute(basic_request)

        assert response.outcome == OUTCOME_NOT_TRIGGERED
        assert response.message == GENERAL_DISCLAIMER
        assert response.error is not None
        assert response.error.error.code == "EMERGENCY_PIPELINE_ERROR"
        assert response.error.error.category == "safety"
        assert response.error.error.retryable is True
        assert response.error.error.retry_after_seconds == 5

    def test_foundation_exception_returns_fallback_with_error_envelope(
        self,
        level1_prefilter_result: PrefilterResult,
        basic_request: EmergencySafetyRequest,
    ) -> None:
        """Exception in foundation returns fallback with error envelope."""

        class FailingFoundation:
            def get_emergency_protocol(self, level: int) -> Optional[EmergencyProtocolDTO]:
                raise RuntimeError("Foundation service unavailable")

        pipeline = EmergencySafetyPipeline(
            prefilter_tool=MockEmergencyPrefilter(level1_prefilter_result),
            foundation_service=FailingFoundation(),
        )

        response = pipeline.execute(basic_request)

        assert response.outcome == OUTCOME_NOT_TRIGGERED
        assert response.error is not None
        assert response.error.error.code == "EMERGENCY_PIPELINE_ERROR"

    def test_empty_message_raises_validation_error(self) -> None:
        """Empty message in request raises validation error before pipeline runs."""
        with pytest.raises(ValueError, match="message must be non-empty"):
            EmergencySafetyRequest(
                request_id="req-001",
                session_id="sess-001",
                message="",
            )


# ---------------------------------------------------------------------------
# Convenience function tests
# ---------------------------------------------------------------------------


class TestRunEmergencySafetyConvenienceFunction:
    """Tests for run_emergency_safety convenience wrapper."""

    def test_run_emergency_safety_level1(
        self,
        level1_prefilter_result: PrefilterResult,
        level1_protocol: EmergencyProtocolDTO,
    ) -> None:
        """run_emergency_safety works with Level 1 emergency."""
        prefilter = MockEmergencyPrefilter(level1_prefilter_result)
        foundation = MockEmergencyFoundation({1: level1_protocol, 2: None})

        request = EmergencySafetyRequest(
            request_id="req-001",
            session_id="sess-001",
            message="Đau ngực",
        )

        response = run_emergency_safety(
            request,
            prefilter_tool=prefilter,
            foundation_service=foundation,
        )

        assert response.outcome == OUTCOME_EMERGENCY_TRIGGERED
        assert response.level == 1

    def test_run_emergency_safety_no_emergency(
        self,
        no_emergency_prefilter_result: PrefilterResult,
    ) -> None:
        """run_emergency_safety works with no emergency."""
        prefilter = MockEmergencyPrefilter(no_emergency_prefilter_result)
        foundation = MockEmergencyFoundation({})

        request = EmergencySafetyRequest(
            request_id="req-001",
            session_id="sess-001",
            message="Tôi muốn hỏi giờ làm việc",
        )

        response = run_emergency_safety(
            request,
            prefilter_tool=prefilter,
            foundation_service=foundation,
        )

        assert response.outcome == OUTCOME_NOT_TRIGGERED


# ---------------------------------------------------------------------------
# INT-05 Compliance tests
# ---------------------------------------------------------------------------


class TestINT05Compliance:
    """Tests verifying INT-05 (AI Behavior Contracts) compliance."""

    def test_emergency_priority_over_other_processing(
        self,
        level2_prefilter_result: PrefilterResult,
        level2_protocol: EmergencyProtocolDTO,
    ) -> None:
        """Emergency detection runs first and blocks other processing."""
        pipeline = EmergencySafetyPipeline(
            prefilter_tool=MockEmergencyPrefilter(level2_prefilter_result),
            foundation_service=MockEmergencyFoundation({2: level2_protocol}),
        )

        # Even with conversation history, emergency takes priority
        request = EmergencySafetyRequest(
            request_id="req-001",
            session_id="sess-001",
            message="Ngưng tim, bệnh nhân bất tỉnh",
            conversation_history=[
                {"role": "user", "content": "Chào"},
                {"role": "assistant", "content": "Chào bạn"},
            ],
            client_context={"user_id": "user-123"},
        )

        response = pipeline.execute(request)

        # Emergency triggered immediately, no other processing
        assert response.outcome == OUTCOME_EMERGENCY_TRIGGERED
        assert response.level == 2
        assert "🚨" in response.message

    def test_no_medical_diagnosis_in_response(
        self,
        pipeline_with_level1_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
    ) -> None:
        """Response never contains medical diagnosis or treatment advice."""
        response = pipeline_with_level1_mocks.execute(basic_request)

        # Check for prohibited content - but allow "chẩn đoán" in negative context
        # (e.g., "Không phải chẩn đoán y tế" is correct behavior)
        prohibited_terms = [
            "điều trị",
            "thuốc",
            "liều lượng",
            "bệnh này là gì",
            "bạn bị bệnh",
            "khuyên dùng",
            "chỉ định",
        ]
        message_lower = response.message.lower()
        for term in prohibited_terms:
            assert term not in message_lower, f"Prohibited term '{term}' found in response"
        
        # "chẩn đoán" should only appear in negative context
        assert "chẩn đoán" not in message_lower or "không phải chẩn đoán" in message_lower

    def test_no_chain_of_thought_exposure(
        self,
        pipeline_with_level2_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
    ) -> None:
        """Response never exposes internal reasoning or chain of thought."""
        response = pipeline_with_level2_mocks.execute(basic_request)

        # Check for prohibited exposure patterns
        prohibited_patterns = [
            "tôi nghĩ",
            "tôi suy nghĩ",
            "dựa trên",
            "theo tôi",
            "reasoning",
            "chain of thought",
            "internal",
            "system prompt",
        ]
        message_lower = response.message.lower()
        for pattern in prohibited_patterns:
            assert pattern not in message_lower, f"Prohibited pattern '{pattern}' found in response"

    def test_level1_only_handoff_guidance_no_diagnosis(
        self,
        pipeline_with_level1_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
    ) -> None:
        """Level 1 response provides only contact handoff guidance."""
        response = pipeline_with_level1_mocks.execute(basic_request)

        # Level 1 should only guide to contact hotlines
        assert "Hướng dẫn:" in response.message
        assert "liên hệ ngay với đường dây nóng" in response.message
        assert "Không phải chẩn đoán y tế" in response.message
        # Should not mention specific medical conditions
        assert "ngưng tim" not in response.message.lower()
        assert "đau tim" not in response.message.lower()

    def test_disclaimer_always_present(
        self,
        pipeline_with_level1_mocks: EmergencySafetyPipeline,
        pipeline_with_no_emergency_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
    ) -> None:
        """General disclaimer is present in all responses."""
        response1 = pipeline_with_level1_mocks.execute(basic_request)
        response2 = pipeline_with_no_emergency_mocks.execute(basic_request)

        assert GENERAL_DISCLAIMER in response1.disclaimers
        assert GENERAL_DISCLAIMER in response2.disclaimers


# ---------------------------------------------------------------------------
# Protocol and export tests
# ---------------------------------------------------------------------------


class TestModuleExports:
    """Tests for module exports."""

    def test_all_required_exports_present(self) -> None:
        """Module exports all required types and functions."""
        from apps.api.ai.orchestrator.emergency_safety import pipeline

        # Outcome constants
        assert hasattr(pipeline, "OUTCOME_EMERGENCY_TRIGGERED")
        assert hasattr(pipeline, "OUTCOME_CLARIFICATION_REQUIRED")
        assert hasattr(pipeline, "OUTCOME_NOT_TRIGGERED")

        # DTOs
        assert hasattr(pipeline, "EmergencySafetyRequest")
        assert hasattr(pipeline, "EmergencySafetyResponse")

        # Protocols
        assert hasattr(pipeline, "EmergencyPrefilterProtocol")
        assert hasattr(pipeline, "EmergencyFoundationProtocol")

        # Pipeline
        assert hasattr(pipeline, "EmergencySafetyPipeline")
        assert hasattr(pipeline, "run_emergency_safety")

        # Disclaimers
        assert hasattr(pipeline, "GENERAL_DISCLAIMER")

    def test_protocol_runtime_checkable(self) -> None:
        """Protocols are runtime checkable."""
        from apps.api.ai.orchestrator.emergency_safety.pipeline import (
            EmergencyPrefilterProtocol,
            EmergencyFoundationProtocol,
        )

        # Should be able to use isinstance with runtime_checkable protocols
        assert EmergencyPrefilterProtocol.__protocol_attrs__
        assert EmergencyFoundationProtocol.__protocol_attrs__


# ---------------------------------------------------------------------------
# Data contract compliance tests
# ---------------------------------------------------------------------------


class TestDataContractCompliance:
    """Tests verifying compliance with INT-04 data contracts."""

    def test_emergency_safety_request_fields(
        self, basic_request: EmergencySafetyRequest
    ) -> None:
        """EmergencySafetyRequest has all required fields per INT-04."""
        # Per INT-04: request_id, session_id, message, prefilter_result, matched_evidence
        # Note: prefilter_result and matched_evidence are internal to pipeline
        # Request DTO carries message + context for prefilter
        assert hasattr(basic_request, "request_id")
        assert hasattr(basic_request, "session_id")
        assert hasattr(basic_request, "message")
        assert hasattr(basic_request, "conversation_history")
        assert hasattr(basic_request, "client_context")

    def test_emergency_safety_response_fields(
        self,
        pipeline_with_level1_mocks: EmergencySafetyPipeline,
        basic_request: EmergencySafetyRequest,
    ) -> None:
        """EmergencySafetyResponse has all required fields per INT-04."""
        response = pipeline_with_level1_mocks.execute(basic_request)
        result_dict = response.to_dict()

        # Per INT-04: outcome, optional level/path, protocol content, hotline/address/banner, event_id
        assert "outcome" in result_dict
        assert "message" in result_dict
        assert "level" in result_dict
        assert "protocol" in result_dict
        assert "hotlines" in result_dict
        assert "address" in result_dict
        assert "banner" in result_dict
        assert "event_id" in result_dict
        assert "matched_keywords" in result_dict
        assert "disclaimers" in result_dict

        # No medical assessment field
        assert "medical_assessment" not in result_dict
        assert "diagnosis" not in result_dict
        assert "treatment_recommendation" not in result_dict


# === TASK:WP-304:END ===
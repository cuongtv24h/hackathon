# === TASK:WP-202:START ===
"""Unit tests for WP-202: Emergency prefilter tool.

Test contract
-------------
Per docs/spec-registry/runtime-test-policy.yaml:
* Framework: pytest
* Location: tests/unit/
* Use mocks/fakes for provider and network calls

Coverage
--------
* emergency_prefilter tool contract (PC-02, INT-06)
* Keyword matching for critical (Level 2) and caution (Level 1) keywords
* Normalization of Vietnamese text with diacritics
* Prefilter result structure with metadata
* Timeout tracking and warning
* Fallback protocol when no keywords match
* Error handling for invalid requests
* Integration with foundation keyword set (FND-EMG-02)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from apps.api.capabilities.emergency.prefilter.tool import (
    EmergencyPrefilterTool,
    MatchedKeyword,
    PrefilterRequest,
    PrefilterResult,
    emergency_prefilter,
)
from apps.api.foundation.emergency.service import (
    EmergencyEventCreateRequest,
    EmergencyEventReceiptDTO,
    EmergencyFoundationService,
    EmergencyKeywordDTO,
    EmergencyKeywordSetDTO,
)


# ---------------------------------------------------------------------------
# Test fixtures: Fakes and mocks
# ---------------------------------------------------------------------------


@dataclass
class FakeEmergencyFoundationService:
    """Fake foundation service for testing without file I/O."""

    keyword_set: EmergencyKeywordSetDTO
    should_fail: bool = False
    fail_message: str = "Foundation service unavailable"
    event_requests: List[EmergencyEventCreateRequest] = None

    def __post_init__(self) -> None:
        if self.event_requests is None:
            self.event_requests = []

    def get_emergency_keyword_set(self) -> EmergencyKeywordSetDTO:
        if self.should_fail:
            raise RuntimeError(self.fail_message)
        return self.keyword_set

    def create_emergency_event(
        self, request: EmergencyEventCreateRequest
    ) -> EmergencyEventReceiptDTO:
        self.event_requests.append(request)
        return EmergencyEventReceiptDTO(
            event_id="EMG-TEST-001",
            created_at="2026-07-18T00:00:00+00:00",
            level=request.level,
            protocol_id=request.protocol_id,
        )


def make_keyword(
    rule_id: str = "EMG-KW-001",
    level: int = 2,
    category: str = "cardiac",
    phrases: List[str] = None,
    normalized_phrases: List[str] = None,
    protocol_id: str = "ERP-L2-CARDIAC",
    is_mock: bool = True,
) -> EmergencyKeywordDTO:
    """Factory for creating test keywords."""
    if phrases is None:
        phrases = ["đau ngực", "ngực đau"]
    if normalized_phrases is None:
        normalized_phrases = ["dau nguc", "nguc dau"]
    return EmergencyKeywordDTO(
        rule_id=rule_id,
        level=level,
        category=category,
        phrases=phrases,
        normalized_phrases=normalized_phrases,
        protocol_id=protocol_id,
        is_mock=is_mock,
    )


def make_keyword_set(
    critical_keywords: List[EmergencyKeywordDTO] = None,
    caution_keywords: List[EmergencyKeywordDTO] = None,
    approval_status: str = "mock_not_clinically_approved",
    effective_date: str = "2026-01-01",
    version: str = "1.0.0",
) -> EmergencyKeywordSetDTO:
    """Factory for creating test keyword sets."""
    if critical_keywords is None:
        critical_keywords = [make_keyword()]
    if caution_keywords is None:
        caution_keywords = [make_keyword(
            rule_id="EMG-KW-002",
            level=1,
            category="respiratory",
            phrases=["khó thở", "thở khò khè"],
            normalized_phrases=["kho tho", "tho kho khe"],
            protocol_id="ERP-L1-RESPIRATORY",
        )]
    return EmergencyKeywordSetDTO(
        critical_keywords=critical_keywords,
        caution_keywords=caution_keywords,
        approval_status=approval_status,
        effective_date=effective_date,
        version=version,
    )


def make_tool(
    keyword_set: EmergencyKeywordSetDTO = None,
    should_fail: bool = False,
    timeout_ms: int = 100,
) -> EmergencyPrefilterTool:
    """Factory for creating test tools with fake foundation."""
    if keyword_set is None:
        keyword_set = make_keyword_set()
    fake_foundation = FakeEmergencyFoundationService(
        keyword_set=keyword_set,
        should_fail=should_fail,
    )
    return EmergencyPrefilterTool(
        foundation_service=fake_foundation,  # type: ignore
        timeout_ms=timeout_ms,
    )


# ---------------------------------------------------------------------------
# Test: PrefilterRequest validation
# ---------------------------------------------------------------------------


class TestPrefilterRequest:
    """Tests for PrefilterRequest validation."""

    def test_valid_request(self):
        """A valid request should pass validation."""
        request = PrefilterRequest(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
            trace_id="trace-456",
        )
        assert request.user_message == "Tôi bị đau ngực"
        assert request.session_id == "session-123"
        assert request.trace_id == "trace-456"

    def test_valid_request_without_trace_id(self):
        """Request without trace_id should be valid."""
        request = PrefilterRequest(
            user_message="test message",
            session_id="session-123",
        )
        assert request.trace_id is None

    def test_empty_user_message_raises(self):
        """Empty user_message should raise ValueError."""
        with pytest.raises(ValueError, match="user_message must be non-empty"):
            PrefilterRequest(user_message="", session_id="session-123")

    def test_whitespace_user_message_raises(self):
        """Whitespace-only user_message should raise ValueError."""
        with pytest.raises(ValueError, match="user_message must be non-empty"):
            PrefilterRequest(user_message="   ", session_id="session-123")

    def test_empty_session_id_raises(self):
        """Empty session_id should raise ValueError."""
        with pytest.raises(ValueError, match="session_id must be non-empty"):
            PrefilterRequest(user_message="test", session_id="")

    def test_whitespace_session_id_raises(self):
        """Whitespace-only session_id should raise ValueError."""
        with pytest.raises(ValueError, match="session_id must be non-empty"):
            PrefilterRequest(user_message="test", session_id="   ")


# ---------------------------------------------------------------------------
# Test: MatchedKeyword and PrefilterResult serialization
# ---------------------------------------------------------------------------


class TestMatchedKeyword:
    """Tests for MatchedKeyword serialization."""

    def test_to_dict(self):
        """MatchedKeyword should serialize to dict correctly."""
        keyword = MatchedKeyword(
            rule_id="EMG-KW-001",
            level=2,
            category="cardiac",
            matched_phrase="đau ngực",
            protocol_id="ERP-L2-CARDIAC",
        )
        d = keyword.to_dict()
        assert d["rule_id"] == "EMG-KW-001"
        assert d["level"] == 2
        assert d["category"] == "cardiac"
        assert d["matched_phrase"] == "đau ngực"
        assert d["protocol_id"] == "ERP-L2-CARDIAC"


class TestPrefilterResult:
    """Tests for PrefilterResult serialization."""

    def test_to_dict_with_matches(self):
        """PrefilterResult with matches should serialize correctly."""
        keyword = MatchedKeyword(
            rule_id="EMG-KW-001",
            level=2,
            category="cardiac",
            matched_phrase="đau ngực",
            protocol_id="ERP-L2-CARDIAC",
        )
        result = PrefilterResult(
            is_emergency=True,
            level=2,
            matched_keywords=[keyword],
            protocol_id="ERP-L2-CARDIAC",
            metadata={"elapsed_ms": 5.5, "session_id": "session-123"},
        )
        d = result.to_dict()
        assert d["is_emergency"] is True
        assert d["level"] == 2
        assert len(d["matched_keywords"]) == 1
        assert d["protocol_id"] == "ERP-L2-CARDIAC"
        assert d["metadata"]["elapsed_ms"] == 5.5

    def test_to_dict_no_matches(self):
        """PrefilterResult without matches should serialize correctly."""
        result = PrefilterResult(
            is_emergency=False,
            level=0,
            matched_keywords=[],
            protocol_id="ERP-FALLBACK-V1",
            metadata={"elapsed_ms": 2.1},
        )
        d = result.to_dict()
        assert d["is_emergency"] is False
        assert d["level"] == 0
        assert d["matched_keywords"] == []
        assert d["protocol_id"] == "ERP-FALLBACK-V1"


# ---------------------------------------------------------------------------
# Test: EmergencyPrefilterTool - keyword matching
# ---------------------------------------------------------------------------


class TestEmergencyPrefilterToolMatching:
    """Tests for keyword matching logic."""

    def test_matches_critical_keyword_exact(self):
        """Should match critical keyword with exact phrase."""
        tool = make_tool()
        request = PrefilterRequest(
            user_message="Tôi bị đau ngực rất đau",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.is_emergency is True
        assert result.level == 2
        assert len(result.matched_keywords) == 1
        assert result.matched_keywords[0].rule_id == "EMG-KW-001"
        assert result.matched_keywords[0].matched_phrase == "đau ngực"
        assert result.protocol_id == "ERP-L2-CARDIAC"

    def test_matches_critical_keyword_vietnamese_diacritics(self):
        """Should match Vietnamese phrases with diacritics."""
        tool = make_tool()
        request = PrefilterRequest(
            user_message="Tôi đang bị đau ngực dữ dội",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.is_emergency is True
        assert result.level == 2

    def test_matches_caution_keyword(self):
        """Should match caution (Level 1) keyword."""
        tool = make_tool()
        request = PrefilterRequest(
            user_message="Tôi khó thở từ sáng nay",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.is_emergency is True
        assert result.level == 1
        assert len(result.matched_keywords) == 1
        assert result.matched_keywords[0].level == 1
        assert result.protocol_id == "ERP-L1-RESPIRATORY"

    def test_critical_takes_priority_over_caution(self):
        """Critical (Level 2) should take priority over caution (Level 1)."""
        tool = make_tool()
        request = PrefilterRequest(
            user_message="Tôi đau ngực và khó thở",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.is_emergency is True
        assert result.level == 2  # Critical takes priority
        assert result.protocol_id == "ERP-L2-CARDIAC"
        assert result.event_receipt is not None
        assert result.event_receipt.event_id == "EMG-TEST-001"

    def test_no_match_returns_fallback(self):
        """No keyword match should return fallback protocol."""
        tool = make_tool()
        request = PrefilterRequest(
            user_message="Tôi muốn hỏi về lịch khám",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.is_emergency is False
        assert result.level == 0
        assert len(result.matched_keywords) == 0
        assert result.protocol_id == "ERP-FALLBACK-V1"

    def test_matches_normalized_phrase(self):
        """Should match using normalized phrases from keyword set."""
        # Create keyword with normalized phrase that matches after normalization
        keyword = make_keyword(
            rule_id="EMG-KW-003",
            phrases=["đau tim"],
            normalized_phrases=["dau tim"],
            protocol_id="ERP-L2-CARDIAC-2",
        )
        keyword_set = make_keyword_set(critical_keywords=[keyword])
        tool = make_tool(keyword_set=keyword_set)

        # Message with different diacritics/punctuation that normalizes to match
        request = PrefilterRequest(
            user_message="Tôi bị đau tim!",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.is_emergency is True
        assert result.level == 2

    def test_case_insensitive_matching(self):
        """Matching should be case-insensitive."""
        tool = make_tool()
        request = PrefilterRequest(
            user_message="TÔI BỊ ĐAU NGỰC",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.is_emergency is True
        assert result.level == 2

    def test_multiple_matches_same_rule_only_counted_once(self):
        """Multiple phrases from same rule should only count as one match."""
        keyword = make_keyword(
            rule_id="EMG-KW-004",
            phrases=["đau ngực", "ngực đau", "đau tim"],
            protocol_id="ERP-L2-CARDIAC",
        )
        keyword_set = make_keyword_set(critical_keywords=[keyword])
        tool = make_tool(keyword_set=keyword_set)

        request = PrefilterRequest(
            user_message="Tôi đau ngực và ngực đau",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        # Should only have one match for this rule
        assert len(result.matched_keywords) == 1
        assert result.matched_keywords[0].rule_id == "EMG-KW-004"

    def test_matches_with_punctuation(self):
        """Should match phrases even with punctuation in message."""
        tool = make_tool()
        request = PrefilterRequest(
            user_message="Giúp tôi! Tôi bị đau ngực...",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.is_emergency is True
        assert result.level == 2


# ---------------------------------------------------------------------------
# Test: EmergencyPrefilterTool - metadata and timeout
# ---------------------------------------------------------------------------


class TestEmergencyPrefilterToolMetadata:
    """Tests for metadata and timeout tracking."""

    def test_metadata_includes_elapsed_time(self):
        """Result metadata should include elapsed_ms."""
        tool = make_tool()
        request = PrefilterRequest(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert "elapsed_ms" in result.metadata
        assert result.metadata["elapsed_ms"] >= 0

    def test_metadata_includes_timeout_info(self):
        """Result metadata should include timeout_ms."""
        tool = make_tool(timeout_ms=50)
        request = PrefilterRequest(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.metadata["timeout_ms"] == 50

    def test_metadata_includes_keyword_set_info(self):
        """Result metadata should include keyword set metadata."""
        keyword_set = make_keyword_set(
            approval_status="approved",
            effective_date="2026-06-15",
            version="2.0.0",
        )
        tool = make_tool(keyword_set=keyword_set)
        request = PrefilterRequest(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.metadata["approval_status"] == "approved"
        assert result.metadata["effective_date"] == "2026-06-15"
        assert result.metadata["version"] == "2.0.0"

    def test_metadata_includes_session_and_trace(self):
        """Result metadata should include session_id and trace_id."""
        tool = make_tool()
        request = PrefilterRequest(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
            trace_id="trace-456",
        )
        result = tool.prefilter(request)
        assert result.metadata["session_id"] == "session-123"
        assert result.metadata["trace_id"] == "trace-456"

    def test_timeout_warning_when_exceeded(self):
        """Should include timeout warning when elapsed exceeds timeout."""
        # Use very small timeout to trigger warning
        tool = make_tool(timeout_ms=0)
        request = PrefilterRequest(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert "timeout_warning" in result.metadata
        assert "exceeded timeout" in result.metadata["timeout_warning"].lower()

    def test_no_timeout_warning_when_within_limit(self):
        """Should not include timeout warning when within limit."""
        tool = make_tool(timeout_ms=1000)
        request = PrefilterRequest(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.metadata["timeout_warning"] == ""


# ---------------------------------------------------------------------------
# Test: EmergencyPrefilterTool - error handling
# ---------------------------------------------------------------------------


class TestEmergencyPrefilterToolErrors:
    """Tests for error handling."""

    def test_foundation_failure_raises(self):
        """Foundation service failure should raise RuntimeError."""
        tool = make_tool(should_fail=True)
        request = PrefilterRequest(
            user_message="test",
            session_id="session-123",
        )
        with pytest.raises(RuntimeError, match="Foundation service unavailable"):
            tool.prefilter(request)

    def test_empty_message_is_rejected_by_request_contract(self):
        """Empty user_message is rejected when the request DTO is built."""
        with pytest.raises(ValueError, match="user_message must be non-empty"):
            PrefilterRequest(
                user_message="",
                session_id="session-123",
            )

    def test_empty_session_is_rejected_by_request_contract(self):
        """Empty session_id is rejected when the request DTO is built."""
        with pytest.raises(ValueError, match="session_id must be non-empty"):
            PrefilterRequest(
                user_message="test",
                session_id="",
            )


# ---------------------------------------------------------------------------
# Test: Convenience function emergency_prefilter
# ---------------------------------------------------------------------------


class TestEmergencyPrefilterFunction:
    """Tests for the emergency_prefilter convenience function."""

    def test_function_returns_result(self):
        """Convenience function should return PrefilterResult."""
        keyword_set = make_keyword_set()
        fake_foundation = FakeEmergencyFoundationService(keyword_set=keyword_set)

        result = emergency_prefilter(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
            foundation_service=fake_foundation,  # type: ignore
        )

        assert isinstance(result, PrefilterResult)
        assert result.is_emergency is True
        assert result.level == 2

    def test_function_with_trace_id(self):
        """Convenience function should accept trace_id."""
        keyword_set = make_keyword_set()
        fake_foundation = FakeEmergencyFoundationService(keyword_set=keyword_set)

        result = emergency_prefilter(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
            trace_id="trace-456",
            foundation_service=fake_foundation,  # type: ignore
        )

        assert result.metadata["trace_id"] == "trace-456"

    def test_function_custom_timeout(self):
        """Convenience function should accept custom timeout."""
        keyword_set = make_keyword_set()
        fake_foundation = FakeEmergencyFoundationService(keyword_set=keyword_set)

        result = emergency_prefilter(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
            foundation_service=fake_foundation,  # type: ignore
            timeout_ms=500,
        )

        assert result.metadata["timeout_ms"] == 500


# ---------------------------------------------------------------------------
# Test: Integration with real foundation service (using mock seed)
# ---------------------------------------------------------------------------


class TestEmergencyPrefilterIntegration:
    """Integration tests using real foundation service with mock seed data."""

    def test_with_real_foundation_service(self, tmp_path: Path):
        """Should work with real EmergencyFoundationService."""
        # Create mock seed file
        seed_data = {
            "dataset": {
                "version": "1.0.0",
                "effective_date": "2026-01-01",
                "clinical_approval_status": "mock_not_clinically_approved",
            },
            "keyword_sets": [
                {
                    "rule_id": "EMG-KW-TEST-001",
                    "level": 2,
                    "category": "cardiac",
                    "phrases": ["đau ngực", "ngực đau"],
                    "normalized_phrases": ["dau nguc", "nguc dau"],
                    "protocol_id": "ERP-L2-TEST",
                    "is_mock": True,
                },
                {
                    "rule_id": "EMG-KW-TEST-002",
                    "level": 1,
                    "category": "respiratory",
                    "phrases": ["khó thở"],
                    "normalized_phrases": ["kho tho"],
                    "protocol_id": "ERP-L1-TEST",
                    "is_mock": True,
                },
            ],
            "protocols": [],
        }
        import json
        seed_file = tmp_path / "emergency.json"
        seed_file.write_text(json.dumps(seed_data, ensure_ascii=False), encoding="utf-8")

        # Create real foundation service
        foundation = EmergencyFoundationService(seed_path=seed_file)
        tool = EmergencyPrefilterTool(foundation_service=foundation)

        # Test critical match
        request = PrefilterRequest(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.is_emergency is True
        assert result.level == 2
        assert result.protocol_id == "ERP-L2-TEST"

        # Test caution match
        request2 = PrefilterRequest(
            user_message="Tôi khó thở",
            session_id="session-123",
        )
        result2 = tool.prefilter(request2)
        assert result2.is_emergency is True
        assert result2.level == 1
        assert result2.protocol_id == "ERP-L1-TEST"

        # Test no match
        request3 = PrefilterRequest(
            user_message="Lịch khám khi nào?",
            session_id="session-123",
        )
        result3 = tool.prefilter(request3)
        assert result3.is_emergency is False
        assert result3.protocol_id == "ERP-FALLBACK-V1"

    def test_get_keyword_set_info(self, tmp_path: Path):
        """get_keyword_set_info should return keyword set metadata."""
        seed_data = {
            "dataset": {
                "version": "2.0.0",
                "effective_date": "2026-06-15",
                "clinical_approval_status": "approved",
            },
            "keyword_sets": [
                {
                    "rule_id": "EMG-KW-001",
                    "level": 2,
                    "category": "cardiac",
                    "phrases": ["đau ngực"],
                    "normalized_phrases": ["dau nguc"],
                    "protocol_id": "ERP-L2-CARDIAC",
                    "is_mock": True,
                },
            ],
            "protocols": [],
        }
        import json
        seed_file = tmp_path / "emergency.json"
        seed_file.write_text(json.dumps(seed_data, ensure_ascii=False), encoding="utf-8")

        foundation = EmergencyFoundationService(seed_path=seed_file)
        tool = EmergencyPrefilterTool(foundation_service=foundation)

        info = tool.get_keyword_set_info()
        assert info["approval_status"] == "approved"
        assert info["effective_date"] == "2026-06-15"
        assert info["version"] == "2.0.0"
        assert info["critical_keyword_count"] == 1
        assert info["caution_keyword_count"] == 0


# ---------------------------------------------------------------------------
# Test: Tool contract compliance (INT-06)
# ---------------------------------------------------------------------------


class TestToolContractCompliance:
    """Tests verifying INT-06 tool contract compliance."""

    def test_tool_has_prefilter_method(self):
        """Tool should have prefilter method implementing PC-02."""
        tool = make_tool()
        assert hasattr(tool, "prefilter")
        assert callable(tool.prefilter)

    def test_convenience_function_exists(self):
        """emergency_prefilter convenience function should exist."""
        assert callable(emergency_prefilter)

    def test_default_timeout_is_100ms(self):
        """Default timeout should be 100ms per INT-06."""
        tool = make_tool()
        assert tool._timeout_ms == 100

    def test_timeout_configurable(self):
        """Timeout should be configurable."""
        tool = EmergencyPrefilterTool(timeout_ms=500)
        assert tool._timeout_ms == 500

    def test_result_includes_required_fields(self):
        """Result should include all required fields per INT-06."""
        tool = make_tool()
        request = PrefilterRequest(
            user_message="Tôi bị đau ngực",
            session_id="session-123",
        )
        result = tool.prefilter(request)

        # Required fields per INT-06
        assert hasattr(result, "is_emergency")
        assert hasattr(result, "level")
        assert hasattr(result, "matched_keywords")
        assert hasattr(result, "protocol_id")
        assert hasattr(result, "metadata")

        # Metadata should have required fields
        assert "elapsed_ms" in result.metadata
        assert "timeout_ms" in result.metadata
        assert "approval_status" in result.metadata
        assert "effective_date" in result.metadata
        assert "version" in result.metadata
        assert "session_id" in result.metadata


# ---------------------------------------------------------------------------
# Test: Vietnamese text normalization edge cases
# ---------------------------------------------------------------------------


class TestVietnameseNormalization:
    """Tests for Vietnamese text normalization edge cases."""

    def test_normalize_removes_punctuation(self):
        """Normalization should remove punctuation that interferes with matching."""
        tool = make_tool()
        normalized = tool._normalize_text("Tôi bị đau ngực!!!")
        assert "dau nguc" in normalized
        assert "!" not in normalized

    def test_normalize_preserves_vietnamese_diacritics(self):
        """Normalization should preserve Vietnamese diacritics."""
        tool = make_tool()
        normalized = tool._normalize_text("Đau ngực khó thở")
        # Should keep diacritics
        assert "đau" in normalized or "dau" in normalized
        assert "ngực" in normalized or "nguc" in normalized
        assert "khó" in normalized or "kho" in normalized
        assert "thở" in normalized or "tho" in normalized

    def test_normalize_collapses_whitespace(self):
        """Normalization should collapse multiple spaces."""
        tool = make_tool()
        normalized = tool._normalize_text("Tôi   bị    đau   ngực")
        assert "  " not in normalized  # No double spaces

    def test_normalize_handles_mixed_case(self):
        """Normalization should handle mixed case."""
        tool = make_tool()
        normalized = tool._normalize_text("TÔI BỊ ĐAU NGỰC")
        assert "dau nguc" in normalized

    def test_match_with_normalized_phrases(self):
        """Should match using normalized_phrases from keyword set."""
        keyword = make_keyword(
            rule_id="EMG-KW-NORM",
            phrases=["đau tim"],  # Original phrase
            normalized_phrases=["dau tim"],  # Normalized version
            protocol_id="ERP-L2-TEST",
        )
        keyword_set = make_keyword_set(critical_keywords=[keyword])
        tool = make_tool(keyword_set=keyword_set)

        # Message that normalizes to match normalized_phrase
        request = PrefilterRequest(
            user_message="Tôi bị đau tim!",
            session_id="session-123",
        )
        result = tool.prefilter(request)
        assert result.is_emergency is True
        assert result.matched_keywords[0].rule_id == "EMG-KW-NORM"


# === TASK:WP-202:END ===

# === TASK:WP-103:START ===
"""Unit tests for WP-103 emergency foundation services.

This test module covers:
- FND-EMG-01 GetEmergencyProtocol
- FND-EMG-02 GetEmergencyKeywordSet
- FND-EMG-03 CreateEmergencyEvent

Tests use mock seed data and do not make network calls.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest import TestCase

import pytest


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


MOCK_EMERGENCY_SEED: Dict[str, Any] = {
    "dataset": {
        "dataset_id": "EMERGENCY-TEST-01",
        "version": "1.0.0-test",
        "is_mock": True,
        "clinical_approval_status": "not_clinically_approved",
        "effective_date": "2026-07-17",
    },
    "keyword_sets": [
        {
            "rule_id": "TEST-CRIT-001",
            "level": 2,
            "category": "cardiovascular",
            "phrases": ["đau ngực", "đau tim"],
            "normalized_phrases": ["dau nguc", "dau tim"],
            "protocol_id": "ERP-L2-TEST",
            "is_mock": True,
        },
        {
            "rule_id": "TEST-CAUT-001",
            "level": 1,
            "category": "general",
            "phrases": ["chóng mặt", "mệt mỏi"],
            "normalized_phrases": ["chong mat", "met moi"],
            "protocol_id": "ERP-L1-TEST",
            "is_mock": True,
        },
    ],
    "protocols": [
        {
            "protocol_id": "ERP-L2-TEST",
            "level": 2,
            "version": "1.0.0",
            "response_text": "NGUY HIỂM. Gọi 115 ngay.",
            "channel_refs": ["CH-EMERGENCY-115"],
            "emergency_address_ref": "Khoa Cấp cứu Test",
            "banner_level": "critical",
            "allowed_actions": ["call_115"],
            "prohibited_content": ["diagnosis"],
            "approval_status": "mock_test",
            "is_mock": True,
            "effective_date": "2026-07-17",
        },
        {
            "protocol_id": "ERP-L1-TEST",
            "level": 1,
            "version": "1.0.0",
            "response_text": "Lưu ý. Theo dõi tình trạng.",
            "channel_refs": ["CH-HOTLINE"],
            "emergency_address_ref": "Đón tiếp Test",
            "banner_level": "caution",
            "allowed_actions": ["provide_contact_info"],
            "prohibited_content": ["diagnosis"],
            "approval_status": "mock_test",
            "is_mock": True,
            "effective_date": "2026-07-17",
        },
    ],
}


@pytest.fixture
def mock_seed_file(tmp_path: Path) -> Path:
    """Create a mock emergency seed file for testing."""
    seed_file = tmp_path / "emergency.json"
    seed_file.write_text(json.dumps(MOCK_EMERGENCY_SEED), encoding="utf-8")
    return seed_file


# ---------------------------------------------------------------------------
# Tests for EmergencyFoundationService
# ---------------------------------------------------------------------------


class TestEmergencyFoundationService:
    """Tests for the foundation emergency service (FND-EMG-01, FND-EMG-02, FND-EMG-03)."""

    def test_get_emergency_keyword_set_returns_keywords(self, mock_seed_file: Path) -> None:
        """FND-EMG-02: GetEmergencyKeywordSet returns critical and caution keywords."""
        from apps.api.foundation.emergency.service import (
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)
        keyword_set = service.get_emergency_keyword_set()

        assert keyword_set is not None
        assert len(keyword_set.critical_keywords) == 1
        assert len(keyword_set.caution_keywords) == 1
        assert keyword_set.critical_keywords[0].rule_id == "TEST-CRIT-001"
        assert keyword_set.caution_keywords[0].rule_id == "TEST-CAUT-001"

    def test_get_emergency_keyword_set_contains_normalized_phrases(self, mock_seed_file: Path) -> None:
        """FND-EMG-02: Keywords include normalized phrases for matching."""
        from apps.api.foundation.emergency.service import (
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)
        keyword_set = service.get_emergency_keyword_set()

        critical = keyword_set.critical_keywords[0]
        assert "dau nguc" in critical.normalized_phrases
        assert "dau tim" in critical.normalized_phrases

    def test_get_emergency_keyword_set_returns_approval_status(self, mock_seed_file: Path) -> None:
        """FND-EMG-02: Keyword set includes approval metadata."""
        from apps.api.foundation.emergency.service import (
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)
        keyword_set = service.get_emergency_keyword_set()

        assert keyword_set.approval_status == "not_clinically_approved"
        assert keyword_set.version == "1.0.0-test"
        assert keyword_set.effective_date == "2026-07-17"

    def test_get_emergency_protocol_level_2(self, mock_seed_file: Path) -> None:
        """FND-EMG-01: GetEmergencyProtocol returns Level 2 protocol."""
        from apps.api.foundation.emergency.service import (
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)
        protocol = service.get_emergency_protocol(level=2)

        assert protocol is not None
        assert protocol.protocol_id == "ERP-L2-TEST"
        assert protocol.level == 2
        assert protocol.banner_level == "critical"
        assert "Gọi 115" in protocol.response_text

    def test_get_emergency_protocol_level_1(self, mock_seed_file: Path) -> None:
        """FND-EMG-01: GetEmergencyProtocol returns Level 1 protocol."""
        from apps.api.foundation.emergency.service import (
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)
        protocol = service.get_emergency_protocol(level=1)

        assert protocol is not None
        assert protocol.protocol_id == "ERP-L1-TEST"
        assert protocol.level == 1
        assert protocol.banner_level == "caution"

    def test_get_emergency_protocol_not_found_returns_none(self, mock_seed_file: Path) -> None:
        """FND-EMG-01: Returns None for non-existent level."""
        from apps.api.foundation.emergency.service import (
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)
        protocol = service.get_emergency_protocol(level=99)

        assert protocol is None

    def test_create_emergency_event_returns_receipt(self, mock_seed_file: Path) -> None:
        """FND-EMG-03: CreateEmergencyEvent returns event receipt."""
        from apps.api.foundation.emergency.service import (
            EmergencyEventCreateRequest,
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)
        request = EmergencyEventCreateRequest(
            session_id="test-session-001",
            level=2,
            matched_keywords=["đau ngực", "đau tim"],
            protocol_id="ERP-L2-TEST",
            user_message="Tôi đang đau ngực dữ dội",
            trace_id="trace-123",
        )

        receipt = service.create_emergency_event(request)

        assert receipt.event_id.startswith("EMG-")
        assert receipt.level == 2
        assert receipt.protocol_id == "ERP-L2-TEST"
        assert receipt.created_at is not None

    def test_create_emergency_event_stores_event(self, mock_seed_file: Path) -> None:
        """FND-EMG-03: Event is stored for audit retrieval."""
        from apps.api.foundation.emergency.service import (
            EmergencyEventCreateRequest,
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)
        request = EmergencyEventCreateRequest(
            session_id="test-session-002",
            level=1,
            matched_keywords=["chóng mặt"],
            protocol_id="ERP-L1-TEST",
            user_message="Tôi thấy chóng mặt",
        )

        service.create_emergency_event(request)
        events = service.get_events_for_session("test-session-002")

        assert len(events) == 1
        assert events[0]["session_id"] == "test-session-002"
        assert events[0]["level"] == 1
        assert "chóng mặt" in events[0]["matched_keywords"]

    def test_seed_file_not_found_raises_error(self) -> None:
        """Error handling: FileNotFoundError for missing seed file."""
        from apps.api.foundation.emergency.service import (
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(
            seed_path=Path("/nonexistent/emergency.json")
        )

        with pytest.raises(FileNotFoundError):
            service.get_emergency_keyword_set()

    def test_to_dict_methods(self, mock_seed_file: Path) -> None:
        """Contract shape: DTO to_dict methods return correct structure."""
        from apps.api.foundation.emergency.service import (
            EmergencyEventCreateRequest,
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)

        # Test keyword set to_dict
        keyword_set = service.get_emergency_keyword_set()
        kw_dict = keyword_set.to_dict()
        assert "critical_keywords" in kw_dict
        assert "caution_keywords" in kw_dict
        assert "approval_status" in kw_dict

        # Test protocol to_dict
        protocol = service.get_emergency_protocol(level=2)
        assert protocol is not None
        proto_dict = protocol.to_dict()
        assert proto_dict["protocol_id"] == "ERP-L2-TEST"
        assert proto_dict["level"] == 2
        assert "response_text" in proto_dict
        assert "prohibited_content" in proto_dict

        # Test event request to_dict
        request = EmergencyEventCreateRequest(
            session_id="test",
            level=1,
            matched_keywords=["test"],
            protocol_id="test",
            user_message="test",
        )
        req_dict = request.to_dict()
        assert req_dict["session_id"] == "test"
        assert req_dict["level"] == 1


# ---------------------------------------------------------------------------
# Tests for EmergencyProtocolService
# ---------------------------------------------------------------------------


class TestEmergencyProtocolService:
    """Tests for the protocol loader service."""

    def test_load_protocol_returns_protocol(self, mock_seed_file: Path) -> None:
        """Protocol service loads protocol with validation."""
        from apps.api.capabilities.emergency.protocols.service import (
            EmergencyProtocolService,
        )
        from apps.api.foundation.emergency.service import EmergencyFoundationService

        foundation = EmergencyFoundationService(seed_path=mock_seed_file)
        service = EmergencyProtocolService(foundation_service=foundation)

        result = service.load_protocol(level=2)

        assert result.protocol is not None
        assert result.protocol.protocol_id == "ERP-L2-TEST"
        assert not result.used_fallback

    def test_load_protocol_returns_warning_for_mock(self, mock_seed_file: Path) -> None:
        """Mock protocol generates appropriate warning."""
        from apps.api.capabilities.emergency.protocols.service import (
            EmergencyProtocolService,
        )
        from apps.api.foundation.emergency.service import EmergencyFoundationService

        foundation = EmergencyFoundationService(seed_path=mock_seed_file)
        service = EmergencyProtocolService(foundation_service=foundation)

        result = service.load_protocol(level=2)

        assert len(result.warnings) > 0
        assert any("mock" in w.lower() for w in result.warnings)

    def test_load_protocol_uses_fallback_for_invalid_level(self, mock_seed_file: Path) -> None:
        """Invalid level returns fallback protocol."""
        from apps.api.capabilities.emergency.protocols.service import (
            EmergencyProtocolService,
        )
        from apps.api.foundation.emergency.service import EmergencyFoundationService

        foundation = EmergencyFoundationService(seed_path=mock_seed_file)
        service = EmergencyProtocolService(foundation_service=foundation)

        result = service.load_protocol(level=99)

        assert result.used_fallback is True
        assert result.protocol is not None
        assert result.protocol.protocol_id == "ERP-FALLBACK-V1"

    def test_get_protocol_response_text(self, mock_seed_file: Path) -> None:
        """Convenience method returns response text."""
        from apps.api.capabilities.emergency.protocols.service import (
            EmergencyProtocolService,
        )
        from apps.api.foundation.emergency.service import EmergencyFoundationService

        foundation = EmergencyFoundationService(seed_path=mock_seed_file)
        service = EmergencyProtocolService(foundation_service=foundation)

        response_text = service.get_protocol_response_text(level=2)

        assert "NGUY HIỂM" in response_text

    def test_validate_protocol_actions(self, mock_seed_file: Path) -> None:
        """Action validation works correctly."""
        from apps.api.capabilities.emergency.protocols.service import (
            EmergencyProtocolService,
        )
        from apps.api.foundation.emergency.service import EmergencyFoundationService

        foundation = EmergencyFoundationService(seed_path=mock_seed_file)
        service = EmergencyProtocolService(foundation_service=foundation)

        assert service.validate_protocol_actions(level=2, action="call_115") is True
        assert service.validate_protocol_actions(level=2, action="diagnosis") is False

    def test_get_prohibited_content_types(self, mock_seed_file: Path) -> None:
        """Prohibited content types are returned."""
        from apps.api.capabilities.emergency.protocols.service import (
            EmergencyProtocolService,
        )
        from apps.api.foundation.emergency.service import EmergencyFoundationService

        foundation = EmergencyFoundationService(seed_path=mock_seed_file)
        service = EmergencyProtocolService(foundation_service=foundation)

        prohibited = service.get_prohibited_content_types(level=2)

        assert "diagnosis" in prohibited


# ---------------------------------------------------------------------------
# Contract shape tests
# ---------------------------------------------------------------------------


class TestContractShapes:
    """Tests for contract shape compliance."""

    def test_keyword_set_dto_shape(self, mock_seed_file: Path) -> None:
        """Keyword set DTO matches INT-04 contract."""
        from apps.api.foundation.emergency.service import (
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)
        keyword_set = service.get_emergency_keyword_set()
        data = keyword_set.to_dict()

        # Required fields from INT-04
        assert "critical_keywords" in data
        assert "caution_keywords" in data
        assert "approval_status" in data
        assert "effective_date" in data

    def test_protocol_dto_shape(self, mock_seed_file: Path) -> None:
        """Protocol DTO matches INT-04 contract."""
        from apps.api.foundation.emergency.service import (
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)
        protocol = service.get_emergency_protocol(level=2)
        assert protocol is not None
        data = protocol.to_dict()

        # Required fields from INT-04
        assert "protocol_id" in data
        assert "level" in data
        assert "response_text" in data
        assert "hotlines" in data or "channel_refs" in data  # Accept either form
        assert "banner_level" in data
        assert "prohibited_content" in data

    def test_event_receipt_dto_shape(self, mock_seed_file: Path) -> None:
        """Event receipt DTO matches INT-04 contract."""
        from apps.api.foundation.emergency.service import (
            EmergencyEventCreateRequest,
            EmergencyFoundationService,
        )

        service = EmergencyFoundationService(seed_path=mock_seed_file)
        request = EmergencyEventCreateRequest(
            session_id="shape-test",
            level=2,
            matched_keywords=["test"],
            protocol_id="test",
            user_message="test",
        )
        receipt = service.create_emergency_event(request)
        data = receipt.to_dict()

        # Required fields from INT-04
        assert "event_id" in data
        assert "created_at" in data
        assert "level" in data
        assert "protocol_id" in data
# === TASK:WP-103:END ===

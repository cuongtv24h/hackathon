# === TASK:WP-101:START ===
"""Pytest contract tests for WP-101 Foundation services.

Tests cover:
- Session service: CreateSession, GetSessionContext, PatchSessionContext
- Configuration service: GetChannels, GetChatConfiguration
- Feedback service: CreateFeedback

All tests use in-memory stores; no external dependencies.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from apps.api.foundation.session.service import (
    SessionService,
    SessionCreateRequest,
    SessionDTO,
    SessionContextDTO,
    MessageDTO,
    EmergencyContextDTO,
    BookingFlowStateDTO,
    SessionContextPatchRequest,
)
from apps.api.foundation.configuration.service import (
    ConfigurationService,
    ChannelConfigurationDTO,
    ChatConfigurationDTO,
)
from apps.api.foundation.feedback.service import (
    FeedbackService,
    FeedbackCreateRequest,
    FeedbackReceiptDTO,
)
from packages.contracts import UnifiedErrorEnvelope


# ---------------------------------------------------------------------------
# Session Service Tests
# ---------------------------------------------------------------------------


class TestSessionService:
    """Tests for SessionService (FND-SES-01, FND-SES-02, FND-SES-03)."""

    def setup_method(self) -> None:
        self.service = SessionService(idle_seconds=1800, max_seconds=86400)

    # ---- FND-SES-01 CreateSession ----

    def test_create_session_success(self) -> None:
        """CreateSession returns a valid SessionDTO with session_id and expiry."""
        request = SessionCreateRequest(
            actor_tag="user_123",
            channel="web_widget",
            locale="vi-VN",
            timezone="Asia/Bangkok",
            metadata={"source": "landing_page"},
        )

        result = self.service.create_session(request)

        assert isinstance(result, SessionDTO)
        assert result.session_id.startswith("ses_")
        assert result.actor_tag == "user_123"
        assert result.channel == "web_widget"
        assert result.locale == "vi-VN"
        assert result.timezone == "Asia/Bangkok"
        assert result.metadata == {"source": "landing_page"}

        # Verify expiry is approximately max_seconds in the future
        created = datetime.fromisoformat(result.created_at.replace("Z", "+00:00"))
        expires = datetime.fromisoformat(result.expires_at.replace("Z", "+00:00"))
        delta = expires - created
        assert 86300 <= delta.total_seconds() <= 86500  # ~24 hours

    def test_create_session_defaults(self) -> None:
        """CreateSession uses default locale and timezone when omitted."""
        request = SessionCreateRequest(actor_tag="user_456", channel="web_page")

        result = self.service.create_session(request)

        assert result.locale == "vi-VN"
        assert result.timezone == "Asia/Bangkok"
        assert result.metadata == {}

    def test_create_session_invalid_actor_tag(self) -> None:
        """CreateSession rejects empty actor_tag with validation error."""
        request = SessionCreateRequest(actor_tag="", channel="web_widget")

        with pytest.raises(Exception) as exc_info:
            self.service.create_session(request)

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == "FIELD_REQUIRED"
        assert error.error.category == "validation"
        assert "actor_tag" in error.error.field_errors

    def test_create_session_invalid_channel(self) -> None:
        """CreateSession rejects invalid channel with validation error."""
        request = SessionCreateRequest(actor_tag="user_123", channel="invalid_channel")

        with pytest.raises(Exception) as exc_info:
            self.service.create_session(request)

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == "INVALID_ENUM"
        assert error.error.category == "validation"
        assert "channel" in error.error.field_errors

    def test_create_session_from_dict(self) -> None:
        """SessionCreateRequest.from_dict handles dict input correctly."""
        data = {
            "actor_tag": "user_dict",
            "channel": "web_widget",
            "locale": "en-US",
            "timezone": "UTC",
            "metadata": {"key": "value"},
        }
        request = SessionCreateRequest.from_dict(data)

        assert request.actor_tag == "user_dict"
        assert request.channel == "web_widget"
        assert request.locale == "en-US"
        assert request.timezone == "UTC"
        assert request.metadata == {"key": "value"}

    # ---- FND-SES-02 GetSessionContext ----

    def test_get_session_context_success(self) -> None:
        """GetSessionContext returns full context for valid session."""
        request = SessionCreateRequest(actor_tag="user_123", channel="web_widget")
        created = self.service.create_session(request)

        context = self.service.get_session_context(created.session_id)

        assert isinstance(context, SessionContextDTO)
        assert context.session_id == created.session_id
        assert context.actor_tag == "user_123"
        assert context.channel == "web_widget"
        assert context.messages == []
        assert context.emergency_context.triggered is False
        assert context.booking_flow.version == 0

    def test_get_session_context_not_found(self) -> None:
        """GetSessionContext returns NOT_FOUND for unknown session_id."""
        with pytest.raises(Exception) as exc_info:
            self.service.get_session_context("ses_nonexistent")

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == "CONTENT_NOT_FOUND"
        assert error.error.category == "not_found"

    def test_get_session_context_empty_id(self) -> None:
        """GetSessionContext rejects empty session_id."""
        with pytest.raises(Exception) as exc_info:
            self.service.get_session_context("")

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == "FIELD_REQUIRED"
        assert error.error.category == "validation"
        assert "session_id" in error.error.field_errors

    # ---- FND-SES-03 PatchSessionContext ----

    def test_patch_session_context_add_message(self) -> None:
        """PatchSessionContext can append messages."""
        request = SessionCreateRequest(actor_tag="user_123", channel="web_widget")
        created = self.service.create_session(request)

        message = MessageDTO(
            role="user",
            content="Hello, I need help with BHYT",
            intent="information_assistance",
        )
        patch = SessionContextPatchRequest(messages=[message])

        updated = self.service.patch_session_context(created.session_id, patch)

        assert len(updated.messages) == 1
        assert updated.messages[0].role == "user"
        assert updated.messages[0].content == "Hello, I need help with BHYT"
        assert updated.messages[0].intent == "information_assistance"

    def test_patch_session_context_update_emergency(self) -> None:
        """PatchSessionContext can update emergency context."""
        request = SessionCreateRequest(actor_tag="user_123", channel="web_widget")
        created = self.service.create_session(request)

        emergency = EmergencyContextDTO(
            triggered=True,
            level=1,
            path="cardiac_arrest",
            time=datetime.now(timezone.utc).isoformat(),
            banner="Call 115 immediately",
        )
        patch = SessionContextPatchRequest(emergency_context=emergency)

        updated = self.service.patch_session_context(created.session_id, patch)

        assert updated.emergency_context.triggered is True
        assert updated.emergency_context.level == 1
        assert updated.emergency_context.path == "cardiac_arrest"

    def test_patch_session_context_update_booking_flow(self) -> None:
        """PatchSessionContext can update booking flow state."""
        request = SessionCreateRequest(actor_tag="user_123", channel="web_widget")
        created = self.service.create_session(request)

        booking = BookingFlowStateDTO(
            flow_id="flow_123",
            step="select_doctor",
            selected_specialty_id="spec_cardio",
            selected_doctor_id="doc_001",
            collected_fields={"patient_name": "Nguyen Van A"},
            missing_fields=["phone", "dob"],
            version=1,
        )
        patch = SessionContextPatchRequest(booking_flow=booking)

        updated = self.service.patch_session_context(created.session_id, patch)

        assert updated.booking_flow.flow_id == "flow_123"
        assert updated.booking_flow.step == "select_doctor"
        assert updated.booking_flow.selected_specialty_id == "spec_cardio"
        assert updated.booking_flow.collected_fields == {"patient_name": "Nguyen Van A"}
        assert updated.booking_flow.missing_fields == ["phone", "dob"]
        assert updated.booking_flow.version == 1

    def test_patch_session_context_merge_metadata(self) -> None:
        """PatchSessionContext replaces metadata entirely."""
        request = SessionCreateRequest(
            actor_tag="user_123", channel="web_widget", metadata={"original": "value"}
        )
        created = self.service.create_session(request)

        patch = SessionContextPatchRequest(metadata={"new": "metadata"})

        updated = self.service.patch_session_context(created.session_id, patch)

        assert updated.metadata == {"new": "metadata"}

    def test_patch_session_context_not_found(self) -> None:
        """PatchSessionContext returns NOT_FOUND for unknown session."""
        patch = SessionContextPatchRequest()

        with pytest.raises(Exception) as exc_info:
            self.service.patch_session_context("ses_nonexistent", patch)

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == "CONTENT_NOT_FOUND"
        assert error.error.category == "not_found"

    def test_patch_session_context_empty_id(self) -> None:
        """PatchSessionContext rejects empty session_id."""
        patch = SessionContextPatchRequest()

        with pytest.raises(Exception) as exc_info:
            self.service.patch_session_context("", patch)

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == "FIELD_REQUIRED"
        assert error.error.category == "validation"

    def test_patch_session_context_from_dict(self) -> None:
        """SessionContextPatchRequest.from_dict handles dict input correctly."""
        data = {
            "messages": [
                {"role": "user", "content": "Test message", "intent": "test"}
            ],
            "emergency_context": {"triggered": True, "level": 2},
            "booking_flow": {"flow_id": "flow_1", "step": "confirm", "version": 2},
            "metadata": {"patched": True},
        }
        patch = SessionContextPatchRequest.from_dict(data)

        assert patch.messages is not None
        assert len(patch.messages) == 1
        assert patch.messages[0].role == "user"
        assert patch.messages[0].content == "Test message"
        assert patch.messages[0].intent == "test"

        assert patch.emergency_context is not None
        assert patch.emergency_context.triggered is True
        assert patch.emergency_context.level == 2

        assert patch.booking_flow is not None
        assert patch.booking_flow.flow_id == "flow_1"
        assert patch.booking_flow.step == "confirm"
        assert patch.booking_flow.version == 2

        assert patch.metadata == {"patched": True}

    # ---- Session Expiry ----

    def test_session_expiry(self) -> None:
        """Expired sessions return NOT_FOUND on get/patch."""
        # Create service with very short expiry
        service = SessionService(idle_seconds=0, max_seconds=0)
        request = SessionCreateRequest(actor_tag="user_123", channel="web_widget")
        created = service.create_session(request)

        # Session should be expired immediately
        with pytest.raises(Exception) as exc_info:
            service.get_session_context(created.session_id)
        assert exc_info.value.error.code == "CONTENT_NOT_FOUND"

        with pytest.raises(Exception) as exc_info:
            service.patch_session_context(created.session_id, SessionContextPatchRequest())
        assert exc_info.value.error.code == "CONTENT_NOT_FOUND"

    # ---- MessageDTO ----

    def test_message_dto_serialization(self) -> None:
        """MessageDTO.to_dict produces correct shape."""
        msg = MessageDTO(
            role="assistant",
            content="Here is the information...",
            intent="information_assistance",
            tools=[{"name": "search_knowledge"}],
            citations=[{"source": "doc_1", "chunk_id": "chunk_1"}],
            emergency_metadata={"level": 0},
        )
        d = msg.to_dict()

        assert d["role"] == "assistant"
        assert d["content"] == "Here is the information..."
        assert d["intent"] == "information_assistance"
        assert d["tools"] == [{"name": "search_knowledge"}]
        assert d["citations"] == [{"source": "doc_1", "chunk_id": "chunk_1"}]
        assert d["emergency_metadata"] == {"level": 0}
        assert "time" in d

    # ---- EmergencyContextDTO ----

    def test_emergency_context_dto_serialization(self) -> None:
        """EmergencyContextDTO.to_dict produces correct shape."""
        ec = EmergencyContextDTO(
            triggered=True, level=1, path="stroke", time="2024-01-01T00:00:00Z", banner="Call 115"
        )
        d = ec.to_dict()

        assert d["triggered"] is True
        assert d["level"] == 1
        assert d["path"] == "stroke"
        assert d["time"] == "2024-01-01T00:00:00Z"
        assert d["banner"] == "Call 115"

    def test_emergency_context_dto_defaults(self) -> None:
        """EmergencyContextDTO defaults to minimal shape."""
        ec = EmergencyContextDTO()
        d = ec.to_dict()

        assert d == {"triggered": False}

    # ---- BookingFlowStateDTO ----

    def test_booking_flow_state_dto_serialization(self) -> None:
        """BookingFlowStateDTO.to_dict produces correct shape."""
        bf = BookingFlowStateDTO(
            flow_id="flow_1",
            step="select_slot",
            selected_specialty_id="spec_1",
            selected_doctor_id="doc_1",
            selected_slot_id="slot_1",
            collected_fields={"name": "A", "phone": "0900000000"},
            missing_fields=["dob"],
            version=3,
        )
        d = bf.to_dict()

        assert d["flow_id"] == "flow_1"
        assert d["step"] == "select_slot"
        assert d["selected_specialty_id"] == "spec_1"
        assert d["selected_doctor_id"] == "doc_1"
        assert d["selected_slot_id"] == "slot_1"
        assert d["collected_fields"] == {"name": "A", "phone": "0900000000"}
        assert d["missing_fields"] == ["dob"]
        assert d["version"] == 3

    # ---- SessionContextDTO ----

    def test_session_context_dto_serialization(self) -> None:
        """SessionContextDTO.to_dict includes all fields."""
        ctx = SessionContextDTO(
            session_id="ses_123",
            actor_tag="user_1",
            channel="web_widget",
            created_at="2024-01-01T00:00:00Z",
            expires_at="2024-01-02T00:00:00Z",
            locale="vi-VN",
            timezone="Asia/Bangkok",
            messages=[MessageDTO(role="user", content="Hello")],
            emergency_context=EmergencyContextDTO(triggered=True, level=1),
            booking_flow=BookingFlowStateDTO(flow_id="flow_1", version=1),
            metadata={"custom": "data"},
        )
        d = ctx.to_dict()

        assert d["session_id"] == "ses_123"
        assert d["actor_tag"] == "user_1"
        assert d["channel"] == "web_widget"
        assert d["created_at"] == "2024-01-01T00:00:00Z"
        assert d["expires_at"] == "2024-01-02T00:00:00Z"
        assert d["locale"] == "vi-VN"
        assert d["timezone"] == "Asia/Bangkok"
        assert len(d["messages"]) == 1
        assert d["emergency_context"]["triggered"] is True
        assert d["emergency_context"]["level"] == 1
        assert d["booking_flow"]["flow_id"] == "flow_1"
        assert d["booking_flow"]["version"] == 1
        assert d["metadata"] == {"custom": "data"}


# ---------------------------------------------------------------------------
# Configuration Service Tests
# ---------------------------------------------------------------------------


class TestConfigurationService:
    """Tests for ConfigurationService (FND-CFG-01, FND-CFG-02)."""

    def setup_method(self) -> None:
        self.service = ConfigurationService()

    # ---- FND-CFG-01 GetChannels ----

    def test_get_channels_returns_both_channels(self) -> None:
        """GetChannels returns web_widget and web_page configurations."""
        channels = self.service.get_channels()

        assert isinstance(channels, list)
        assert len(channels) == 2

        channel_ids = {c.channel for c in channels}
        assert channel_ids == {"web_widget", "web_page"}

        for channel in channels:
            assert isinstance(channel, ChannelConfigurationDTO)
            assert channel.enabled is True
            assert channel.display_name is not None

    def test_get_channels_web_widget_config(self) -> None:
        """web_widget channel has expected configuration."""
        channels = self.service.get_channels()
        widget = next(c for c in channels if c.channel == "web_widget")

        assert widget.enabled is True
        assert widget.base_url is not None
        assert "widget" in widget.base_url.lower()

    def test_get_channels_web_page_config(self) -> None:
        """web_page channel has expected configuration."""
        channels = self.service.get_channels()
        page = next(c for c in channels if c.channel == "web_page")

        assert page.enabled is True
        assert page.base_url is not None
        assert "chat" in page.base_url.lower()

    def test_get_channels_serialization(self) -> None:
        """ChannelConfigurationDTO.to_dict produces correct shape."""
        channels = self.service.get_channels()
        for channel in channels:
            d = channel.to_dict()
            assert d["channel"] in ("web_widget", "web_page")
            assert "enabled" in d
            assert "display_name" in d
            if channel.base_url:
                assert "base_url" in d

    # ---- FND-CFG-02 GetChatConfiguration ----

    def test_get_chat_configuration_returns_defaults(self) -> None:
        """GetChatConfiguration returns MVP binding values from INT-09."""
        config = self.service.get_chat_configuration()

        assert isinstance(config, ChatConfigurationDTO)
        assert config.max_message_length == 4000
        assert config.max_messages_per_session == 100
        assert config.messages_per_session_per_minute == 20
        assert config.messages_per_ip_per_minute == 60
        assert config.appointment_create_per_session_per_minute == 5
        assert config.content_write_per_user_per_minute == 30
        assert config.analytics_read_per_user_per_minute == 60
        assert config.idle_timeout_seconds == 1800
        assert config.max_session_duration_seconds == 86400

    def test_get_chat_configuration_serialization(self) -> None:
        """ChatConfigurationDTO.to_dict produces correct shape (per INT-04 contract)."""
        config = self.service.get_chat_configuration()
        d = config.to_dict()

        # Per INT-04 / packages.contracts.ChatConfigurationDTO, metadata is always included
        expected_keys = {
            "max_message_length",
            "max_messages_per_session",
            "messages_per_session_per_minute",
            "messages_per_ip_per_minute",
            "appointment_create_per_session_per_minute",
            "content_write_per_user_per_minute",
            "analytics_read_per_user_per_minute",
            "idle_timeout_seconds",
            "max_session_duration_seconds",
            "metadata",
        }
        assert set(d.keys()) == expected_keys
        assert all(isinstance(v, int) for k, v in d.items() if k != "metadata")
        assert isinstance(d["metadata"], dict)


# ---------------------------------------------------------------------------
# Feedback Service Tests
# ---------------------------------------------------------------------------


class TestFeedbackService:
    """Tests for FeedbackService (FND-FBK-01)."""

    def setup_method(self) -> None:
        self.service = FeedbackService()

    # ---- FND-FBK-01 CreateFeedback ----

    def test_create_feedback_success(self) -> None:
        """CreateFeedback returns a valid FeedbackReceiptDTO."""
        request = FeedbackCreateRequest(
            session_id="ses_123",
            rating=5,
            comment="Great service!",
            category="general",
            metadata={"page": "/chat"},
        )

        receipt = self.service.create_feedback(request)

        assert isinstance(receipt, FeedbackReceiptDTO)
        assert receipt.feedback_id.startswith("fbk_")
        assert receipt.session_id == "ses_123"
        assert receipt.rating == 5
        assert receipt.comment == "Great service!"
        assert receipt.category == "general"
        assert receipt.metadata == {"page": "/chat"}
        assert receipt.created_at is not None

    def test_create_feedback_minimal(self) -> None:
        """CreateFeedback works with only required fields."""
        request = FeedbackCreateRequest(session_id="ses_456", rating=3)

        receipt = self.service.create_feedback(request)

        assert receipt.session_id == "ses_456"
        assert receipt.rating == 3
        assert receipt.comment is None
        assert receipt.category is None
        assert receipt.metadata == {}

    def test_create_feedback_from_dict(self) -> None:
        """FeedbackCreateRequest.from_dict handles dict input."""
        data = {
            "session_id": "ses_dict",
            "rating": 4,
            "comment": "Good",
            "category": "ui",
            "metadata": {"browser": "chrome"},
        }
        request = FeedbackCreateRequest.from_dict(data)

        assert request.session_id == "ses_dict"
        assert request.rating == 4
        assert request.comment == "Good"
        assert request.category == "ui"
        assert request.metadata == {"browser": "chrome"}

    def test_create_feedback_invalid_session_id(self) -> None:
        """CreateFeedback rejects empty session_id."""
        request = FeedbackCreateRequest(session_id="", rating=5)

        with pytest.raises(Exception) as exc_info:
            self.service.create_feedback(request)

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == "FIELD_REQUIRED"
        assert error.error.category == "validation"
        assert "session_id" in error.error.field_errors

    def test_create_feedback_invalid_rating_low(self) -> None:
        """CreateFeedback rejects rating < 1."""
        request = FeedbackCreateRequest(session_id="ses_123", rating=0)

        with pytest.raises(Exception) as exc_info:
            self.service.create_feedback(request)

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == "INVALID_REQUEST"
        assert error.error.category == "validation"
        assert "rating" in error.error.field_errors

    def test_create_feedback_invalid_rating_high(self) -> None:
        """CreateFeedback rejects rating > 5."""
        request = FeedbackCreateRequest(session_id="ses_123", rating=6)

        with pytest.raises(Exception) as exc_info:
            self.service.create_feedback(request)

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == "INVALID_REQUEST"
        assert error.error.category == "validation"
        assert "rating" in error.error.field_errors

    def test_create_feedback_comment_too_long(self) -> None:
        """CreateFeedback rejects comment > 4000 chars."""
        request = FeedbackCreateRequest(
            session_id="ses_123", rating=5, comment="x" * 4001
        )

        with pytest.raises(Exception) as exc_info:
            self.service.create_feedback(request)

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == "MESSAGE_TOO_LONG"
        assert error.error.category == "validation"
        assert "comment" in error.error.field_errors

    def test_create_feedback_non_integer_rating(self) -> None:
        """CreateFeedback rejects non-integer rating."""
        request = FeedbackCreateRequest(session_id="ses_123", rating=3.5)  # type: ignore

        with pytest.raises(Exception) as exc_info:
            self.service.create_feedback(request)

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == "INVALID_REQUEST"
        assert error.error.category == "validation"
        assert "rating" in error.error.field_errors

    # ---- Helper methods ----

    def test_get_feedback_by_id(self) -> None:
        """get_feedback retrieves created feedback."""
        request = FeedbackCreateRequest(session_id="ses_123", rating=5)
        receipt = self.service.create_feedback(request)

        fetched = self.service.get_feedback(receipt.feedback_id)

        assert fetched is not None
        assert fetched.feedback_id == receipt.feedback_id
        assert fetched.session_id == "ses_123"
        assert fetched.rating == 5

    def test_get_feedback_not_found(self) -> None:
        """get_feedback returns None for unknown ID."""
        result = self.service.get_feedback("fbk_nonexistent")
        assert result is None

    def test_list_feedback_by_session(self) -> None:
        """list_feedback_by_session returns all feedback for a session."""
        self.service.create_feedback(FeedbackCreateRequest(session_id="ses_list", rating=4))
        self.service.create_feedback(FeedbackCreateRequest(session_id="ses_list", rating=5))
        self.service.create_feedback(FeedbackCreateRequest(session_id="ses_other", rating=3))

        results = self.service.list_feedback_by_session("ses_list")

        assert len(results) == 2
        assert all(r.session_id == "ses_list" for r in results)
        assert {r.rating for r in results} == {4, 5}

    # ---- FeedbackReceiptDTO ----

    def test_feedback_receipt_dto_serialization(self) -> None:
        """FeedbackReceiptDTO.to_dict produces correct shape."""
        receipt = FeedbackReceiptDTO(
            feedback_id="fbk_123",
            session_id="ses_123",
            rating=5,
            comment="Excellent",
            category="general",
            created_at="2024-01-01T00:00:00Z",
            metadata={"source": "web"},
        )
        d = receipt.to_dict()

        assert d["feedback_id"] == "fbk_123"
        assert d["session_id"] == "ses_123"
        assert d["rating"] == 5
        assert d["comment"] == "Excellent"
        assert d["category"] == "general"
        assert d["created_at"] == "2024-01-01T00:00:00Z"
        assert d["metadata"] == {"source": "web"}

    def test_feedback_receipt_dto_minimal(self) -> None:
        """FeedbackReceiptDTO.to_dict omits optional None fields."""
        receipt = FeedbackReceiptDTO(
            feedback_id="fbk_123",
            session_id="ses_123",
            rating=3,
            comment=None,
            category=None,
            created_at="2024-01-01T00:00:00Z",
            metadata={},
        )
        d = receipt.to_dict()

        assert "comment" not in d
        assert "category" not in d
        assert "metadata" not in d
        assert d["feedback_id"] == "fbk_123"
        assert d["rating"] == 3


# ---------------------------------------------------------------------------
# Contract Shape Tests
# ---------------------------------------------------------------------------


class TestContractShapes:
    """Verify DTO shapes match INT-04 canonical contracts."""

    def test_session_dto_has_required_fields(self) -> None:
        """SessionDTO includes all fields from INT-04."""
        dto = SessionDTO(
            session_id="ses_1",
            actor_tag="user_1",
            channel="web_widget",
            created_at="2024-01-01T00:00:00Z",
            expires_at="2024-01-02T00:00:00Z",
            locale="vi-VN",
            timezone="Asia/Bangkok",
            metadata={},
        )
        d = dto.to_dict()

        required = {
            "session_id",
            "actor_tag",
            "channel",
            "created_at",
            "expires_at",
            "locale",
            "timezone",
            "metadata",
        }
        assert set(d.keys()) == required

    def test_session_context_dto_has_required_fields(self) -> None:
        """SessionContextDTO includes all fields from INT-04."""
        dto = SessionContextDTO(
            session_id="ses_1",
            actor_tag="user_1",
            channel="web_widget",
            created_at="2024-01-01T00:00:00Z",
            expires_at="2024-01-02T00:00:00Z",
            locale="vi-VN",
            timezone="Asia/Bangkok",
        )
        d = dto.to_dict()

        required = {
            "session_id",
            "actor_tag",
            "channel",
            "created_at",
            "expires_at",
            "locale",
            "timezone",
            "messages",
            "emergency_context",
            "booking_flow",
            "metadata",
        }
        assert set(d.keys()) == required

    def test_channel_configuration_dto_has_required_fields(self) -> None:
        """ChannelConfigurationDTO includes all fields from INT-04 (per packages.contracts)."""
        dto = ChannelConfigurationDTO(
            channel="web_widget", enabled=True, base_url="https://example.com/widget"
        )
        d = dto.to_dict()

        # Per INT-04 / packages.contracts.ChannelConfigurationDTO, optional fields
        # (display_name, metadata) are only included when non-None/non-empty
        required = {"channel", "enabled", "base_url"}
        assert set(d.keys()) == required
        assert d["channel"] == "web_widget"
        assert d["enabled"] is True
        assert d["base_url"] == "https://example.com/widget"

    def test_chat_configuration_dto_has_required_fields(self) -> None:
        """ChatConfigurationDTO includes all MVP binding values from INT-09."""
        dto = ChatConfigurationDTO()
        d = dto.to_dict()

        required = {
            "max_message_length",
            "max_messages_per_session",
            "messages_per_session_per_minute",
            "messages_per_ip_per_minute",
            "appointment_create_per_session_per_minute",
            "content_write_per_user_per_minute",
            "analytics_read_per_user_per_minute",
            "idle_timeout_seconds",
            "max_session_duration_seconds",
            "metadata",
        }
        assert set(d.keys()) == required

    def test_feedback_receipt_dto_has_required_fields(self) -> None:
        """FeedbackReceiptDTO includes all fields from INT-04 (per packages.contracts)."""
        dto = FeedbackReceiptDTO(
            feedback_id="fbk_1",
            session_id="ses_1",
            rating=5,
            comment="Good",
            category="general",
            created_at="2024-01-01T00:00:00Z",
            metadata={},
        )
        d = dto.to_dict()

        # Per INT-04 / local FeedbackReceiptDTO, optional fields are only
        # included when non-None; metadata is only included when non-empty
        required = {"feedback_id", "session_id", "rating", "created_at"}
        optional_present = {"comment", "category"}
        assert set(d.keys()) == required | optional_present
        assert d["feedback_id"] == "fbk_1"
        assert d["session_id"] == "ses_1"
        assert d["rating"] == 5
        assert d["comment"] == "Good"
        assert d["category"] == "general"
        assert d["created_at"] == "2024-01-01T00:00:00Z"
        # metadata is empty so not included
        assert "metadata" not in d


# === TASK:WP-101:END ===
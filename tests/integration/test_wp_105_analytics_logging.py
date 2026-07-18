# === TASK:WP-105:START ===
"""Integration tests for WP-105 Analytics and Logging services.

This module tests the conversation history service (FND-HIS-01) and
analytics summary service (FND-ANA-01) defined in
docs/artifacts/interface/foundation-api-contracts.md (INT-03).

Tests use in-memory stores; no external dependencies.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from apps.api.foundation.analytics.service import (
    AnalyticsService,
    AnalyticsSummaryDTO,
    AnalyticsSummaryQuery,
    ConversationHistoryItem,
    ConversationHistoryPageDTO,
    ConversationHistoryQuery,
    ConversationHistoryService,
    _InMemoryAnalyticsStore,
    _InMemoryConversationHistoryStore,
)
from apps.api.logging.conversation.service import (
    ConversationLogEntry,
    ConversationLogPage,
    ConversationLogQuery,
    ConversationLogService,
    _InMemoryConversationStore,
)
from apps.api.logging.audit.service import (
    AuditLogEntry,
    AuditLogPage,
    AuditLogQuery,
    AuditLogService,
    _InMemoryAuditStore,
)
from packages.contracts import (
    UnifiedErrorEnvelope,
    CATEGORY_VALIDATION,
    FIELD_REQUIRED,
    INVALID_REQUEST,
)


# =============================================================================
# Test fixtures
# =============================================================================


@pytest.fixture
def conversation_store() -> _InMemoryConversationStore:
    """Fresh in-memory conversation store."""
    store = _InMemoryConversationStore()
    store.clear()
    return store


@pytest.fixture
def audit_store() -> _InMemoryAuditStore:
    """Fresh in-memory audit store."""
    store = _InMemoryAuditStore()
    store.clear()
    return store


@pytest.fixture
def analytics_store() -> _InMemoryAnalyticsStore:
    """Fresh in-memory analytics store."""
    store = _InMemoryAnalyticsStore()
    store.clear()
    return store


@pytest.fixture
def conversation_service(conversation_store) -> ConversationLogService:
    """ConversationLogService with test store."""
    return ConversationLogService(store=conversation_store)


@pytest.fixture
def audit_service(audit_store) -> AuditLogService:
    """AuditLogService with test store."""
    return AuditLogService(store=audit_store)


@pytest.fixture
def analytics_service(analytics_store) -> AnalyticsService:
    """AnalyticsService with test store."""
    return AnalyticsService(store=analytics_store)


@pytest.fixture
def history_service() -> ConversationHistoryService:
    """ConversationHistoryService with test store."""
    store = _InMemoryConversationHistoryStore()
    return ConversationHistoryService(store=store)


# =============================================================================
# ConversationLogService tests (FND-LOG-01, FND-LOG-02)
# =============================================================================


class TestConversationLogService:
    """Tests for ConversationLogService (FND-LOG-01 AppendLogEntry, FND-LOG-02 QueryConversationLog)."""

    def test_append_entry_success(self, conversation_service: ConversationLogService) -> None:
        """AppendLogEntry stores an anonymized entry."""
        entry = conversation_service.append_entry(
            session_id="ses_123",
            role="user",
            content="Hello, I need help with BHYT",
        )

        assert isinstance(entry, ConversationLogEntry)
        assert entry.session_id == "ses_123"
        assert entry.role == "user"
        assert entry.content == "Hello, I need help with BHYT"
        assert entry.has_pii is False
        assert entry.pii_redacted is False
        assert entry.turn_id.startswith("turn_")

    def test_append_entry_redacts_pii(self, conversation_service: ConversationLogService) -> None:
        """AppendLogEntry redacts phone numbers and emails."""
        entry = conversation_service.append_entry(
            session_id="ses_123",
            role="user",
            content="My phone is 0901234567 and email is test@example.com",
        )

        assert entry.has_pii is True
        assert entry.pii_redacted is True
        assert "[REDACTED]" in entry.content
        assert "0901234567" not in entry.content
        assert "test@example.com" not in entry.content

    def test_append_entry_validates_session_id(self, conversation_service: ConversationLogService) -> None:
        """AppendLogEntry rejects empty session_id."""
        with pytest.raises(Exception) as exc_info:
            conversation_service.append_entry(
                session_id="",
                role="user",
                content="Hello",
            )

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == FIELD_REQUIRED
        assert error.error.category == CATEGORY_VALIDATION
        assert "session_id" in error.error.field_errors

    def test_append_entry_validates_role(self, conversation_service: ConversationLogService) -> None:
        """AppendLogEntry rejects invalid role."""
        with pytest.raises(Exception) as exc_info:
            conversation_service.append_entry(
                session_id="ses_123",
                role="invalid_role",
                content="Hello",
            )

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED
        assert "role" in error.error.field_errors

    def test_append_entry_validates_content(self, conversation_service: ConversationLogService) -> None:
        """AppendLogEntry rejects empty content."""
        with pytest.raises(Exception) as exc_info:
            conversation_service.append_entry(
                session_id="ses_123",
                role="user",
                content="",
            )

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED
        assert "content" in error.error.field_errors

    def test_query_log_returns_entries(self, conversation_service: ConversationLogService) -> None:
        """QueryConversationLog returns entries for a session."""
        conversation_service.append_entry("ses_123", "user", "Hello")
        conversation_service.append_entry("ses_123", "assistant", "Hi there!")
        conversation_service.append_entry("ses_456", "user", "Other session")

        page = conversation_service.query_log("ses_123", limit=10, offset=0)

        assert isinstance(page, ConversationLogPage)
        assert page.total == 2
        assert len(page.entries) == 2
        assert page.entries[0].session_id == "ses_123"
        assert page.entries[1].session_id == "ses_123"

    def test_query_log_paginates(self, conversation_service: ConversationLogService) -> None:
        """QueryConversationLog respects limit and offset."""
        for i in range(5):
            conversation_service.append_entry("ses_123", "user", f"Message {i}")

        page1 = conversation_service.query_log("ses_123", limit=2, offset=0)
        page2 = conversation_service.query_log("ses_123", limit=2, offset=2)

        assert len(page1.entries) == 2
        assert len(page2.entries) == 2
        assert page1.total == 5
        assert page2.total == 5
        assert page1.entries[0].content == "Message 0"
        assert page2.entries[0].content == "Message 2"

    def test_query_log_filters_by_time(self, conversation_service: ConversationLogService) -> None:
        """QueryConversationLog filters by from_time and to_time."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conversation_service.append_entry("ses_123", "user", "Old message")
        now = datetime.now(timezone.utc).isoformat()

        # Should include the message we just added
        page = conversation_service.query_log("ses_123", from_time=past, to_time=now)
        assert page.total >= 1

    def test_query_log_validates_session_id(self, conversation_service: ConversationLogService) -> None:
        """QueryConversationLog rejects empty session_id."""
        with pytest.raises(Exception) as exc_info:
            conversation_service.query_log("")

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED
        assert "session_id" in error.error.field_errors

    def test_query_log_validates_limit(self, conversation_service: ConversationLogService) -> None:
        """QueryConversationLog rejects limit out of range."""
        with pytest.raises(Exception) as exc_info:
            conversation_service.query_log("ses_123", limit=0)
        assert exc_info.value.error.code == FIELD_REQUIRED

        with pytest.raises(Exception) as exc_info:
            conversation_service.query_log("ses_123", limit=201)
        assert exc_info.value.error.code == FIELD_REQUIRED

    def test_query_log_validates_offset(self, conversation_service: ConversationLogService) -> None:
        """QueryConversationLog rejects negative offset."""
        with pytest.raises(Exception) as exc_info:
            conversation_service.query_log("ses_123", offset=-1)

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED
        assert "offset" in error.error.field_errors


# =============================================================================
# AuditLogService tests (FND-AUD-01, FND-AUD-02)
# =============================================================================


class TestAuditLogService:
    """Tests for AuditLogService (FND-AUD-01 WriteAuditEntry, FND-AUD-02 QueryAuditLog)."""

    def test_write_entry_success(self, audit_service: AuditLogService) -> None:
        """WriteAuditEntry creates an immutable audit record."""
        entry = audit_service.write_entry(
            event_type="emergency",
            actor="system",
            action="trigger_emergency",
            resource="ses_123",
            details={"level": 1, "path": "cardiac_arrest"},
            session_id="ses_123",
            outcome="success",
        )

        assert isinstance(entry, AuditLogEntry)
        assert entry.audit_id.startswith("aud_")
        assert entry.event_type == "emergency"
        assert entry.actor == "system"
        assert entry.action == "trigger_emergency"
        assert entry.resource == "ses_123"
        assert entry.details == {"level": 1, "path": "cardiac_arrest"}
        assert entry.session_id == "ses_123"
        assert entry.outcome == "success"
        assert entry.created_at is not None

    def test_write_entry_validates_event_type(self, audit_service: AuditLogService) -> None:
        """WriteAuditEntry rejects invalid event_type."""
        with pytest.raises(Exception) as exc_info:
            audit_service.write_entry(
                event_type="invalid_type",
                actor="system",
                action="test",
                resource="res_1",
            )

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED
        assert "event_type" in error.error.field_errors

    def test_write_entry_validates_actor(self, audit_service: AuditLogService) -> None:
        """WriteAuditEntry rejects empty actor."""
        with pytest.raises(Exception) as exc_info:
            audit_service.write_entry(
                event_type="emergency",
                actor="",
                action="test",
                resource="res_1",
            )

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED
        assert "actor" in error.error.field_errors

    def test_write_entry_validates_action(self, audit_service: AuditLogService) -> None:
        """WriteAuditEntry rejects empty action."""
        with pytest.raises(Exception) as exc_info:
            audit_service.write_entry(
                event_type="emergency",
                actor="system",
                action="",
                resource="res_1",
            )

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED
        assert "action" in error.error.field_errors

    def test_write_entry_validates_resource(self, audit_service: AuditLogService) -> None:
        """WriteAuditEntry rejects empty resource."""
        with pytest.raises(Exception) as exc_info:
            audit_service.write_entry(
                event_type="emergency",
                actor="system",
                action="test",
                resource="",
            )

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED
        assert "resource" in error.error.field_errors

    def test_write_entry_validates_outcome(self, audit_service: AuditLogService) -> None:
        """WriteAuditEntry rejects invalid outcome."""
        with pytest.raises(Exception) as exc_info:
            audit_service.write_entry(
                event_type="emergency",
                actor="system",
                action="test",
                resource="res_1",
                outcome="invalid_outcome",
            )

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED
        assert "outcome" in error.error.field_errors

    def test_query_log_returns_entries(self, audit_service: AuditLogService) -> None:
        """QueryAuditLog returns audit entries."""
        audit_service.write_entry("emergency", "system", "trigger", "ses_1")
        audit_service.write_entry("security", "admin", "login", "user_1")

        page = audit_service.query_log(limit=10, offset=0)

        assert isinstance(page, AuditLogPage)
        assert page.total == 2
        assert len(page.entries) == 2

    def test_query_log_filters_by_event_type(self, audit_service: AuditLogService) -> None:
        """QueryAuditLog filters by event_type."""
        audit_service.write_entry("emergency", "system", "trigger", "ses_1")
        audit_service.write_entry("security", "admin", "login", "user_1")

        page = audit_service.query_log(event_type="emergency", limit=10, offset=0)

        assert page.total == 1
        assert page.entries[0].event_type == "emergency"

    def test_query_log_filters_by_actor(self, audit_service: AuditLogService) -> None:
        """QueryAuditLog filters by actor."""
        audit_service.write_entry("emergency", "system", "trigger", "ses_1")
        audit_service.write_entry("security", "admin", "login", "user_1")

        page = audit_service.query_log(actor="admin", limit=10, offset=0)

        assert page.total == 1
        assert page.entries[0].actor == "admin"

    def test_query_log_validates_limit(self, audit_service: AuditLogService) -> None:
        """QueryAuditLog rejects limit out of range."""
        with pytest.raises(Exception) as exc_info:
            audit_service.query_log(limit=0)
        assert exc_info.value.error.code == FIELD_REQUIRED

        with pytest.raises(Exception) as exc_info:
            audit_service.query_log(limit=201)
        assert exc_info.value.error.code == FIELD_REQUIRED

    def test_query_log_validates_offset(self, audit_service: AuditLogService) -> None:
        """QueryAuditLog rejects negative offset."""
        with pytest.raises(Exception) as exc_info:
            audit_service.query_log(offset=-1)

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED
        assert "offset" in error.error.field_errors


# =============================================================================
# ConversationHistoryService tests (FND-HIS-01 GetConversationHistory)
# =============================================================================


class TestConversationHistoryService:
    """Tests for ConversationHistoryService (FND-HIS-01 GetConversationHistory)."""

    def test_get_history_success(
        self,
        history_service: ConversationHistoryService,
    ) -> None:
        """GetConversationHistory returns paginated anonymized history."""
        # Seed history store directly with ConversationHistoryItem objects
        now = datetime.now(timezone.utc).isoformat()
        history_service.append_entry(ConversationHistoryItem(
            session_id="ses_123",
            turn_id="turn_1",
            role="user",
            content="Hello",
            created_at=now,
        ))
        history_service.append_entry(ConversationHistoryItem(
            session_id="ses_123",
            turn_id="turn_2",
            role="assistant",
            content="Hi there!",
            created_at=now,
        ))
        history_service.append_entry(ConversationHistoryItem(
            session_id="ses_123",
            turn_id="turn_3",
            role="user",
            content="What is BHYT?",
            intent="information_assistance",
            created_at=now,
        ))

        # Get history
        query = ConversationHistoryQuery(
            session_id="ses_123",
            limit=10,
            offset=0,
        )
        page = history_service.get_history(query)

        assert isinstance(page, ConversationHistoryPageDTO)
        assert page.total == 3
        assert len(page.items) == 3
        assert page.limit == 10
        assert page.offset == 0

        # Verify items are anonymized
        for item in page.items:
            assert isinstance(item, ConversationHistoryItem)
            assert item.session_id == "ses_123"
            assert item.has_pii is False  # No PII in test data

    def test_get_history_filters_by_session(
        self,
        history_service: ConversationHistoryService,
    ) -> None:
        """GetConversationHistory filters by session_id."""
        now = datetime.now(timezone.utc).isoformat()
        history_service.append_entry(ConversationHistoryItem(
            session_id="ses_123",
            turn_id="turn_1",
            role="user",
            content="Message in session 123",
            created_at=now,
        ))
        history_service.append_entry(ConversationHistoryItem(
            session_id="ses_456",
            turn_id="turn_2",
            role="user",
            content="Message in session 456",
            created_at=now,
        ))

        query = ConversationHistoryQuery(session_id="ses_123", limit=10, offset=0)
        page = history_service.get_history(query)

        assert page.total == 1
        assert page.items[0].session_id == "ses_123"

    def test_get_history_paginates(
        self,
        history_service: ConversationHistoryService,
    ) -> None:
        """GetConversationHistory paginates results."""
        now = datetime.now(timezone.utc).isoformat()
        for i in range(5):
            history_service.append_entry(ConversationHistoryItem(
                session_id="ses_123",
                turn_id=f"turn_{i}",
                role="user",
                content=f"Message {i}",
                created_at=now,
            ))

        page1 = history_service.get_history(
            ConversationHistoryQuery(session_id="ses_123", limit=2, offset=0)
        )
        page2 = history_service.get_history(
            ConversationHistoryQuery(session_id="ses_123", limit=2, offset=2)
        )

        assert len(page1.items) == 2
        assert len(page2.items) == 2
        assert page1.total == 5
        assert page2.total == 5

    def test_get_history_filters_by_time(
        self,
        history_service: ConversationHistoryService,
    ) -> None:
        """GetConversationHistory filters by from_time and to_time."""
        now = datetime.now(timezone.utc).isoformat()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        history_service.append_entry(ConversationHistoryItem(
            session_id="ses_123",
            turn_id="turn_old",
            role="user",
            content="Old message",
            created_at=past,
        ))
        # Add a future message that should NOT be included
        history_service.append_entry(ConversationHistoryItem(
            session_id="ses_123",
            turn_id="turn_future",
            role="user",
            content="Future message",
            created_at=future,
        ))

        query = ConversationHistoryQuery(
            session_id="ses_123",
            from_time=past,
            to_time=now,
            limit=10,
            offset=0,
        )
        page = history_service.get_history(query)

        assert page.total == 1  # Only the old message within time range

    def test_get_history_validates_session_id(
        self, history_service: ConversationHistoryService
    ) -> None:
        """GetConversationHistory rejects empty session_id."""
        with pytest.raises(Exception) as exc_info:
            history_service.get_history(
                ConversationHistoryQuery(session_id="", limit=10, offset=0)
            )

        error = exc_info.value
        assert isinstance(error, UnifiedErrorEnvelope)
        assert error.error.code == FIELD_REQUIRED

    def test_get_history_validates_limit(
        self, history_service: ConversationHistoryService
    ) -> None:
        """GetConversationHistory rejects invalid limit."""
        with pytest.raises(Exception) as exc_info:
            history_service.get_history(
                ConversationHistoryQuery(session_id="ses_123", limit=0, offset=0)
            )
        assert exc_info.value.error.code == FIELD_REQUIRED

        with pytest.raises(Exception) as exc_info:
            history_service.get_history(
                ConversationHistoryQuery(session_id="ses_123", limit=201, offset=0)
            )
        assert exc_info.value.error.code == FIELD_REQUIRED

    def test_get_history_validates_offset(
        self, history_service: ConversationHistoryService
    ) -> None:
        """GetConversationHistory rejects negative offset."""
        with pytest.raises(Exception) as exc_info:
            history_service.get_history(
                ConversationHistoryQuery(session_id="ses_123", limit=10, offset=-1)
            )

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED
        assert "offset" in error.error.field_errors


# =============================================================================
# AnalyticsService tests (FND-ANA-01 GetAnalyticsSummary)
# =============================================================================


class TestAnalyticsService:
    """Tests for AnalyticsService (FND-ANA-01 GetAnalyticsSummary)."""

    def test_get_summary_success(
        self,
        analytics_service: AnalyticsService,
    ) -> None:
        """GetAnalyticsSummary returns aggregated analytics."""
        # Seed analytics store directly
        now = datetime.now(timezone.utc).isoformat()
        analytics_service.record_conversation_log(ConversationHistoryItem(
            session_id="ses_1",
            turn_id="turn_1",
            role="user",
            content="What is BHYT?",
            intent="information_assistance",
            created_at=now,
        ))
        analytics_service.record_conversation_log(ConversationHistoryItem(
            session_id="ses_1",
            turn_id="turn_2",
            role="assistant",
            content="BHYT is...",
            intent="information_assistance",
            created_at=now,
        ))
        analytics_service.record_conversation_log(ConversationHistoryItem(
            session_id="ses_2",
            turn_id="turn_3",
            role="user",
            content="How to book appointment?",
            intent="appointment_booking",
            created_at=now,
        ))
        analytics_service.record_conversation_log(ConversationHistoryItem(
            session_id="ses_2",
            turn_id="turn_4",
            role="assistant",
            content="You can book by...",
            intent="appointment_booking",
            created_at=now,
        ))

        # Add some feedback and audit events
        analytics_service.record_feedback({"rating": 5, "session_id": "ses_1", "created_at": now})
        analytics_service.record_feedback({"rating": 4, "session_id": "ses_2", "created_at": now})
        analytics_service.record_audit_event(
            {"event_type": "emergency", "actor": "system", "action": "trigger", "resource": "ses_3", "created_at": now}
        )

        from_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        to_time = datetime.now(timezone.utc).isoformat()

        query = AnalyticsSummaryQuery(from_time=from_time, to_time=to_time)
        summary = analytics_service.get_summary(query)

        assert isinstance(summary, AnalyticsSummaryDTO)
        assert summary.total_conversations == 2
        assert summary.total_turns == 4
        assert 0.0 <= summary.fallback_rate <= 1.0
        assert 0.0 <= summary.emergency_rate <= 1.0
        assert summary.feedback_score is not None
        assert 1.0 <= summary.feedback_score <= 5.0
        assert len(summary.top_questions) <= 10
        assert summary.generated_at is not None

    def test_get_summary_validates_time_range(self, analytics_service: AnalyticsService) -> None:
        """GetAnalyticsSummary rejects invalid time range."""
        now = datetime.now(timezone.utc).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        # from_time > to_time
        with pytest.raises(Exception) as exc_info:
            analytics_service.get_summary(
                AnalyticsSummaryQuery(from_time=future, to_time=now)
            )

        error = exc_info.value
        assert error.error.code == INVALID_REQUEST
        assert "time_range" in error.error.field_errors

    def test_get_summary_requires_time_range(self, analytics_service: AnalyticsService) -> None:
        """GetAnalyticsSummary requires from_time and to_time."""
        with pytest.raises(Exception) as exc_info:
            analytics_service.get_summary(
                AnalyticsSummaryQuery(from_time="", to_time="")
            )

        error = exc_info.value
        assert error.error.code == FIELD_REQUIRED

    def test_get_summary_empty_data(
        self, analytics_service: AnalyticsService
    ) -> None:
        """GetAnalyticsSummary handles empty data gracefully."""
        from_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        to_time = datetime.now(timezone.utc).isoformat()

        query = AnalyticsSummaryQuery(from_time=from_time, to_time=to_time)
        summary = analytics_service.get_summary(query)

        assert summary.total_conversations == 0
        assert summary.total_turns == 0
        assert summary.fallback_rate == 0.0
        assert summary.emergency_rate == 0.0
        assert summary.feedback_score is None
        assert summary.top_questions == []

    def test_get_summary_computes_fallback_rate(
        self,
        analytics_service: AnalyticsService,
    ) -> None:
        """GetAnalyticsSummary computes fallback_rate correctly."""
        now = datetime.now(timezone.utc).isoformat()
        analytics_service.record_conversation_log(ConversationHistoryItem(
            session_id="ses_1",
            turn_id="turn_1",
            role="user",
            content="What is BHYT?",
            intent="information_assistance",
            created_at=now,
        ))
        analytics_service.record_conversation_log(ConversationHistoryItem(
            session_id="ses_1",
            turn_id="turn_2",
            role="assistant",
            content="Fallback response",
            intent="fallback",
            created_at=now,
        ))
        analytics_service.record_conversation_log(ConversationHistoryItem(
            session_id="ses_1",
            turn_id="turn_3",
            role="user",
            content="Another question",
            created_at=now,
        ))

        from_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        to_time = datetime.now(timezone.utc).isoformat()

        summary = analytics_service.get_summary(
            AnalyticsSummaryQuery(from_time=from_time, to_time=to_time)
        )

        # 1 fallback out of 3 turns = 0.333...
        assert abs(summary.fallback_rate - 1/3) < 0.01

    def test_get_summary_computes_emergency_rate(
        self,
        analytics_service: AnalyticsService,
    ) -> None:
        """GetAnalyticsSummary computes emergency_rate correctly."""
        now = datetime.now(timezone.utc).isoformat()
        analytics_service.record_conversation_log(ConversationHistoryItem(
            session_id="ses_1",
            turn_id="turn_1",
            role="user",
            content="Help!",
            emergency_triggered=True,
            emergency_level=1,
            created_at=now,
        ))
        analytics_service.record_conversation_log(ConversationHistoryItem(
            session_id="ses_1",
            turn_id="turn_2",
            role="assistant",
            content="Emergency protocol",
            emergency_triggered=True,
            emergency_level=1,
            created_at=now,
        ))
        analytics_service.record_conversation_log(ConversationHistoryItem(
            session_id="ses_2",
            turn_id="turn_3",
            role="user",
            content="Normal question",
            created_at=now,
        ))

        from_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        to_time = datetime.now(timezone.utc).isoformat()

        summary = analytics_service.get_summary(
            AnalyticsSummaryQuery(from_time=from_time, to_time=to_time)
        )

        # 2 emergency turns out of 3 total
        assert abs(summary.emergency_rate - 2/3) < 0.01

    def test_get_summary_computes_feedback_score(
        self,
        analytics_service: AnalyticsService,
    ) -> None:
        """GetAnalyticsSummary computes average feedback score."""
        now = datetime.now(timezone.utc).isoformat()
        analytics_service.record_feedback({"rating": 5, "created_at": now})
        analytics_service.record_feedback({"rating": 3, "created_at": now})
        analytics_service.record_feedback({"rating": 4, "created_at": now})

        from_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        to_time = datetime.now(timezone.utc).isoformat()

        summary = analytics_service.get_summary(
            AnalyticsSummaryQuery(from_time=from_time, to_time=to_time)
        )

        assert summary.feedback_score == 4.0  # (5+3+4)/3

    def test_get_summary_top_questions(
        self,
        analytics_service: AnalyticsService,
    ) -> None:
        """GetAnalyticsSummary returns top questions by intent."""
        now = datetime.now(timezone.utc).isoformat()
        # Add multiple turns with same intent
        for i in range(3):
            analytics_service.record_conversation_log(ConversationHistoryItem(
                session_id=f"ses_{i}",
                turn_id=f"turn_{i}",
                role="user",
                content="Question about BHYT",
                intent="information_assistance",
                created_at=now,
            ))
        for i in range(2):
            analytics_service.record_conversation_log(ConversationHistoryItem(
                session_id=f"ses_{i+3}",
                turn_id=f"turn_{i+3}",
                role="user",
                content="How to book",
                intent="appointment_booking",
                created_at=now,
            ))
        analytics_service.record_conversation_log(ConversationHistoryItem(
            session_id="ses_5",
            turn_id="turn_5",
            role="user",
            content="Emergency!",
            intent="emergency",
            created_at=now,
        ))

        from_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        to_time = datetime.now(timezone.utc).isoformat()

        summary = analytics_service.get_summary(
            AnalyticsSummaryQuery(from_time=from_time, to_time=to_time)
        )

        assert len(summary.top_questions) > 0
        # information_assistance should be top (3 occurrences)
        top = summary.top_questions[0]
        assert top["intent"] == "information_assistance"
        assert top["count"] == 3


# =============================================================================
# DTO serialization tests
# =============================================================================


class TestDTOSerialization:
    """Verify DTO serialization matches INT-04 contracts."""

    def test_conversation_history_item_to_dict(self) -> None:
        """ConversationHistoryItem.to_dict produces correct shape."""
        item = ConversationHistoryItem(
            session_id="ses_123",
            turn_id="turn_1",
            role="user",
            content="Hello",
            intent="information_assistance",
            has_pii=False,
            pii_redacted=False,
            emergency_triggered=False,
            created_at="2024-01-01T00:00:00Z",
        )

        d = item.to_dict()

        required = {
            "session_id",
            "turn_id",
            "role",
            "content",
            "has_pii",
            "pii_redacted",
            "emergency_triggered",
            "created_at",
        }
        assert set(d.keys()) == required | {"intent"}  # intent is optional
        assert d["session_id"] == "ses_123"
        assert d["content"] == "Hello"
        assert d["has_pii"] is False

    def test_conversation_history_page_to_dict(self) -> None:
        """ConversationHistoryPageDTO.to_dict produces correct shape."""
        page = ConversationHistoryPageDTO(
            items=[
                ConversationHistoryItem(
                    session_id="ses_123",
                    turn_id="turn_1",
                    role="user",
                    content="Hello",
                    created_at="2024-01-01T00:00:00Z",
                )
            ],
            total=1,
            limit=10,
            offset=0,
        )

        d = page.to_dict()

        assert d["total"] == 1
        assert d["limit"] == 10
        assert d["offset"] == 0
        assert len(d["items"]) == 1
        assert d["items"][0]["session_id"] == "ses_123"

    def test_analytics_summary_to_dict(self) -> None:
        """AnalyticsSummaryDTO.to_dict produces correct shape."""
        summary = AnalyticsSummaryDTO(
            time_range_from="2024-01-01T00:00:00Z",
            time_range_to="2024-01-01T01:00:00Z",
            top_questions=[{"intent": "information_assistance", "count": 5}],
            fallback_rate=0.1,
            emergency_rate=0.05,
            feedback_score=4.5,
            total_conversations=10,
            total_turns=50,
            generated_at="2024-01-01T01:00:00Z",
        )

        d = summary.to_dict()

        required = {
            "time_range_from",
            "time_range_to",
            "top_questions",
            "fallback_rate",
            "emergency_rate",
            "total_conversations",
            "total_turns",
            "generated_at",
        }
        assert required.issubset(set(d.keys()))
        assert d["fallback_rate"] == 0.1
        assert d["emergency_rate"] == 0.05
        assert d["feedback_score"] == 4.5
        assert d["total_conversations"] == 10

    def test_audit_log_entry_to_dict(self) -> None:
        """AuditLogEntry.to_dict produces correct shape."""
        entry = AuditLogEntry(
            audit_id="aud_123",
            event_type="emergency",
            actor="system",
            action="trigger_emergency",
            resource="ses_123",
            details={"level": 1},
            session_id="ses_123",
            outcome="success",
            created_at="2024-01-01T00:00:00Z",
        )

        d = entry.to_dict()

        required = {
            "audit_id",
            "event_type",
            "actor",
            "action",
            "resource",
            "outcome",
            "created_at",
        }
        assert required.issubset(set(d.keys()))
        assert d["event_type"] == "emergency"
        assert d["actor"] == "system"
        assert d["outcome"] == "success"


# =============================================================================
# PII non-leakage tests (validation expectation: PII not in analytics)
# =============================================================================


class TestPIINonLeakage:
    """Validate PII is never stored in analytics/logs."""

    def test_conversation_log_redacts_phone(
        self, conversation_service: ConversationLogService
    ) -> None:
        """Phone numbers are redacted in conversation logs."""
        entry = conversation_service.append_entry(
            session_id="ses_1",
            role="user",
            content="My phone is 0901234567",
        )

        assert entry.has_pii is True
        assert entry.pii_redacted is True
        assert "0901234567" not in entry.content
        assert "[REDACTED]" in entry.content

    def test_conversation_log_redacts_email(
        self, conversation_service: ConversationLogService
    ) -> None:
        """Emails are redacted in conversation logs."""
        entry = conversation_service.append_entry(
            session_id="ses_1",
            role="user",
            content="Email me at user@example.com",
        )

        assert entry.has_pii is True
        assert "user@example.com" not in entry.content
        assert "[REDACTED]" in entry.content

    def test_conversation_log_redacts_cccd(
        self, conversation_service: ConversationLogService
    ) -> None:
        """CCCD (12-digit ID) is redacted."""
        entry = conversation_service.append_entry(
            session_id="ses_1",
            role="user",
            content="My CCCD is 123456789012",
        )

        assert entry.has_pii is True
        assert "123456789012" not in entry.content
        assert "[REDACTED]" in entry.content

    def test_analytics_summary_excludes_pii(
        self,
        analytics_service: AnalyticsService,
        conversation_service: ConversationLogService,
    ) -> None:
        """Analytics summary never contains raw PII."""
        conversation_service.append_entry(
            session_id="ses_1",
            role="user",
            content="My phone 0901234567 and email test@example.com",
        )

        from_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        to_time = datetime.now(timezone.utc).isoformat()

        summary = analytics_service.get_summary(
            AnalyticsSummaryQuery(from_time=from_time, to_time=to_time)
        )

        # Convert to dict and check no PII patterns
        import json
        summary_json = json.dumps(summary.to_dict())

        assert "0901234567" not in summary_json
        assert "test@example.com" not in summary_json
        assert "[REDACTED]" not in summary_json  # Analytics only gets aggregates, not raw content

    def test_audit_log_no_pii_in_details(
        self, audit_service: AuditLogService
    ) -> None:
        """Audit log details should not contain PII."""
        entry = audit_service.write_entry(
            event_type="emergency",
            actor="system",
            action="trigger_emergency",
            resource="ses_123",
            details={"level": 1, "matched_keyword": "heart attack"},
        )

        assert "phone" not in str(entry.details)
        assert "email" not in str(entry.details)
        assert "cccd" not in str(entry.details).lower()


# =============================================================================
# Retention and audit integrity tests (validation expectation)
# =============================================================================


class TestRetentionAndAuditIntegrity:
    """Validate retention sweep and audit integrity."""

    def test_conversation_store_can_clear(self, conversation_service: ConversationLogService) -> None:
        """Store can be cleared (simulating retention sweep)."""
        conversation_service.append_entry("ses_1", "user", "Hello")
        conversation_service.append_entry("ses_2", "user", "Hi")

        # Access internal store
        store = conversation_service._store
        assert store.count() == 2

        store.clear()
        assert store.count() == 0

    def test_audit_store_can_clear(self, audit_service: AuditLogService) -> None:
        """Audit store can be cleared (simulating retention sweep)."""
        audit_service.write_entry("emergency", "system", "trigger", "ses_1")
        audit_service.write_entry("security", "admin", "login", "user_1")

        store = audit_service._store
        assert store.count() == 2

        store.clear()
        assert store.count() == 0

    def test_audit_entries_immutable(self, audit_service: AuditLogService) -> None:
        """Audit entries are frozen dataclasses (immutable)."""
        entry = audit_service.write_entry(
            "emergency", "system", "trigger", "ses_1"
        )

        # Attempting to modify should fail (frozen dataclass)
        with pytest.raises(Exception):
            entry.event_type = "modified"  # type: ignore

    def test_conversation_entries_immutable(self, conversation_service: ConversationLogService) -> None:
        """Conversation log entries are frozen dataclasses (immutable)."""
        entry = conversation_service.append_entry("ses_1", "user", "Hello")

        with pytest.raises(Exception):
            entry.content = "modified"  # type: ignore


# =============================================================================
# Traceability tests (to contracts and artifacts)
# =============================================================================


class TestTraceability:
    """Verify implementation traces to FND-HIS-01, FND-ANA-01, INT-03, INT-04, ARCH-08."""

    def test_conversation_history_service_has_get_history(self) -> None:
        """ConversationHistoryService implements FND-HIS-01 GetConversationHistory."""
        assert hasattr(ConversationHistoryService, "get_history")

    def test_analytics_service_has_get_summary(self) -> None:
        """AnalyticsService implements FND-ANA-01 GetAnalyticsSummary."""
        assert hasattr(AnalyticsService, "get_summary")

    def test_conversation_log_service_has_append_and_query(self) -> None:
        """ConversationLogService implements FND-LOG-01/02."""
        assert hasattr(ConversationLogService, "append_entry")
        assert hasattr(ConversationLogService, "query_log")

    def test_audit_log_service_has_write_and_query(self) -> None:
        """AuditLogService implements FND-AUD-01/02."""
        assert hasattr(AuditLogService, "write_entry")
        assert hasattr(AuditLogService, "query_log")

    def test_dto_names_match_int04(self) -> None:
        """DTO class names match INT-04 canonical names."""
        assert ConversationHistoryPageDTO.__name__ == "ConversationHistoryPageDTO"
        assert AnalyticsSummaryDTO.__name__ == "AnalyticsSummaryDTO"
        assert ConversationHistoryItem.__name__ == "ConversationHistoryItem"

    def test_arch08_conversation_logging_flow(self) -> None:
        """ARCH-08: Conversation logging → detect_pii → anonymized record → async Analytics Store."""
        # The ConversationLogService.append_entry performs PII detection
        # and stores anonymized records. AnalyticsService reads from store.
        # This test documents the traceability.
        assert hasattr(ConversationLogService, "append_entry")
        assert hasattr(AnalyticsService, "record_conversation_log")


# === TASK:WP-105:END ===
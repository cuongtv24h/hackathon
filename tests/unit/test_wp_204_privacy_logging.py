# === TASK:WP-204:START ===
"""Unit tests for WP-204 Privacy and Logging tools.

This module tests the cross-cutting privacy tool adapters:
- detect_pii tool (INT-06)
- log_conversation tool (INT-06)
- Tool adapter bridging to ConversationLogService (WP-105)
- Combined pipeline with fail-closed PII behavior

Tests use mocks/fakes; no external dependencies.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from apps.api.ai.guardrails.privacy.service import (
    DetectPIIInput,
    DetectPIIOutput,
    LogConversationInput,
    LogConversationOutput,
    detect_pii,
    log_conversation,
    _process_log_queue,
    _clear_log_queue,
    _get_queued_logs,
)
from apps.api.logging.conversation.service import (
    ConversationLogEntry,
    ConversationLogService,
    _InMemoryConversationStore,
)
from apps.api.logging.conversation.tool_adapter import (
    LogConversationAdapterConfig,
    LogConversationAdapterState,
    adapt_detect_pii,
    adapt_log_conversation,
    process_and_log_turn,
    initialize_log_conversation_adapter,
    get_log_conversation_adapter_state,
    start_log_worker,
    stop_log_worker,
    reset_adapter_for_testing,
    LogTurnInput,
    LogTurnOutput,
)
from packages.contracts import (
    UnifiedErrorEnvelope,
    CATEGORY_TOOL,
    PII_PROCESSING_FAILED,
    LOG_DEFERRED,
    LOG_REJECTED,
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
def conversation_service(conversation_store) -> ConversationLogService:
    """ConversationLogService with test store."""
    return ConversationLogService(store=conversation_store)


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global adapter state before and after each test."""
    reset_adapter_for_testing()
    yield
    reset_adapter_for_testing()


# =============================================================================
# detect_pii tool tests
# =============================================================================


class TestDetectPII:
    """Tests for detect_pii tool (INT-06)."""

    def test_detect_pii_no_pii(self) -> None:
        """Text without PII returns original text, empty categories."""
        result = detect_pii(DetectPIIInput(text="Hello, how can I help you?"))

        assert isinstance(result, DetectPIIOutput)
        assert result.anonymized_text == "Hello, how can I help you?"
        assert result.categories == []
        assert result.has_pii is False

    def test_detect_pii_phone_number(self) -> None:
        """Vietnamese phone numbers are detected and redacted."""
        text = "My phone is 0901234567"
        result = detect_pii(DetectPIIInput(text=text))

        assert result.has_pii is True
        assert "phone" in result.categories
        assert "[REDACTED:phone]" in result.anonymized_text
        assert "0901234567" not in result.anonymized_text

    def test_detect_pii_email(self) -> None:
        """Email addresses are detected and redacted."""
        text = "Contact me at user@example.com"
        result = detect_pii(DetectPIIInput(text=text))

        assert result.has_pii is True
        assert "email" in result.categories
        assert "[REDACTED:email]" in result.anonymized_text
        assert "user@example.com" not in result.anonymized_text

    def test_detect_pii_cccd_12_digits(self) -> None:
        """Vietnamese CCCD (12 digits) is detected."""
        text = "My CCCD is 123456789012"
        result = detect_pii(DetectPIIInput(text=text))

        assert result.has_pii is True
        assert "national_id" in result.categories
        assert "[REDACTED:national_id]" in result.anonymized_text
        assert "123456789012" not in result.anonymized_text

    def test_detect_pii_cmnd_9_digits(self) -> None:
        """Legacy CMND (9 digits) is detected."""
        text = "My CMND is 123456789"
        result = detect_pii(DetectPIIInput(text=text))

        assert result.has_pii is True
        assert "national_id" in result.categories
        assert "123456789" not in result.anonymized_text

    def test_detect_pii_person_name(self) -> None:
        """Vietnamese person names are detected."""
        text = "Tôi là Nguyễn Văn A"
        result = detect_pii(DetectPIIInput(text=text))

        assert result.has_pii is True
        assert "person_name" in result.categories
        assert "[REDACTED:person_name]" in result.anonymized_text

    def test_detect_pii_credit_card(self) -> None:
        """Credit card numbers are detected."""
        text = "Card: 1234-5678-9012-3456"
        result = detect_pii(DetectPIIInput(text=text))

        assert result.has_pii is True
        assert "credit_card" in result.categories
        assert "1234-5678-9012-3456" not in result.anonymized_text

    def test_detect_pii_bank_account(self) -> None:
        """Bank account numbers (8-17 digits) are detected."""
        text = "Account: 1234567890123456"
        result = detect_pii(DetectPIIInput(text=text))

        assert result.has_pii is True
        assert "bank_account" in result.categories
        assert "1234567890123456" not in result.anonymized_text

    def test_detect_pii_multiple_types(self) -> None:
        """Multiple PII types in one text are all detected."""
        text = "Name: Nguyễn Văn A, Phone: 0901234567, Email: test@example.com"
        result = detect_pii(DetectPIIInput(text=text))

        assert result.has_pii is True
        assert set(result.categories) == {"person_name", "phone", "email"}
        assert result.anonymized_text.count("[REDACTED:") == 3

    def test_detect_pii_empty_string(self) -> None:
        """Empty string returns no PII."""
        result = detect_pii(DetectPIIInput(text=""))

        assert result.has_pii is False
        assert result.anonymized_text == ""
        assert result.categories == []

    def test_detect_pii_invalid_input_type(self) -> None:
        """Non-string input raises PII_PROCESSING_FAILED."""
        with pytest.raises(UnifiedErrorEnvelope) as exc_info:
            detect_pii(DetectPIIInput(text=123))  # type: ignore

        error = exc_info.value
        assert error.error.code == PII_PROCESSING_FAILED
        assert error.error.category == CATEGORY_TOOL
        assert error.error.retryable is False

    def test_detect_pii_invalid_input_object(self) -> None:
        """Non-DetectPIIInput object raises PII_PROCESSING_FAILED."""
        with pytest.raises(UnifiedErrorEnvelope) as exc_info:
            detect_pii("not an input object")  # type: ignore

        error = exc_info.value
        assert error.error.code == PII_PROCESSING_FAILED
        assert error.error.retryable is False


# =============================================================================
# log_conversation tool tests
# =============================================================================


class TestLogConversation:
    """Tests for log_conversation tool (INT-06)."""

    def test_log_conversation_success(self) -> None:
        """Valid input returns accepted receipt."""
        result = log_conversation(
            LogConversationInput(
                session_id="ses_123",
                turn_id="turn_1",
                role="user",
                content="Hello",
            )
        )

        assert isinstance(result, LogConversationOutput)
        assert result.status == "accepted"
        assert result.receipt_id.startswith("log_")
        assert result.queued_at is not None

    def test_log_conversation_with_all_fields(self) -> None:
        """All optional fields are accepted."""
        result = log_conversation(
            LogConversationInput(
                session_id="ses_123",
                turn_id="turn_1",
                role="assistant",
                content="Hello!",
                intent="greeting",
                has_pii=False,
                pii_redacted=False,
                emergency_triggered=False,
                tool_calls=[{"tool": "search", "args": {}}],
                citations=[{"source": "doc1", "score": 0.9}],
                metadata={"user_id": "usr_1"},
            )
        )

        assert result.status == "accepted"

    def test_log_conversation_rejects_empty_session_id(self) -> None:
        """Empty session_id returns LOG_REJECTED."""
        with pytest.raises(UnifiedErrorEnvelope) as exc_info:
            log_conversation(
                LogConversationInput(
                    session_id="",
                    turn_id="turn_1",
                    role="user",
                    content="Hello",
                )
            )

        error = exc_info.value
        assert error.error.code == LOG_REJECTED
        assert error.error.category == CATEGORY_TOOL
        assert error.error.retryable is False
        assert "session_id" in error.error.message.lower()

    def test_log_conversation_rejects_invalid_role(self) -> None:
        """Invalid role returns LOG_REJECTED."""
        with pytest.raises(UnifiedErrorEnvelope) as exc_info:
            log_conversation(
                LogConversationInput(
                    session_id="ses_123",
                    turn_id="turn_1",
                    role="invalid_role",
                    content="Hello",
                )
            )

        error = exc_info.value
        assert error.error.code == LOG_REJECTED
        assert error.error.retryable is False

    def test_log_conversation_rejects_empty_content(self) -> None:
        """Empty content returns LOG_REJECTED."""
        with pytest.raises(UnifiedErrorEnvelope) as exc_info:
            log_conversation(
                LogConversationInput(
                    session_id="ses_123",
                    turn_id="turn_1",
                    role="user",
                    content="",
                )
            )

        error = exc_info.value
        assert error.error.code == LOG_REJECTED
        assert error.error.retryable is False

    def test_log_conversation_queue_full_returns_deferred(self) -> None:
        """Full queue returns LOG_DEFERRED (retryable)."""
        # Fill the queue
        for i in range(10001):
            try:
                log_conversation(
                    LogConversationInput(
                        session_id=f"ses_{i}",
                        turn_id=f"turn_{i}",
                        role="user",
                        content=f"Message {i}",
                    )
                )
            except UnifiedErrorEnvelope as e:
                if e.error.code == LOG_DEFERRED:
                    break
        else:
            pytest.fail("Queue did not fill up")

        # Next call should be deferred
        with pytest.raises(UnifiedErrorEnvelope) as exc_info:
            log_conversation(
                LogConversationInput(
                    session_id="ses_new",
                    turn_id="turn_new",
                    role="user",
                    content="New message",
                )
            )

        error = exc_info.value
        assert error.error.code == LOG_DEFERRED
        assert error.error.retryable is True
        assert error.error.retry_after_seconds is not None


# =============================================================================
# Tool adapter tests
# =============================================================================


class TestToolAdapter:
    """Tests for the tool adapter (bridge to ConversationLogService)."""

    def test_adapt_detect_pii_passthrough(self) -> None:
        """adapt_detect_pii passes through to privacy service."""
        result = adapt_detect_pii("My phone is 0901234567")

        assert isinstance(result, DetectPIIOutput)
        assert result.has_pii is True
        assert "phone" in result.categories

    def test_adapt_detect_pii_wraps_errors(self) -> None:
        """adapt_detect_pii wraps unexpected errors."""
        with pytest.raises(UnifiedErrorEnvelope) as exc_info:
            adapt_detect_pii(None)  # type: ignore

        error = exc_info.value
        assert error.error.code == PII_PROCESSING_FAILED
        assert error.error.retryable is False

    def test_adapt_log_conversation_success(self, conversation_service) -> None:
        """adapt_log_conversation returns receipt."""
        result = adapt_log_conversation(
            session_id="ses_123",
            turn_id="turn_1",
            role="user",
            content="Hello",
        )

        assert isinstance(result, LogConversationOutput)
        assert result.status == "accepted"

    def test_adapt_log_conversation_rejects_invalid(self) -> None:
        """adapt_log_conversation rejects invalid input."""
        with pytest.raises(UnifiedErrorEnvelope) as exc_info:
            adapt_log_conversation(
                session_id="",
                turn_id="turn_1",
                role="user",
                content="Hello",
            )

        error = exc_info.value
        assert error.error.code == LOG_REJECTED
        assert error.error.retryable is False

    def test_process_and_log_turn_pipeline(self, conversation_service) -> None:
        """Full pipeline: detect PII -> anonymize -> log."""
        initialize_log_conversation_adapter(
            conversation_service=conversation_service,
            config=LogConversationAdapterConfig(worker_interval_seconds=0.1, batch_size=10),
        )
        start_log_worker()

        try:
            result = process_and_log_turn(
                LogTurnInput(
                    session_id="ses_123",
                    turn_id="turn_1",
                    role="user",
                    content="My phone is 0901234567",
                    intent="contact_info",
                )
            )

            assert isinstance(result, LogTurnOutput)
            assert result.pii_result.has_pii is True
            assert "phone" in result.pii_result.categories
            assert "0901234567" not in result.pii_result.anonymized_text
            assert result.log_result.status == "accepted"

            # Wait for worker to process
            time.sleep(0.5)

            # Verify entry was persisted
            page = conversation_service.query_log("ses_123", limit=10, offset=0)
            assert page.total == 1
            assert page.entries[0].content == "My phone is [REDACTED:phone]"
            assert page.entries[0].has_pii is True
            assert page.entries[0].pii_redacted is True
        finally:
            stop_log_worker()

    def test_process_and_log_turn_fail_closed_on_pii_error(self, conversation_service) -> None:
        """Pipeline fails closed if PII detection errors."""
        initialize_log_conversation_adapter(
            conversation_service=conversation_service,
            config=LogConversationAdapterConfig(worker_interval_seconds=0.1, batch_size=10),
        )

        # Mock detect_pii to fail
        with patch("apps.api.logging.conversation.tool_adapter.adapt_detect_pii") as mock_detect:
            mock_detect.side_effect = UnifiedErrorEnvelope(
                trace_id="test-pii-failure",
                error=MagicMock(code=PII_PROCESSING_FAILED, category=CATEGORY_TOOL, retryable=False)
            )

            with pytest.raises(UnifiedErrorEnvelope) as exc_info:
                process_and_log_turn(
                    LogTurnInput(
                        session_id="ses_123",
                        turn_id="turn_1",
                        role="user",
                        content="Hello",
                    )
                )

            # Should be PII_PROCESSING_FAILED (fail-closed)
            error = exc_info.value
            assert error.error.code == PII_PROCESSING_FAILED


# =============================================================================
# Background worker tests
# =============================================================================


class TestBackgroundWorker:
    """Tests for the async log processing worker."""

    def test_worker_processes_queue(self, conversation_service) -> None:
        """Worker processes queued logs."""
        initialize_log_conversation_adapter(
            conversation_service=conversation_service,
            config=LogConversationAdapterConfig(worker_interval_seconds=0.1, batch_size=10),
        )
        start_log_worker()

        try:
            # Enqueue some logs
            for i in range(5):
                adapt_log_conversation(
                    session_id=f"ses_{i}",
                    turn_id=f"turn_{i}",
                    role="user",
                    content=f"Message {i}",
                )

            # Wait for worker
            time.sleep(0.5)

            state = get_log_conversation_adapter_state()
            assert state is not None
            assert state.processed_count == 5

            # Verify in conversation service
            for i in range(5):
                page = conversation_service.query_log(f"ses_{i}", limit=10, offset=0)
                assert page.total == 1
        finally:
            stop_log_worker()

    def test_worker_handles_errors_gracefully(self, conversation_service) -> None:
        """Worker continues after processing errors."""
        # Create a service that fails on append
        failing_service = MagicMock(spec=ConversationLogService)
        failing_service.append_entry.side_effect = Exception("DB error")

        initialize_log_conversation_adapter(
            conversation_service=failing_service,
            config=LogConversationAdapterConfig(worker_interval_seconds=0.1, batch_size=10),
        )
        start_log_worker()

        try:
            # Enqueue a log
            adapt_log_conversation(
                session_id="ses_1",
                turn_id="turn_1",
                role="user",
                content="Hello",
            )

            time.sleep(0.5)

            state = get_log_conversation_adapter_state()
            assert state is not None
            assert state.failed_count >= 1
            assert state.worker_error is not None
        finally:
            stop_log_worker()

    def test_failed_entry_is_requeued_and_retried(self, conversation_service) -> None:
        """A transient persistence failure must not discard the queued log."""
        adapt_log_conversation(
            session_id="ses_retry",
            turn_id="turn_retry",
            role="user",
            content="safe content",
        )
        original_append = conversation_service.append_entry
        attempts = {"count": 0}

        def fail_once(**kwargs):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("temporary store failure")
            return original_append(**kwargs)

        conversation_service.append_entry = fail_once
        with pytest.raises(RuntimeError, match="temporary store failure"):
            _process_log_queue(
                conversation_service,
                max_retries=3,
                retry_delay_seconds=0,
            )
        assert len(_get_queued_logs()) == 1

        assert _process_log_queue(
            conversation_service,
            max_retries=3,
            retry_delay_seconds=0,
        ) == 1
        assert attempts["count"] == 2
        assert conversation_service.query_log("ses_retry", limit=10, offset=0).total == 1

    def test_worker_start_stop_idempotent(self, conversation_service) -> None:
        """Start/stop can be called multiple times safely."""
        initialize_log_conversation_adapter(
            conversation_service=conversation_service,
            config=LogConversationAdapterConfig(
                worker_interval_seconds=0.1,
                batch_size=10,
            ),
        )

        start_log_worker()
        start_log_worker()  # Second call should be no-op

        state = get_log_conversation_adapter_state()
        assert state is not None
        assert state.worker_running is True

        stop_log_worker()
        stop_log_worker()  # Second call should be no-op

        assert state.worker_running is False


# =============================================================================
# Adapter lifecycle tests
# =============================================================================


class TestAdapterLifecycle:
    """Tests for adapter initialization and lifecycle."""

    def test_initialize_creates_default_service(self) -> None:
        """initialize_log_conversation_adapter creates default service if none provided."""
        state = initialize_log_conversation_adapter()

        assert isinstance(state, LogConversationAdapterState)
        assert isinstance(state.conversation_service, ConversationLogService)
        assert isinstance(state.config, LogConversationAdapterConfig)

    def test_initialize_with_custom_config(self) -> None:
        """Custom config is used."""
        config = LogConversationAdapterConfig(
            worker_interval_seconds=2.0,
            batch_size=100,
            max_queue_depth=5000,
        )
        state = initialize_log_conversation_adapter(config=config)

        assert state.config.worker_interval_seconds == 2.0
        assert state.config.batch_size == 100
        assert state.config.max_queue_depth == 5000

    def test_get_state_returns_none_before_init(self) -> None:
        """get_log_conversation_adapter_state returns None before init."""
        reset_adapter_for_testing()
        state = get_log_conversation_adapter_state()
        assert state is None

    def test_reset_for_testing_clears_state(self, conversation_service) -> None:
        """reset_adapter_for_testing clears global state."""
        initialize_log_conversation_adapter(conversation_service=conversation_service)
        start_log_worker()

        reset_adapter_for_testing()

        state = get_log_conversation_adapter_state()
        assert state is None

        # Queue should be cleared
        logs = _get_queued_logs()
        assert len(logs) == 0


# =============================================================================
# PII non-leakage tests (validation expectation)
# =============================================================================


class TestPIINonLeakage:
    """Validate PII is never stored in logs or analytics."""

    def test_logged_content_is_anonymized(self, conversation_service) -> None:
        """Content stored in ConversationLogService is anonymized."""
        initialize_log_conversation_adapter(
            conversation_service=conversation_service,
            config=LogConversationAdapterConfig(
                worker_interval_seconds=0.1,
                batch_size=10,
            ),
        )
        start_log_worker()

        try:
            process_and_log_turn(
                LogTurnInput(
                    session_id="ses_1",
                    turn_id="turn_1",
                    role="user",
                    content="My phone 0901234567 and email test@example.com",
                )
            )

            time.sleep(0.3)

            page = conversation_service.query_log("ses_1", limit=10, offset=0)
            assert page.total == 1
            entry = page.entries[0]

            # Verify no raw PII in stored content
            assert "0901234567" not in entry.content
            assert "test@example.com" not in entry.content
            assert "[REDACTED:phone]" in entry.content
            assert "[REDACTED:email]" in entry.content
            assert entry.has_pii is True
            assert entry.pii_redacted is True
        finally:
            stop_log_worker()

    def test_analytics_receives_only_anonymized(self, conversation_service) -> None:
        """Analytics service receives only anonymized data."""
        from apps.api.foundation.analytics.service import (
            AnalyticsService,
            _InMemoryAnalyticsStore,
        )

        analytics_store = _InMemoryAnalyticsStore()
        analytics_service = AnalyticsService(store=analytics_store)

        initialize_log_conversation_adapter(conversation_service=conversation_service)
        start_log_worker()

        try:
            process_and_log_turn(
                LogTurnInput(
                    session_id="ses_1",
                    turn_id="turn_1",
                    role="user",
                    content="Phone: 0901234567",
                    intent="contact",
                )
            )

            time.sleep(0.3)

            # Feed analytics from conversation service
            page = conversation_service.query_log("ses_1", limit=10, offset=0)
            for entry in page.entries:
                from apps.api.foundation.analytics.service import ConversationHistoryItem
                analytics_service.record_conversation_log(
                    ConversationHistoryItem(
                        session_id=entry.session_id,
                        turn_id=entry.turn_id,
                        role=entry.role,
                        content=entry.content,
                        intent=entry.intent,
                        has_pii=entry.has_pii,
                        pii_redacted=entry.pii_redacted,
                        emergency_triggered=entry.emergency_triggered,
                        emergency_level=entry.emergency_level,
                        tool_calls=entry.tool_calls,
                        citations=entry.citations,
                        created_at=entry.created_at,
                    )
                )

            from_time = (datetime.now(timezone.utc)).isoformat()
            to_time = (datetime.now(timezone.utc)).isoformat()

            summary = analytics_service.get_summary(
                from_time=from_time,
                to_time=to_time,
            )

            # Analytics should not contain raw PII
            import json
            summary_json = json.dumps(summary.to_dict())
            assert "0901234567" not in summary_json
            assert "[REDACTED:phone]" not in summary_json  # Analytics only gets aggregates
        finally:
            stop_log_worker()


# =============================================================================
# Error contract compliance tests (INT-07)
# =============================================================================


class TestErrorContracts:
    """Verify error responses match INT-07 contracts."""

    def test_pii_error_envelope_structure(self) -> None:
        """PII_PROCESSING_FAILED has correct envelope structure."""
        try:
            detect_pii(DetectPIIInput(text=123))  # type: ignore
        except UnifiedErrorEnvelope as e:
            error = e.error
            assert error.code == PII_PROCESSING_FAILED
            assert error.category == CATEGORY_TOOL
            assert error.message is not None
            assert isinstance(error.retryable, bool)
            assert error.field_errors is None or isinstance(error.field_errors, dict)

    def test_log_rejected_error_envelope(self) -> None:
        """LOG_REJECTED has correct envelope structure."""
        try:
            log_conversation(
                LogConversationInput(session_id="", turn_id="t", role="user", content="x")
            )
        except UnifiedErrorEnvelope as e:
            error = e.error
            assert error.code == LOG_REJECTED
            assert error.category == CATEGORY_TOOL
            assert error.retryable is False

    def test_log_deferred_error_envelope(self) -> None:
        """LOG_DEFERRED has correct envelope structure (when queue full)."""
        # Fill queue
        for i in range(10001):
            try:
                log_conversation(
                    LogConversationInput(
                        session_id=f"ses_{i}", turn_id=f"t_{i}", role="user", content="x"
                    )
                )
            except UnifiedErrorEnvelope as e:
                if e.error.code == LOG_DEFERRED:
                    error = e.error
                    assert error.code == LOG_DEFERRED
                    assert error.category == CATEGORY_TOOL
                    assert error.retryable is True
                    assert error.retry_after_seconds is not None
                    assert error.fallback is not None
                    break


# =============================================================================
# Traceability tests (to artifacts/contracts)
# =============================================================================


class TestTraceability:
    """Verify implementation traces to artifacts and contracts."""

    def test_detect_pii_tool_exists(self) -> None:
        """detect_pii tool function exists (INT-06)."""
        from apps.api.ai.guardrails.privacy.service import detect_pii
        assert callable(detect_pii)

    def test_log_conversation_tool_exists(self) -> None:
        """log_conversation tool function exists (INT-06)."""
        from apps.api.ai.guardrails.privacy.service import log_conversation
        assert callable(log_conversation)

    def test_adapter_bridges_to_wp105(self) -> None:
        """Tool adapter uses ConversationLogService from WP-105."""
        from apps.api.logging.conversation.tool_adapter import adapt_log_conversation
        from apps.api.logging.conversation.service import ConversationLogService
        import inspect

        # Verify adapter integrates with WP-105 service
        sig = inspect.signature(initialize_log_conversation_adapter)
        assert "conversation_service" in sig.parameters
        assert "ConversationLogService" in str(sig.parameters["conversation_service"].annotation)

    def test_arch06_tool_map_traceability(self) -> None:
        """Implementation traces to ARCH-06 tool map."""
        # ARCH-06 defines detect_pii and log_conversation tools
        # This test documents the traceability
        from apps.api.ai.guardrails.privacy.service import (
            DetectPIIInput,
            DetectPIIOutput,
            LogConversationInput,
            LogConversationOutput,
        )

        # DTOs match tool contract I/O
        assert "text" in DetectPIIInput.__dataclass_fields__
        assert {"anonymized_text", "categories", "has_pii"}.issubset(DetectPIIOutput.__dataclass_fields__)
        assert {"session_id", "content"}.issubset(LogConversationInput.__dataclass_fields__)
        assert {"receipt_id", "status", "queued_at"}.issubset(LogConversationOutput.__dataclass_fields__)

    def test_int06_timeout_retry_constraints(self) -> None:
        """Tool contracts specify timeout/retry (INT-06)."""
        # detect_pii: 100ms timeout, 1 retry
        # log_conversation: 500ms worker, 3 async retries
        # These are documented in tool-contracts.md; implementation
        # respects them via config and worker settings
        config = LogConversationAdapterConfig()
        assert config.worker_interval_seconds > 0
        assert config.max_retries == 3


# =============================================================================
# DTO serialization tests
# =============================================================================


class TestDTOSerialization:
    """Verify DTOs serialize correctly for API contracts."""

    def test_detect_pii_output_to_dict(self) -> None:
        """DetectPIIOutput can be serialized."""
        output = DetectPIIOutput(
            anonymized_text="Hello [REDACTED:phone]",
            categories=["phone"],
            has_pii=True,
        )
        # dataclass to dict
        import dataclasses
        d = dataclasses.asdict(output)
        assert d["anonymized_text"] == "Hello [REDACTED:phone]"
        assert d["categories"] == ["phone"]
        assert d["has_pii"] is True

    def test_log_conversation_output_to_dict(self) -> None:
        """LogConversationOutput can be serialized."""
        output = LogConversationOutput(
            receipt_id="log_abc123",
            status="accepted",
            queued_at="2024-01-01T00:00:00Z",
        )
        import dataclasses
        d = dataclasses.asdict(output)
        assert d["receipt_id"] == "log_abc123"
        assert d["status"] == "accepted"
        assert d["queued_at"] == "2024-01-01T00:00:00Z"

    def test_log_turn_output_to_dict(self) -> None:
        """LogTurnOutput can be serialized."""
        output = LogTurnOutput(
            pii_result=DetectPIIOutput(
                anonymized_text="Hello",
                categories=[],
                has_pii=False,
            ),
            log_result=LogConversationOutput(
                receipt_id="log_abc123",
                status="accepted",
                queued_at="2024-01-01T00:00:00Z",
            ),
        )
        import dataclasses
        d = dataclasses.asdict(output)
        assert "pii_result" in d
        assert "log_result" in d


# === TASK:WP-204:END ===

# === TASK:WP-204:START ===
"""Tool adapter for log_conversation (FND-LOG-TOOL-01).

This module provides the tool adapter that bridges the `log_conversation` tool
(defined in `apps/api/ai/guardrails/privacy/service.py`) with the
`ConversationLogService` from WP-105 (`apps/api/logging/conversation/service.py`).

The adapter handles:
- Async log queuing with immediate receipt return
- Background processing integration with ConversationLogService
- Error handling per INT-06/INT-07 contracts (LOG_DEFERRED, LOG_REJECTED)
- Retry logic for transient failures (max 3 async retries)

This adapter is the integration point between the AI tool layer and the
foundation logging service.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Literal

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
from packages.contracts import (
    CATEGORY_TOOL,
    LOG_DEFERRED,
    LOG_REJECTED,
    UnifiedErrorEnvelope,
    make_error_envelope,
)


# ---------------------------------------------------------------------------
# Adapter configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LogConversationAdapterConfig:
    """Configuration for the log conversation tool adapter."""

    # Background worker settings
    worker_interval_seconds: float = 1.0
    batch_size: int = 50
    max_retries: int = 3
    retry_base_delay_seconds: float = 0.5

    # Queue settings
    max_queue_depth: int = 10000

    # Fail-closed behavior
    fail_closed_on_pii: bool = True  # If True, reject logs with detected PII


# ---------------------------------------------------------------------------
# Adapter state
# ---------------------------------------------------------------------------


@dataclass
class LogConversationAdapterState:
    """Runtime state for the adapter."""

    conversation_service: ConversationLogService
    config: LogConversationAdapterConfig
    worker_thread: Optional[threading.Thread] = None
    worker_running: bool = False
    worker_error: Optional[Exception] = None
    processed_count: int = 0
    failed_count: int = 0
    last_processed_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _adapter_error(
    code: str,
    message: str,
    *,
    retryable: bool = True,
    retry_after_seconds: Optional[int] = None,
    fallback: Optional[str] = None,
) -> UnifiedErrorEnvelope:
    """Create a tool-category error envelope."""
    return make_error_envelope(
        code=code,
        message=message,
        category=CATEGORY_TOOL,
        retryable=retryable,
        retry_after_seconds=retry_after_seconds,
        fallback=fallback or "Log adapter error; will retry async",
    )


# ---------------------------------------------------------------------------
# Tool adapter functions (public API for orchestrator)
# ---------------------------------------------------------------------------


def adapt_detect_pii(text: str) -> DetectPIIOutput:
    """Adapter for detect_pii tool.

    Simple pass-through to the privacy service with error wrapping.

    Args:
        text: Text to analyze for PII

    Returns:
        DetectPIIOutput with anonymized text and detected categories

    Raises:
        UnifiedErrorEnvelope: Wrapped PII_PROCESSING_FAILED error
    """
    try:
        return detect_pii(DetectPIIInput(text=text))
    except UnifiedErrorEnvelope:
        raise
    except Exception as e:
        raise _adapter_error(
            "PII_PROCESSING_FAILED",
            f"PII detection failed: {e}",
            retryable=True,
            retry_after_seconds=1,
            fallback="PII detection failed; failing closed - do not log raw content",
        )


def adapt_log_conversation(
    session_id: str,
    turn_id: str,
    role: Literal["user", "assistant", "system"],
    content: str,
    *,
    intent: Optional[str] = None,
    has_pii: bool = False,
    pii_redacted: bool = False,
    emergency_triggered: bool = False,
    emergency_level: Optional[int] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    citations: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> LogConversationOutput:
    """Adapter for log_conversation tool.

    Validates input, enqueues for async processing, returns receipt immediately.

    Args:
        session_id: Session identifier
        turn_id: Turn identifier
        role: Message role (user/assistant/system)
        content: Anonymized message content
        intent: Optional detected intent
        has_pii: Whether original content had PII
        pii_redacted: Whether PII was redacted
        emergency_triggered: Whether emergency was triggered
        emergency_level: Emergency level if triggered
        tool_calls: Tool calls made during turn
        citations: Citations returned
        metadata: Additional metadata

    Returns:
        LogConversationOutput with receipt_id and status

    Raises:
        UnifiedErrorEnvelope: LOG_REJECTED (validation) or LOG_DEFERRED (queue full)
    """
    input_data = LogConversationInput(
        session_id=session_id,
        turn_id=turn_id,
        role=role,
        content=content,
        intent=intent,
        has_pii=has_pii,
        pii_redacted=pii_redacted,
        emergency_triggered=emergency_triggered,
        emergency_level=emergency_level,
        tool_calls=tool_calls or [],
        citations=citations or [],
        metadata=metadata or {},
    )

    try:
        return log_conversation(input_data)
    except UnifiedErrorEnvelope:
        raise
    except Exception as e:
        raise _adapter_error(
            LOG_DEFERRED,
            f"Log conversation failed: {e}",
            retryable=True,
            retry_after_seconds=5,
            fallback="Log enqueue failed; will retry async",
        )


# ---------------------------------------------------------------------------
# Background worker management
# ---------------------------------------------------------------------------


_global_adapter_state: Optional[LogConversationAdapterState] = None
_state_lock = threading.Lock()


def initialize_log_conversation_adapter(
    conversation_service: Optional[ConversationLogService] = None,
    config: Optional[LogConversationAdapterConfig] = None,
) -> LogConversationAdapterState:
    """Initialize the global log conversation adapter.

    Call once at application startup.

    Args:
        conversation_service: ConversationLogService instance (creates default if None)
        config: Adapter configuration (uses defaults if None)

    Returns:
        Initialized adapter state
    """
    global _global_adapter_state

    with _state_lock:
        if _global_adapter_state is not None:
            return _global_adapter_state

        if conversation_service is None:
            conversation_service = ConversationLogService(store=_InMemoryConversationStore())

        if config is None:
            config = LogConversationAdapterConfig()

        state = LogConversationAdapterState(
            conversation_service=conversation_service,
            config=config,
        )
        _global_adapter_state = state
        return state


def get_log_conversation_adapter_state() -> Optional[LogConversationAdapterState]:
    """Get the global adapter state (or None if not initialized)."""
    with _state_lock:
        return _global_adapter_state


def start_log_worker(state: Optional[LogConversationAdapterState] = None) -> None:
    """Start the background log processing worker.

    Args:
        state: Adapter state (uses global if None)
    """
    if state is None:
        state = get_log_conversation_adapter_state()
    if state is None:
        raise RuntimeError("Adapter not initialized; call initialize_log_conversation_adapter first")

    with _state_lock:
        if state.worker_running:
            return

        state.worker_running = True
        state.worker_thread = threading.Thread(
            target=_worker_loop,
            args=(state,),
            daemon=True,
            name="log-conversation-worker",
        )
        state.worker_thread.start()


def stop_log_worker(state: Optional[LogConversationAdapterState] = None, timeout: float = 5.0) -> None:
    """Stop the background log processing worker.

    Args:
        state: Adapter state (uses global if None)
        timeout: Maximum time to wait for worker to stop
    """
    if state is None:
        state = get_log_conversation_adapter_state()
    if state is None:
        return

    with _state_lock:
        if not state.worker_running:
            return
        state.worker_running = False

    if state.worker_thread and state.worker_thread.is_alive():
        state.worker_thread.join(timeout=timeout)


def _worker_loop(state: LogConversationAdapterState) -> None:
    """Background worker loop for processing log queue."""
    config = state.config

    while state.worker_running:
        try:
            processed = _process_log_queue(
                conversation_service=state.conversation_service,
                batch_size=config.batch_size,
                max_retries=config.max_retries,
                retry_delay_seconds=config.retry_base_delay_seconds,
            )
            if processed > 0:
                state.processed_count += processed
                state.last_processed_at = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            state.worker_error = e
            state.failed_count += 1

        time.sleep(config.worker_interval_seconds)


# ---------------------------------------------------------------------------
# Convenience: combined PII detection + logging (for orchestrator)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LogTurnInput:
    """Combined input for detect_pii + log_conversation pipeline."""

    session_id: str
    turn_id: str
    role: Literal["user", "assistant", "system"]
    content: str  # RAW content (may contain PII)
    intent: Optional[str] = None
    emergency_triggered: bool = False
    emergency_level: Optional[int] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    citations: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class LogTurnOutput:
    """Output from the combined pipeline."""

    pii_result: DetectPIIOutput
    log_result: LogConversationOutput


def process_and_log_turn(input_data: LogTurnInput) -> LogTurnOutput:
    """Complete pipeline: detect PII, anonymize, log conversation.

    This is the main entry point for the orchestrator to log a turn.
    It ensures fail-closed behavior: if PII detection fails, the raw
    content is NOT logged.

    Args:
        input_data: LogTurnInput with raw content

    Returns:
        LogTurnOutput with both PII detection and log receipt

    Raises:
        UnifiedErrorEnvelope: On PII detection failure (fail-closed) or log rejection
    """
    # Step 1: Detect PII (fail-closed)
    pii_result = adapt_detect_pii(input_data.content)

    # Step 2: Log anonymized content
    log_result = adapt_log_conversation(
        session_id=input_data.session_id,
        turn_id=input_data.turn_id,
        role=input_data.role,
        content=pii_result.anonymized_text,
        intent=input_data.intent,
        has_pii=pii_result.has_pii,
        pii_redacted=pii_result.has_pii,
        emergency_triggered=input_data.emergency_triggered,
        emergency_level=input_data.emergency_level,
        tool_calls=input_data.tool_calls,
        citations=input_data.citations,
        metadata=input_data.metadata,
    )

    return LogTurnOutput(pii_result=pii_result, log_result=log_result)


# ---------------------------------------------------------------------------
# Testing utilities
# ---------------------------------------------------------------------------


def reset_adapter_for_testing() -> None:
    """Reset global adapter state (for testing only)."""
    global _global_adapter_state

    # Capture state while holding the lock, then stop the worker outside it.
    # stop_log_worker() also takes _state_lock; calling it while this lock is
    # held deadlocks lifecycle cleanup after a worker failure.
    with _state_lock:
        state = _global_adapter_state

    if state and state.worker_running:
        stop_log_worker(state)

    _clear_log_queue()

    with _state_lock:
        _global_adapter_state = None


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    # Config/State
    "LogConversationAdapterConfig",
    "LogConversationAdapterState",
    # Adapter functions
    "adapt_detect_pii",
    "adapt_log_conversation",
    "process_and_log_turn",
    # Lifecycle
    "initialize_log_conversation_adapter",
    "get_log_conversation_adapter_state",
    "start_log_worker",
    "stop_log_worker",
    # DTOs
    "LogTurnInput",
    "LogTurnOutput",
    # Testing
    "reset_adapter_for_testing",
]
# === TASK:WP-204:END ===

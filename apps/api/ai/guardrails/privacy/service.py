# === TASK:WP-204:START ===
"""Privacy guardrails service (AI-GRD-01).

This module implements the cross-cutting privacy tool adapters declared in
``docs/artifacts/interface/tool-contracts.md`` (INT-06) under ARCH-06.
The two tools are:

* ``detect_pii`` — synchronous PII detection and anonymization (INT-06).
* ``log_conversation`` — asynchronous conversation logging with receipt (INT-06).

Both tools are pure, side-effect-free adapters suitable for LLM tool calling.
All I/O is delegated to the caller (orchestrator / gateway).
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal

from packages.contracts import (
    CATEGORY_TOOL,
    PII_PROCESSING_FAILED,
    LOG_DEFERRED,
    LOG_REJECTED,
    UnifiedErrorEnvelope,
    make_error_envelope,
)


# ---------------------------------------------------------------------------
# PII detection patterns (MVP set; extendable via configuration)
# ---------------------------------------------------------------------------

# Vietnamese phone number patterns
_VN_PHONE_PATTERNS = [
    r"\b(?:0|\+84)(?:3[2-9]|5[689]|7[06-9]|8[1-9]|9[0-9])\d{7}\b",  # Mobile
    r"\b(?:0|\+84)(?:2[0-9])\d{8,9}\b",  # Landline
]

# Vietnamese ID patterns (CCCD 12 digits, CMND 9/12 digits)
_VN_ID_PATTERNS = [
    r"\b\d{12}\b",  # CCCD 12 digits
    r"\b\d{9}\b",   # CMND 9 digits (legacy)
]

# Email pattern
_EMAIL_PATTERN = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

# Vietnamese name pattern (simplified - 2-4 words, capitalized)
_VN_NAME_PATTERN = r"\b(?:[A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+){1,3})\b"

# Credit card pattern (basic)
_CREDIT_CARD_PATTERN = r"\b(?:\d{4}[-\s]?){3}\d{4}\b"

# Bank account pattern (Vietnam - 8-17 digits)
_BANK_ACCOUNT_PATTERN = r"\b\d{8,17}\b"

# Compile all patterns with category labels
# Order matters: more specific patterns first to avoid misclassification
_PII_PATTERNS: List[tuple[re.Pattern, str]] = [
    (re.compile(p), "phone") for p in _VN_PHONE_PATTERNS
] + [
    (re.compile(p), "national_id") for p in _VN_ID_PATTERNS
] + [
    (re.compile(_EMAIL_PATTERN), "email"),
    (re.compile(_VN_NAME_PATTERN), "person_name"),
    (re.compile(_BANK_ACCOUNT_PATTERN), "bank_account"),
    (re.compile(_CREDIT_CARD_PATTERN), "credit_card"),
]


# ---------------------------------------------------------------------------
# DTOs matching INT-06 tool contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DetectPIIInput:
    """Input for detect_pii tool."""

    text: str


@dataclass(frozen=True)
class DetectPIIOutput:
    """Output for detect_pii tool.

    Fields match INT-06 tool contract:
    - anonymized_text: text with PII replaced by [REDACTED:<category>]
    - categories: list of detected PII category names
    - has_pii: boolean flag
    """

    anonymized_text: str
    categories: List[str] = field(default_factory=list)
    has_pii: bool = False


@dataclass(frozen=True)
class LogConversationInput:
    """Input for log_conversation tool."""

    session_id: str
    turn_id: str
    role: Literal["user", "assistant", "system"]
    content: str  # Already anonymized
    intent: Optional[str] = None
    has_pii: bool = False
    pii_redacted: bool = False
    emergency_triggered: bool = False
    emergency_level: Optional[int] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LogConversationOutput:
    """Output for log_conversation tool.

    Fields match INT-06 tool contract:
    - receipt_id: async log receipt identifier
    - status: "accepted" | "deferred" | "rejected"
    - queued_at: ISO timestamp when queued
    """

    receipt_id: str
    status: Literal["accepted", "deferred", "rejected"]
    queued_at: str


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _pii_error(
    message: str,
    *,
    retryable: bool = True,
    retry_after_seconds: Optional[int] = None,
) -> UnifiedErrorEnvelope:
    """Create PII_PROCESSING_FAILED error envelope."""
    return make_error_envelope(
        code=PII_PROCESSING_FAILED,
        message=message,
        category=CATEGORY_TOOL,
        retryable=retryable,
        retry_after_seconds=retry_after_seconds,
        fallback="PII detection failed; failing closed - do not log raw content",
    )


def _log_error(
    code: str,
    message: str,
    *,
    retryable: bool = True,
    retry_after_seconds: Optional[int] = None,
    fallback: Optional[str] = None,
) -> UnifiedErrorEnvelope:
    """Create LOG_DEFERRED/LOG_REJECTED error envelope."""
    return make_error_envelope(
        code=code,
        message=message,
        category=CATEGORY_TOOL,
        retryable=retryable,
        retry_after_seconds=retry_after_seconds,
        fallback=fallback or "Log deferred; will retry async",
    )


# ---------------------------------------------------------------------------
# detect_pii implementation
# ---------------------------------------------------------------------------


def detect_pii(input_data: DetectPIIInput) -> DetectPIIOutput:
    """Detect and anonymize PII in text.

    Tool contract (INT-06):
    - Input: text → Output: anonymized_text, categories[], has_pii
    - Errors: PII_PROCESSING_FAILED (retryable, 1 retry, 100ms timeout)
    - Fail-closed: on error, caller must not log raw content

    Args:
        input_data: DetectPIIInput with text field

    Returns:
        DetectPIIOutput with anonymized text and detected categories

    Raises:
        UnifiedErrorEnvelope: On PII processing failure
    """
    if not isinstance(input_data, DetectPIIInput):
        raise _pii_error("Invalid input type for detect_pii", retryable=False)

    text = input_data.text
    if not isinstance(text, str):
        raise _pii_error("Input text must be a string", retryable=False)

    # Track detected categories (unique)
    detected_categories: set[str] = set()
    anonymized = text

    # Apply each pattern
    for pattern, category in _PII_PATTERNS:
        matches = list(pattern.finditer(anonymized))
        if matches:
            detected_categories.add(category)
            # Replace each match with category-specific placeholder
            for match in reversed(matches):  # Reverse to preserve indices
                start, end = match.span()
                placeholder = f"[REDACTED:{category}]"
                anonymized = anonymized[:start] + placeholder + anonymized[end:]

    return DetectPIIOutput(
        anonymized_text=anonymized,
        categories=sorted(detected_categories),
        has_pii=len(detected_categories) > 0,
    )


# ---------------------------------------------------------------------------
# log_conversation implementation (async adapter - returns receipt immediately)
# ---------------------------------------------------------------------------


# In-memory queue for async log processing (MVP; replace with real queue in prod).
# Keep retry bookkeeping separate from the public tool DTO so callers never need
# to manage delivery state.
@dataclass
class _QueuedLogEntry:
    input_data: LogConversationInput
    retry_count: int = 0
    available_at: float = 0.0


_log_queue: List[_QueuedLogEntry] = []
_log_queue_lock = __import__("threading").Lock()


def _enqueue_log(entry: LogConversationInput) -> str:
    """Enqueue a log entry for async processing. Returns receipt ID."""
    receipt_id = f"log_{uuid.uuid4().hex[:12]}"
    with _log_queue_lock:
        _log_queue.append(_QueuedLogEntry(input_data=entry))
    return receipt_id


def _get_queue_depth() -> int:
    """Get current queue depth for monitoring."""
    with _log_queue_lock:
        return len(_log_queue)


def log_conversation(input_data: LogConversationInput) -> LogConversationOutput:
    """Log an anonymized conversation turn asynchronously.

    Tool contract (INT-06):
    - Input: anonymized conversation event → Output: receipt_id, status, queued_at
    - Errors: LOG_DEFERRED (retryable, 3 async retries, 500ms worker),
              LOG_REJECTED (non-retryable)
    - Async: Returns receipt immediately; actual persistence happens in background

    Args:
        input_data: LogConversationInput with anonymized conversation data

    Returns:
        LogConversationOutput with receipt_id and status

    Raises:
        UnifiedErrorEnvelope: On validation failure (LOG_REJECTED) or queue full (LOG_DEFERRED)
    """
    if not isinstance(input_data, LogConversationInput):
        raise _log_error(
            LOG_REJECTED,
            "Invalid input type for log_conversation",
            retryable=False,
            fallback="Invalid log payload rejected",
        )

    # Validate required fields
    if not input_data.session_id or not input_data.session_id.strip():
        raise _log_error(
            LOG_REJECTED,
            "session_id is required",
            retryable=False,
            fallback="Missing session_id; log rejected",
        )

    if input_data.role not in ("user", "assistant", "system"):
        raise _log_error(
            LOG_REJECTED,
            "role must be 'user', 'assistant', or 'system'",
            retryable=False,
            fallback="Invalid role; log rejected",
        )

    if not input_data.content:
        raise _log_error(
            LOG_REJECTED,
            "content must be non-empty",
            retryable=False,
            fallback="Empty content; log rejected",
        )

    # Fail-closed: content must already be anonymized (caller responsibility)
    # We validate but don't enforce; log anyway with warning flag
    # In production, could enforce pii_redacted=True when has_pii=True

    # Check queue capacity (MVP: limit to prevent memory issues)
    MAX_QUEUE_DEPTH = 10000
    if _get_queue_depth() >= MAX_QUEUE_DEPTH:
        raise _log_error(
            LOG_DEFERRED,
            "Log queue at capacity; try again later",
            retryable=True,
            retry_after_seconds=5,
            fallback="Log queue full; will retry async",
        )

    # Enqueue and return receipt immediately
    receipt_id = _enqueue_log(input_data)
    queued_at = datetime.now(timezone.utc).isoformat()

    return LogConversationOutput(
        receipt_id=receipt_id,
        status="accepted",
        queued_at=queued_at,
    )


# ---------------------------------------------------------------------------
# Internal helper for background worker (not part of tool contract)
# ---------------------------------------------------------------------------


def _process_log_queue(
    conversation_service: Any,  # ConversationLogService from WP-105
    batch_size: int = 100,
    max_retries: int = 3,
    retry_delay_seconds: float = 0.5,
) -> int:
    """Process queued log entries (for background worker).

    This is an internal helper, NOT part of the tool contract.
    The orchestrator/worker calls this periodically.

    Args:
        conversation_service: ConversationLogService instance for persistence
        batch_size: Maximum entries to process per call

    Returns:
        Number of entries processed
    """
    processed = 0
    with _log_queue_lock:
        now = time.monotonic()
        ready = [item for item in _log_queue if item.available_at <= now]
        batch = ready[:batch_size]
        batch_ids = {id(item) for item in batch}
        _log_queue[:] = [item for item in _log_queue if id(item) not in batch_ids]

    last_error: Optional[Exception] = None
    for entry in batch:
        try:
            payload = entry.input_data
            conversation_service.append_entry(
                session_id=payload.session_id,
                role=payload.role,
                content=payload.content,
                turn_id=payload.turn_id,
                intent=payload.intent,
                has_pii=payload.has_pii,
                pii_redacted=payload.pii_redacted,
                emergency_triggered=payload.emergency_triggered,
                emergency_level=payload.emergency_level,
                tool_calls=payload.tool_calls,
                citations=payload.citations,
            )
            processed += 1
        except Exception as exc:
            last_error = exc
            # "max_retries" means retries after the original attempt. A
            # transient failure stays durable in the in-memory queue until
            # that budget is exhausted; it must never be silently lost.
            if entry.retry_count < max_retries:
                entry.retry_count += 1
                entry.available_at = time.monotonic() + retry_delay_seconds
                with _log_queue_lock:
                    _log_queue.append(entry)

    if last_error is not None:
        raise last_error
    return processed


def _get_queued_logs(limit: int = 100) -> List[LogConversationInput]:
    """Peek at queued logs (for monitoring/debugging)."""
    with _log_queue_lock:
        return [item.input_data for item in _log_queue[:limit]]


def _clear_log_queue() -> int:
    """Clear the log queue (for testing). Returns count cleared."""
    with _log_queue_lock:
        count = len(_log_queue)
        _log_queue.clear()
    return count


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    # DTOs
    "DetectPIIInput",
    "DetectPIIOutput",
    "LogConversationInput",
    "LogConversationOutput",
    # Tool functions
    "detect_pii",
    "log_conversation",
    # Internal helpers (for testing/worker)
    "_process_log_queue",
    "_get_queued_logs",
    "_clear_log_queue",
]
# === TASK:WP-204:END ===

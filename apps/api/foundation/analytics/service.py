# === TASK:WP-105:START ===
"""Analytics and conversation history foundation service (FND-HIS-01, FND-ANA-01).

This module implements the analytics foundation APIs declared in
``docs/artifacts/interface/foundation-api-contracts.md`` (INT-03). The two
operations are:

* ``FND-HIS-01 GetConversationHistory`` — ``GET /v1/foundation/conversation-history``
* ``FND-ANA-01 GetAnalyticsSummary`` — ``GET /v1/foundation/analytics/summary``

No AI reasoning is performed; the services return deterministic analytics data
derived from anonymized conversation logs and audit records.

Key design decisions:
* PII is never included in analytics; only anonymized aggregates are returned.
* The stores are in-memory fakes by default (for tests and local dev).
* Retention is handled externally by the retention sweep (WP-006).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal

from packages.contracts import (
    CATEGORY_VALIDATION,
    FIELD_REQUIRED,
    INVALID_REQUEST,
    UnifiedErrorEnvelope,
    make_error_envelope,
)


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------


def _service_error(
    code: str,
    message: str,
    *,
    category: str,
    field_errors: Optional[Dict[str, str]] = None,
    retryable: bool = False,
    retry_after_seconds: Optional[int] = None,
    fallback: Optional[str] = None,
) -> UnifiedErrorEnvelope:
    """Create a unified error envelope for service-layer errors."""
    return make_error_envelope(
        code=code,
        message=message,
        category=category,
        field_errors=field_errors,
        retryable=retryable,
        retry_after_seconds=retry_after_seconds,
        fallback=fallback,
    )


# ---------------------------------------------------------------------------
# DTOs per INT-04 (Data Contracts)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConversationHistoryItem:
    """A single anonymized conversation history item.

    Per INT-04, this contains no PII. All content is already anonymized
    by the conversation logging service (FND-LOG-01).
    """

    session_id: str
    turn_id: str
    role: Literal["user", "assistant", "system"]
    content: str  # already anonymized
    intent: Optional[str] = None
    has_pii: bool = False
    pii_redacted: bool = False
    emergency_triggered: bool = False
    emergency_level: Optional[int] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "role": self.role,
            "content": self.content,
            "has_pii": self.has_pii,
            "pii_redacted": self.pii_redacted,
            "emergency_triggered": self.emergency_triggered,
            "created_at": self.created_at,
        }
        if self.intent is not None:
            result["intent"] = self.intent
        if self.emergency_level is not None:
            result["emergency_level"] = self.emergency_level
        if self.tool_calls:
            result["tool_calls"] = list(self.tool_calls)
        if self.citations:
            result["citations"] = list(self.citations)
        return result


@dataclass(frozen=True)
class ConversationHistoryPageDTO:
    """Paginated response for FND-HIS-01 GetConversationHistory.

    Per INT-04: items[] (no PII), page metadata; audit access metadata.
    """

    items: List[ConversationHistoryItem] = field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
    next_cursor: Optional[str] = None
    has_more: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "next_cursor": self.next_cursor,
            "has_more": self.has_more,
        }


@dataclass(frozen=True)
class AnalyticsSummaryDTO:
    """Analytics summary response for FND-ANA-01 GetAnalyticsSummary.

    Per INT-04: time range; top_questions; fallback_rate; emergency_rate;
    feedback_score; generated_at; only aggregate safe data.
    """

    time_range_from: str
    time_range_to: str
    top_questions: List[Dict[str, Any]] = field(default_factory=list)
    fallback_rate: float = 0.0
    emergency_rate: float = 0.0
    feedback_score: Optional[float] = None
    total_conversations: int = 0
    total_turns: int = 0
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "time_range_from": self.time_range_from,
            "time_range_to": self.time_range_to,
            "top_questions": list(self.top_questions),
            "fallback_rate": self.fallback_rate,
            "emergency_rate": self.emergency_rate,
            "total_conversations": self.total_conversations,
            "total_turns": self.total_turns,
            "generated_at": self.generated_at,
        }
        if self.feedback_score is not None:
            result["feedback_score"] = self.feedback_score
        return result


@dataclass(frozen=True)
class ConversationHistoryQuery:
    """Query parameters for FND-HIS-01 GetConversationHistory."""

    session_id: Optional[str] = None
    from_time: Optional[str] = None
    to_time: Optional[str] = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class AnalyticsSummaryQuery:
    """Query parameters for FND-ANA-01 GetAnalyticsSummary."""

    from_time: str
    to_time: str
    dimensions: Optional[List[str]] = None  # e.g., ["intent", "domain"]


# ---------------------------------------------------------------------------
# In-memory stores (for tests and local dev)
# ---------------------------------------------------------------------------


class _InMemoryConversationHistoryStore:
    """Thread-safe in-memory store for conversation history items."""

    def __init__(self) -> None:
        self._items: List[ConversationHistoryItem] = []
        self._lock = __import__("threading").Lock()

    def append(self, item: ConversationHistoryItem) -> None:
        with self._lock:
            self._items.append(item)

    def query(self, query: ConversationHistoryQuery) -> ConversationHistoryPageDTO:
        with self._lock:
            filtered = list(self._items)
            if query.session_id:
                filtered = [
                    e for e in filtered if e.session_id == query.session_id
                ]
            if query.from_time:
                filtered = [
                    e for e in filtered if e.created_at >= query.from_time
                ]
            if query.to_time:
                filtered = [
                    e for e in filtered if e.created_at <= query.to_time
                ]
            # Sort by created_at descending (newest first)
            filtered.sort(key=lambda e: e.created_at, reverse=True)
            total = len(filtered)
            page = filtered[query.offset : query.offset + query.limit]
            next_offset = query.offset + query.limit
            has_more = next_offset < total
            next_cursor = str(next_offset) if has_more else None
            return ConversationHistoryPageDTO(
                items=page,
                total=total,
                limit=query.limit,
                offset=query.offset,
                next_cursor=next_cursor,
                has_more=has_more,
            )

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class _InMemoryAnalyticsStore:
    """Thread-safe in-memory store for analytics aggregates."""

    def __init__(self) -> None:
        self._conversation_logs: List[ConversationHistoryItem] = []
        self._audit_events: List[Dict[str, Any]] = []
        self._feedback_entries: List[Dict[str, Any]] = []
        self._lock = __import__("threading").Lock()

    def add_conversation_log(self, item: ConversationHistoryItem) -> None:
        with self._lock:
            self._conversation_logs.append(item)

    def add_audit_event(self, event: Dict[str, Any]) -> None:
        with self._lock:
            self._audit_events.append(event)

    def add_feedback(self, feedback: Dict[str, Any]) -> None:
        with self._lock:
            self._feedback_entries.append(feedback)

    def get_conversation_logs(
        self, from_time: str, to_time: str
    ) -> List[ConversationHistoryItem]:
        with self._lock:
            return [
                log
                for log in self._conversation_logs
                if from_time <= log.created_at <= to_time
            ]

    def get_audit_events(
        self, from_time: str, to_time: str
    ) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                evt
                for evt in self._audit_events
                if from_time <= evt.get("created_at", "") <= to_time
            ]

    def get_feedback_entries(
        self, from_time: str, to_time: str
    ) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                fb
                for fb in self._feedback_entries
                if from_time <= fb.get("created_at", "") <= to_time
            ]

    def clear(self) -> None:
        with self._lock:
            self._conversation_logs.clear()
            self._audit_events.clear()
            self._feedback_entries.clear()


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


class ConversationHistoryService:
    """Conversation history service (FND-HIS-01).

    Provides paginated access to anonymized conversation logs.
    """

    def __init__(
        self,
        store: Optional[_InMemoryConversationHistoryStore] = None,
    ) -> None:
        self._store = store if store is not None else _InMemoryConversationHistoryStore()

    # -----------------------------------------------------------------------
    # FND-HIS-01 GetConversationHistory
    # -----------------------------------------------------------------------
    def get_history(
        self,
        query: Optional[ConversationHistoryQuery] = None,
        *,
        session_id: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConversationHistoryPageDTO:
        """Get paginated conversation history (FND-HIS-01).

        Parameters
        ----------
        query : ConversationHistoryQuery, optional
            Query object with all filter parameters.
        session_id : str, optional
            Filter by specific session.
        from_time : str, optional
            ISO 8601 lower bound (inclusive).
        to_time : str, optional
            ISO 8601 upper bound (inclusive).
        limit : int
            Maximum items to return (1-200).
        offset : int
            Number of items to skip.

        Returns
        -------
        ConversationHistoryPageDTO
            A page of anonymized conversation history items.
        """
        # Support both query object and keyword arguments
        if query is not None:
            session_id = query.session_id
            from_time = query.from_time
            to_time = query.to_time
            limit = query.limit
            offset = query.offset

        if not session_id or not session_id.strip():
            raise _service_error(
                code=FIELD_REQUIRED,
                message="session_id is required",
                category=CATEGORY_VALIDATION,
                field_errors={"session_id": "required"},
            )

        if limit < 1 or limit > 200:
            raise _service_error(
                code=FIELD_REQUIRED,
                message="limit must be between 1 and 200",
                category=CATEGORY_VALIDATION,
                field_errors={"limit": "out of range"},
            )
        if offset < 0:
            raise _service_error(
                code=FIELD_REQUIRED,
                message="offset must be >= 0",
                category=CATEGORY_VALIDATION,
                field_errors={"offset": "negative"},
            )
        if from_time and to_time and from_time > to_time:
            raise _service_error(
                code=INVALID_REQUEST,
                message="from_time must be before to_time",
                category=CATEGORY_VALIDATION,
                field_errors={"time_range": "invalid"},
            )

        query_obj = ConversationHistoryQuery(
            session_id=session_id,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
            offset=offset,
        )
        return self._store.query(query_obj)

    # -----------------------------------------------------------------------
    # Internal: used by conversation logger to feed history store
    # -----------------------------------------------------------------------
    def append_entry(self, entry: ConversationHistoryItem) -> None:
        """Append an entry to the history store (internal use)."""
        self._store.append(entry)


class AnalyticsService:
    """Analytics service (FND-ANA-01).

    Computes aggregate analytics from anonymized conversation logs,
    audit events, and feedback.
    """

    def __init__(
        self,
        store: Optional[_InMemoryAnalyticsStore] = None,
    ) -> None:
        self._store = store if store is not None else _InMemoryAnalyticsStore()

    # -----------------------------------------------------------------------
    # FND-ANA-01 GetAnalyticsSummary
    # -----------------------------------------------------------------------
    def get_summary(
        self,
        query: Optional[AnalyticsSummaryQuery] = None,
        *,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        dimensions: Optional[List[str]] = None,
    ) -> AnalyticsSummaryDTO:
        """Get analytics summary for a time range (FND-ANA-01).

        Parameters
        ----------
        query : AnalyticsSummaryQuery, optional
            Query object with time range and dimensions.
        from_time : str, optional
            ISO 8601 lower bound (inclusive), required if query not provided.
        to_time : str, optional
            ISO 8601 upper bound (inclusive), required if query not provided.
        dimensions : list[str], optional
            Breakdown dimensions (e.g., ["intent", "domain"]).

        Returns
        -------
        AnalyticsSummaryDTO
            Aggregated analytics summary.

        Raises
        ------
        UnifiedErrorEnvelope
            If time range is invalid.
        """
        # Support both query object and keyword arguments
        if query is not None:
            from_time = query.from_time
            to_time = query.to_time
            dimensions = query.dimensions

        if not from_time or not to_time:
            raise _service_error(
                code=FIELD_REQUIRED,
                message="from_time and to_time are required",
                category=CATEGORY_VALIDATION,
                field_errors={"time_range": "required"},
            )
        if from_time > to_time:
            raise _service_error(
                code=INVALID_REQUEST,
                message="from_time must be before to_time",
                category=CATEGORY_VALIDATION,
                field_errors={"time_range": "invalid"},
            )

        # Fetch data in time range
        conversation_logs = self._store.get_conversation_logs(from_time, to_time)
        audit_events = self._store.get_audit_events(from_time, to_time)
        feedback_entries = self._store.get_feedback_entries(from_time, to_time)

        # Compute aggregates
        total_conversations = len(
            {log.session_id for log in conversation_logs}
        )
        total_turns = len(conversation_logs)

        # Fallback rate: turns with intent == "fallback" or outcome == "fallback"
        fallback_turns = sum(
            1
            for log in conversation_logs
            if log.intent == "fallback"
        )
        fallback_rate = (
            fallback_turns / total_turns if total_turns > 0 else 0.0
        )

        # Emergency rate: turns where emergency_triggered is True
        emergency_turns = sum(
            1 for log in conversation_logs if log.emergency_triggered
        )
        emergency_rate = (
            emergency_turns / total_turns if total_turns > 0 else 0.0
        )

        # Feedback score: average rating
        ratings = [fb.get("rating") for fb in feedback_entries if fb.get("rating")]
        feedback_score = (
            sum(ratings) / len(ratings) if ratings else None
        )

        # Top questions: group by intent or extract from user messages
        intent_counts: Dict[str, int] = {}
        for log in conversation_logs:
            if log.role == "user" and log.intent:
                intent_counts[log.intent] = intent_counts.get(log.intent, 0) + 1

        top_questions = [
            {"intent": intent, "count": count}
            for intent, count in sorted(
                intent_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]
        ]

        return AnalyticsSummaryDTO(
            time_range_from=from_time,
            time_range_to=to_time,
            top_questions=top_questions,
            fallback_rate=round(fallback_rate, 4),
            emergency_rate=round(emergency_rate, 4),
            feedback_score=round(feedback_score, 2) if feedback_score else None,
            total_conversations=total_conversations,
            total_turns=total_turns,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # -----------------------------------------------------------------------
    # Internal: used by other services to feed analytics store
    # -----------------------------------------------------------------------
    def record_conversation_log(self, item: ConversationHistoryItem) -> None:
        """Record a conversation log entry for analytics (internal use)."""
        self._store.add_conversation_log(item)

    def record_audit_event(self, event: Dict[str, Any]) -> None:
        """Record an audit event for analytics (internal use)."""
        self._store.add_audit_event(event)

    def record_feedback(self, feedback: Dict[str, Any]) -> None:
        """Record a feedback entry for analytics (internal use)."""
        self._store.add_feedback(feedback)


__all__ = [
    "ConversationHistoryItem",
    "ConversationHistoryPageDTO",
    "ConversationHistoryQuery",
    "ConversationHistoryService",
    "AnalyticsSummaryDTO",
    "AnalyticsSummaryQuery",
    "AnalyticsService",
]
# === TASK:WP-105:END ===
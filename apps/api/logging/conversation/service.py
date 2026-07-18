# === TASK:WP-105:START ===
"""Conversation logging service (FND-LOG-01).

This module implements anonymized conversation logging as described in
``docs/artifacts/architecture/integration-data-flow.md`` (ARCH-08) under
the *Conversation logging* section.

Key design decisions
--------------------
* PII detection is performed before storage; raw PII is never persisted.
* The store is an in-memory fake by default (for tests and local dev).
* Consistency is eventual; the service does not block on write completion.
* Retention is handled externally by the retention sweep (WP-006).

Contracts
---------
* ``ConversationLogEntry`` — the anonymized record stored for each turn.
* ``ConversationLogService`` — the public API for appending and querying logs.
"""

from __future__ import annotations

import re
import time
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from packages.contracts import (
    CATEGORY_VALIDATION,
    FIELD_REQUIRED,
    INTERNAL_ERROR,
    UnifiedErrorEnvelope,
    make_error_envelope,
)
from apps.api.foundation.operational_repository import OperationalRepository


# ---------------------------------------------------------------------------
# PII detection helpers
# ---------------------------------------------------------------------------

# Simple patterns for MVP PII detection. These are intentionally basic;
# production would use a dedicated PII service.
_PII_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b\d{10,15}\b"),  # phone numbers (10-15 digits)
    re.compile(r"\b\d{9}\b"),  # 9-digit identifiers (e.g., some IDs)
    re.compile(r"\b\d{12}\b"),  # 12-digit identifiers (e.g., CCCD)
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # email
]


def _detect_pii(text: str) -> bool:
    """Return True if *text* contains any pattern that looks like PII."""
    for pattern in _PII_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _anonymize(text: str) -> str:
    """Replace detected PII with a placeholder.

    For MVP this simply replaces each matched token with ``[REDACTED]``.
    """
    result = text
    for pattern in _PII_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConversationLogEntry:
    """An anonymized conversation log entry.

    This is the canonical record stored for each user/assistant turn.
    No raw PII is present in any field.
    """

    session_id: str
    turn_id: str
    role: str  # "user" | "assistant" | "system"
    content: str  # anonymized
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
class ConversationLogQuery:
    """Query parameters for retrieving conversation logs."""

    session_id: str
    limit: int = 50
    offset: int = 0
    from_time: Optional[str] = None
    to_time: Optional[str] = None


@dataclass(frozen=True)
class ConversationLogPage:
    """A page of conversation log entries."""

    entries: List[ConversationLogEntry] = field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
        }


# ---------------------------------------------------------------------------
# In-memory store (for tests and local dev)
# ---------------------------------------------------------------------------


class _InMemoryConversationStore:
    """Thread-safe in-memory store for conversation logs."""

    def __init__(self) -> None:
        self._entries: List[ConversationLogEntry] = []
        self._lock = __import__("threading").Lock()

    def append(self, entry: ConversationLogEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def query(self, query: ConversationLogQuery) -> ConversationLogPage:
        with self._lock:
            filtered = [e for e in self._entries if e.session_id == query.session_id]
            if query.from_time:
                filtered = [e for e in filtered if e.created_at >= query.from_time]
            if query.to_time:
                filtered = [e for e in filtered if e.created_at <= query.to_time]
            total = len(filtered)
            page = filtered[query.offset : query.offset + query.limit]
            return ConversationLogPage(
                entries=page,
                total=total,
                limit=query.limit,
                offset=query.offset,
            )

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ConversationLogService:
    """Conversation logging service (FND-LOG-01).

    Handles anonymized logging of conversation turns. PII is detected and
    redacted before storage.
    """

    def __init__(
        self,
        store: Optional[_InMemoryConversationStore] = None,
        repository: Optional[OperationalRepository] = None,
    ) -> None:
        self._store = store if store is not None else _InMemoryConversationStore()
        self._repository = repository or (OperationalRepository(os.environ["DATABASE_URL"])
                                          if os.environ.get("DATABASE_URL") else None)

    # -------------------------------------------------------------------
    # FND-LOG-01 AppendLogEntry
    # -------------------------------------------------------------------
    def append_entry(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        turn_id: Optional[str] = None,
        intent: Optional[str] = None,
        has_pii: Optional[bool] = None,
        pii_redacted: Optional[bool] = None,
        emergency_triggered: bool = False,
        emergency_level: Optional[int] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        citations: Optional[List[Dict[str, Any]]] = None,
    ) -> ConversationLogEntry:
        """Append an anonymized conversation log entry.

        Parameters
        ----------
        session_id : str
            The session this entry belongs to.
        role : str
            One of ``"user"``, ``"assistant"``, ``"system"``.
        content : str
            The message content (will be anonymized if PII is detected).
        turn_id : str, optional
            Unique turn identifier. Auto-generated if not provided.
        intent : str, optional
            Detected intent for this turn.
        emergency_triggered : bool
            Whether an emergency was triggered.
        emergency_level : int, optional
            Emergency level if triggered.
        tool_calls : list, optional
            Tool calls made during this turn.
        citations : list, optional
            Citations returned.

        Returns
        -------
        ConversationLogEntry
            The stored anonymized entry.
        """
        if not session_id or not session_id.strip():
            raise _service_error(
                code=FIELD_REQUIRED,
                message="session_id is required",
                category=CATEGORY_VALIDATION,
                field_errors={"session_id": "required"},
            )
        if not role or role not in ("user", "assistant", "system"):
            raise _service_error(
                code=FIELD_REQUIRED,
                message="role must be 'user', 'assistant', or 'system'",
                category=CATEGORY_VALIDATION,
                field_errors={"role": "invalid role"},
            )
        if not content:
            raise _service_error(
                code=FIELD_REQUIRED,
                message="content must be non-empty",
                category=CATEGORY_VALIDATION,
                field_errors={"content": "required"},
            )

        # Detect and redact when callers submit raw content.  Guardrail
        # callers may already have redacted the text; in that case they pass
        # the original detection result so the audit record retains the fact
        # that PII was present without persisting the raw value.
        detected_has_pii = _detect_pii(content)
        anonymized = _anonymize(content) if detected_has_pii else content
        entry_has_pii = detected_has_pii if has_pii is None else has_pii
        entry_pii_redacted = detected_has_pii if pii_redacted is None else pii_redacted

        actual_turn_id = turn_id or f"turn_{int(time.time() * 1000)}_{id(content) % 10000}"

        entry = ConversationLogEntry(
            session_id=session_id,
            turn_id=actual_turn_id,
            role=role,
            content=anonymized,
            intent=intent,
            has_pii=entry_has_pii,
            pii_redacted=entry_pii_redacted,
            emergency_triggered=emergency_triggered,
            emergency_level=emergency_level,
            tool_calls=tool_calls or [],
            citations=citations or [],
        )
        if self._repository is not None:
            self._repository.append_message(session_id, role, anonymized, intent=intent,
                tools_called=tool_calls or [], citations=citations or [],
                emergency_triggered=emergency_triggered,
                detection_path="keyword" if emergency_triggered else None)
        else:
            self._store.append(entry)
        return entry

    # -------------------------------------------------------------------
    # FND-LOG-02 QueryConversationLog
    # -------------------------------------------------------------------
    def query_log(
        self,
        session_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
    ) -> ConversationLogPage:
        """Query conversation log entries for a session.

        Parameters
        ----------
        session_id : str
            The session to query.
        limit : int
            Maximum entries to return (1-200).
        offset : int
            Number of entries to skip.
        from_time : str, optional
            ISO 8601 lower bound (inclusive).
        to_time : str, optional
            ISO 8601 upper bound (inclusive).

        Returns
        -------
        ConversationLogPage
            A page of anonymized log entries.
        """
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

        query = ConversationLogQuery(
            session_id=session_id,
            limit=limit,
            offset=offset,
            from_time=from_time,
            to_time=to_time,
        )
        if self._repository is None:
            return self._store.query(query)
        result = self._repository.conversation_history(session_id, limit, offset, from_time, to_time)
        entries = [ConversationLogEntry(session_id=item["session_id"], turn_id=item["turn_id"],
                   role=item["role"], content=item["content"], intent=item.get("intent"),
                   emergency_triggered=item.get("emergency_triggered", False),
                   tool_calls=item.get("tool_calls") or [], citations=item.get("citations") or [],
                   created_at=item["created_at"]) for item in result["items"]]
        return ConversationLogPage(entries=entries, total=result["total"], limit=limit, offset=offset)


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


__all__ = [
    "ConversationLogEntry",
    "ConversationLogQuery",
    "ConversationLogPage",
    "ConversationLogService",
]
# === TASK:WP-105:END ===

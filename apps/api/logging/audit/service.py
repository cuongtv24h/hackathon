# === TASK:WP-105:START ===
"""Audit logging service (FND-AUD-01).

This module implements immutable audit logging as described in
``docs/artifacts/architecture/integration-data-flow.md`` (ARCH-08) under
the *Emergency keyword path* and *Emergency LLM path* sections, which
both require async/immutable audit.

Key design decisions
--------------------
* Audit entries are append-only; once written they cannot be modified.
* The store is an in-memory fake by default (for tests and local dev).
* Retention is handled externally by the retention sweep (WP-006).
* Emergency, security, and content audit events all use the same schema.

Contracts
---------
* ``AuditLogEntry`` — the immutable audit record.
* ``AuditLogService`` — the public API for writing and querying audit logs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from packages.contracts import (
    CATEGORY_VALIDATION,
    FIELD_REQUIRED,
    UnifiedErrorEnvelope,
    make_error_envelope,
)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditLogEntry:
    """An immutable audit log entry.

    Once created, this record must never be modified. The ``event_type``
    categorises the entry (e.g. ``"emergency"``, ``"content_publish"``,
    ``"security"``, ``"admin_action"``).
    """

    audit_id: str
    event_type: str
    actor: str
    action: str
    resource: str
    details: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    outcome: str = "success"  # "success" | "failure" | "deferred"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "audit_id": self.audit_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "outcome": self.outcome,
            "created_at": self.created_at,
        }
        if self.details:
            result["details"] = dict(self.details)
        if self.session_id is not None:
            result["session_id"] = self.session_id
        return result


@dataclass(frozen=True)
class AuditLogQuery:
    """Query parameters for retrieving audit log entries."""

    event_type: Optional[str] = None
    actor: Optional[str] = None
    limit: int = 50
    offset: int = 0
    from_time: Optional[str] = None
    to_time: Optional[str] = None


@dataclass(frozen=True)
class AuditLogPage:
    """A page of audit log entries."""

    entries: List[AuditLogEntry] = field(default_factory=list)
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


class _InMemoryAuditStore:
    """Thread-safe in-memory store for audit logs."""

    def __init__(self) -> None:
        self._entries: List[AuditLogEntry] = []
        self._lock = __import__("threading").Lock()

    def append(self, entry: AuditLogEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def query(self, query: AuditLogQuery) -> AuditLogPage:
        with self._lock:
            filtered = list(self._entries)
            if query.event_type:
                filtered = [e for e in filtered if e.event_type == query.event_type]
            if query.actor:
                filtered = [e for e in filtered if e.actor == query.actor]
            if query.from_time:
                filtered = [e for e in filtered if e.created_at >= query.from_time]
            if query.to_time:
                filtered = [e for e in filtered if e.created_at <= query.to_time]
            total = len(filtered)
            page = filtered[query.offset : query.offset + query.limit]
            return AuditLogPage(
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


class AuditLogService:
    """Audit logging service (FND-AUD-01).

    Provides append-only audit logging for emergency events, content
    operations, security events, and admin actions.
    """

    VALID_EVENT_TYPES = frozenset({
        "emergency",
        "content_publish",
        "content_review",
        "security",
        "admin_action",
        "system",
    })

    VALID_OUTCOMES = frozenset({"success", "failure", "deferred"})

    def __init__(
        self,
        store: Optional[_InMemoryAuditStore] = None,
    ) -> None:
        self._store = store if store is not None else _InMemoryAuditStore()

    # -------------------------------------------------------------------
    # FND-AUD-01 WriteAuditEntry
    # -------------------------------------------------------------------
    def write_entry(
        self,
        event_type: str,
        actor: str,
        action: str,
        resource: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        outcome: str = "success",
    ) -> AuditLogEntry:
        """Write an immutable audit log entry.

        Parameters
        ----------
        event_type : str
            One of ``"emergency"``, ``"content_publish"``, ``"content_review"``,
            ``"security"``, ``"admin_action"``, ``"system"``.
        actor : str
            The identity that performed the action.
        action : str
            A short description of the action (e.g. ``"trigger_emergency"``).
        resource : str
            The resource affected (e.g. session ID, draft ID, config key).
        details : dict, optional
            Additional structured context.
        session_id : str, optional
            Associated session if applicable.
        outcome : str
            One of ``"success"``, ``"failure"``, ``"deferred"``.

        Returns
        -------
        AuditLogEntry
            The immutable audit record.
        """
        if not event_type or event_type not in self.VALID_EVENT_TYPES:
            raise _service_error(
                code=FIELD_REQUIRED,
                message=f"event_type must be one of {sorted(self.VALID_EVENT_TYPES)}",
                category=CATEGORY_VALIDATION,
                field_errors={"event_type": "invalid"},
            )
        if not actor or not actor.strip():
            raise _service_error(
                code=FIELD_REQUIRED,
                message="actor is required",
                category=CATEGORY_VALIDATION,
                field_errors={"actor": "required"},
            )
        if not action or not action.strip():
            raise _service_error(
                code=FIELD_REQUIRED,
                message="action is required",
                category=CATEGORY_VALIDATION,
                field_errors={"action": "required"},
            )
        if not resource or not resource.strip():
            raise _service_error(
                code=FIELD_REQUIRED,
                message="resource is required",
                category=CATEGORY_VALIDATION,
                field_errors={"resource": "required"},
            )
        if outcome not in self.VALID_OUTCOMES:
            raise _service_error(
                code=FIELD_REQUIRED,
                message=f"outcome must be one of {sorted(self.VALID_OUTCOMES)}",
                category=CATEGORY_VALIDATION,
                field_errors={"outcome": "invalid"},
            )

        audit_id = f"aud_{int(time.time() * 1000)}_{id(event_type) % 10000}"

        entry = AuditLogEntry(
            audit_id=audit_id,
            event_type=event_type,
            actor=actor,
            action=action,
            resource=resource,
            details=details or {},
            session_id=session_id,
            outcome=outcome,
        )
        self._store.append(entry)
        return entry

    # -------------------------------------------------------------------
    # FND-AUD-02 QueryAuditLog
    # -------------------------------------------------------------------
    def query_log(
        self,
        *,
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
    ) -> AuditLogPage:
        """Query audit log entries.

        Parameters
        ----------
        event_type : str, optional
            Filter by event type.
        actor : str, optional
            Filter by actor identity.
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
        AuditLogPage
            A page of audit log entries.
        """
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

        query = AuditLogQuery(
            event_type=event_type,
            actor=actor,
            limit=limit,
            offset=offset,
            from_time=from_time,
            to_time=to_time,
        )
        return self._store.query(query)


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
    "AuditLogEntry",
    "AuditLogQuery",
    "AuditLogPage",
    "AuditLogService",
]
# === TASK:WP-105:END ===
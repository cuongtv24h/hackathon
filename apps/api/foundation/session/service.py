# === TASK:WP-101:START ===
"""Foundation session service (FND-SES-01, FND-SES-02, FND-SES-03).

This module implements the session/context foundation APIs declared in
``docs/artifacts/interface/foundation-api-contracts.md`` (INT-03). The three
operations are:

* ``FND-SES-01 CreateSession``  — ``POST /v1/foundation/sessions``
* ``FND-SES-02 GetSessionContext`` — ``GET /v1/foundation/sessions/{session_id}``
* ``FND-SES-03 PatchSessionContext`` — ``PATCH /v1/foundation/sessions/{session_id}/context``

No AI reasoning is performed; the service is pure session/context lifecycle.
"""

from __future__ import annotations

import secrets
import time
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Literal, Mapping, Optional

from packages.contracts import (
    UnifiedErrorEnvelope,
    make_error_envelope,
    CATEGORY_NOT_FOUND,
    CATEGORY_VALIDATION,
    CATEGORY_SYSTEM,
    CONTENT_NOT_FOUND,
    INVALID_REQUEST,
    INTERNAL_ERROR,
    INVALID_ENUM,
    FIELD_REQUIRED,
)
from apps.api.foundation.database.connection import DatabaseClient, DatabaseError
from apps.api.foundation.operational_repository import OperationalRepository


# ---------------------------------------------------------------------------
# Session DTOs (from INT-04 / data-contracts.md)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionCreateRequest:
    """Request body for creating a new session."""

    actor_tag: str
    channel: Literal["web_widget", "web_page"]
    locale: str = "vi-VN"
    timezone: str = "Asia/Bangkok"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SessionCreateRequest":
        """Construct from a plain dictionary (e.g., parsed JSON)."""
        return cls(
            actor_tag=data.get("actor_tag", ""),
            channel=data.get("channel", "web_widget"),
            locale=data.get("locale", "vi-VN"),
            timezone=data.get("timezone", "Asia/Bangkok"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class SessionDTO:
    """Session identity and creation metadata returned by CreateSession."""

    session_id: str
    actor_tag: str
    channel: Literal["web_widget", "web_page"]
    created_at: str  # ISO 8601
    expires_at: str  # ISO 8601
    locale: str
    timezone: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "actor_tag": self.actor_tag,
            "channel": self.channel,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "locale": self.locale,
            "timezone": self.timezone,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class MessageDTO:
    """A single message in the session context."""

    role: Literal["user", "assistant", "system"]
    content: str
    intent: Optional[str] = None
    tools: List[Dict[str, Any]] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    emergency_metadata: Optional[Dict[str, Any]] = None
    time: str = field(default_factory=lambda: datetime.now(dt_timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "role": self.role,
            "content": self.content,
            "time": self.time,
        }
        if self.intent is not None:
            result["intent"] = self.intent
        if self.tools:
            result["tools"] = list(self.tools)
        if self.citations:
            result["citations"] = list(self.citations)
        if self.emergency_metadata is not None:
            result["emergency_metadata"] = dict(self.emergency_metadata)
        return result


@dataclass(frozen=True)
class EmergencyContextDTO:
    """Emergency context attached to a session."""

    triggered: bool = False
    level: Optional[int] = None
    path: Optional[str] = None
    time: Optional[str] = None
    banner: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"triggered": self.triggered}
        if self.level is not None:
            result["level"] = self.level
        if self.path is not None:
            result["path"] = self.path
        if self.time is not None:
            result["time"] = self.time
        if self.banner is not None:
            result["banner"] = self.banner
        return result


@dataclass(frozen=True)
class BookingFlowStateDTO:
    """Booking flow state attached to a session."""

    flow_id: Optional[str] = None
    step: Optional[str] = None
    selected_specialty_id: Optional[str] = None
    selected_doctor_id: Optional[str] = None
    selected_slot_id: Optional[str] = None
    collected_fields: Dict[str, Any] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    version: int = 0

    def to_dict(self) -> Dict[str, Any]:
        result = {"version": self.version}
        if self.flow_id is not None:
            result["flow_id"] = self.flow_id
        if self.step is not None:
            result["step"] = self.step
        if self.selected_specialty_id is not None:
            result["selected_specialty_id"] = self.selected_specialty_id
        if self.selected_doctor_id is not None:
            result["selected_doctor_id"] = self.selected_doctor_id
        if self.selected_slot_id is not None:
            result["selected_slot_id"] = self.selected_slot_id
        if self.collected_fields:
            result["collected_fields"] = dict(self.collected_fields)
        if self.missing_fields:
            result["missing_fields"] = list(self.missing_fields)
        return result


@dataclass(frozen=True)
class SessionContextDTO:
    """Full session context returned by GetSessionContext and PatchSessionContext."""

    session_id: str
    actor_tag: str
    channel: Literal["web_widget", "web_page"]
    created_at: str
    expires_at: str
    locale: str
    timezone: str
    messages: List[MessageDTO] = field(default_factory=list)
    emergency_context: EmergencyContextDTO = field(default_factory=EmergencyContextDTO)
    booking_flow: BookingFlowStateDTO = field(default_factory=BookingFlowStateDTO)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "session_id": self.session_id,
            "actor_tag": self.actor_tag,
            "channel": self.channel,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "locale": self.locale,
            "timezone": self.timezone,
            "messages": [m.to_dict() for m in self.messages],
            "emergency_context": self.emergency_context.to_dict(),
            "booking_flow": self.booking_flow.to_dict(),
            "metadata": dict(self.metadata),
        }
        return result


@dataclass(frozen=True)
class SessionContextPatchRequest:
    """Request body for patching session context."""

    messages: Optional[List[MessageDTO]] = None
    emergency_context: Optional[EmergencyContextDTO] = None
    booking_flow: Optional[BookingFlowStateDTO] = None
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SessionContextPatchRequest":
        """Construct from a plain dictionary (e.g., parsed JSON)."""
        messages = None
        if "messages" in data and data["messages"] is not None:
            messages = []
            for msg in data["messages"]:
                if isinstance(msg, MessageDTO):
                    messages.append(msg)
                else:
                    messages.append(
                        MessageDTO(
                            role=msg.get("role", "user"),
                            content=msg.get("content", ""),
                            intent=msg.get("intent"),
                            tools=msg.get("tools", []),
                            citations=msg.get("citations", []),
                            emergency_metadata=msg.get("emergency_metadata"),
                            time=msg.get("time", datetime.now(dt_timezone.utc).isoformat()),
                        )
                    )

        emergency_context = None
        if "emergency_context" in data and data["emergency_context"] is not None:
            ec = data["emergency_context"]
            emergency_context = EmergencyContextDTO(
                triggered=ec.get("triggered", False),
                level=ec.get("level"),
                path=ec.get("path"),
                time=ec.get("time"),
                banner=ec.get("banner"),
            )

        booking_flow = None
        if "booking_flow" in data and data["booking_flow"] is not None:
            bf = data["booking_flow"]
            booking_flow = BookingFlowStateDTO(
                flow_id=bf.get("flow_id"),
                step=bf.get("step"),
                selected_specialty_id=bf.get("selected_specialty_id"),
                selected_doctor_id=bf.get("selected_doctor_id"),
                selected_slot_id=bf.get("selected_slot_id"),
                collected_fields=bf.get("collected_fields", {}),
                missing_fields=bf.get("missing_fields", []),
                version=bf.get("version", 0),
            )

        metadata = dict(data.get("metadata", {})) if data.get("metadata") else None

        return cls(
            messages=messages,
            emergency_context=emergency_context,
            booking_flow=booking_flow,
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# In-memory session store (for tests and local dev without DB)
# ---------------------------------------------------------------------------


class _InMemorySessionStore:
    """Thread-safe in-memory session store for unit tests."""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionContextDTO] = {}
        self._lock = __import__("threading").Lock()

    def create(
        self,
        session_id: str,
        actor_tag: str,
        channel: Literal["web_widget", "web_page"],
        locale: str,
        tz_str: str,
        metadata: Dict[str, Any],
        idle_seconds: int,
        max_seconds: int,
    ) -> SessionContextDTO:
        now = datetime.now(dt_timezone.utc)
        max_delta = __import__("datetime").timedelta(seconds=max_seconds)
        created_at = now.isoformat()
        expires_at = (now + max_delta).isoformat()

        ctx = SessionContextDTO(
            session_id=session_id,
            actor_tag=actor_tag,
            channel=channel,
            created_at=created_at,
            expires_at=expires_at,
            locale=locale,
            timezone=tz_str,
            messages=[],
            emergency_context=EmergencyContextDTO(),
            booking_flow=BookingFlowStateDTO(),
            metadata=dict(metadata),
        )
        with self._lock:
            self._sessions[session_id] = ctx
        return ctx

    def get(self, session_id: str) -> Optional[SessionContextDTO]:
        with self._lock:
            ctx = self._sessions.get(session_id)
            if ctx is None:
                return None
            # Check expiry
            exp = datetime.fromisoformat(ctx.expires_at.replace("Z", "+00:00"))
            if datetime.now(dt_timezone.utc) > exp:
                # Expired - remove and return None
                del self._sessions[session_id]
                return None
            return ctx

    def patch(
        self,
        session_id: str,
        patch: SessionContextPatchRequest,
        idle_seconds: int,
        max_seconds: int,
    ) -> Optional[SessionContextDTO]:
        with self._lock:
            ctx = self._sessions.get(session_id)
            if ctx is None:
                return None
            # Check expiry
            exp = datetime.fromisoformat(ctx.expires_at.replace("Z", "+00:00"))
            if datetime.now(dt_timezone.utc) > exp:
                del self._sessions[session_id]
                return None

            # Apply patch
            messages = patch.messages if patch.messages is not None else ctx.messages
            emergency_context = (
                patch.emergency_context
                if patch.emergency_context is not None
                else ctx.emergency_context
            )
            booking_flow = (
                patch.booking_flow if patch.booking_flow is not None else ctx.booking_flow
            )
            metadata = patch.metadata if patch.metadata is not None else ctx.metadata

            now = datetime.now(dt_timezone.utc)
            max_delta = __import__("datetime").timedelta(seconds=max_seconds)
            expires_at = (now + max_delta).isoformat()

            new_ctx = SessionContextDTO(
                session_id=ctx.session_id,
                actor_tag=ctx.actor_tag,
                channel=ctx.channel,
                created_at=ctx.created_at,
                expires_at=expires_at,
                locale=ctx.locale,
                timezone=ctx.timezone,
                messages=messages,
                emergency_context=emergency_context,
                booking_flow=booking_flow,
                metadata=metadata,
            )
            self._sessions[session_id] = new_ctx
            return new_ctx

    def delete(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False


# ---------------------------------------------------------------------------
# Session Service
# ---------------------------------------------------------------------------


class SessionService:
    """Foundation session service implementing FND-SES-01/02/03."""

    def __init__(
        self,
        db: Optional[DatabaseClient] = None,
        repository: Optional[OperationalRepository] = None,
        *,
        idle_seconds: int = 1800,  # 30 minutes
        max_seconds: int = 86400,  # 24 hours
    ) -> None:
        self._db = db
        self._repository = repository or (
            OperationalRepository(os.environ["DATABASE_URL"])
            if os.environ.get("DATABASE_URL") else None
        )
        self._idle_seconds = idle_seconds
        self._max_seconds = max_seconds
        self._memory = _InMemorySessionStore()

    # -----------------------------------------------------------------------
    # FND-SES-01 CreateSession
    # -----------------------------------------------------------------------
    def create_session(self, request: SessionCreateRequest) -> SessionDTO:
        """Create a new session (FND-SES-01)."""
        if not request.actor_tag or not request.actor_tag.strip():
            raise _service_error(
                code=FIELD_REQUIRED,
                message="actor_tag is required",
                category=CATEGORY_VALIDATION,
                field_errors={"actor_tag": "required"},
            )

        if request.channel not in ("web_widget", "web_page"):
            raise _service_error(
                code=INVALID_ENUM,
                message="channel must be web_widget or web_page",
                category=CATEGORY_VALIDATION,
                field_errors={"channel": "invalid enum value"},
            )

        session_id = f"ses_{secrets.token_urlsafe(16)}"
        now = datetime.now(dt_timezone.utc)
        max_delta = __import__("datetime").timedelta(seconds=self._max_seconds)

        session = SessionDTO(
            session_id=session_id,
            actor_tag=request.actor_tag,
            channel=request.channel,
            created_at=now.isoformat(),
            expires_at=(now + max_delta).isoformat(),
            locale=request.locale,
            timezone=request.timezone,
            metadata=dict(request.metadata),
        )

        # Tests inject/use the explicit in-memory store. Runtime persistence is
        # selected whenever DATABASE_URL is configured; it never silently
        # falls back after a repository error.
        if self._repository is not None:
            context = SessionContextDTO(session_id=session_id, actor_tag=request.actor_tag,
                channel=request.channel, created_at=session.created_at, expires_at=session.expires_at,
                locale=request.locale, timezone=request.timezone, metadata=dict(request.metadata))
            metadata = dict(request.metadata)
            metadata.update({"actor_tag": request.actor_tag, "locale": request.locale,
                             "timezone": request.timezone, "session_context": context.to_dict()})
            row = self._repository.create_session(session_id, request.channel, metadata)
            return SessionDTO(session_id=session_id, actor_tag=request.actor_tag, channel=request.channel,
                              created_at=row["started_at"], expires_at=row["expires_at"],
                              locale=request.locale, timezone=request.timezone, metadata=dict(request.metadata))
        self._memory.create(
            session_id=session_id, actor_tag=request.actor_tag, channel=request.channel,
            locale=request.locale, tz_str=request.timezone, metadata=request.metadata,
            idle_seconds=self._idle_seconds, max_seconds=self._max_seconds,
        )
        return session

    # -----------------------------------------------------------------------
    # FND-SES-02 GetSessionContext
    # -----------------------------------------------------------------------
    def get_session_context(self, session_id: str) -> SessionContextDTO:
        """Retrieve full session context (FND-SES-02)."""
        if not session_id or not session_id.strip():
            raise _service_error(
                code=FIELD_REQUIRED,
                message="session_id is required",
                category=CATEGORY_VALIDATION,
                field_errors={"session_id": "required"},
            )

        if self._repository is not None:
            row = self._repository.get_session_context(session_id)
            ctx = self._context_from_row(session_id, row) if row else None
        else:
            ctx = self._memory.get(session_id)
        if ctx is None:
            raise _service_error(
                code=CONTENT_NOT_FOUND,
                message="session not found or expired",
                category=CATEGORY_NOT_FOUND,
            )

        return ctx

    # -----------------------------------------------------------------------
    # FND-SES-03 PatchSessionContext
    # -----------------------------------------------------------------------
    def patch_session_context(
        self, session_id: str, patch: SessionContextPatchRequest
    ) -> SessionContextDTO:
        """Patch session context (FND-SES-03)."""
        if not session_id or not session_id.strip():
            raise _service_error(
                code=FIELD_REQUIRED,
                message="session_id is required",
                category=CATEGORY_VALIDATION,
                field_errors={"session_id": "required"},
            )

        if self._repository is not None:
            row = self._repository.get_session_context(session_id)
            current = self._context_from_row(session_id, row) if row else None
            ctx = self._apply_patch(current, patch) if current else None
            if ctx is not None:
                metadata = dict(row["metadata"])
                metadata["session_context"] = ctx.to_dict()
                updated = self._repository.update_session_context(session_id, metadata)
                ctx = self._context_from_row(session_id, updated) if updated else None
        else:
            ctx = self._memory.patch(
            session_id=session_id,
            patch=patch,
            idle_seconds=self._idle_seconds,
            max_seconds=self._max_seconds,
        )
        if ctx is None:
            raise _service_error(
                code=CONTENT_NOT_FOUND,
                message="session not found or expired",
                category=CATEGORY_NOT_FOUND,
            )

        return ctx

    def _context_from_row(self, session_id, row):
        data = dict((row or {}).get("metadata") or {}).get("session_context") or {}
        if not data:
            return None
        return SessionContextPatchRequest.from_dict(data) and SessionContextDTO(
            session_id=session_id, actor_tag=data.get("actor_tag", row["metadata"].get("actor_tag", "")),
            channel=row["channel"], created_at=row["started_at"], expires_at=row["expires_at"],
            locale=data.get("locale", row["metadata"].get("locale", "vi-VN")),
            timezone=data.get("timezone", row["metadata"].get("timezone", "Asia/Bangkok")),
            messages=SessionContextPatchRequest.from_dict(data).messages or [],
            emergency_context=SessionContextPatchRequest.from_dict(data).emergency_context or EmergencyContextDTO(),
            booking_flow=SessionContextPatchRequest.from_dict(data).booking_flow or BookingFlowStateDTO(),
            metadata=data.get("metadata", {}),
        )

    def _apply_patch(self, ctx, patch):
        now = datetime.now(dt_timezone.utc)
        expires_at = (now + __import__("datetime").timedelta(seconds=self._max_seconds)).isoformat()
        return SessionContextDTO(session_id=ctx.session_id, actor_tag=ctx.actor_tag, channel=ctx.channel,
            created_at=ctx.created_at, expires_at=expires_at, locale=ctx.locale, timezone=ctx.timezone,
            messages=patch.messages if patch.messages is not None else ctx.messages,
            emergency_context=patch.emergency_context if patch.emergency_context is not None else ctx.emergency_context,
            booking_flow=patch.booking_flow if patch.booking_flow is not None else ctx.booking_flow,
            metadata=patch.metadata if patch.metadata is not None else ctx.metadata)


# ---------------------------------------------------------------------------
# Error helpers
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
    """Create a unified error envelope for service-layer errors (raised directly)."""
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
    # DTOs
    "SessionCreateRequest",
    "SessionDTO",
    "SessionContextDTO",
    "MessageDTO",
    "EmergencyContextDTO",
    "BookingFlowStateDTO",
    "SessionContextPatchRequest",
    # Service
    "SessionService",
]
# === TASK:WP-101:END ===

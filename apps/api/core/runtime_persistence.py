"""Shared operational persistence wiring for capability runtime requests."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from apps.api.foundation.analytics.service import AnalyticsService, ConversationHistoryService
from apps.api.foundation.feedback.service import FeedbackService
from apps.api.foundation.operational_repository import OperationalRepository
from apps.api.foundation.session.service import SessionService
from apps.api.logging.audit.service import AuditLogService
from apps.api.logging.conversation.service import ConversationLogService

logger = logging.getLogger(__name__)

SAFE_CHANNELS = {"web_page", "web_widget"}
SAFE_FALLBACK_MESSAGE = "Yêu cầu khẩn cấp đã được nhận. Vui lòng gọi 115 hoặc đến cơ sở cấp cứu gần nhất ngay lập tức."


@dataclass(frozen=True)
class OperationalRuntime:
    repository: Any
    sessions: SessionService
    conversations: ConversationLogService
    feedback: FeedbackService
    audit: AuditLogService
    history: ConversationHistoryService
    analytics: AnalyticsService


def build_operational_runtime(database_url: Optional[str] = None, *, repository: Any = None) -> OperationalRuntime:
    """Build the one shared operational runtime composition."""
    repo = repository
    if repo is None:
        if database_url is None:
            database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("operational persistence is unavailable")
        repo = OperationalRepository(database_url)
    return OperationalRuntime(
        repository=repo,
        sessions=SessionService(repository=repo),
        conversations=ConversationLogService(repository=repo),
        feedback=FeedbackService(repository=repo),
        audit=AuditLogService(repository=repo),
        history=ConversationHistoryService(repository=repo),
        analytics=AnalyticsService(repository=repo),
    )


def get_operational_runtime(request: Any) -> Optional[OperationalRuntime]:
    return getattr(getattr(request, "app", None).state, "operational_runtime", None)


def safe_session_metadata(client_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    context = dict(client_context or {})
    channel = context.get("channel") if context.get("channel") in SAFE_CHANNELS else "web_widget"
    return {
        "actor_tag": "anonymous",
        "locale": context.get("locale") or "vi-VN",
        "timezone": context.get("timezone") or "Asia/Bangkok",
        "client": {"channel": channel},
        "session_context": {
            "actor_tag": "anonymous",
            "locale": context.get("locale") or "vi-VN",
            "timezone": context.get("timezone") or "Asia/Bangkok",
            "metadata": {},
        },
    }


def ensure_persistent_session(runtime: OperationalRuntime, session_id: str, client_context: Optional[Dict[str, Any]] = None) -> None:
    if runtime.repository.get_session_context(session_id):
        return
    metadata = safe_session_metadata(client_context)
    runtime.repository.create_session(session_id, metadata["client"]["channel"], metadata)


def append_user_turn(runtime: Optional[OperationalRuntime], session_id: str, message: str, *, client_context: Optional[Dict[str, Any]] = None, intent: Optional[str] = None, critical: bool = False) -> bool:
    if runtime is None:
        return False
    try:
        ensure_persistent_session(runtime, session_id, client_context)
        runtime.conversations.append_entry(session_id, "user", message or "[empty]", intent=intent)
        return True
    except Exception:
        logger.warning("operational conversation user turn write failed", exc_info=False)
        if critical:
            raise
        return False


def _response_text(result: Dict[str, Any]) -> str:
    for key in ("answer", "message", "banner", "status_message", "next_step"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return result.get("outcome") or "capability response"


def append_assistant_turn(runtime: Optional[OperationalRuntime], session_id: str, capability: str, envelope: Dict[str, Any], *, tools: Optional[list] = None, emergency: bool = False, critical: bool = False) -> bool:
    if runtime is None:
        return False
    try:
        result = dict(envelope.get("result") or {})
        citations = result.get("citations") or (result.get("explainability") or {}).get("citations") or []
        tool_calls = tools if tools is not None else result.get("tool_calls") or result.get("tools") or []
        runtime.conversations.append_entry(
            session_id,
            "assistant",
            _response_text(result),
            intent=capability,
            tool_calls=tool_calls,
            citations=citations,
            emergency_triggered=emergency,
        )
        return True
    except Exception:
        logger.warning("operational conversation assistant turn write failed", exc_info=False)
        if critical:
            raise
        return False


def write_audit(runtime: Optional[OperationalRuntime], event_type: str, session_id: str, action: str, resource: str, *, details: Optional[Dict[str, Any]] = None, outcome: str = "success", critical: bool = False) -> bool:
    if runtime is None:
        if critical:
            raise RuntimeError("operational audit unavailable")
        return False
    try:
        runtime.audit.write_entry(event_type, "anonymous", action, resource, details=details or {}, session_id=session_id, outcome=outcome)
        return True
    except Exception:
        logger.warning("operational audit write failed", exc_info=False)
        if critical:
            raise
        return False

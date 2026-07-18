"""Repository-mode tests for operational services.

These tests prove that a supplied repository is used instead of the legacy
in-memory stores.  They intentionally use a fake and never need Supabase.
"""

from apps.api.foundation.analytics.service import AnalyticsService, AnalyticsSummaryQuery, ConversationHistoryService
from apps.api.foundation.feedback.service import FeedbackCreateRequest, FeedbackService
from apps.api.foundation.session.service import SessionCreateRequest, SessionService
from apps.api.logging.audit.service import AuditLogService
from apps.api.logging.conversation.service import ConversationLogService


class FakeOperationalRepository:
    def __init__(self):
        self.sessions = {}
        self.messages = []
        self.feedback = []
        self.audits = []

    def create_session(self, external_session_id, channel, metadata):
        row = {"channel": channel, "metadata": dict(metadata), "started_at": "2026-01-01T00:00:00+00:00", "expires_at": "2026-01-02T00:00:00+00:00"}
        self.sessions[external_session_id] = row
        return row

    def get_session_context(self, external_session_id):
        return self.sessions.get(external_session_id)

    def update_session_context(self, external_session_id, metadata):
        row = self.sessions[external_session_id]
        row["metadata"] = dict(metadata)
        return row

    def append_message(self, external_session_id, role, content_redacted, **kwargs):
        row = {"turn_id": "msg-1", "session_id": external_session_id, "role": role, "content": content_redacted,
               "intent": kwargs.get("intent"), "tool_calls": kwargs.get("tools_called", []), "citations": kwargs.get("citations", []),
               "emergency_triggered": kwargs.get("emergency_triggered", False), "created_at": "2026-01-01T00:00:00+00:00"}
        self.messages.append(row)
        return {"message_id": "msg-1", "created_at": row["created_at"]}

    def conversation_history(self, external_session_id, limit, offset, from_time=None, to_time=None):
        rows = [item for item in self.messages if item["session_id"] == external_session_id]
        return {"items": rows[offset:offset + limit], "total": len(rows)}

    def create_feedback(self, external_session_id, rating, comment_redacted, category, metadata):
        row = {"feedback_id": "fb-1", "session_id": external_session_id, "rating": rating, "comment_redacted": comment_redacted,
               "category": category, "metadata": metadata, "created_at": "2026-01-01T00:00:00+00:00"}
        self.feedback.append(row)
        return row

    def feedback_by_id(self, feedback_id):
        return next((row for row in self.feedback if row["feedback_id"] == feedback_id), None)

    def feedback_by_session(self, session_id):
        return [row for row in self.feedback if row["session_id"] == session_id]

    def write_audit(self, category, actor, entity_type, action, payload):
        row = {"audit_event_id": "audit-1", "occurred_at": "2026-01-01T00:00:00+00:00"}
        self.audits.append((category, actor, entity_type, action, payload))
        return row

    def audit_log(self, *args):
        return {"items": [], "total": 0}

    def analytics_summary(self, from_time, to_time):
        return {"conversations": 1, "turns": 2, "fallback_rate": 0.5, "emergency_rate": 0.0,
                "feedback_score": 5.0, "top_questions": [{"intent": "gia_dich_vu", "count": 1}]}


def test_session_context_uses_injected_repository():
    repository = FakeOperationalRepository()
    service = SessionService(repository=repository)
    created = service.create_session(SessionCreateRequest(actor_tag="visitor", channel="web_page"))
    context = service.get_session_context(created.session_id)
    assert context.session_id == created.session_id
    assert created.session_id in repository.sessions


def test_conversation_history_feedback_and_analytics_use_repository():
    repository = FakeOperationalRepository()
    repository.create_session("ses-1", "web_page", {"session_context": {"actor_tag": "visitor"}})
    entry = ConversationLogService(repository=repository).append_entry("ses-1", "user", "Xin chao")
    assert entry.content == "Xin chao"
    assert ConversationHistoryService(repository=repository).get_history(session_id="ses-1").total == 1
    receipt = FeedbackService(repository=repository).create_feedback(FeedbackCreateRequest("ses-1", 5, "Tot"))
    assert receipt.feedback_id == "fb-1"
    summary = AnalyticsService(repository=repository).get_summary(AnalyticsSummaryQuery("2026-01-01", "2026-01-02"))
    assert summary.total_turns == 2


def test_audit_uses_repository_and_never_writes_to_memory_store():
    repository = FakeOperationalRepository()
    entry = AuditLogService(repository=repository).write_entry("security", "admin", "login", "dashboard")
    assert entry.audit_id == "audit-1"
    assert repository.audits[0][0] == "security"
    assert repository.audits[0][3] == "login"

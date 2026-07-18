# === TASK:WP-605:START ===
"""WP-605 admin dashboard QA integration tests.

These tests validate the admin content workflow/conflict and analytics/audit
contracts with in-memory fakes only. They do not call providers or networks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from apps.api.foundation.analytics.service import (
    AnalyticsService,
    AnalyticsSummaryQuery,
    ConversationHistoryItem,
    ConversationHistoryQuery,
    ConversationHistoryService,
    _InMemoryAnalyticsStore,
    _InMemoryConversationHistoryStore,
)
from apps.api.foundation.knowledge.content.service import (
    ContentConflictResolveRequest,
    ContentManagementService,
    ContentPublishRequest,
    ContentReviewRequest,
)


@dataclass
class FakeContentAdminRepository:
    """In-memory content workflow/conflict fake for the admin dashboard."""

    drafts: dict[str, dict[str, Any]] = field(default_factory=dict)
    conflicts: dict[str, dict[str, Any]] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)

    def draft_repo(self, action: str, *args: Any, **_: Any) -> dict[str, Any] | None:
        if action == "get":
            return self.drafts.get(args[0])
        if action == "submit":
            draft_id, author = args
            draft = self.drafts[draft_id]
            draft.update(status="submitted", author=author, updated_at=_iso_now())
            self.audit_events.append({"action": "submit", "resource": draft_id, "actor": author})
            return draft
        if action == "review":
            draft_id, reviewer, approved, reason = args
            draft = self.drafts[draft_id]
            draft.update(
                status="approved" if approved else "rejected",
                reviewer=reviewer,
                rejection_reason=reason,
                updated_at=_iso_now(),
            )
            self.audit_events.append({"action": "approve" if approved else "reject", "resource": draft_id, "actor": reviewer})
            return draft
        if action == "publish":
            draft_id, publisher = args
            draft = self.drafts[draft_id]
            draft.update(status="published", updated_at=_iso_now())
            self.audit_events.append({"action": "publish", "resource": draft_id, "actor": publisher})
            return {"chunk_id": "chunk-wp-605", "version": draft["version"], "published_at": _iso_now(), "publisher": publisher}
        raise AssertionError(f"unexpected draft action: {action}")

    def conflict_repo(self, action: str, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        if action == "list":
            state_filter = kwargs.get("state_filter")
            conflicts = list(self.conflicts.values())
            if state_filter:
                conflicts = [conflict for conflict in conflicts if conflict["state"] == state_filter]
            return {"conflicts": conflicts, "total": len(conflicts)}
        if action == "get":
            return self.conflicts.get(args[0])
        if action == "resolve":
            conflict_id, resolution, notes, resolved_by = args
            conflict = self.conflicts[conflict_id]
            conflict.update(state=resolution, resolution_notes=notes, resolved_by=resolved_by, updated_at=_iso_now())
            self.audit_events.append({"action": "resolve_conflict", "resource": conflict_id, "actor": resolved_by})
            return conflict
        raise AssertionError(f"unexpected conflict action: {action}")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_admin_repo() -> FakeContentAdminRepository:
    now = datetime.now(timezone.utc)
    repo = FakeContentAdminRepository()
    repo.drafts["draft-wp-605"] = {
        "draft_id": "draft-wp-605",
        "content": "Quy trình khám BHYT đã rà soát.",
        "domain": "bhyt",
        "sub_topic": "quy_trinh_kham",
        "source_id": "source-wp-605",
        "source_section": "BHYT",
        "source_page": "1",
        "version": "1.0.0",
        "status": "submitted",
        "tags": ["bhyt"],
        "author": "content_admin_demo",
        "reviewer": "",
        "rejection_reason": "",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    repo.conflicts["conflict-wp-605"] = {
        "conflict_id": "conflict-wp-605",
        "source_chunk_ids": ["chunk-old", "chunk-new"],
        "conflicting_fields": ["price", "effective_date"],
        "description": "Bảng giá dịch vụ có thông tin mâu thuẫn.",
        "state": "open",
        "due_date": (now + timedelta(hours=24)).isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "resolution_notes": "",
        "resolved_by": "",
    }
    return repo


def test_admin_dashboard_surfaces_conflict_with_24_hour_due_date_and_audit_resolution() -> None:
    repo = _seed_admin_repo()
    service = ContentManagementService(draft_repo=repo.draft_repo, conflict_repo=repo.conflict_repo)

    page = service.list_conflicts(page=1, page_size=20, state_filter="open")
    conflict = page.conflicts[0]
    created_at = datetime.fromisoformat(conflict.created_at)
    due_date = datetime.fromisoformat(conflict.due_date)

    assert page.total == 1
    assert conflict.conflict_id == "conflict-wp-605"
    assert conflict.state == "open"
    assert conflict.conflicting_fields == ["price", "effective_date"]
    assert due_date - created_at == timedelta(hours=24)

    resolved = service.resolve_conflict(
        ContentConflictResolveRequest(
            conflict_id="conflict-wp-605",
            resolution="resolved",
            notes="Đã đối chiếu nguồn bảng giá mới.",
            resolved_by="domain_owner_demo",
        )
    )

    assert resolved.state == "resolved"
    assert resolved.resolution_notes == "Đã đối chiếu nguồn bảng giá mới."
    assert {"action": "resolve_conflict", "resource": "conflict-wp-605", "actor": "domain_owner_demo"} in repo.audit_events


def test_full_access_demo_role_can_approve_and_publish_without_contract_redesign() -> None:
    repo = _seed_admin_repo()
    service = ContentManagementService(draft_repo=repo.draft_repo, conflict_repo=repo.conflict_repo)

    approval = service.review_draft(
        request=ContentReviewRequest(
            draft_id="draft-wp-605",
            reviewer="full_access_demo",
            approved=True,
        )
    )
    version = service.publish_draft(
        request=ContentPublishRequest(
            draft_id="draft-wp-605",
            publisher="full_access_demo",
        )
    )

    assert approval.status == "approved"
    assert version.chunk_id == "chunk-wp-605"
    assert version.publisher == "full_access_demo"
    assert {"action": "approve", "resource": "draft-wp-605", "actor": "full_access_demo"} in repo.audit_events
    assert {"action": "publish", "resource": "draft-wp-605", "actor": "full_access_demo"} in repo.audit_events


def test_analytics_filters_by_time_range_and_returns_no_pii() -> None:
    store = _InMemoryAnalyticsStore()
    service = AnalyticsService(store=store)
    now = datetime.now(timezone.utc)
    in_range = now.isoformat()
    out_of_range = (now - timedelta(days=2)).isoformat()

    service.record_conversation_log(ConversationHistoryItem("session-safe", "turn-1", "user", "[REDACTED] hỏi BHYT", "information_assistance", True, True, False, created_at=in_range))
    service.record_conversation_log(ConversationHistoryItem("session-safe", "turn-2", "assistant", "Thông tin BHYT tổng hợp", "information_assistance", False, False, False, created_at=in_range))
    service.record_conversation_log(ConversationHistoryItem("session-old", "turn-3", "user", "[REDACTED]", "appointment_booking", True, True, False, created_at=out_of_range))

    summary = service.get_summary(AnalyticsSummaryQuery(from_time=(now - timedelta(hours=1)).isoformat(), to_time=(now + timedelta(hours=1)).isoformat()))
    serialized = summary.to_dict()

    assert summary.total_conversations == 1
    assert summary.total_turns == 2
    assert summary.top_questions == [{"intent": "information_assistance", "count": 1}]
    assert "0901234567" not in repr(serialized)
    assert "patient@example.com" not in repr(serialized)


def test_conversation_history_filter_keeps_anonymized_rows_only() -> None:
    store = _InMemoryConversationHistoryStore()
    service = ConversationHistoryService(store=store)
    now = datetime.now(timezone.utc).isoformat()
    service.append_entry(ConversationHistoryItem("session-wp-605", "turn-1", "user", "[REDACTED] cần hỗ trợ", "appointment_status", True, True, False, created_at=now))
    service.append_entry(ConversationHistoryItem("session-other", "turn-2", "user", "[REDACTED]", "bhyt", True, True, False, created_at=now))

    page = service.get_history(ConversationHistoryQuery(session_id="session-wp-605", limit=20, offset=0))
    body = page.to_dict()

    assert page.total == 1
    assert body["items"][0]["content"] == "[REDACTED] cần hỗ trợ"
    assert body["items"][0]["pii_redacted"] is True
    assert "0901234567" not in repr(body)
# === TASK:WP-605:END ===

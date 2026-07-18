# === TASK:WP-102:START ===
"""Integration test for WP-102 — Knowledge repository and content management services.

Validates
---------
* KnowledgeRepositoryService — search and get_chunk with fake providers
* ContentManagementService — draft lifecycle (create, patch, submit, review, publish)
* ContentManagementService — conflict lifecycle (list, resolve)
* Input validation and edge cases
* State-machine guards (wrong status transitions rejected)
* All provider/network calls use fakes — no live DB or embedding API needed
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


# ---------------------------------------------------------------------------
# Fake providers for KnowledgeRepositoryService
# ---------------------------------------------------------------------------


def _fake_embedding(text: str) -> List[float]:
    """Deterministic fake embedding: returns a 1024-D vector based on text length."""
    return [float(hash(text) % 1000) / 1000.0 for _ in range(1024)]


FAKE_CHUNK_ROWS = [
    {
        "chunk_id": "KCH-BHYT-001",
        "content": "BHYT coverage includes inpatient and outpatient services.",
        "domain": "bhyt",
        "sub_topic": "coverage",
        "source_id": "SRC-BHYT-001",
        "source_section": "coverage-scope",
        "source_page": "5",
        "version": "1.0",
        "is_active": True,
        "approval_status": "approved_for_pilot",
        "effective_date": "2026-01-01",
        "tags": ["bhyt", "coverage"],
        "is_mock": False,
        "answerable": True,
        "source_path": "docs/knowledge/bhyt/coverage.md",
    },
    {
        "chunk_id": "KCH-BHYT-002",
        "content": "BHYT card holders must present their card at registration.",
        "domain": "bhyt",
        "sub_topic": "registration",
        "source_id": "SRC-BHYT-001",
        "source_section": "registration-procedure",
        "source_page": "8",
        "version": "1.0",
        "is_active": True,
        "approval_status": "approved_for_pilot",
        "effective_date": "2026-01-01",
        "tags": ["bhyt", "registration"],
        "is_mock": False,
        "answerable": True,
        "source_path": "docs/knowledge/bhyt/coverage.md",
    },
    {
        "chunk_id": "KCH-PRICE-001",
        "content": "Hospital price list is published online.",
        "domain": "price",
        "sub_topic": "publication",
        "source_id": "SRC-PRICE-001",
        "source_section": "overview",
        "source_page": "1",
        "version": "1.0",
        "is_active": True,
        "approval_status": "approved_for_pilot",
        "effective_date": "2026-01-01",
        "tags": ["price"],
        "is_mock": False,
        "answerable": True,
        "source_path": "docs/knowledge/price/list.md",
    },
]


class FakeChunkRepository:
    """Fake chunk repository that returns predetermined results."""

    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None) -> None:
        self._rows = rows if rows is not None else FAKE_CHUNK_ROWS
        self.last_call: Optional[Dict[str, Any]] = None

    def __call__(
        self,
        *,
        embedding: List[float],
        domain_filter: Optional[str] = None,
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        self.last_call = {
            "embedding_len": len(embedding),
            "domain_filter": domain_filter,
            "top_k": top_k,
            "threshold": threshold,
        }
        results = list(self._rows)
        if domain_filter:
            results = [r for r in results if r["domain"] == domain_filter]
        return results[:top_k]


class FakeChunkByIdRepository:
    """Fake repository for single-chunk retrieval."""

    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None) -> None:
        self._by_id = {r["chunk_id"]: r for r in (rows if rows is not None else FAKE_CHUNK_ROWS)}

    def __call__(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        return self._by_id.get(chunk_id)


class FakeConflictCheck:
    """Fake conflict checker."""

    def __init__(self, conflicted_ids: Optional[List[str]] = None) -> None:
        self._conflicted = set(conflicted_ids or [])
        self.last_call_ids: Optional[List[str]] = None

    def __call__(self, chunk_ids: List[str]) -> List[str]:
        self.last_call_ids = list(chunk_ids)
        return [cid for cid in chunk_ids if cid in self._conflicted]


# ---------------------------------------------------------------------------
# Fake repositories for ContentManagementService
# ---------------------------------------------------------------------------


class FakeDraftRepository:
    """Fake draft repository that stores drafts in memory."""

    def __init__(self) -> None:
        self._drafts: Dict[str, Dict[str, Any]] = {}
        self._next_id = 1000
        self.operations: List[str] = []

    def __call__(self, action: str, *args: Any, **kwargs: Any) -> Any:
        self.operations.append(action)
        if action == "create":
            data = args[0]
            draft_id = f"DRF-{self._next_id}"
            self._next_id += 1
            draft = dict(data)
            draft["draft_id"] = draft_id
            draft["version"] = "0.1"
            self._drafts[draft_id] = draft
            return draft
        elif action == "get":
            draft_id = args[0]
            return self._drafts.get(draft_id)
        elif action == "patch":
            draft_id, updates = args
            if draft_id in self._drafts:
                self._drafts[draft_id].update(updates)
            return self._drafts.get(draft_id, {})
        elif action == "submit":
            draft_id, author = args
            if draft_id in self._drafts:
                self._drafts[draft_id]["status"] = "submitted"
                self._drafts[draft_id]["updated_at"] = _now_iso()
            return self._drafts.get(draft_id, {})
        elif action == "review":
            draft_id, reviewer, approved, reason = args
            if draft_id in self._drafts:
                self._drafts[draft_id]["reviewer"] = reviewer
                self._drafts[draft_id]["rejection_reason"] = reason
                self._drafts[draft_id]["status"] = "approved" if approved else "rejected"
                self._drafts[draft_id]["updated_at"] = _now_iso()
            return self._drafts.get(draft_id, {})
        elif action == "publish":
            draft_id, publisher = args
            if draft_id in self._drafts:
                draft = self._drafts[draft_id]
                draft["status"] = "published"
                draft["updated_at"] = _now_iso()
                # Simulate publishing: return version info
                return {
                    "chunk_id": f"KCH-{draft_id}",
                    "version": "1.0",
                    "published_at": _now_iso(),
                    "publisher": publisher,
                }
            return {}
        return {}


class FakeConflictRepository:
    """Fake conflict repository that stores conflicts in memory."""

    def __init__(self) -> None:
        self._conflicts: Dict[str, Dict[str, Any]] = {}
        self._next_id = 500
        self.operations: List[str] = []

    def add_conflict(
        self,
        chunk_ids: List[str],
        fields: List[str],
        description: str = "Test conflict",
    ) -> str:
        cid = f"CONF-{self._next_id}"
        self._next_id += 1
        now = _now_iso()
        self._conflicts[cid] = {
            "conflict_id": cid,
            "source_chunk_ids": list(chunk_ids),
            "conflicting_fields": list(fields),
            "description": description,
            "state": "open",
            "due_date": "2026-07-19T10:00:00+00:00",
            "created_at": now,
            "updated_at": now,
            "resolution_notes": "",
            "resolved_by": "",
        }
        return cid

    def __call__(self, action: str, *args: Any, **kwargs: Any) -> Any:
        self.operations.append(action)
        if action == "list":
            page = kwargs.get("page", 1)
            page_size = kwargs.get("page_size", 20)
            state_filter = kwargs.get("state_filter")
            items = list(self._conflicts.values())
            if state_filter:
                items = [c for c in items if c["state"] == state_filter]
            total = len(items)
            start = (page - 1) * page_size
            end = start + page_size
            return {"conflicts": items[start:end], "total": total}
        elif action == "get":
            conflict_id = args[0]
            return self._conflicts.get(conflict_id)
        elif action == "resolve":
            conflict_id, resolution, notes, resolved_by = args
            if conflict_id in self._conflicts:
                self._conflicts[conflict_id]["state"] = resolution
                self._conflicts[conflict_id]["resolution_notes"] = notes
                self._conflicts[conflict_id]["resolved_by"] = resolved_by
                self._conflicts[conflict_id]["updated_at"] = _now_iso()
            return self._conflicts.get(conflict_id, {})
        return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def repo_service():
    """Fixture: KnowledgeRepositoryService with all fakes."""
    from foundation.knowledge.repository.service import KnowledgeRepositoryService

    chunk_repo = FakeChunkRepository()
    chunk_by_id = FakeChunkByIdRepository()
    conflict_check = FakeConflictCheck()
    return (
        KnowledgeRepositoryService(
            embed_provider=_fake_embedding,
            chunk_repo=chunk_repo,
            chunk_by_id_repo=chunk_by_id,
            conflict_check=conflict_check,
        ),
        chunk_repo,
        chunk_by_id,
        conflict_check,
    )


@pytest.fixture
def content_service():
    """Fixture: ContentManagementService with fake repositories."""
    from foundation.knowledge.content.service import ContentManagementService

    draft_repo = FakeDraftRepository()
    conflict_repo = FakeConflictRepository()
    svc = ContentManagementService(draft_repo=draft_repo, conflict_repo=conflict_repo)
    return svc, draft_repo, conflict_repo


# ===================================================================
# TestKnowledgeRepositoryService
# ===================================================================


class TestKnowledgeRepositoryService:
    """Tests for FND-KNW-01 SearchKnowledge and FND-KNW-02 GetKnowledgeChunk."""

    # ------------------------------------------------------------------
    # FND-KNW-01 SearchKnowledge
    # ------------------------------------------------------------------

    def test_search_returns_chunks(self, repo_service):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        svc, chunk_repo, _, _ = repo_service
        request = KnowledgeSearchRequest(query="BHYT coverage")
        response = svc.search(request)

        assert len(response.chunks) > 0
        assert response.result_sufficient is True
        assert all(isinstance(c.chunk_id, str) for c in response.chunks)

    def test_search_respects_domain_filter(self, repo_service):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        svc, chunk_repo, _, _ = repo_service
        request = KnowledgeSearchRequest(query="price", domain_filter="price")
        response = svc.search(request)

        assert len(response.chunks) > 0
        for c in response.chunks:
            assert c.domain == "price"

    def test_search_respects_top_k(self, repo_service):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        svc, chunk_repo, _, _ = repo_service
        request = KnowledgeSearchRequest(query="test", top_k=2)
        response = svc.search(request)

        assert len(response.chunks) <= 2

    def test_search_passes_correct_embedding_dimension(self, repo_service):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        svc, chunk_repo, _, _ = repo_service
        request = KnowledgeSearchRequest(query="BHYT coverage")
        svc.search(request)

        assert chunk_repo.last_call is not None
        assert chunk_repo.last_call["embedding_len"] == 1024

    def test_search_no_results_returns_empty(self, repo_service):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        empty_repo = FakeChunkRepository(rows=[])
        empty_by_id = FakeChunkByIdRepository(rows=[])
        from foundation.knowledge.repository.service import KnowledgeRepositoryService

        svc = KnowledgeRepositoryService(
            embed_provider=_fake_embedding,
            chunk_repo=empty_repo,
            chunk_by_id_repo=empty_by_id,
            conflict_check=FakeConflictCheck(),
        )
        request = KnowledgeSearchRequest(query="nothing")
        response = svc.search(request)

        assert len(response.chunks) == 0
        assert response.result_sufficient is False

    def test_search_conflict_flag_set_when_conflicts_exist(self, repo_service):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        svc, chunk_repo, _, conflict_check = repo_service
        # Make all chunks conflicted
        conflict_check._conflicted = {"KCH-BHYT-001", "KCH-BHYT-002", "KCH-PRICE-001"}
        request = KnowledgeSearchRequest(query="test")
        response = svc.search(request)

        assert response.conflict_flag is True

    def test_search_conflict_flag_false_when_no_conflicts(self, repo_service):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        svc, _, _, _ = repo_service
        request = KnowledgeSearchRequest(query="test")
        response = svc.search(request)

        assert response.conflict_flag is False

    def test_search_request_validation_empty_query(self, repo_service):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        with pytest.raises(ValueError, match="query must be non-empty"):
            KnowledgeSearchRequest(query="")

    def test_search_request_validation_top_k_out_of_range(self, repo_service):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        with pytest.raises(ValueError, match="top_k must be between 1 and 20"):
            KnowledgeSearchRequest(query="test", top_k=0)

        with pytest.raises(ValueError, match="top_k must be between 1 and 20"):
            KnowledgeSearchRequest(query="test", top_k=21)

    def test_search_request_validation_threshold_out_of_range(self, repo_service):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        with pytest.raises(ValueError, match="threshold must be between 0 and 1"):
            KnowledgeSearchRequest(query="test", threshold=-0.1)

        with pytest.raises(ValueError, match="threshold must be between 0 and 1"):
            KnowledgeSearchRequest(query="test", threshold=1.1)

    # ------------------------------------------------------------------
    # FND-KNW-02 GetKnowledgeChunk
    # ------------------------------------------------------------------

    def test_get_chunk_returns_chunk(self, repo_service):
        svc, _, _, _ = repo_service
        chunk = svc.get_chunk("KCH-BHYT-001")

        assert chunk is not None
        assert chunk.chunk_id == "KCH-BHYT-001"
        assert chunk.content == "BHYT coverage includes inpatient and outpatient services."
        assert chunk.domain == "bhyt"

    def test_get_chunk_returns_none_for_unknown(self, repo_service):
        svc, _, _, _ = repo_service
        chunk = svc.get_chunk("NONEXISTENT")
        assert chunk is None

    def test_get_chunk_validation_empty_id(self, repo_service):
        svc, _, _, _ = repo_service
        with pytest.raises(ValueError, match="chunk_id must be non-empty"):
            svc.get_chunk("")

    def test_get_chunk_to_dict_has_all_fields(self, repo_service):
        svc, _, _, _ = repo_service
        chunk = svc.get_chunk("KCH-BHYT-001")
        assert chunk is not None
        d = chunk.to_dict()
        for key in (
            "chunk_id", "content", "domain", "sub_topic", "source_id",
            "source_section", "source_page", "version", "is_active",
            "approval_status", "effective_date", "tags",
        ):
            assert key in d, f"Missing key: {key}"

    def test_search_response_to_dict(self, repo_service):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        svc, _, _, _ = repo_service
        request = KnowledgeSearchRequest(query="BHYT")
        response = svc.search(request)
        d = response.to_dict()
        assert "chunks" in d
        assert "result_sufficient" in d
        assert "conflict_flag" in d
        assert "metadata" in d


# ===================================================================
# TestContentManagementService — Draft Lifecycle (FND-KNW-03)
# ===================================================================


class TestContentManagementServiceDrafts:
    """Tests for FND-KNW-03 CreateContentDraft: create, patch, submit, review, publish."""

    def test_create_draft(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
        )

        svc, draft_repo, _ = content_service
        request = ContentDraftCreateRequest(
            content="Test draft content",
            domain="bhyt",
            sub_topic="coverage",
            source_id="SRC-BHYT-001",
        )
        draft = svc.create_draft(request)
        assert draft.draft_id.startswith("DRF-")
        assert draft.status == "draft"
        assert draft.content == "Test draft content"
        assert draft.domain == "bhyt"

    def test_create_draft_validates_content(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
        )

        svc, _, _ = content_service
        with pytest.raises(ValueError, match="content must be non-empty"):
            svc.create_draft(ContentDraftCreateRequest(
                content="", domain="bhyt", sub_topic="t", source_id="S",
            ))

    def test_create_draft_validates_domain(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
        )

        svc, _, _ = content_service
        with pytest.raises(ValueError, match="domain must be non-empty"):
            svc.create_draft(ContentDraftCreateRequest(
                content="x", domain="", sub_topic="t", source_id="S",
            ))

    def test_create_draft_validates_source_id(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
        )

        svc, _, _ = content_service
        with pytest.raises(ValueError, match="source_id must be non-empty"):
            svc.create_draft(ContentDraftCreateRequest(
                content="x", domain="bhyt", sub_topic="t", source_id="",
            ))

    def test_patch_draft(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
            ContentDraftPatchRequest,
        )

        svc, _, _ = content_service
        draft = svc.create_draft(ContentDraftCreateRequest(
            content="Original", domain="bhyt", sub_topic="t", source_id="S",
        ))
        patched = svc.patch_draft(ContentDraftPatchRequest(
            draft_id=draft.draft_id, content="Updated content",
        ))
        assert patched.content == "Updated content"
        assert patched.draft_id == draft.draft_id

    def test_patch_draft_fails_if_not_found(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftPatchRequest,
        )

        svc, _, _ = content_service
        with pytest.raises(ValueError, match="draft not found"):
            svc.patch_draft(ContentDraftPatchRequest(
                draft_id="NONEXISTENT", content="x",
            ))

    def test_patch_draft_fails_if_not_draft_status(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
            ContentDraftPatchRequest,
            ContentSubmitRequest,
        )

        svc, _, _ = content_service
        draft = svc.create_draft(ContentDraftCreateRequest(
            content="x", domain="bhyt", sub_topic="t", source_id="S",
        ))
        svc.submit_draft(ContentSubmitRequest(draft_id=draft.draft_id))
        with pytest.raises(ValueError, match="cannot patch draft in status"):
            svc.patch_draft(ContentDraftPatchRequest(
                draft_id=draft.draft_id, content="y",
            ))

    def test_submit_draft(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
            ContentSubmitRequest,
        )

        svc, _, _ = content_service
        draft = svc.create_draft(ContentDraftCreateRequest(
            content="x", domain="bhyt", sub_topic="t", source_id="S",
        ))
        submitted = svc.submit_draft(ContentSubmitRequest(draft_id=draft.draft_id))
        assert submitted.status == "submitted"

    def test_submit_draft_fails_if_not_draft(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
            ContentSubmitRequest,
        )

        svc, _, _ = content_service
        with pytest.raises(ValueError, match="draft not found"):
            svc.submit_draft(ContentSubmitRequest(draft_id="NONEXISTENT"))

    def test_review_approve_draft(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
            ContentReviewRequest,
            ContentSubmitRequest,
        )

        svc, _, _ = content_service
        draft = svc.create_draft(ContentDraftCreateRequest(
            content="x", domain="bhyt", sub_topic="t", source_id="S",
        ))
        svc.submit_draft(ContentSubmitRequest(draft_id=draft.draft_id))
        result = svc.review_draft(ContentReviewRequest(
            draft_id=draft.draft_id, reviewer="reviewer1", approved=True,
        ))
        assert result.status == "approved"
        assert result.reviewer == "reviewer1"

    def test_review_reject_draft(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
            ContentReviewRequest,
            ContentSubmitRequest,
        )

        svc, _, _ = content_service
        draft = svc.create_draft(ContentDraftCreateRequest(
            content="x", domain="bhyt", sub_topic="t", source_id="S",
        ))
        svc.submit_draft(ContentSubmitRequest(draft_id=draft.draft_id))
        result = svc.review_draft(ContentReviewRequest(
            draft_id=draft.draft_id, reviewer="reviewer1",
            approved=False, rejection_reason="Incomplete",
        ))
        assert result.status == "rejected"
        assert result.rejection_reason == "Incomplete"

    def test_review_fails_on_wrong_status(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
            ContentReviewRequest,
        )

        svc, _, _ = content_service
        draft = svc.create_draft(ContentDraftCreateRequest(
            content="x", domain="bhyt", sub_topic="t", source_id="S",
        ))
        # Cannot review a draft that is still in "draft" status
        with pytest.raises(ValueError, match="cannot review draft in status"):
            svc.review_draft(ContentReviewRequest(
                draft_id=draft.draft_id, reviewer="r", approved=True,
            ))

    def test_publish_approved_draft(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
            ContentPublishRequest,
            ContentReviewRequest,
            ContentSubmitRequest,
        )

        svc, _, _ = content_service
        draft = svc.create_draft(ContentDraftCreateRequest(
            content="x", domain="bhyt", sub_topic="t", source_id="S",
        ))
        svc.submit_draft(ContentSubmitRequest(draft_id=draft.draft_id))
        svc.review_draft(ContentReviewRequest(
            draft_id=draft.draft_id, reviewer="r", approved=True,
        ))
        version = svc.publish_draft(ContentPublishRequest(
            draft_id=draft.draft_id, publisher="pub1",
        ))
        assert version.chunk_id.startswith("KCH-")
        assert version.version == "1.0"
        assert version.publisher == "pub1"

    def test_publish_fails_if_not_approved(self, content_service):
        from foundation.knowledge.content.service import (
            ContentDraftCreateRequest,
            ContentPublishRequest,
        )

        svc, _, _ = content_service
        draft = svc.create_draft(ContentDraftCreateRequest(
            content="x", domain="bhyt", sub_topic="t", source_id="S",
        ))
        with pytest.raises(ValueError, match="cannot publish draft in status"):
            svc.publish_draft(ContentPublishRequest(draft_id=draft.draft_id))

    def test_publish_fails_if_draft_not_found(self, content_service):
        from foundation.knowledge.content.service import ContentPublishRequest

        svc, _, _ = content_service
        with pytest.raises(ValueError, match="draft not found"):
            svc.publish_draft(ContentPublishRequest(draft_id="NONEXISTENT"))


# ===================================================================
# TestContentManagementService — Conflicts (FND-KNW-08, FND-KNW-09)
# ===================================================================


class TestContentManagementServiceConflicts:
    """Tests for FND-KNW-08 ListContentConflicts and FND-KNW-09 ResolveContentConflict."""

    def test_list_conflicts_empty(self, content_service):
        svc, _, _ = content_service
        page = svc.list_conflicts()
        assert page.total == 0
        assert len(page.conflicts) == 0

    def test_list_conflicts_with_data(self, content_service):
        svc, draft_repo, conflict_repo = content_service
        # Pre-seed a conflict
        conflict_repo.add_conflict(
            chunk_ids=["KCH-BHYT-001", "KCH-BHYT-002"],
            fields=["content"],
            description="Duplicate content",
        )
        page = svc.list_conflicts()
        assert page.total == 1
        assert len(page.conflicts) == 1
        assert page.conflicts[0].state == "open"
        assert "KCH-BHYT-001" in page.conflicts[0].source_chunk_ids

    def test_list_conflicts_with_state_filter(self, content_service):
        svc, _, conflict_repo = content_service
        conflict_repo.add_conflict(
            chunk_ids=["KCH-001"], fields=["content"],
        )
        conflict_repo.add_conflict(
            chunk_ids=["KCH-002"], fields=["title"],
        )
        # Resolve one
        cid = list(conflict_repo._conflicts.keys())[0]
        conflict_repo("resolve", cid, "resolved", "Fixed", "admin")
        page = svc.list_conflicts(state_filter="resolved")
        assert page.total == 1
        assert page.conflicts[0].state == "resolved"

    def test_list_conflicts_pagination(self, content_service):
        svc, _, conflict_repo = content_service
        for i in range(5):
            conflict_repo.add_conflict(
                chunk_ids=[f"KCH-{i:03d}"], fields=["content"],
            )
        page1 = svc.list_conflicts(page=1, page_size=2)
        assert len(page1.conflicts) == 2
        assert page1.total == 5
        page2 = svc.list_conflicts(page=2, page_size=2)
        assert len(page2.conflicts) == 2
        page3 = svc.list_conflicts(page=3, page_size=2)
        assert len(page3.conflicts) == 1

    def test_list_conflicts_validates_page(self, content_service):
        svc, _, _ = content_service
        with pytest.raises(ValueError, match="page must be >= 1"):
            svc.list_conflicts(page=0)

    def test_list_conflicts_validates_page_size(self, content_service):
        svc, _, _ = content_service
        with pytest.raises(ValueError, match="page_size must be between 1 and 100"):
            svc.list_conflicts(page_size=0)
        with pytest.raises(ValueError, match="page_size must be between 1 and 100"):
            svc.list_conflicts(page_size=101)

    def test_resolve_conflict(self, content_service):
        from foundation.knowledge.content.service import (
            ContentConflictResolveRequest,
        )

        svc, _, conflict_repo = content_service
        cid = conflict_repo.add_conflict(
            chunk_ids=["KCH-001"], fields=["content"],
        )
        result = svc.resolve_conflict(ContentConflictResolveRequest(
            conflict_id=cid, resolution="resolved",
            notes="All good now", resolved_by="admin",
        ))
        assert result.state == "resolved"
        assert result.resolution_notes == "All good now"
        assert result.resolved_by == "admin"

    def test_resolve_dismissed(self, content_service):
        from foundation.knowledge.content.service import (
            ContentConflictResolveRequest,
        )

        svc, _, conflict_repo = content_service
        cid = conflict_repo.add_conflict(
            chunk_ids=["KCH-001"], fields=["content"],
        )
        result = svc.resolve_conflict(ContentConflictResolveRequest(
            conflict_id=cid, resolution="dismissed",
            notes="False alarm", resolved_by="admin",
        ))
        assert result.state == "dismissed"

    def test_resolve_conflict_fails_not_found(self, content_service):
        from foundation.knowledge.content.service import (
            ContentConflictResolveRequest,
        )

        svc, _, _ = content_service
        with pytest.raises(ValueError, match="conflict not found"):
            svc.resolve_conflict(ContentConflictResolveRequest(
                conflict_id="NONEXISTENT", resolution="resolved",
            ))

    def test_resolve_conflict_fails_invalid_resolution(self, content_service):
        from foundation.knowledge.content.service import (
            ContentConflictResolveRequest,
        )

        svc, _, conflict_repo = content_service
        cid = conflict_repo.add_conflict(
            chunk_ids=["KCH-001"], fields=["content"],
        )
        with pytest.raises(ValueError, match="resolution must be 'resolved' or 'dismissed'"):
            svc.resolve_conflict(ContentConflictResolveRequest(
                conflict_id=cid, resolution="invalid",
            ))

    def test_resolve_twice_fails(self, content_service):
        from foundation.knowledge.content.service import (
            ContentConflictResolveRequest,
        )

        svc, _, conflict_repo = content_service
        cid = conflict_repo.add_conflict(
            chunk_ids=["KCH-001"], fields=["content"],
        )
        svc.resolve_conflict(ContentConflictResolveRequest(
            conflict_id=cid, resolution="resolved", notes="Done",
        ))
        with pytest.raises(ValueError, match="already in terminal state"):
            svc.resolve_conflict(ContentConflictResolveRequest(
                conflict_id=cid, resolution="dismissed",
            ))

    def test_conflict_to_dict(self, content_service):
        svc, _, conflict_repo = content_service
        cid = conflict_repo.add_conflict(["KCH-001"], ["content"])
        page = svc.list_conflicts()
        conflict = page.conflicts[0]
        d = conflict.to_dict()
        for key in (
            "conflict_id", "source_chunk_ids", "conflicting_fields",
            "description", "state", "due_date", "created_at", "updated_at",
        ):
            assert key in d, f"Missing key: {key}"

    def test_conflict_page_to_dict(self, content_service):
        svc, _, conflict_repo = content_service
        conflict_repo.add_conflict(["KCH-001"], ["content"])
        page = svc.list_conflicts()
        d = page.to_dict()
        assert "conflicts" in d
        assert "total" in d
        assert "page" in d
        assert "page_size" in d


# ===================================================================
# TestDTOContracts
# ===================================================================


class TestDTOContracts:
    """Verify that DTOs match the canonical contract definitions from INT-04."""

    def test_knowledge_search_request_defaults(self):
        from foundation.knowledge.repository.service import KnowledgeSearchRequest

        r = KnowledgeSearchRequest(query="test")
        assert r.query == "test"
        assert r.domain_filter is None
        assert r.top_k == 5
        assert r.threshold == 0.0

    def test_knowledge_chunk_dto_matches_contract(self):
        from foundation.knowledge.repository.service import KnowledgeChunkDTO

        dto = KnowledgeChunkDTO(
            chunk_id="KCH-TEST",
            content="test",
            domain="bhyt",
            sub_topic="t",
            source_id="S",
            source_section="",
            source_page="",
            version="1.0",
            is_active=True,
            approval_status="approved_for_pilot",
            effective_date="2026-01-01",
        )
        d = dto.to_dict()
        expected_fields = {
            "chunk_id", "content", "domain", "sub_topic", "source_id",
            "source_section", "source_page", "version", "is_active",
            "approval_status", "effective_date", "tags", "is_mock",
            "answerable", "source_path",
        }
        assert set(d.keys()) == expected_fields

    def test_content_draft_dto_frozen(self):
        from foundation.knowledge.content.service import ContentDraftDTO

        dto = ContentDraftDTO(
            draft_id="DRF-001", content="x", domain="bhyt",
            sub_topic="t", source_id="S", source_section="",
            source_page="", version="0.1", status="draft",
        )
        with pytest.raises(AttributeError):
            dto.content = "modified"  # type: ignore[misc]

    def test_content_conflict_dto_frozen(self):
        from foundation.knowledge.content.service import ContentConflictDTO

        dto = ContentConflictDTO(
            conflict_id="CONF-001",
            source_chunk_ids=["KCH-001"],
            conflicting_fields=["content"],
            description="test",
            state="open",
            due_date="2026-07-19T10:00:00+00:00",
            created_at="2026-07-18T10:00:00+00:00",
            updated_at="2026-07-18T10:00:00+00:00",
        )
        with pytest.raises(AttributeError):
            dto.state = "resolved"  # type: ignore[misc]

    def test_knowledge_search_response_defaults(self):
        from foundation.knowledge.repository.service import (
            KnowledgeSearchResponse,
            KnowledgeChunkDTO,
        )

        chunk = KnowledgeChunkDTO(
            chunk_id="KCH-T", content="x", domain="d",
            sub_topic="t", source_id="S", source_section="",
            source_page="", version="1", is_active=True,
            approval_status="approved", effective_date="2026-01-01",
        )
        resp = KnowledgeSearchResponse(chunks=[chunk])
        assert resp.result_sufficient is True
        assert resp.conflict_flag is False
        assert resp.metadata == {}


# === TASK:WP-102:END ===
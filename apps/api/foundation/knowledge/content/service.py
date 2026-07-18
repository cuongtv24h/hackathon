# === TASK:WP-102:START ===
"""Content management service — draft lifecycle and conflict resolution.

Contracts implemented
---------------------
* FND-KNW-03 CreateContentDraft — draft create/patch/submit/review/publish
* FND-KNW-08 ListContentConflicts — list open conflicts
* FND-KNW-09 ResolveContentConflict — resolve a conflict with audit trail

Design notes
------------
* Draft lifecycle: create → patch → submit → review → publish.
* Only approved content is visible to the retrieval layer.
* Conflicts have a 24-hour due date and an audit trail (open → investigating
  → resolved | dismissed).
* All provider/network calls are abstracted behind callable interfaces so
  tests can inject fakes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTOs — canonical contracts from INT-04 / data-contracts.md
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContentDraftCreateRequest:
    """Request to create a new content draft."""

    content: str
    domain: str
    sub_topic: str
    source_id: str
    source_section: str = ""
    source_page: str = ""
    tags: List[str] = field(default_factory=list)
    author: str = ""


@dataclass(frozen=True)
class ContentDraftPatchRequest:
    """Request to update an existing draft (partial update)."""

    draft_id: str
    content: Optional[str] = None
    sub_topic: Optional[str] = None
    tags: Optional[List[str]] = None
    source_section: Optional[str] = None
    source_page: Optional[str] = None


@dataclass(frozen=True)
class ContentDraftDTO:
    """Canonical draft DTO."""

    draft_id: str
    content: str
    domain: str
    sub_topic: str
    source_id: str
    source_section: str
    source_page: str
    version: str
    status: Literal["draft", "submitted", "in_review", "approved", "rejected"]
    tags: List[str] = field(default_factory=list)
    author: str = ""
    reviewer: str = ""
    rejection_reason: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "content": self.content,
            "domain": self.domain,
            "sub_topic": self.sub_topic,
            "source_id": self.source_id,
            "source_section": self.source_section,
            "source_page": self.source_page,
            "version": self.version,
            "status": self.status,
            "tags": list(self.tags),
            "author": self.author,
            "reviewer": self.reviewer,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ContentSubmitRequest:
    """Request to submit a draft for review."""

    draft_id: str
    author: str = ""


@dataclass(frozen=True)
class ContentReviewRequest:
    """Request to review (approve or reject) a submitted draft."""

    draft_id: str
    reviewer: str
    approved: bool
    rejection_reason: str = ""


@dataclass(frozen=True)
class ContentApprovalStateDTO:
    """DTO representing the approval state after a review action."""

    draft_id: str
    status: Literal["draft", "submitted", "in_review", "approved", "rejected"]
    reviewer: str = ""
    rejection_reason: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "status": self.status,
            "reviewer": self.reviewer,
            "rejection_reason": self.rejection_reason,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ContentPublishRequest:
    """Request to publish an approved draft."""

    draft_id: str
    publisher: str = ""


@dataclass(frozen=True)
class ContentVersionDTO:
    """DTO representing a published content version."""

    chunk_id: str
    version: str
    published_at: str
    publisher: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "version": self.version,
            "published_at": self.published_at,
            "publisher": self.publisher,
        }


# ---------------------------------------------------------------------------
# Conflict DTOs
# ---------------------------------------------------------------------------


ConflictState = Literal["open", "investigating", "resolved", "dismissed"]


@dataclass(frozen=True)
class ContentConflictDTO:
    """Canonical conflict DTO from INT-04."""

    conflict_id: str
    source_chunk_ids: List[str]
    conflicting_fields: List[str]
    description: str
    state: ConflictState
    due_date: str
    created_at: str
    updated_at: str
    resolution_notes: str = ""
    resolved_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "source_chunk_ids": list(self.source_chunk_ids),
            "conflicting_fields": list(self.conflicting_fields),
            "description": self.description,
            "state": self.state,
            "due_date": self.due_date,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolution_notes": self.resolution_notes,
            "resolved_by": self.resolved_by,
        }


@dataclass(frozen=True)
class ContentConflictPageDTO:
    """Paginated list of content conflicts."""

    conflicts: List[ContentConflictDTO]
    total: int
    page: int
    page_size: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflicts": [c.to_dict() for c in self.conflicts],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
        }


@dataclass(frozen=True)
class ContentConflictResolveRequest:
    """Request to resolve a content conflict."""

    conflict_id: str
    resolution: Literal["resolved", "dismissed"]
    notes: str = ""
    resolved_by: str = ""


# ---------------------------------------------------------------------------
# Abstract repository interfaces (for testability)
# ---------------------------------------------------------------------------

DraftRepository = Callable[..., Any]
"""Signature: ``create(draft_data) -> dict``, ``get(draft_id) -> dict | None``,
``patch(draft_id, updates) -> dict``, ``submit(draft_id, author) -> dict``,
``review(draft_id, reviewer, approved, reason) -> dict``,
``publish(draft_id, publisher) -> dict``.
"""

ConflictRepository = Callable[..., Any]
"""Signature: ``list(page, page_size, state_filter) -> dict``,
``get(conflict_id) -> dict | None``,
``resolve(conflict_id, resolution, notes, resolved_by) -> dict``.
"""


# ---------------------------------------------------------------------------
# Service implementation
# ---------------------------------------------------------------------------


class ContentManagementService:
    """Stateless service for content draft lifecycle and conflict management.

    All persistence is delegated to injected repository callables so tests
    can provide fakes without a live database.
    """

    def __init__(
        self,
        *,
        draft_repo: DraftRepository,
        conflict_repo: ConflictRepository,
    ) -> None:
        self._draft_repo = draft_repo
        self._conflict_repo = conflict_repo

    # ------------------------------------------------------------------
    # FND-KNW-03 CreateContentDraft — create
    # ------------------------------------------------------------------

    def create_draft(self, request: ContentDraftCreateRequest) -> ContentDraftDTO:
        """Create a new content draft."""
        if not request.content or not request.content.strip():
            raise ValueError("content must be non-empty")
        if not request.domain or not request.domain.strip():
            raise ValueError("domain must be non-empty")
        if not request.source_id or not request.source_id.strip():
            raise ValueError("source_id must be non-empty")

        now = _now_iso()
        draft_data = {
            "content": request.content,
            "domain": request.domain,
            "sub_topic": request.sub_topic,
            "source_id": request.source_id,
            "source_section": request.source_section,
            "source_page": request.source_page,
            "tags": list(request.tags),
            "author": request.author,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }
        result = self._draft_repo("create", draft_data)
        return _draft_row_to_dto(result)

    # ------------------------------------------------------------------
    # FND-KNW-03 CreateContentDraft — patch
    # ------------------------------------------------------------------

    def patch_draft(self, request: ContentDraftPatchRequest) -> ContentDraftDTO:
        """Update an existing draft (partial update)."""
        if not request.draft_id or not request.draft_id.strip():
            raise ValueError("draft_id must be non-empty")

        existing = self._draft_repo("get", request.draft_id)
        if existing is None:
            raise ValueError(f"draft not found: {request.draft_id}")
        if existing.get("status") != "draft":
            raise ValueError(f"cannot patch draft in status: {existing.get('status')}")

        updates: Dict[str, Any] = {}
        if request.content is not None:
            updates["content"] = request.content
        if request.sub_topic is not None:
            updates["sub_topic"] = request.sub_topic
        if request.tags is not None:
            updates["tags"] = list(request.tags)
        if request.source_section is not None:
            updates["source_section"] = request.source_section
        if request.source_page is not None:
            updates["source_page"] = request.source_page
        updates["updated_at"] = _now_iso()

        result = self._draft_repo("patch", request.draft_id, updates)
        return _draft_row_to_dto(result)

    # ------------------------------------------------------------------
    # FND-KNW-03 CreateContentDraft — submit
    # ------------------------------------------------------------------

    def submit_draft(self, request: ContentSubmitRequest) -> ContentDraftDTO:
        """Submit a draft for review."""
        if not request.draft_id or not request.draft_id.strip():
            raise ValueError("draft_id must be non-empty")

        existing = self._draft_repo("get", request.draft_id)
        if existing is None:
            raise ValueError(f"draft not found: {request.draft_id}")
        if existing.get("status") != "draft":
            raise ValueError(f"cannot submit draft in status: {existing.get('status')}")

        result = self._draft_repo("submit", request.draft_id, request.author)
        return _draft_row_to_dto(result)

    # ------------------------------------------------------------------
    # FND-KNW-03 CreateContentDraft — review
    # ------------------------------------------------------------------

    def review_draft(self, request: ContentReviewRequest) -> ContentApprovalStateDTO:
        """Review (approve or reject) a submitted draft."""
        if not request.draft_id or not request.draft_id.strip():
            raise ValueError("draft_id must be non-empty")
        if not request.reviewer or not request.reviewer.strip():
            raise ValueError("reviewer must be non-empty")

        existing = self._draft_repo("get", request.draft_id)
        if existing is None:
            raise ValueError(f"draft not found: {request.draft_id}")
        if existing.get("status") not in ("submitted", "in_review"):
            raise ValueError(
                f"cannot review draft in status: {existing.get('status')}"
            )

        result = self._draft_repo(
            "review",
            request.draft_id,
            request.reviewer,
            request.approved,
            request.rejection_reason,
        )
        return ContentApprovalStateDTO(
            draft_id=str(result.get("draft_id", request.draft_id)),
            status=str(result.get("status", "draft")),
            reviewer=str(result.get("reviewer", request.reviewer)),
            rejection_reason=str(result.get("rejection_reason", request.rejection_reason)),
            updated_at=str(result.get("updated_at", _now_iso())),
        )

    # ------------------------------------------------------------------
    # FND-KNW-03 CreateContentDraft — publish
    # ------------------------------------------------------------------

    def publish_draft(self, request: ContentPublishRequest) -> ContentVersionDTO:
        """Publish an approved draft, creating a new content version."""
        if not request.draft_id or not request.draft_id.strip():
            raise ValueError("draft_id must be non-empty")

        existing = self._draft_repo("get", request.draft_id)
        if existing is None:
            raise ValueError(f"draft not found: {request.draft_id}")
        if existing.get("status") != "approved":
            raise ValueError(
                f"cannot publish draft in status: {existing.get('status')}"
            )

        result = self._draft_repo("publish", request.draft_id, request.publisher)
        return ContentVersionDTO(
            chunk_id=str(result.get("chunk_id", "")),
            version=str(result.get("version", "")),
            published_at=str(result.get("published_at", _now_iso())),
            publisher=str(result.get("publisher", request.publisher)),
        )

    # ------------------------------------------------------------------
    # FND-KNW-08 ListContentConflicts
    # ------------------------------------------------------------------

    def list_conflicts(
        self,
        page: int = 1,
        page_size: int = 20,
        state_filter: Optional[ConflictState] = None,
    ) -> ContentConflictPageDTO:
        """List content conflicts with pagination and optional state filter."""
        if page < 1:
            raise ValueError("page must be >= 1")
        if not (1 <= page_size <= 100):
            raise ValueError("page_size must be between 1 and 100")

        result = self._conflict_repo(
            "list", page=page, page_size=page_size, state_filter=state_filter,
        )
        conflicts = [_conflict_row_to_dto(r) for r in result.get("conflicts", [])]
        return ContentConflictPageDTO(
            conflicts=conflicts,
            total=int(result.get("total", 0)),
            page=page,
            page_size=page_size,
        )

    # ------------------------------------------------------------------
    # FND-KNW-09 ResolveContentConflict
    # ------------------------------------------------------------------

    def resolve_conflict(
        self, request: ContentConflictResolveRequest
    ) -> ContentConflictDTO:
        """Resolve or dismiss a content conflict with audit trail."""
        if not request.conflict_id or not request.conflict_id.strip():
            raise ValueError("conflict_id must be non-empty")
        if request.resolution not in ("resolved", "dismissed"):
            raise ValueError("resolution must be 'resolved' or 'dismissed'")

        existing = self._conflict_repo("get", request.conflict_id)
        if existing is None:
            raise ValueError(f"conflict not found: {request.conflict_id}")
        if existing.get("state") in ("resolved", "dismissed"):
            raise ValueError(
                f"conflict already in terminal state: {existing.get('state')}"
            )

        result = self._conflict_repo(
            "resolve",
            request.conflict_id,
            request.resolution,
            request.notes,
            request.resolved_by,
        )
        return _conflict_row_to_dto(result)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC timestamp as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _draft_row_to_dto(row: Dict[str, Any]) -> ContentDraftDTO:
    """Map a raw draft row dict to a ``ContentDraftDTO``."""
    return ContentDraftDTO(
        draft_id=str(row.get("draft_id", "")),
        content=str(row.get("content", "")),
        domain=str(row.get("domain", "")),
        sub_topic=str(row.get("sub_topic", "")),
        source_id=str(row.get("source_id", "")),
        source_section=str(row.get("source_section", "")),
        source_page=str(row.get("source_page", "")),
        version=str(row.get("version", "")),
        status=str(row.get("status", "draft")),
        tags=list(row.get("tags", [])),
        author=str(row.get("author", "")),
        reviewer=str(row.get("reviewer", "")),
        rejection_reason=str(row.get("rejection_reason", "")),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
    )


def _conflict_row_to_dto(row: Dict[str, Any]) -> ContentConflictDTO:
    """Map a raw conflict row dict to a ``ContentConflictDTO``."""
    return ContentConflictDTO(
        conflict_id=str(row.get("conflict_id", "")),
        source_chunk_ids=list(row.get("source_chunk_ids", [])),
        conflicting_fields=list(row.get("conflicting_fields", [])),
        description=str(row.get("description", "")),
        state=str(row.get("state", "open")),
        due_date=str(row.get("due_date", "")),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        resolution_notes=str(row.get("resolution_notes", "")),
        resolved_by=str(row.get("resolved_by", "")),
    )


__all__ = [
    "ContentDraftCreateRequest",
    "ContentDraftPatchRequest",
    "ContentDraftDTO",
    "ContentSubmitRequest",
    "ContentReviewRequest",
    "ContentApprovalStateDTO",
    "ContentPublishRequest",
    "ContentVersionDTO",
    "ContentConflictDTO",
    "ContentConflictPageDTO",
    "ContentConflictResolveRequest",
    "ContentManagementService",
    "ConflictState",
    "DraftRepository",
    "ConflictRepository",
]
# === TASK:WP-102:END ===
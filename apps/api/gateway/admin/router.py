"""Admin operational dashboard APIs backed only by Supabase."""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.foundation.operational_repository import OperationalRepository
from apps.api.foundation.knowledge.content.service import (
    ContentDraftCreateRequest, ContentDraftPatchRequest, ContentManagementService,
    ContentPublishRequest, ContentReviewRequest, ContentSubmitRequest,
)

router = APIRouter(prefix="/v1/admin", tags=["admin"])

def repository():
    return OperationalRepository(os.environ.get("DATABASE_URL"))

def content_service():
    repo = repository()
    return ContentManagementService(draft_repo=repo.content_draft, conflict_repo=lambda *args, **kwargs: {})

@router.get("/dashboard")
def dashboard():
    try:
        return repository().dashboard()
    except Exception as exc:
        raise HTTPException(503, "admin dashboard is unavailable") from exc

@router.get("/history")
def history(limit: int = 50, offset: int = 0):
    try:
        return repository().history(limit=min(max(limit, 1), 200), offset=max(offset, 0))
    except Exception as exc:
        raise HTTPException(503, "conversation history is unavailable") from exc

@router.get("/content/conflicts")
def conflicts():
    try:
        return {"conflicts": repository().conflicts()}
    except Exception as exc:
        raise HTTPException(503, "content conflicts are unavailable") from exc

@router.get("/content/drafts")
def content_drafts():
    # A compact MVP list; drafts are addressed by UUID and use no raw patient data.
    try:
        repo = repository()
        with repo._cursor() as cursor:
            cursor.execute("select draft_id::text from content_drafts order by updated_at desc")
            return {"drafts": [repo.content_draft("get", row["draft_id"]) for row in cursor.fetchall()]}
    except Exception as exc:
        raise HTTPException(503, "content drafts are unavailable") from exc

class DraftCreate(BaseModel):
    content: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    sub_topic: str = ""
    source_id: str = Field(min_length=1)
    source_section: str = ""
    source_page: str = ""
    tags: list[str] = []
    author: str = "demo-admin"

class DraftPatch(BaseModel):
    content: Optional[str] = None
    sub_topic: Optional[str] = None
    tags: Optional[list[str]] = None
    source_section: Optional[str] = None
    source_page: Optional[str] = None

class DraftActor(BaseModel):
    actor: str = Field(min_length=1, max_length=200)

class DraftReview(DraftActor):
    approved: bool
    rejection_reason: str = ""

@router.post("/content/drafts")
def create_draft(payload: DraftCreate):
    try:
        return content_service().create_draft(ContentDraftCreateRequest(**payload.model_dump())).to_dict()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@router.patch("/content/drafts/{draft_id}")
def patch_draft(draft_id: str, payload: DraftPatch):
    try:
        return content_service().patch_draft(ContentDraftPatchRequest(draft_id=draft_id, **payload.model_dump())).to_dict()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@router.post("/content/drafts/{draft_id}/submit")
def submit_draft(draft_id: str, payload: DraftActor):
    try:
        return content_service().submit_draft(ContentSubmitRequest(draft_id=draft_id, author=payload.actor)).to_dict()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@router.post("/content/drafts/{draft_id}/review")
def review_draft(draft_id: str, payload: DraftReview):
    try:
        return content_service().review_draft(ContentReviewRequest(draft_id=draft_id, reviewer=payload.actor, approved=payload.approved, rejection_reason=payload.rejection_reason)).to_dict()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@router.post("/content/drafts/{draft_id}/publish")
def publish_draft(draft_id: str, payload: DraftActor):
    try:
        return content_service().publish_draft(ContentPublishRequest(draft_id=draft_id, publisher=payload.actor)).to_dict()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

class ConflictResolution(BaseModel):
    state: str = Field(pattern="^(resolved|dismissed)$")
    note: str = Field(min_length=1, max_length=4000)
    actor: str = Field(min_length=1, max_length=200)

@router.patch("/content/conflicts/{conflict_id}")
def resolve_conflict(conflict_id: str, payload: ConflictResolution):
    try:
        result = repository().resolve_conflict(conflict_id, payload.state, payload.note, payload.actor)
        repository().write_audit("content", payload.actor, "content_conflict", "resolve_conflict", result)
        return result
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "content conflict resolution is unavailable") from exc

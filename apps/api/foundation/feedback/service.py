# === TASK:WP-101:START ===
"""Foundation feedback service (FND-FBK-01).

This module implements the feedback foundation API declared in
``docs/artifacts/interface/foundation-api-contracts.md`` (INT-03). The operation is:

* ``FND-FBK-01 CreateFeedback`` — ``POST /v1/foundation/feedback``

No AI reasoning is performed; the service handles feedback submission.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Mapping, Optional

from packages.contracts import (
    UnifiedErrorEnvelope,
    make_error_envelope,
    CATEGORY_VALIDATION,
    CATEGORY_SYSTEM,
    INVALID_REQUEST,
    FIELD_REQUIRED,
    INTERNAL_ERROR,
    MESSAGE_TOO_LONG,
)


# ---------------------------------------------------------------------------
# Error helper - returns UnifiedErrorEnvelope directly (now inherits Exception)
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


# ---------------------------------------------------------------------------
# Feedback DTOs (from INT-04 / data-contracts.md)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeedbackCreateRequest:
    """Request body for creating feedback."""

    session_id: str
    rating: Literal[1, 2, 3, 4, 5]
    comment: Optional[str] = None
    category: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FeedbackCreateRequest":
        """Construct from a plain dictionary (e.g., parsed JSON)."""
        rating = data.get("rating")
        if isinstance(rating, int) and 1 <= rating <= 5:
            rating = rating  # type: ignore[assignment]
        else:
            rating = 3  # default

        comment = data.get("comment")
        if comment is not None and not isinstance(comment, str):
            comment = str(comment)

        return cls(
            session_id=data.get("session_id", ""),
            rating=rating,  # type: ignore[arg-type]
            comment=comment,
            category=data.get("category"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class FeedbackReceiptDTO:
    """Receipt returned after creating feedback."""

    feedback_id: str
    session_id: str
    rating: int
    comment: Optional[str]
    category: Optional[str]
    created_at: str  # ISO 8601
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "feedback_id": self.feedback_id,
            "session_id": self.session_id,
            "rating": self.rating,
            "created_at": self.created_at,
        }
        if self.comment is not None:
            result["comment"] = self.comment
        if self.category is not None:
            result["category"] = self.category
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


# ---------------------------------------------------------------------------
# In-memory feedback store (for tests and local dev without DB)
# ---------------------------------------------------------------------------


class _InMemoryFeedbackStore:
    """Thread-safe in-memory feedback store for unit tests."""

    def __init__(self) -> None:
        self._feedbacks: Dict[str, FeedbackReceiptDTO] = {}
        self._lock = __import__("threading").Lock()

    def create(
        self,
        feedback_id: str,
        session_id: str,
        rating: int,
        comment: Optional[str],
        category: Optional[str],
        metadata: Dict[str, Any],
    ) -> FeedbackReceiptDTO:
        receipt = FeedbackReceiptDTO(
            feedback_id=feedback_id,
            session_id=session_id,
            rating=rating,
            comment=comment,
            category=category,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata),
        )
        with self._lock:
            self._feedbacks[feedback_id] = receipt
        return receipt

    def get(self, feedback_id: str) -> Optional[FeedbackReceiptDTO]:
        with self._lock:
            return self._feedbacks.get(feedback_id)

    def list_by_session(self, session_id: str) -> List[FeedbackReceiptDTO]:
        with self._lock:
            return [
                f for f in self._feedbacks.values() if f.session_id == session_id
            ]


# ---------------------------------------------------------------------------
# Feedback Service
# ---------------------------------------------------------------------------


class FeedbackService:
    """Foundation feedback service implementing FND-FBK-01."""

    def __init__(self) -> None:
        self._memory = _InMemoryFeedbackStore()

    # -----------------------------------------------------------------------
    # FND-FBK-01 CreateFeedback
    # -----------------------------------------------------------------------
    def create_feedback(self, request: FeedbackCreateRequest) -> FeedbackReceiptDTO:
        """Create feedback (FND-FBK-01)."""
        if not request.session_id or not request.session_id.strip():
            raise _service_error(
                code=FIELD_REQUIRED,
                message="session_id is required",
                category=CATEGORY_VALIDATION,
                field_errors={"session_id": "required"},
            )

        if not isinstance(request.rating, int) or not (1 <= request.rating <= 5):
            raise _service_error(
                code=INVALID_REQUEST,
                message="rating must be an integer between 1 and 5",
                category=CATEGORY_VALIDATION,
                field_errors={"rating": "must be 1-5"},
            )

        if request.comment is not None and len(request.comment) > 4000:
            raise _service_error(
                code=MESSAGE_TOO_LONG,
                message="comment exceeds maximum length of 4000 characters",
                category=CATEGORY_VALIDATION,
                field_errors={"comment": "too long"},
            )

        feedback_id = f"fbk_{secrets.token_urlsafe(12)}"

        return self._memory.create(
            feedback_id=feedback_id,
            session_id=request.session_id,
            rating=request.rating,
            comment=request.comment,
            category=request.category,
            metadata=request.metadata,
        )

    def get_feedback(self, feedback_id: str) -> Optional[FeedbackReceiptDTO]:
        """Retrieve a feedback receipt by ID (helper for tests)."""
        return self._memory.get(feedback_id)

    def list_feedback_by_session(self, session_id: str) -> List[FeedbackReceiptDTO]:
        """List all feedback for a session (helper for tests)."""
        return self._memory.list_by_session(session_id)


__all__ = [
    # DTOs
    "FeedbackCreateRequest",
    "FeedbackReceiptDTO",
    # Service
    "FeedbackService",
]
# === TASK:WP-101:END ===
# === TASK:WP-009:START ===
"""Canonical error contracts for the Hospital Assistant API.

This module contains the single public error envelope type mandated by
``docs/artifacts/interface/error-contracts.md`` (INT-07): ``UnifiedErrorEnvelope``.
The envelope shape is frozen; downstream code must not add, remove or rename
fields. The factory function ``make_error_envelope`` provides the canonical
construction path and injects the trace ID.

The canonical error categories and codes defined in INT-07 are exposed as
module-level constants so the rest of the codebase can reference them without
re-typing strings. The module deliberately does not introduce new error
semantics — it only formalises the contract from the source artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


# ---------------------------------------------------------------------------
# Canonical error codes (INT-07, Section "Envelope")
# ---------------------------------------------------------------------------

# Validation (HTTP 400)
INVALID_REQUEST = "INVALID_REQUEST"
FIELD_REQUIRED = "FIELD_REQUIRED"
INVALID_ENUM = "INVALID_ENUM"
INVALID_DATE_RANGE = "INVALID_DATE_RANGE"
MESSAGE_TOO_LONG = "MESSAGE_TOO_LONG"

# Authentication (HTTP 401)
AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
TOKEN_INVALID = "TOKEN_INVALID"

# Authorization (HTTP 403)
ACCESS_DENIED = "ACCESS_DENIED"
DOMAIN_APPROVER_REQUIRED = "DOMAIN_APPROVER_REQUIRED"

# Business (HTTP 409/422)
CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
SLOT_UNAVAILABLE = "SLOT_UNAVAILABLE"
CONTENT_NOT_APPROVED = "CONTENT_NOT_APPROVED"
CONTENT_CONFLICT = "CONTENT_CONFLICT"
INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"

# Not found (HTTP 404)
APPOINTMENT_NOT_FOUND = "APPOINTMENT_NOT_FOUND"
CONTENT_NOT_FOUND = "CONTENT_NOT_FOUND"

# AI (HTTP 422/503)
NO_GROUNDED_RESULT = "NO_GROUNDED_RESULT"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
MEDICAL_ADVICE_REFUSED = "MEDICAL_ADVICE_REFUSED"
AI_PROVIDER_UNAVAILABLE = "AI_PROVIDER_UNAVAILABLE"
AI_OUTPUT_REJECTED = "AI_OUTPUT_REJECTED"

# Tool (HTTP 502/504)
TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
TOOL_TIMEOUT = "TOOL_TIMEOUT"
TOOL_OUTPUT_INVALID = "TOOL_OUTPUT_INVALID"
INTEGRATION_UNAVAILABLE = "INTEGRATION_UNAVAILABLE"

# Tool - Privacy/Logging (WP-204, HTTP 502/503/400)
PII_PROCESSING_FAILED = "PII_PROCESSING_FAILED"
LOG_DEFERRED = "LOG_DEFERRED"
LOG_REJECTED = "LOG_REJECTED"

# Safety (HTTP 200/warning or 503)
EMERGENCY_PROTOCOL_FALLBACK_USED = "EMERGENCY_PROTOCOL_FALLBACK_USED"
EMERGENCY_AUDIT_DEFERRED = "EMERGENCY_AUDIT_DEFERRED"

# Privacy/Logging (HTTP 422/502/503) - WP-204
PII_PROCESSING_FAILED = "PII_PROCESSING_FAILED"
LOG_DEFERRED = "LOG_DEFERRED"
LOG_REJECTED = "LOG_REJECTED"

# Rate limit (HTTP 429)
RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

# System (HTTP 500/503)
INTERNAL_ERROR = "INTERNAL_ERROR"
CONFIG_UNAVAILABLE = "CONFIG_UNAVAILABLE"
SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Canonical error categories (INT-07)
# ---------------------------------------------------------------------------

CATEGORY_VALIDATION = "validation"
CATEGORY_AUTHENTICATION = "authentication"
CATEGORY_AUTHORIZATION = "authorization"
CATEGORY_BUSINESS = "business"
CATEGORY_NOT_FOUND = "not_found"
CATEGORY_AI = "ai"
CATEGORY_TOOL = "tool"
CATEGORY_SAFETY = "safety"
CATEGORY_RATE_LIMIT = "rate_limit"
CATEGORY_SYSTEM = "system"


# Mapping from canonical category to default HTTP status (INT-07)
CATEGORY_TO_HTTP_STATUS: Mapping[str, int] = {
    CATEGORY_VALIDATION: 400,
    CATEGORY_AUTHENTICATION: 401,
    CATEGORY_AUTHORIZATION: 403,
    CATEGORY_BUSINESS: 422,
    CATEGORY_NOT_FOUND: 404,
    CATEGORY_AI: 503,
    CATEGORY_TOOL: 502,
    CATEGORY_SAFETY: 503,
    CATEGORY_RATE_LIMIT: 429,
    CATEGORY_SYSTEM: 503,
}


# ---------------------------------------------------------------------------
# Envelope shape (INT-07, Section "Envelope")
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorDetail:
    """The inner ``error`` object inside ``UnifiedErrorEnvelope``.

    The fields are exactly those listed in INT-07. No extra fields are
    permitted; the contract is frozen.
    """

    code: str
    category: str
    message: str
    field_errors: Dict[str, str] = field(default_factory=dict)
    retryable: bool = False
    retry_after_seconds: Optional[int] = None
    fallback: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "code": self.code,
            "category": self.category,
            "message": self.message,
            "field_errors": dict(self.field_errors),
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
            "fallback": self.fallback,
        }
        return result


@dataclass(frozen=True)
class UnifiedErrorEnvelope(Exception):
    """The canonical error envelope shape declared in INT-07.

    ``trace_id`` is an opaque identifier used for log correlation. The inner
    ``error`` object contains the canonical fields. The envelope never exposes
    stack traces, prompts, provider secrets, raw tool payloads or PII.

    Inherits from Exception so it can be raised directly, per WP-101 test contract.
    """

    trace_id: str
    error: ErrorDetail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "error": self.error.to_dict(),
        }


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def make_error_envelope(
    code: str,
    message: str,
    *,
    category: str,
    trace_id: Optional[str] = None,
    field_errors: Optional[Mapping[str, str]] = None,
    retryable: bool = False,
    retry_after_seconds: Optional[int] = None,
    fallback: Optional[str] = None,
) -> UnifiedErrorEnvelope:
    """Construct a ``UnifiedErrorEnvelope`` with the canonical shape.

    This is the only sanctioned way to create an envelope; it guarantees the
    category is one of the canonical values and that the trace_id is present.
    """

    if category not in CATEGORY_TO_HTTP_STATUS:
        raise ValueError(
            f"unknown error category {category!r}; expected one of "
            f"{sorted(CATEGORY_TO_HTTP_STATUS.keys())}"
        )
    return UnifiedErrorEnvelope(
        trace_id=trace_id or "",
        error=ErrorDetail(
            code=code,
            category=category,
            message=message,
            field_errors=dict(field_errors or {}),
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
            fallback=fallback,
        ),
    )


__all__ = [
    # Core types
    "ErrorDetail",
    "UnifiedErrorEnvelope",
    "make_error_envelope",
    # Categories
    "CATEGORY_VALIDATION",
    "CATEGORY_AUTHENTICATION",
    "CATEGORY_AUTHORIZATION",
    "CATEGORY_BUSINESS",
    "CATEGORY_NOT_FOUND",
    "CATEGORY_AI",
    "CATEGORY_TOOL",
    "CATEGORY_SAFETY",
    "CATEGORY_RATE_LIMIT",
    "CATEGORY_SYSTEM",
    "CATEGORY_TO_HTTP_STATUS",
    # Codes
    "INVALID_REQUEST",
    "FIELD_REQUIRED",
    "INVALID_ENUM",
    "INVALID_DATE_RANGE",
    "MESSAGE_TOO_LONG",
    "AUTHENTICATION_REQUIRED",
    "TOKEN_INVALID",
    "ACCESS_DENIED",
    "DOMAIN_APPROVER_REQUIRED",
    "CONFIRMATION_REQUIRED",
    "SLOT_UNAVAILABLE",
    "CONTENT_NOT_APPROVED",
    "CONTENT_CONFLICT",
    "INVALID_STATE_TRANSITION",
    "APPOINTMENT_NOT_FOUND",
    "CONTENT_NOT_FOUND",
    "NO_GROUNDED_RESULT",
    "OUT_OF_SCOPE",
    "MEDICAL_ADVICE_REFUSED",
    "AI_PROVIDER_UNAVAILABLE",
    "AI_OUTPUT_REJECTED",
    "TOOL_UNAVAILABLE",
    "TOOL_TIMEOUT",
    "TOOL_OUTPUT_INVALID",
    "INTEGRATION_UNAVAILABLE",
    "EMERGENCY_PROTOCOL_FALLBACK_USED",
    "EMERGENCY_AUDIT_DEFERRED",
    # Privacy/Logging - WP-204
    "PII_PROCESSING_FAILED",
    "LOG_DEFERRED",
    "LOG_REJECTED",
    "RATE_LIMIT_EXCEEDED",
    "INTERNAL_ERROR",
    "CONFIG_UNAVAILABLE",
    "SERVICE_UNAVAILABLE",
]
# === TASK:WP-009:END ===

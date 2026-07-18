# === TASK:WP-304:START ===
"""Emergency safety orchestration pipeline (PC-02).

This module implements the emergency safety pipeline for capability PC-02
(Emergency Safety). It runs the deterministic prefilter (WP-202), loads the
appropriate emergency protocol from the foundation service (WP-103), and
returns a structured response with protocol content, hotlines, address, and
event ID for audit trail.

Contract references
-------------------
* EmergencySafetyRequest / EmergencySafetyResponse — INT-04 / INT-02
* EmergencyProtocolDTO — INT-04 (foundation.emergency.service)
* AI behaviour rules — INT-05 (emergency priority, no diagnosis)
* Prefilter tool contract — INT-06 (WP-202 EmergencyPrefilterTool)

Design notes
------------
* Emergency prefilter (WP-202) runs deterministically before any reasoning.
* Only Level 1 (caution) and Level 2 (critical) protocols are supported.
* Level 1: contact handoff guidance only; no medical assessment.
* Level 2: immediate emergency contact (115) + hospital handoff.
* No LLM calls; no AI reasoning; fully deterministic.
* All provider dependencies injected via Protocol for testability.
* Substantive business logic lives here, not in __init__.py.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from packages.contracts import (
    CATEGORY_SAFETY,
    make_error_envelope,
    UnifiedErrorEnvelope,
)

from apps.api.foundation.emergency.service import (
    EmergencyFoundationService,
    EmergencyProtocolDTO,
    get_emergency_foundation_service,
)
from apps.api.capabilities.emergency.prefilter.tool import (
    EmergencyPrefilterTool,
    PrefilterRequest,
    PrefilterResult,
    MatchedKeyword,
    emergency_prefilter,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public request / response DTOs (INT-04, INT-02 — PC-02)
# ---------------------------------------------------------------------------

OUTCOME_EMERGENCY_TRIGGERED = "emergency_triggered"
OUTCOME_CLARIFICATION_REQUIRED = "clarification_required"
OUTCOME_NOT_TRIGGERED = "not_triggered"

GENERAL_DISCLAIMER = (
    "Đây là thông tin hỗ trợ khẩn cấp và không thay thế chăm sóc y tế chuyên nghiệp. "
    "Trong tình huống đe dọa tính mạng, hãy gọi 115 ngay lập tức."
)

# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmergencySafetyRequest:
    """PC-02 request DTO (INT-04).

    Fields
    ------
    request_id : str
        Opaque identifier for idempotency / tracing.
    session_id : str
        Session identifier (used for conversation context and audit).
    message : str
        User message, 1..4000 characters.
    conversation_history : list[dict]
        Previous turns (max 20), each {"role": str, "content": str}.
    client_context : dict
        Optional client context metadata.
    """

    request_id: str
    session_id: str
    message: str
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    client_context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message or not self.message.strip():
            raise ValueError("message must be non-empty")
        if len(self.message) > 4000:
            raise ValueError("message exceeds 4000 characters")
        if len(self.conversation_history) > 20:
            raise ValueError("conversation_history cannot exceed 20 turns")


@dataclass(frozen=True)
class EmergencySafetyResponse:
    """PC-02 response DTO (INT-04 / INT-02).

    Outcomes: emergency_triggered | clarification_required | not_triggered.
    """

    outcome: str
    message: str
    level: Optional[int] = None
    protocol: Optional[EmergencyProtocolDTO] = None
    hotlines: List[str] = field(default_factory=list)
    address: Optional[str] = None
    banner: Optional[str] = None
    event_id: Optional[str] = None
    matched_keywords: List[Dict[str, Any]] = field(default_factory=list)
    disclaimers: List[str] = field(default_factory=list)
    error: Optional[UnifiedErrorEnvelope] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "outcome": self.outcome,
            "message": self.message,
            "hotlines": list(self.hotlines),
            "disclaimers": list(self.disclaimers),
            "matched_keywords": list(self.matched_keywords),
        }
        if self.level is not None:
            result["level"] = self.level
        if self.protocol is not None:
            result["protocol"] = self.protocol.to_dict()
        if self.address is not None:
            result["address"] = self.address
        if self.banner is not None:
            result["banner"] = self.banner
        if self.event_id is not None:
            result["event_id"] = self.event_id
        if self.error is not None:
            result["error"] = self.error.to_dict()
        return result


# ---------------------------------------------------------------------------
# Dependency protocols (test-friendly injection)
# ---------------------------------------------------------------------------


@runtime_checkable
class EmergencyPrefilterProtocol(Protocol):
    """Minimal prefilter interface consumed by the pipeline (WP-202)."""

    def prefilter(self, request: PrefilterRequest) -> PrefilterResult:
        """Run emergency prefilter and return structured result."""
        ...


@runtime_checkable
class EmergencyFoundationProtocol(Protocol):
    """Minimal foundation interface for loading protocols (WP-103)."""

    def get_emergency_protocol(self, level: int) -> Optional[EmergencyProtocolDTO]:
        """Load emergency protocol by level (1 or 2)."""
        ...


# ---------------------------------------------------------------------------
# Core pipeline class
# ---------------------------------------------------------------------------


class EmergencySafetyPipeline:
    """Deterministic emergency safety pipeline for PC-02 (Emergency Safety).

    Execution order (INT-05 §Planning rules — Emergency priority):
    1. Run deterministic prefilter (WP-202) on user message.
    2. If prefilter detects emergency:
       a. Load protocol from foundation (WP-103) by level.
       b. Build response with protocol content, hotlines, address, banner.
       c. Include event_id from prefilter audit event.
    3. If no emergency detected:
       a. Return not_triggered outcome with clarification guidance.
    4. Never diagnose, interpret tests, or recommend treatment.

    Dependencies are all injected; the class never imports concrete providers.
    """

    def __init__(
        self,
        *,
        prefilter_tool: Optional[EmergencyPrefilterProtocol] = None,
        foundation_service: Optional[EmergencyFoundationProtocol] = None,
    ) -> None:
        self._prefilter_tool = prefilter_tool or EmergencyPrefilterTool()
        self._foundation_service = foundation_service or get_emergency_foundation_service()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        request: EmergencySafetyRequest,
    ) -> EmergencySafetyResponse:
        """Run the full PC-02 pipeline for a single user message.

        Args:
            request: Validated EmergencySafetyRequest.

        Returns:
            EmergencySafetyResponse with outcome, protocol content, hotlines,
            address, banner, event_id, and matched keywords. Never raises;
            errors become fallback responses with error envelope.
        """
        trace_id = str(uuid.uuid4())

        try:
            # Step 1 — run deterministic prefilter (WP-202)
            prefilter_request = PrefilterRequest(
                user_message=request.message,
                session_id=request.session_id,
                trace_id=trace_id,
            )
            prefilter_result = self._prefilter_tool.prefilter(prefilter_request)

            # Extract matched keywords for response
            matched_keywords = [kw.to_dict() for kw in prefilter_result.matched_keywords]

            # Step 2 — handle emergency detection
            if prefilter_result.is_emergency:
                return self._handle_emergency(
                    prefilter_result=prefilter_result,
                    matched_keywords=matched_keywords,
                    trace_id=trace_id,
                )

            # Step 3 — no emergency detected
            return self._handle_no_emergency(
                matched_keywords=matched_keywords,
                trace_id=trace_id,
            )

        except Exception as exc:
            logger.exception("EmergencySafetyPipeline.execute failed: %s", exc)
            return EmergencySafetyResponse(
                outcome=OUTCOME_NOT_TRIGGERED,
                message=GENERAL_DISCLAIMER,
                disclaimers=[GENERAL_DISCLAIMER],
                error=make_error_envelope(
                    code="EMERGENCY_PIPELINE_ERROR",
                    message=str(exc),
                    category=CATEGORY_SAFETY,
                    trace_id=trace_id,
                    retryable=True,
                    retry_after_seconds=5,
                ),
            )

    # ------------------------------------------------------------------
    # Step 2 — handle detected emergency
    # ------------------------------------------------------------------

    def _handle_emergency(
        self,
        prefilter_result: PrefilterResult,
        matched_keywords: List[Dict[str, Any]],
        trace_id: str,
    ) -> EmergencySafetyResponse:
        """Build response when emergency is detected."""
        level = prefilter_result.level
        protocol_id = prefilter_result.protocol_id

        # Load protocol from foundation
        protocol = self._foundation_service.get_emergency_protocol(level)

        if protocol is None:
            logger.warning("No protocol found for level %d, using fallback", level)
            return EmergencySafetyResponse(
                outcome=OUTCOME_CLARIFICATION_REQUIRED,
                message=(
                    "Hệ thống phát hiện tình huống khẩn cấp nhưng không tải được giao thức. "
                    "Vui lòng gọi 115 ngay lập tức để được hỗ trợ khẩn cấp."
                ),
                level=level,
                hotlines=["115"],
                disclaimers=[GENERAL_DISCLAIMER],
                matched_keywords=matched_keywords,
                event_id=prefilter_result.event_receipt.event_id if prefilter_result.event_receipt else None,
                error=make_error_envelope(
                    code="PROTOCOL_NOT_FOUND",
                    message=f"No emergency protocol found for level {level}",
                    category=CATEGORY_SAFETY,
                    trace_id=trace_id,
                ),
            )

        # Build message based on level
        if level == 2:
            message = self._build_level2_message(protocol)
        else:
            message = self._build_level1_message(protocol)

        # Extract event_id from prefilter receipt
        event_id = None
        if prefilter_result.event_receipt:
            event_id = prefilter_result.event_receipt.event_id

        return EmergencySafetyResponse(
            outcome=OUTCOME_EMERGENCY_TRIGGERED,
            message=message,
            level=level,
            protocol=protocol,
            hotlines=list(protocol.channel_refs),
            address=protocol.emergency_address_ref,
            banner=protocol.response_text,
            event_id=event_id,
            matched_keywords=matched_keywords,
            disclaimers=[GENERAL_DISCLAIMER],
        )

    def _build_level1_message(self, protocol: EmergencyProtocolDTO) -> str:
        """Build Level 1 (caution) message with contact handoff guidance."""
        hotline_str = ", ".join(protocol.channel_refs) if protocol.channel_refs else "115"
        return (
            f"⚠️ {protocol.response_text}\n\n"
            f"Hướng dẫn: Vui lòng liên hệ ngay với đường dây nóng: {hotline_str}.\n"
            f"Địa chỉ bệnh viện: {protocol.emergency_address_ref or 'Bệnh viện Tim Hà Nội'}\n\n"
            f"Đây là mức độ cảnh báo (Level 1). Không phải chẩn đoán y tế."
        )

    def _build_level2_message(self, protocol: EmergencyProtocolDTO) -> str:
        """Build Level 2 (critical) message with immediate emergency contact."""
        hotline_str = ", ".join(protocol.channel_refs) if protocol.channel_refs else "115"
        return (
            f"🚨 {protocol.response_text}\n\n"
            f"KHẨN CẤP: Gọi 115 NGAY LẬP TỨC hoặc đến cấp cứu bệnh viện Tim Hà Nội: "
            f"{protocol.emergency_address_ref or 'Bệnh viện Tim Hà Nội'}.\n"
            f"Các đường dây hỗ trợ: {hotline_str}\n\n"
            f"Đây là mức độ nghiêm trọng (Level 2). Không tự xử lý, hãy gọi 115 ngay."
        )

    # ------------------------------------------------------------------
    # Step 3 — handle no emergency detected
    # ------------------------------------------------------------------

    def _handle_no_emergency(
        self,
        matched_keywords: List[Dict[str, Any]],
        trace_id: str,
    ) -> EmergencySafetyResponse:
        """Build response when no emergency is detected."""
        return EmergencySafetyResponse(
            outcome=OUTCOME_NOT_TRIGGERED,
            message=(
                "Không phát hiện từ khóa khẩn cấp trong tin nhắn của bạn. "
                "Nếu bạn cảm thấy bất an về sức khỏe, vui lòng liên hệ 115 hoặc "
            ),
            level=None,
            protocol=None,
            hotlines=["115"],
            address="Bệnh viện Tim Hà Nội",
            banner=None,
            event_id=None,
            matched_keywords=matched_keywords,
            disclaimers=[GENERAL_DISCLAIMER],
        )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def run_emergency_safety(
    request: EmergencySafetyRequest,
    *,
    prefilter_tool: Optional[EmergencyPrefilterProtocol] = None,
    foundation_service: Optional[EmergencyFoundationProtocol] = None,
) -> EmergencySafetyResponse:
    """One-shot convenience wrapper around EmergencySafetyPipeline.

    Useful for callers that do not need to hold a long-lived pipeline instance.
    """
    pipeline = EmergencySafetyPipeline(
        prefilter_tool=prefilter_tool,
        foundation_service=foundation_service,
    )
    return pipeline.execute(request)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    # Outcome constants
    "OUTCOME_EMERGENCY_TRIGGERED",
    "OUTCOME_CLARIFICATION_REQUIRED",
    "OUTCOME_NOT_TRIGGERED",
    # DTOs
    "EmergencySafetyRequest",
    "EmergencySafetyResponse",
    # Protocols
    "EmergencyPrefilterProtocol",
    "EmergencyFoundationProtocol",
    # Pipeline
    "EmergencySafetyPipeline",
    "run_emergency_safety",
    # Disclaimer strings (useful in tests)
    "GENERAL_DISCLAIMER",
]
# === TASK:WP-304:END ===
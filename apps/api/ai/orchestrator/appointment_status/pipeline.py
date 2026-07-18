# === TASK:WP-306:START ===
"""Appointment-status orchestration pipeline for PC-04.

The pipeline performs a minimal-reference lookup through the WP-203
``lookup_appointment`` tool.  It does not infer an appointment status, request
extra PII, or call an LLM.  Every branch returns a safe next action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from apps.api.foundation.appointments.tools.service import (
    AppointmentToolError,
    LookupAppointmentInput,
)


OUTCOME_FOUND = "found"
OUTCOME_NOT_FOUND = "not_found"
OUTCOME_REDIRECTED = "redirected"
OUTCOME_UNAVAILABLE = "unavailable"

_APPOINTMENT_ID_PATTERN = re.compile(r"^HEN-\d{4}-\d{4}$")
_KNOWN_STATUSES = {"pending", "confirmed", "cancelled", "rejected", "completed"}


@dataclass(frozen=True)
class AppointmentStatusRequest:
    """PC-04 request using only the approved appointment reference."""

    request_id: str
    session_id: str
    appointment_reference: Dict[str, str]

    def __post_init__(self) -> None:
        if not self.request_id or not self.request_id.strip():
            raise ValueError("request_id must be non-empty")
        if not self.session_id or not self.session_id.strip():
            raise ValueError("session_id must be non-empty")
        if not isinstance(self.appointment_reference, dict):
            raise ValueError("appointment_reference must be an object")

    @property
    def appointment_id(self) -> str:
        value = self.appointment_reference.get("appointment_id", "")
        return value.strip() if isinstance(value, str) else ""


@dataclass(frozen=True)
class AppointmentStatusResponse:
    """PC-04 response with a minimal appointment summary and next steps."""

    outcome: str
    message: str
    next_steps: List[Dict[str, str]] = field(default_factory=list)
    appointment: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "message": self.message,
            "next_steps": [dict(item) for item in self.next_steps],
            "appointment": dict(self.appointment) if self.appointment else None,
            "warnings": list(self.warnings),
        }


class AppointmentLookupProtocol(Protocol):
    """The narrow WP-203 tool surface consumed by this pipeline."""

    def lookup_appointment(self, input_data: LookupAppointmentInput) -> Any:
        """Return an appointment output or ``None`` when it is not found."""


class AppointmentStatusPipeline:
    """Safe appointment-status orchestration without status inference."""

    def __init__(
        self,
        *,
        appointment_tools: AppointmentLookupProtocol,
        channel_resolver: Optional[Callable[[], List[str]]] = None,
    ) -> None:
        self._appointment_tools = appointment_tools
        self._channel_resolver = channel_resolver or (lambda: ["reception", "hotline"])

    def execute(self, request: AppointmentStatusRequest) -> AppointmentStatusResponse:
        """Look up the reference and return status-specific safe guidance."""
        appointment_id = request.appointment_id
        if not _APPOINTMENT_ID_PATTERN.fullmatch(appointment_id):
            return self._not_found_response("Mã lịch hẹn không đúng định dạng.")

        try:
            appointment = self._appointment_tools.lookup_appointment(
                LookupAppointmentInput(appointment_id=appointment_id)
            )
        except AppointmentToolError:
            return self._redirected_response()
        except Exception:
            return self._unavailable_response()

        if appointment is None:
            return self._not_found_response("Không tìm thấy lịch hẹn với mã đã cung cấp.")

        status = getattr(appointment, "status", "")
        if status not in _KNOWN_STATUSES:
            return self._unavailable_response()

        summary = {
            "appointment_id": getattr(appointment, "appointment_id", appointment_id),
            "doctor_id": getattr(appointment, "doctor_id", None),
            "slot_id": getattr(appointment, "slot_id", None),
            "status": status,
            "created_at": getattr(appointment, "created_at", None),
            "updated_at": getattr(appointment, "updated_at", None),
        }
        return AppointmentStatusResponse(
            outcome=OUTCOME_FOUND,
            message=self._status_message(status),
            appointment=summary,
            next_steps=self._next_steps_for_status(status),
        )

    def _not_found_response(self, message: str) -> AppointmentStatusResponse:
        return AppointmentStatusResponse(
            outcome=OUTCOME_NOT_FOUND,
            message=message,
            next_steps=[
                {"action": "verify_appointment_code", "label": "Kiểm tra lại mã lịch hẹn"},
                {"action": "contact_reception", "label": "Liên hệ bộ phận tiếp nhận"},
            ],
        )

    def _redirected_response(self) -> AppointmentStatusResponse:
        return AppointmentStatusResponse(
            outcome=OUTCOME_REDIRECTED,
            message="Hệ thống tra cứu lịch hẹn đang tạm thời không khả dụng.",
            next_steps=[
                {"action": "contact_channel", "label": channel}
                for channel in self._channel_resolver()
            ],
            warnings=["appointment_lookup_redirected"],
        )

    def _unavailable_response(self) -> AppointmentStatusResponse:
        return AppointmentStatusResponse(
            outcome=OUTCOME_UNAVAILABLE,
            message="Chưa thể xác nhận trạng thái lịch hẹn. Vui lòng thử lại hoặc liên hệ tiếp nhận.",
            next_steps=[{"action": "contact_reception", "label": "Liên hệ bộ phận tiếp nhận"}],
            warnings=["appointment_status_unavailable"],
        )

    @staticmethod
    def _status_message(status: str) -> str:
        return {
            "pending": "Lịch hẹn đang chờ xác nhận.",
            "confirmed": "Lịch hẹn đã được xác nhận.",
            "cancelled": "Lịch hẹn đã bị hủy.",
            "rejected": "Lịch hẹn chưa được chấp nhận.",
            "completed": "Lịch hẹn đã hoàn tất.",
        }[status]

    @staticmethod
    def _next_steps_for_status(status: str) -> List[Dict[str, str]]:
        return {
            "pending": [{"action": "wait_for_confirmation", "label": "Chờ bệnh viện xác nhận"}],
            "confirmed": [{"action": "attend_appointment", "label": "Đến khám theo lịch hẹn"}],
            "cancelled": [{"action": "book_new_appointment", "label": "Đặt lịch hẹn mới"}],
            "rejected": [{"action": "contact_reception", "label": "Liên hệ bộ phận tiếp nhận"}],
            "completed": [{"action": "no_further_action", "label": "Lịch hẹn đã hoàn tất"}],
        }[status]


__all__ = [
    "AppointmentStatusPipeline",
    "AppointmentStatusRequest",
    "AppointmentStatusResponse",
    "OUTCOME_FOUND",
    "OUTCOME_NOT_FOUND",
    "OUTCOME_REDIRECTED",
    "OUTCOME_UNAVAILABLE",
]
# === TASK:WP-306:END ===

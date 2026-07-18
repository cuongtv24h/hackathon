# === TASK:WP-305:START ===
"""Appointment booking orchestration pipeline for PC-03.

The pipeline collects appointment data across turns, asks for explicit
confirmation, and only then invokes the injected appointment creation tool.
Substantive behavior lives in this snake_case leaf module per WP-305-R1.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Literal, Optional, Protocol, runtime_checkable

from apps.api.foundation.appointments.tools.service import CreateAppointmentInput

BookingStep = Literal[
    "visit_type",
    "specialty",
    "doctor",
    "slot",
    "patient_data",
    "confirmation",
    "created",
]
BookingOutcome = Literal[
    "collecting",
    "confirmation_required",
    "created",
    "error",
]

REQUIRED_PATIENT_FIELDS = ("patient_name", "patient_phone", "patient_dob", "has_insurance", "visit_reason")
ALLOWED_VISIT_TYPES = ("first_visit", "follow_up")
CONFIRMATION_WORDS = {"confirm", "confirmed", "yes", "đồng ý", "xac nhan", "xác nhận"}


@dataclass(frozen=True)
class PatientAppointmentDataDTO:
    """Collected patient data needed for appointment creation."""

    patient_name: str
    patient_phone: str
    patient_dob: str
    has_insurance: bool
    visit_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patient_name": self.patient_name,
            "patient_phone": self.patient_phone,
            "patient_dob": self.patient_dob,
            "has_insurance": self.has_insurance,
            "visit_reason": self.visit_reason,
        }


@dataclass(frozen=True)
class BookingFlowStateDTO:
    """Multi-turn state for PC-03 booking collection."""

    session_id: str
    current_step: BookingStep = "visit_type"
    visit_type: Optional[str] = None
    specialty_id: Optional[str] = None
    doctor_id: Optional[str] = None
    slot_id: Optional[str] = None
    patient_data: Optional[PatientAppointmentDataDTO] = None
    confirmation_token: Optional[str] = None
    idempotency_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "current_step": self.current_step,
            "visit_type": self.visit_type,
            "specialty_id": self.specialty_id,
            "doctor_id": self.doctor_id,
            "slot_id": self.slot_id,
            "patient_data": self.patient_data.to_dict() if self.patient_data else None,
            "confirmation_token": self.confirmation_token,
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True)
class AppointmentBookingRequest:
    """PC-03 orchestration request."""

    request_id: str
    session_id: str
    message: str = ""
    state: Optional[BookingFlowStateDTO] = None
    form_data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AppointmentBookingResponse:
    """PC-03 orchestration response."""

    outcome: BookingOutcome
    message: str
    conversation_state: BookingFlowStateDTO
    appointment: Optional[Dict[str, Any]] = None
    suggested_actions: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "outcome": self.outcome,
            "message": self.message,
            "conversation_state": self.conversation_state.to_dict(),
            "suggested_actions": list(self.suggested_actions),
        }
        if self.appointment is not None:
            result["appointment"] = dict(self.appointment)
        if self.error is not None:
            result["error"] = dict(self.error)
        return result


@runtime_checkable
class AppointmentCreationToolProtocol(Protocol):
    """Injected WP-203 appointment creation tool interface."""

    def create_appointment(self, input_data: CreateAppointmentInput) -> Any:
        """Create an appointment only after explicit confirmation."""
        ...


def _normalise_state(request: AppointmentBookingRequest) -> BookingFlowStateDTO:
    return request.state or BookingFlowStateDTO(session_id=request.session_id)


def _is_confirmed(message: str, form_data: Dict[str, Any]) -> bool:
    if form_data.get("confirmed") is True:
        return True
    return message.strip().lower() in CONFIRMATION_WORDS


def _appointment_to_dict(appointment: Any) -> Dict[str, Any]:
    if isinstance(appointment, dict):
        return dict(appointment)
    if hasattr(appointment, "to_dict"):
        return appointment.to_dict()
    return {
        "appointment_id": appointment.appointment_id,
        "doctor_id": appointment.doctor_id,
        "slot_id": appointment.slot_id,
        "status": appointment.status,
    }


def _confirmation_summary(state: BookingFlowStateDTO) -> str:
    patient = state.patient_data
    patient_text = patient.to_dict() if patient else {}
    return (
        "Vui lòng xác nhận thông tin đặt lịch: "
        f"loại khám={state.visit_type}, chuyên khoa={state.specialty_id}, "
        f"bác sĩ={state.doctor_id}, khung giờ={state.slot_id}, "
        f"bệnh nhân={patient_text}."
    )


class AppointmentBookingPipeline:
    """Collect, confirm, then create pending appointment for PC-03."""

    def __init__(self, *, appointment_tools: Optional[AppointmentCreationToolProtocol] = None) -> None:
        self._appointment_tools = appointment_tools

    def execute(self, request: AppointmentBookingRequest) -> AppointmentBookingResponse:
        """Advance the booking state by one turn without creating before confirmation."""
        state = _normalise_state(request)
        data = request.form_data

        try:
            state = self._collect_visit_type(state, data)
            if state.current_step == "visit_type":
                return self._ask(state, "Bạn muốn đặt lịch khám lần đầu hay tái khám?", "collect_visit_type")

            state = self._collect_specialty(state, data)
            if state.current_step == "specialty":
                return self._ask(state, "Vui lòng chọn chuyên khoa cần khám.", "collect_specialty")

            state = self._collect_doctor(state, data)
            if state.current_step == "doctor":
                return self._ask(state, "Vui lòng chọn bác sĩ phù hợp.", "collect_doctor")

            state = self._collect_slot(state, data)
            if state.current_step == "slot":
                return self._ask(state, "Vui lòng chọn khung giờ khám còn trống.", "collect_slot")

            state = self._collect_patient_data(state, data)
            if state.current_step == "patient_data":
                return self._ask(state, "Vui lòng cung cấp họ tên, số điện thoại, ngày sinh, BHYT và lý do khám.", "collect_patient_data")

            if state.current_step == "confirmation" and not _is_confirmed(request.message, data):
                return AppointmentBookingResponse(
                    outcome="confirmation_required",
                    message=_confirmation_summary(state),
                    conversation_state=state,
                    suggested_actions=[{"type": "confirm", "label": "Xác nhận đặt lịch"}],
                )

            return self._create_pending_appointment(state)
        except Exception as exc:
            return AppointmentBookingResponse(
                outcome="error",
                message="Không thể xử lý đặt lịch ở thời điểm này.",
                conversation_state=state,
                error={"code": "APPOINTMENT_BOOKING_FAILED", "message": str(exc)},
            )

    def _collect_visit_type(self, state: BookingFlowStateDTO, data: Dict[str, Any]) -> BookingFlowStateDTO:
        visit_type = state.visit_type or data.get("visit_type")
        if visit_type not in ALLOWED_VISIT_TYPES:
            return replace(state, current_step="visit_type")
        return replace(state, visit_type=visit_type, current_step="specialty")

    def _collect_specialty(self, state: BookingFlowStateDTO, data: Dict[str, Any]) -> BookingFlowStateDTO:
        specialty_id = state.specialty_id or data.get("specialty_id")
        if not specialty_id:
            return replace(state, current_step="specialty")
        return replace(state, specialty_id=specialty_id, current_step="doctor")

    def _collect_doctor(self, state: BookingFlowStateDTO, data: Dict[str, Any]) -> BookingFlowStateDTO:
        doctor_id = state.doctor_id or data.get("doctor_id")
        if not doctor_id:
            return replace(state, current_step="doctor")
        return replace(state, doctor_id=doctor_id, current_step="slot")

    def _collect_slot(self, state: BookingFlowStateDTO, data: Dict[str, Any]) -> BookingFlowStateDTO:
        slot_id = state.slot_id or data.get("slot_id")
        if not slot_id:
            return replace(state, current_step="slot")
        return replace(state, slot_id=slot_id, current_step="patient_data")

    def _collect_patient_data(self, state: BookingFlowStateDTO, data: Dict[str, Any]) -> BookingFlowStateDTO:
        if state.patient_data is not None:
            return replace(state, current_step="confirmation")
        if not all(field_name in data for field_name in REQUIRED_PATIENT_FIELDS):
            return replace(state, current_step="patient_data")
        patient = PatientAppointmentDataDTO(
            patient_name=str(data["patient_name"]),
            patient_phone=str(data["patient_phone"]),
            patient_dob=str(data["patient_dob"]),
            has_insurance=bool(data["has_insurance"]),
            visit_reason=str(data["visit_reason"]),
        )
        return replace(
            state,
            patient_data=patient,
            confirmation_token=state.confirmation_token or f"confirm-{uuid.uuid4()}",
            # The gateway copies the Idempotency-Key header into form_data.
            # Preserve it across the confirmation retry so Mock HIS receives
            # the same key even though this MVP pipeline is reconstructed per
            # HTTP request.
            idempotency_key=state.idempotency_key or data.get("idempotency_key") or f"booking-{state.session_id}-{uuid.uuid4()}",
            current_step="confirmation",
        )

    def _create_pending_appointment(self, state: BookingFlowStateDTO) -> AppointmentBookingResponse:
        if self._appointment_tools is None:
            raise RuntimeError("appointment creation tool is not configured")
        if not state.patient_data or not state.visit_type or not state.doctor_id or not state.slot_id:
            raise ValueError("appointment data is incomplete")
        created = self._appointment_tools.create_appointment(
            CreateAppointmentInput(
                doctor_id=state.doctor_id,
                slot_id=state.slot_id,
                patient_name=state.patient_data.patient_name,
                patient_phone=state.patient_data.patient_phone,
                patient_dob=state.patient_data.patient_dob,
                has_insurance=state.patient_data.has_insurance,
                visit_reason=state.patient_data.visit_reason,
                visit_type=state.visit_type,  # type: ignore[arg-type]
                confirmation_token=state.confirmation_token or "confirmed",
                idempotency_key=state.idempotency_key,
            )
        )
        appointment = _appointment_to_dict(created)
        final_state = replace(state, current_step="created")
        return AppointmentBookingResponse(
            outcome="created",
            message=f"Đã tạo lịch hẹn trạng thái pending. Mã lịch hẹn: {appointment.get('appointment_id')}.",
            conversation_state=final_state,
            appointment=appointment,
            suggested_actions=[{"type": "lookup", "appointment_id": appointment.get("appointment_id")}],
        )

    def _ask(self, state: BookingFlowStateDTO, message: str, action: str) -> AppointmentBookingResponse:
        return AppointmentBookingResponse(
            outcome="collecting",
            message=message,
            conversation_state=state,
            suggested_actions=[{"type": "provide", "field": action}],
        )


def run_appointment_booking(
    request: AppointmentBookingRequest,
    *,
    appointment_tools: Optional[AppointmentCreationToolProtocol] = None,
) -> AppointmentBookingResponse:
    """One-shot wrapper for appointment booking orchestration."""
    return AppointmentBookingPipeline(appointment_tools=appointment_tools).execute(request)


__all__ = [
    "AppointmentBookingPipeline",
    "AppointmentBookingRequest",
    "AppointmentBookingResponse",
    "BookingFlowStateDTO",
    "PatientAppointmentDataDTO",
    "run_appointment_booking",
]
# === TASK:WP-305:END ===

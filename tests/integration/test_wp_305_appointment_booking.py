# === TASK:WP-305:START ===
"""Integration tests for WP-305 appointment booking orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from apps.api.ai.orchestrator.appointment_booking.pipeline import (
    AppointmentBookingPipeline,
    AppointmentBookingRequest,
    AppointmentBookingResponse,
    BookingFlowStateDTO,
)


@dataclass(frozen=True)
class FakeAppointmentOutput:
    appointment_id: str
    doctor_id: str
    slot_id: str
    patient_name: str
    patient_phone: str
    patient_dob: str
    has_insurance: bool
    visit_reason: str
    visit_type: str
    status: str = "pending"
    rejection_reason: str | None = None
    created_at: str = "2026-07-18T06:00:00Z"
    updated_at: str = "2026-07-18T06:00:00Z"

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class FakeAppointmentTools:
    """Fake WP-203 appointment tools with no provider or network calls."""

    def __init__(self) -> None:
        self.created_inputs: List[Any] = []

    def create_appointment(self, input_data: Any) -> FakeAppointmentOutput:
        self.created_inputs.append(input_data)
        return FakeAppointmentOutput(
            appointment_id="HEN-2026-0001",
            doctor_id=input_data.doctor_id,
            slot_id=input_data.slot_id,
            patient_name=input_data.patient_name,
            patient_phone=input_data.patient_phone,
            patient_dob=input_data.patient_dob,
            has_insurance=input_data.has_insurance,
            visit_reason=input_data.visit_reason,
            visit_type=input_data.visit_type,
        )


def _request(form_data: Dict[str, Any], state: BookingFlowStateDTO | None = None, message: str = "") -> AppointmentBookingRequest:
    return AppointmentBookingRequest(
        request_id="REQ-305",
        session_id="SESSION-305",
        message=message,
        state=state,
        form_data=form_data,
    )


def _complete_form() -> Dict[str, Any]:
    return {
        "visit_type": "first_visit",
        "specialty_id": "SP-001",
        "doctor_id": "DR-001",
        "slot_id": "SLOT-001",
        "patient_name": "Nguyen Van A",
        "patient_phone": "0901234567",
        "patient_dob": "1990-01-01",
        "has_insurance": True,
        "visit_reason": "Đau ngực khi gắng sức",
    }


def test_collects_data_and_requires_confirmation_before_create() -> None:
    tools = FakeAppointmentTools()
    pipeline = AppointmentBookingPipeline(appointment_tools=tools)

    response = pipeline.execute(_request(_complete_form()))

    assert response.outcome == "confirmation_required"
    assert response.conversation_state.current_step == "confirmation"
    assert response.conversation_state.visit_type == "first_visit"
    assert response.conversation_state.patient_data is not None
    assert "Xác nhận" in response.suggested_actions[0]["label"]
    assert tools.created_inputs == []


def test_preserves_gateway_idempotency_key_in_reconstructed_state() -> None:
    tools = FakeAppointmentTools()
    pipeline = AppointmentBookingPipeline(appointment_tools=tools)
    form_data = _complete_form()
    form_data["idempotency_key"] = "e2e-booking-key"

    confirmation = pipeline.execute(_request(form_data))
    created = pipeline.execute(
        _request(form_data | {"confirmed": True}, message="confirm")
    )

    assert confirmation.conversation_state.idempotency_key == "e2e-booking-key"
    assert created.outcome == "created"
    assert tools.created_inputs[0].idempotency_key == "e2e-booking-key"


def test_confirmed_request_creates_pending_appointment_with_contract_shape() -> None:
    tools = FakeAppointmentTools()
    pipeline = AppointmentBookingPipeline(appointment_tools=tools)
    confirmation_response = pipeline.execute(_request(_complete_form()))

    response = pipeline.execute(
        _request({}, state=confirmation_response.conversation_state, message="xác nhận")
    )
    as_dict = response.to_dict()

    assert response.outcome == "created"
    assert response.conversation_state.current_step == "created"
    assert response.appointment is not None
    assert response.appointment["appointment_id"] == "HEN-2026-0001"
    assert response.appointment["status"] == "pending"
    assert len(tools.created_inputs) == 1
    assert tools.created_inputs[0].confirmation_token.startswith("confirm-")
    assert set(as_dict) >= {"outcome", "message", "conversation_state", "suggested_actions", "appointment"}
    assert as_dict["appointment"]["appointment_id"].startswith("HEN-")


def test_missing_data_advances_to_expected_collection_step_without_create() -> None:
    tools = FakeAppointmentTools()
    pipeline = AppointmentBookingPipeline(appointment_tools=tools)

    response = pipeline.execute(_request({"visit_type": "follow_up", "specialty_id": "SP-001"}))

    assert response.outcome == "collecting"
    assert response.conversation_state.current_step == "doctor"
    assert response.suggested_actions == [{"type": "provide", "field": "collect_doctor"}]
    assert tools.created_inputs == []


def test_invalid_visit_type_is_edge_case_and_keeps_visit_type_step() -> None:
    tools = FakeAppointmentTools()
    pipeline = AppointmentBookingPipeline(appointment_tools=tools)

    response: AppointmentBookingResponse = pipeline.execute(_request({"visit_type": "surgery"}))

    assert response.outcome == "collecting"
    assert response.conversation_state.current_step == "visit_type"
    assert response.conversation_state.visit_type is None
    assert tools.created_inputs == []
# === TASK:WP-305:END ===

# === TASK:WP-306:START ===
"""Integration tests for the WP-306 appointment-status pipeline."""

from dataclasses import dataclass

import pytest

from apps.api.ai.orchestrator.appointment_status.pipeline import (
    AppointmentStatusPipeline,
    AppointmentStatusRequest,
    OUTCOME_FOUND,
    OUTCOME_NOT_FOUND,
    OUTCOME_REDIRECTED,
    OUTCOME_UNAVAILABLE,
)
from apps.api.foundation.appointments.tools.service import AppointmentToolError
from packages.contracts import CATEGORY_TOOL, INTEGRATION_UNAVAILABLE, make_error_envelope


@dataclass
class FakeAppointment:
    appointment_id: str = "HEN-2026-0001"
    doctor_id: str = "DR-001"
    slot_id: str = "SLOT-001"
    status: str = "pending"
    created_at: str = "2026-07-18T00:00:00+00:00"
    updated_at: str = "2026-07-18T00:00:00+00:00"
    patient_name: str = "Must not be exposed"
    patient_phone: str = "0900000000"


class FakeAppointmentTools:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.requested_ids = []

    def lookup_appointment(self, input_data):
        self.requested_ids.append(input_data.appointment_id)
        if self.error:
            raise self.error
        return self.result


def make_request(appointment_id="HEN-2026-0001"):
    return AppointmentStatusRequest(
        request_id="req-306",
        session_id="ses-306",
        appointment_reference={"appointment_id": appointment_id},
    )


@pytest.mark.parametrize("status", ["pending", "confirmed", "cancelled", "rejected", "completed"])
def test_found_status_returns_minimal_summary_and_next_step(status):
    tools = FakeAppointmentTools(result=FakeAppointment(status=status))
    response = AppointmentStatusPipeline(appointment_tools=tools).execute(make_request())

    assert response.outcome == OUTCOME_FOUND
    assert response.appointment["status"] == status
    assert response.next_steps
    assert "patient_name" not in response.appointment
    assert "patient_phone" not in response.appointment


def test_not_found_never_requests_extra_pii():
    tools = FakeAppointmentTools(result=None)
    response = AppointmentStatusPipeline(appointment_tools=tools).execute(make_request())

    assert response.outcome == OUTCOME_NOT_FOUND
    assert tools.requested_ids == ["HEN-2026-0001"]
    assert any(item["action"] == "verify_appointment_code" for item in response.next_steps)


def test_invalid_reference_returns_safe_not_found_without_lookup():
    tools = FakeAppointmentTools(result=FakeAppointment())
    response = AppointmentStatusPipeline(appointment_tools=tools).execute(make_request("bad"))

    assert response.outcome == OUTCOME_NOT_FOUND
    assert tools.requested_ids == []


def test_tool_unavailable_redirects_to_configured_channels():
    error = AppointmentToolError(make_error_envelope(
        code=INTEGRATION_UNAVAILABLE,
        message="HIS unavailable",
        category=CATEGORY_TOOL,
        retryable=True,
    ))
    tools = FakeAppointmentTools(error=error)
    response = AppointmentStatusPipeline(
        appointment_tools=tools,
        channel_resolver=lambda: ["pilot-hotline"],
    ).execute(make_request())

    assert response.outcome == OUTCOME_REDIRECTED
    assert response.next_steps == [{"action": "contact_channel", "label": "pilot-hotline"}]


def test_unexpected_status_is_not_inferred():
    tools = FakeAppointmentTools(result=FakeAppointment(status="mystery"))
    response = AppointmentStatusPipeline(appointment_tools=tools).execute(make_request())

    assert response.outcome == OUTCOME_UNAVAILABLE
    assert response.appointment is None


def test_request_validation_and_response_serialization():
    with pytest.raises(ValueError, match="request_id"):
        AppointmentStatusRequest("", "ses-306", {"appointment_id": "HEN-2026-0001"})

    response = AppointmentStatusPipeline(
        appointment_tools=FakeAppointmentTools(result=FakeAppointment())
    ).execute(make_request())
    serialized = response.to_dict()
    assert serialized["outcome"] == OUTCOME_FOUND
    assert serialized["appointment"]["appointment_id"] == "HEN-2026-0001"
# === TASK:WP-306:END ===

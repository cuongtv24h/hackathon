# === TASK:WP-203:START ===
import pytest
from apps.api.foundation.appointments.tools import book_appointment_mock, MockBookingRequest

def test_mock_booking_tool_returns_receipt_without_side_effects():
    req = MockBookingRequest(
        doctor_id="doc-123",
        patient_name="Nguyen Van A",
        patient_phone="0901234567",
        schedule_date="2026-07-20",
        time_slot="09:00-09:30"
    )

    result = book_appointment_mock(req)
    assert result["outcome"] == "success"
    assert "appointment" in result

    apt = result["appointment"]
    assert apt["appointment_id"] == "MOCK-APT-99999"
    assert apt["status"] == "mock_pending"
    assert "demo" in apt["detail"]
# === TASK:WP-203:END ===

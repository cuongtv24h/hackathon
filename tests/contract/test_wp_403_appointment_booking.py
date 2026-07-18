# === TASK:WP-403:START ===
"""Contract tests for WP-403 PC-03 Appointment Booking gateway router."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.ai.orchestrator.appointment_booking.pipeline import (
    AppointmentBookingResponse,
    BookingFlowStateDTO,
    PatientAppointmentDataDTO,
)
from apps.api.gateway.capabilities.appointment_booking.router import (
    CAPABILITY_NAME,
    CAPABILITY_ROUTE,
    router,
    set_appointment_booking_pipeline,
)


class FakePipeline:
    """Network/provider-free fake for gateway contract tests."""

    def __init__(self, response: AppointmentBookingResponse) -> None:
        self.response = response
        self.seen_request = None

    def execute(self, request):  # type: ignore[no-untyped-def]
        self.seen_request = request
        return self.response


def make_client(fake_pipeline: FakePipeline) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    set_appointment_booking_pipeline(fake_pipeline)  # type: ignore[arg-type]
    return TestClient(app)


def make_payload(**overrides):  # type: ignore[no-untyped-def]
    payload = {
        "request_id": "req-403",
        "session_id": "sess-403",
        "message": "Tôi muốn đặt lịch khám",
        "conversation_history": [],
        "response_mode": "sync",
        "client_context": {"channel": "web_widget", "locale": "vi-VN"},
        "form_data": {},
    }
    payload.update(overrides)
    return payload


def collecting_state() -> BookingFlowStateDTO:
    return BookingFlowStateDTO(
        session_id="sess-403",
        current_step="visit_type",
        visit_type=None,
        specialty_id=None,
        doctor_id=None,
        slot_id=None,
        patient_data=None,
        confirmation_token=None,
    )


def confirmation_required_state() -> BookingFlowStateDTO:
    return BookingFlowStateDTO(
        session_id="sess-403",
        current_step="confirmation",
        visit_type="first_visit",
        specialty_id="SP-001",
        doctor_id="DR-001",
        slot_id="SLOT-001",
        patient_data=PatientAppointmentDataDTO(
            patient_name="Nguyen Van A",
            patient_phone="0901234567",
            patient_dob="1990-01-01",
            has_insurance=True,
            visit_reason="Đau ngực khi gắng sức",
        ),
        confirmation_token="confirm-abc123",
    )


def created_state() -> BookingFlowStateDTO:
    return BookingFlowStateDTO(
        session_id="sess-403",
        current_step="created",
        visit_type="first_visit",
        specialty_id="SP-001",
        doctor_id="DR-001",
        slot_id="SLOT-001",
        patient_data=PatientAppointmentDataDTO(
            patient_name="Nguyen Van A",
            patient_phone="0901234567",
            patient_dob="1990-01-01",
            has_insurance=True,
            visit_reason="Đau ngực khi gắng sức",
        ),
        confirmation_token="confirm-abc123",
    )


def collecting_response() -> AppointmentBookingResponse:
    return AppointmentBookingResponse(
        outcome="collecting",
        message="Vui lòng chọn loại khám: khám lần đầu hay khám lại?",
        conversation_state=collecting_state(),
        suggested_actions=[{"type": "provide", "field": "collect_visit_type"}],
    )


def confirmation_required_response() -> AppointmentBookingResponse:
    return AppointmentBookingResponse(
        outcome="confirmation_required",
        message="Xác nhận đặt lịch khám lần đầu cho bác sĩ DR-001 vào khung giờ SLOT-001?",
        conversation_state=confirmation_required_state(),
        suggested_actions=[
            {"type": "confirm", "label": "Xác nhận đặt lịch"},
            {"type": "cancel", "label": "Hủy"},
        ],
    )


def created_response() -> AppointmentBookingResponse:
    return AppointmentBookingResponse(
        outcome="created",
        message="Đã tạo lịch hẹn HEN-2026-0001. Trạng thái: pending.",
        conversation_state=created_state(),
        appointment={
            "appointment_id": "HEN-2026-0001",
            "doctor_id": "DR-001",
            "slot_id": "SLOT-001",
            "patient_name": "Nguyen Van A",
            "patient_phone": "0901234567",
            "patient_dob": "1990-01-01",
            "has_insurance": True,
            "visit_reason": "Đau ngực khi gắng sức",
            "visit_type": "first_visit",
            "status": "pending",
            "rejection_reason": None,
            "created_at": "2026-07-18T06:00:00Z",
            "updated_at": "2026-07-18T06:00:00Z",
        },
        suggested_actions=[],
    )


def test_appointment_booking_sync_collecting_contract_shape() -> None:
    fake_pipeline = FakePipeline(collecting_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(),
        headers={"x-trace-id": "trace-403"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trace-403"
    assert body["request_id"] == "req-403"
    assert body["capability"] == CAPABILITY_NAME
    assert body["outcome"] == "collecting"
    assert body["timestamp"]
    assert body["errors"] == []
    assert body["warnings"] == []
    assert body["result"]["message"] == "Vui lòng chọn loại khám: khám lần đầu hay khám lại?"
    assert body["result"]["conversation_state"]["current_step"] == "visit_type"
    assert body["result"]["suggested_actions"] == [{"type": "provide", "field": "collect_visit_type"}]
    assert fake_pipeline.seen_request.request_id == "req-403"
    assert fake_pipeline.seen_request.form_data == {}


def test_appointment_booking_sync_confirmation_required_contract_shape() -> None:
    fake_pipeline = FakePipeline(confirmation_required_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(),
        headers={"x-trace-id": "trace-403-confirm"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trace-403-confirm"
    assert body["request_id"] == "req-403"
    assert body["capability"] == CAPABILITY_NAME
    assert body["outcome"] == "confirmation_required"
    assert body["result"]["conversation_state"]["current_step"] == "confirmation"
    assert body["result"]["conversation_state"]["confirmation_token"] == "confirm-abc123"
    assert body["result"]["suggested_actions"] == [
        {"type": "confirm", "label": "Xác nhận đặt lịch"},
        {"type": "cancel", "label": "Hủy"},
    ]


def test_appointment_booking_sync_created_contract_shape() -> None:
    fake_pipeline = FakePipeline(created_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(),
        headers={"x-trace-id": "trace-403-created"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trace-403-created"
    assert body["request_id"] == "req-403"
    assert body["capability"] == CAPABILITY_NAME
    assert body["outcome"] == "created"
    assert body["result"]["appointment"]["appointment_id"] == "HEN-2026-0001"
    assert body["result"]["appointment"]["status"] == "pending"
    assert body["result"]["appointment"]["doctor_id"] == "DR-001"
    assert body["result"]["appointment"]["slot_id"] == "SLOT-001"
    assert body["result"]["conversation_state"]["current_step"] == "created"
    assert body["result"]["suggested_actions"] == []


def test_appointment_booking_stream_keeps_completed_envelope_semantics() -> None:
    fake_pipeline = FakePipeline(created_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(response_mode="stream"),
        headers={"x-trace-id": "trace-stream-403"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: ack" in response.text
    assert "event: completed" in response.text
    completed_line = [
        line for line in response.text.splitlines() if line.startswith("data: {")
    ][-1]
    completed = json.loads(completed_line.removeprefix("data: "))
    assert completed["trace_id"] == "trace-stream-403"
    assert completed["capability"] == CAPABILITY_NAME
    assert completed["outcome"] == "created"
    assert completed["result"]["appointment"]["appointment_id"] == "HEN-2026-0001"


def test_appointment_booking_validation_rejects_invalid_response_mode() -> None:
    fake_pipeline = FakePipeline(collecting_response())
    client = make_client(fake_pipeline)

    response = client.post(CAPABILITY_ROUTE, json=make_payload(response_mode="xml"))

    assert response.status_code == 422
    assert fake_pipeline.seen_request is None


def test_appointment_booking_validation_rejects_empty_message() -> None:
    fake_pipeline = FakePipeline(collecting_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(message="   "),
    )

    assert response.status_code == 422
    assert fake_pipeline.seen_request is None


def test_appointment_booking_validation_rejects_excessive_history() -> None:
    fake_pipeline = FakePipeline(collecting_response())
    client = make_client(fake_pipeline)

    history = [{"role": "user", "content": f"msg{i}"} for i in range(21)]
    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(conversation_history=history),
    )

    assert response.status_code == 422
    assert fake_pipeline.seen_request is None


def test_appointment_booking_form_data_passthrough() -> None:
    fake_pipeline = FakePipeline(collecting_response())
    client = make_client(fake_pipeline)

    form_data = {
        "visit_type": "first_visit",
        "specialty_id": "SP-001",
        "doctor_id": "DR-001",
    }
    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(form_data=form_data),
        headers={"x-trace-id": "trace-403-form"},
    )

    assert response.status_code == 200
    assert fake_pipeline.seen_request.form_data == form_data


def test_appointment_booking_requires_idempotency_key_for_create_confirmation() -> None:
    fake_pipeline = FakePipeline(created_response())
    client = make_client(fake_pipeline)

    response = client.post(CAPABILITY_ROUTE, json=make_payload(message="xác nhận"))

    assert response.status_code == 400
    assert fake_pipeline.seen_request is None


def test_appointment_booking_passes_idempotency_key_to_pipeline_form_data() -> None:
    fake_pipeline = FakePipeline(created_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(message="xác nhận"),
        headers={"idempotency-key": "idem-403", "x-trace-id": "trace-idem-403"},
    )

    assert response.status_code == 200
    assert fake_pipeline.seen_request.form_data["idempotency_key"] == "idem-403"
# === TASK:WP-403:END ===
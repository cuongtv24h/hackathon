# === TASK:WP-604:START ===
"""WP-604 appointment booking/status QA integration tests.

These tests exercise PC-03 and PC-04 through the FastAPI gateway routers with
provider/network-free fakes. They verify booking creates remain pending,
idempotent duplicate confirmations do not create duplicate appointments, and
status lookup covers found, not-found, and upstream error paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.ai.orchestrator.appointment_booking.pipeline import (
    AppointmentBookingResponse,
    BookingFlowStateDTO,
    PatientAppointmentDataDTO,
)
from apps.api.gateway.capabilities.appointment_booking.router import (
    CAPABILITY_ROUTE as BOOKING_ROUTE,
    router as booking_router,
    set_appointment_booking_pipeline,
)
from apps.api.gateway.capabilities.appointment_status.router import (
    CAPABILITY_ROUTE as STATUS_ROUTE,
    router as status_router,
    set_appointment_status_pipeline,
)


@dataclass(frozen=True)
class StoredAppointment:
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
    created_at: str = "2026-07-18T06:04:00Z"
    updated_at: str = "2026-07-18T06:04:00Z"

    def to_booking_dict(self) -> dict[str, Any]:
        return {
            "appointment_id": self.appointment_id,
            "doctor_id": self.doctor_id,
            "slot_id": self.slot_id,
            "patient_name": self.patient_name,
            "patient_phone": self.patient_phone,
            "patient_dob": self.patient_dob,
            "has_insurance": self.has_insurance,
            "visit_reason": self.visit_reason,
            "visit_type": self.visit_type,
            "status": self.status,
            "rejection_reason": None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_status_dict(self) -> dict[str, Any]:
        return {
            "appointment_id": self.appointment_id,
            "doctor_id": self.doctor_id,
            "slot_id": self.slot_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class FakeAppointmentLedger:
    """In-memory Mock HIS fake with idempotent create semantics."""

    def __init__(self) -> None:
        self.appointments: dict[str, StoredAppointment] = {}
        self.idempotency_index: dict[str, str] = {}
        self.create_attempts = 0
        self.raise_lookup_error = False

    def create_pending_appointment(self, form_data: dict[str, Any]) -> StoredAppointment:
        self.create_attempts += 1
        idempotency_key = form_data["idempotency_key"]
        existing_id = self.idempotency_index.get(idempotency_key)
        if existing_id:
            return self.appointments[existing_id]

        appointment_id = f"HEN-2026-{len(self.appointments) + 1:04d}"
        appointment = StoredAppointment(
            appointment_id=appointment_id,
            doctor_id=form_data["doctor_id"],
            slot_id=form_data["slot_id"],
            patient_name=form_data["patient_name"],
            patient_phone=form_data["patient_phone"],
            patient_dob=form_data["patient_dob"],
            has_insurance=form_data["has_insurance"],
            visit_reason=form_data["visit_reason"],
            visit_type=form_data["visit_type"],
        )
        self.appointments[appointment_id] = appointment
        self.idempotency_index[idempotency_key] = appointment_id
        return appointment

    def lookup_appointment(self, appointment_id: str) -> StoredAppointment | None:
        if self.raise_lookup_error:
            raise RuntimeError("mock HIS unavailable")
        return self.appointments.get(appointment_id)


class FakeBookingPipeline:
    """Gateway-facing booking fake that preserves WP-403 response contract."""

    def __init__(self, ledger: FakeAppointmentLedger) -> None:
        self.ledger = ledger

    def execute(self, request: Any) -> AppointmentBookingResponse:
        form_data = request.form_data
        appointment = self.ledger.create_pending_appointment(form_data)
        return AppointmentBookingResponse(
            outcome="created",
            message=f"Đã tạo lịch hẹn {appointment.appointment_id}. Trạng thái: pending.",
            conversation_state=BookingFlowStateDTO(
                session_id=request.session_id,
                current_step="created",
                visit_type=appointment.visit_type,
                specialty_id=form_data["specialty_id"],
                doctor_id=appointment.doctor_id,
                slot_id=appointment.slot_id,
                patient_data=PatientAppointmentDataDTO(
                    patient_name=appointment.patient_name,
                    patient_phone=appointment.patient_phone,
                    patient_dob=appointment.patient_dob,
                    has_insurance=appointment.has_insurance,
                    visit_reason=appointment.visit_reason,
                ),
                confirmation_token="confirm-wp-604",
            ),
            appointment=appointment.to_booking_dict(),
            suggested_actions=[],
        )


@dataclass(frozen=True)
class FakeStatusResponse:
    outcome: str
    message: str
    appointment: dict[str, Any] | None = None
    next_steps: list[dict[str, str]] | None = None
    warnings: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "message": self.message,
            "appointment": self.appointment,
            "next_steps": list(self.next_steps or []),
            "warnings": list(self.warnings or []),
        }


class FakeStatusPipeline:
    """Gateway-facing status fake covering found/not-found/error lookup paths."""

    def __init__(self, ledger: FakeAppointmentLedger) -> None:
        self.ledger = ledger

    def execute(self, request: Any) -> FakeStatusResponse:
        appointment_id = request.appointment_reference["appointment_id"]
        try:
            appointment = self.ledger.lookup_appointment(appointment_id)
        except RuntimeError:
            return FakeStatusResponse(
                outcome="redirected",
                message="Không thể tra cứu lịch hẹn lúc này. Vui lòng liên hệ bệnh viện.",
                next_steps=[{"action": "contact_channel", "label": "Hotline bệnh viện"}],
                warnings=["appointment_lookup_redirected"],
            )
        if appointment is None:
            return FakeStatusResponse(
                outcome="not_found",
                message="Không tìm thấy lịch hẹn với mã đã cung cấp.",
                next_steps=[{"action": "verify_appointment_code", "label": "Kiểm tra lại mã lịch hẹn"}],
            )
        return FakeStatusResponse(
            outcome="found",
            message="Lịch hẹn đang chờ xác nhận.",
            appointment=appointment.to_status_dict(),
            next_steps=[{"action": "wait_for_confirmation", "label": "Chờ bệnh viện xác nhận"}],
        )


def build_client(ledger: FakeAppointmentLedger) -> TestClient:
    app = FastAPI()
    app.include_router(booking_router)
    app.include_router(status_router)
    set_appointment_booking_pipeline(FakeBookingPipeline(ledger))  # type: ignore[arg-type]
    set_appointment_status_pipeline(FakeStatusPipeline(ledger))  # type: ignore[arg-type]
    return TestClient(app)


def booking_payload(**form_overrides: Any) -> dict[str, Any]:
    form_data = {
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
    form_data.update(form_overrides)
    return {
        "request_id": "req-604-book",
        "session_id": "ses-604",
        "message": "xác nhận",
        "conversation_history": [],
        "response_mode": "sync",
        "client_context": {"channel": "web_widget", "locale": "vi-VN"},
        "form_data": form_data,
    }


def status_payload(appointment_id: str) -> dict[str, Any]:
    return {
        "request_id": "req-604-status",
        "session_id": "ses-604",
        "appointment_reference": {"appointment_id": appointment_id},
    }


def test_booking_create_is_pending_and_idempotent_without_duplicate() -> None:
    ledger = FakeAppointmentLedger()
    client = build_client(ledger)

    first = client.post(
        BOOKING_ROUTE,
        json=booking_payload(),
        headers={"idempotency-key": "idem-wp-604", "x-trace-id": "trace-604-create-1"},
    )
    second = client.post(
        BOOKING_ROUTE,
        json=booking_payload(),
        headers={"idempotency-key": "idem-wp-604", "x-trace-id": "trace-604-create-2"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["capability"] == "appointment_booking"
    assert first_body["outcome"] == "created"
    assert first_body["result"]["appointment"]["status"] == "pending"
    assert first_body["result"]["appointment"]["appointment_id"] == "HEN-2026-0001"
    assert second_body["result"]["appointment"]["appointment_id"] == "HEN-2026-0001"
    assert len(ledger.appointments) == 1
    assert ledger.create_attempts == 2


def test_booking_create_confirmation_requires_idempotency_key() -> None:
    ledger = FakeAppointmentLedger()
    client = build_client(ledger)

    response = client.post(BOOKING_ROUTE, json=booking_payload())

    assert response.status_code == 400
    assert ledger.appointments == {}


def test_status_lookup_found_uses_created_pending_appointment_contract_shape() -> None:
    ledger = FakeAppointmentLedger()
    client = build_client(ledger)
    create_response = client.post(
        BOOKING_ROUTE,
        json=booking_payload(),
        headers={"idempotency-key": "idem-wp-604-status"},
    )
    appointment_id = create_response.json()["result"]["appointment"]["appointment_id"]

    response = client.post(STATUS_ROUTE, json=status_payload(appointment_id), headers={"x-trace-id": "trace-604-status"})

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trace-604-status"
    assert body["capability"] == "appointment_status"
    assert body["outcome"] == "found"
    assert body["result"]["appointment"] == {
        "appointment_id": "HEN-2026-0001",
        "doctor_id": "DR-001",
        "slot_id": "SLOT-001",
        "status": "pending",
        "created_at": "2026-07-18T06:04:00Z",
        "updated_at": "2026-07-18T06:04:00Z",
    }
    assert "patient_name" not in body["result"]["appointment"]
    assert body["errors"] == []


def test_status_lookup_not_found_returns_safe_next_step() -> None:
    ledger = FakeAppointmentLedger()
    client = build_client(ledger)

    response = client.post(STATUS_ROUTE, json=status_payload("HEN-2026-9999"))

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "not_found"
    assert body["result"]["appointment"] is None
    assert body["result"]["next_steps"] == [
        {"action": "verify_appointment_code", "label": "Kiểm tra lại mã lịch hẹn"}
    ]
    assert body["errors"] == []


def test_status_lookup_error_redirects_without_provider_or_network_call() -> None:
    ledger = FakeAppointmentLedger()
    ledger.raise_lookup_error = True
    client = build_client(ledger)

    response = client.post(STATUS_ROUTE, json=status_payload("HEN-2026-0001"))

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "redirected"
    assert body["warnings"] == ["appointment_lookup_redirected"]
    assert body["result"]["next_steps"] == [{"action": "contact_channel", "label": "Hotline bệnh viện"}]
# === TASK:WP-604:END ===

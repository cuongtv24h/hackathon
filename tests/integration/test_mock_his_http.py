"""HTTP integration coverage for the pilot Mock HIS boundary."""

from contextlib import contextmanager
import socket
from threading import Thread
import time

from fastapi.testclient import TestClient
import pytest
import uvicorn

from apps.api.foundation.appointments.service import (
    AppointmentService,
    AppointmentServiceError,
    MockHISClient,
    PatientAppointmentDataDTO,
)
from apps.mock_his.main import create_app
from apps.mock_his.service import MockHISStore


@contextmanager
def running_mock_his(app):
    """Start a real local HTTP server so the HIS client crosses HTTP."""
    socket_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket_listener.bind(("127.0.0.1", 0))
    port = socket_listener.getsockname()[1]
    socket_listener.close()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        raise RuntimeError("Mock HIS test server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_mock_his_exposes_seeded_lookup_endpoints():
    client = TestClient(create_app(MockHISStore()))
    assert client.get("/health").json()["is_mock"] is True
    assert len(client.get("/mock-his/specialties").json()["specialties"]) == 5
    assert len(client.get("/mock-his/doctors").json()["doctors"]) == 10
    assert len(client.get("/mock-his/slots").json()["slots"]) == 20


def test_mock_his_creates_pending_appointment_once():
    client = TestClient(create_app(MockHISStore()))
    body = {
        "doctor_id": "DOC-001", "slot_id": "SL-001", "patient_name": "Test Patient",
        "patient_phone": "0900000099", "patient_dob": "1990-01-01", "has_insurance": True,
        "visit_reason": "Pilot test", "visit_type": "first_visit",
        "confirmation_token": "confirmed", "idempotency_key": "test-key-001",
    }
    first = client.post("/mock-his/appointments", json=body)
    second = client.post("/mock-his/appointments", json=body)
    assert first.status_code == 201
    assert first.json()["status"] == "pending"
    assert second.json()["appointment_id"] == first.json()["appointment_id"]
    assert client.get("/mock-his/appointments/" + first.json()["appointment_id"]).status_code == 200


def test_appointment_service_translates_live_http_domain_errors():
    store = MockHISStore()
    app = create_app(store)
    with running_mock_his(app) as base_url:
        service = AppointmentService(MockHISClient(base_url))
        assert service.list_doctors(specialty_id="SP-CARD-GEN").total == 3
        with pytest.raises(AppointmentServiceError) as error:
            service.get_appointment("HEN-2026-9999")
        assert error.value.envelope.error.code == "APPOINTMENT_NOT_FOUND"

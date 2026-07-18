# === TASK:WP-404:START ===
"""Contract tests for the WP-404 appointment-status capability API."""

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.gateway.capabilities.appointment_status.router import (
    CAPABILITY_ROUTE,
    router,
    set_appointment_status_pipeline,
)


@dataclass
class FakePipelineResponse:
    outcome: str = "found"
    warnings: list[str] | None = None

    def to_dict(self):
        return {
            "outcome": self.outcome,
            "message": "Lịch hẹn đang chờ xác nhận.",
            "next_steps": [
                {"action": "wait_for_confirmation", "label": "Chờ bệnh viện xác nhận"}
            ],
            "appointment": {
                "appointment_id": "HEN-2026-0001",
                "doctor_id": "DR-001",
                "slot_id": "SLOT-001",
                "status": "pending",
                "created_at": "2026-07-18T00:00:00+00:00",
                "updated_at": "2026-07-18T00:00:00+00:00",
            },
            "warnings": list(self.warnings or []),
        }


class FakeAppointmentStatusPipeline:
    def __init__(self, response=None):
        self.response = response or FakePipelineResponse()
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.response


def build_client(pipeline):
    app = FastAPI()
    app.include_router(router)
    set_appointment_status_pipeline(pipeline)
    return TestClient(app)


def test_execute_appointment_status_returns_canonical_envelope():
    pipeline = FakeAppointmentStatusPipeline()
    client = build_client(pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json={
            "request_id": "req-404",
            "session_id": "ses-404",
            "appointment_reference": {"appointment_id": "HEN-2026-0001"},
        },
        headers={"x-trace-id": "trace-404"},
    )

    assert response.status_code == 200
    body = response.json()
    assert response.headers["x-trace-id"] == "trace-404"
    assert body["trace_id"] == "trace-404"
    assert body["request_id"] == "req-404"
    assert body["capability"] == "appointment_status"
    assert body["outcome"] == "found"
    assert body["result"]["appointment"]["appointment_id"] == "HEN-2026-0001"
    assert body["result"]["appointment"]["status"] == "pending"
    assert body["explainability"]["reference_fields_used"] == ["appointment_id"]
    assert body["warnings"] == []
    assert body["errors"] == []
    assert "timestamp" in body
    assert pipeline.requests[0].request_id == "req-404"
    assert pipeline.requests[0].session_id == "ses-404"
    assert pipeline.requests[0].appointment_reference == {"appointment_id": "HEN-2026-0001"}


def test_execute_appointment_status_stream_returns_ack_and_completed_events():
    pipeline = FakeAppointmentStatusPipeline()
    client = build_client(pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json={
            "request_id": "req-404-stream",
            "session_id": "ses-404",
            "appointment_reference": {"appointment_id": "HEN-2026-0001"},
            "response_mode": "stream",
        },
        headers={"x-trace-id": "trace-stream-404"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: ack" in response.text
    assert "event: completed" in response.text
    assert '"capability": "appointment_status"' in response.text
    assert '"outcome": "found"' in response.text


def test_execute_appointment_status_rejects_extra_reference_fields():
    pipeline = FakeAppointmentStatusPipeline()
    client = build_client(pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json={
            "request_id": "req-404-extra",
            "session_id": "ses-404",
            "appointment_reference": {
                "appointment_id": "HEN-2026-0001",
                "phone_number": "0900000000",
            },
        },
    )

    assert response.status_code == 422
    assert pipeline.requests == []


def test_execute_appointment_status_rejects_invalid_response_mode():
    pipeline = FakeAppointmentStatusPipeline()
    client = build_client(pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json={
            "request_id": "req-404-mode",
            "session_id": "ses-404",
            "appointment_reference": {"appointment_id": "HEN-2026-0001"},
            "response_mode": "poll",
        },
    )

    assert response.status_code == 422
    assert pipeline.requests == []


def test_execute_appointment_status_maps_not_found_contract_shape():
    pipeline = FakeAppointmentStatusPipeline(
        FakePipelineResponse(outcome="not_found", warnings=["appointment_lookup_redirected"])
    )
    client = build_client(pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json={
            "request_id": "req-404-not-found",
            "session_id": "ses-404",
            "appointment_reference": {"appointment_id": "HEN-2026-9999"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "not_found"
    assert body["result"]["outcome"] == "not_found"
    assert body["warnings"] == ["appointment_lookup_redirected"]
    assert body["errors"] == []
# === TASK:WP-404:END ===

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.ai.orchestrator.appointment_booking.pipeline import AppointmentBookingResponse, BookingFlowStateDTO, BookingOutcome
from apps.api.ai.orchestrator.emergency_safety.pipeline import EmergencySafetyResponse, OUTCOME_EMERGENCY_TRIGGERED
from apps.api.ai.orchestrator.information_assistance.pipeline import CitationDTO, ExplainabilityDTO, InformationAssistanceResponse, OUTCOME_ANSWERED
from apps.api.core.runtime_persistence import build_operational_runtime
from apps.api.gateway.capabilities.appointment_booking.router import CAPABILITY_ROUTE as BOOK_ROUTE, router as book_router, set_appointment_booking_pipeline
from apps.api.gateway.capabilities.emergency_safety.router import CAPABILITY_ROUTE as EMG_ROUTE, router as emg_router, set_emergency_safety_pipeline
from apps.api.gateway.capabilities.information_assistance.router import CAPABILITY_ROUTE as INFO_ROUTE, router as info_router, set_information_assistance_pipeline
from apps.api.gateway.capabilities.appointment_status.router import CAPABILITY_ROUTE as STATUS_ROUTE, router as status_router, set_appointment_status_pipeline
from apps.api.ai.orchestrator.appointment_status.pipeline import AppointmentStatusResponse


class FakeOperationalRepository:
    def __init__(self, fail_messages=False, fail_audit=False):
        self.sessions = {}
        self.messages = []
        self.audits = []
        self.fail_messages = fail_messages
        self.fail_audit = fail_audit

    def get_session_context(self, session_id):
        return self.sessions.get(session_id)

    def create_session(self, session_id, channel, metadata):
        row = {"channel": channel, "metadata": dict(metadata), "started_at": "2026-01-01T00:00:00+00:00", "expires_at": "2026-01-02T00:00:00+00:00"}
        self.sessions[session_id] = row
        return row

    def append_message(self, session_id, role, content_redacted, **kwargs):
        if self.fail_messages:
            raise RuntimeError("database unavailable")
        self.messages.append({"session_id": session_id, "role": role, "content": content_redacted, **kwargs})
        return {"message_id": f"m-{len(self.messages)}", "created_at": "2026-01-01T00:00:00+00:00"}

    def write_audit(self, category, actor, entity_type, action, payload):
        if self.fail_audit:
            raise RuntimeError("database unavailable")
        self.audits.append({"category": category, "actor": actor, "entity_type": entity_type, "action": action, "payload": payload})
        return {"audit_event_id": f"a-{len(self.audits)}", "occurred_at": "2026-01-01T00:00:00+00:00"}


class InfoPipeline:
    def execute(self, request):
        citation = CitationDTO(chunk_id="chunk-1", content="safe", domain="bhyt", source_section="section", effective_date="2026-01-01", score=0.9)
        return InformationAssistanceResponse(outcome=OUTCOME_ANSWERED, message="Trả lời an toàn", citations=[citation], explainability=ExplainabilityDTO(citations=[citation], confidence_band="high"))


class EmergencyPipeline:
    def execute(self, request):
        return EmergencySafetyResponse(outcome=OUTCOME_EMERGENCY_TRIGGERED, level=1, message="Gọi 115 ngay", banner="Khẩn cấp")


class BookingPipeline:
    def execute(self, request):
        return AppointmentBookingResponse(outcome="created", message="Đã đặt lịch", appointment={"appointment_id": "apt-1"}, conversation_state=BookingFlowStateDTO(session_id=request.session_id, current_step="created"))


class StatusPipeline:
    def execute(self, request):
        return AppointmentStatusResponse(
            outcome="found",
            message="Appointment is pending.",
            appointment={"appointment_id": request.appointment_id, "status": "pending"},
        )


def app_with(router, repo):
    app = FastAPI()
    app.state.operational_runtime = build_operational_runtime(repository=repo)
    app.include_router(router)
    return TestClient(app)


def test_lifespan_builds_one_shared_operational_composition(monkeypatch):
    import apps.api.main as application_main

    repo = FakeOperationalRepository()
    runtime = build_operational_runtime(repository=repo)
    calls = []

    def build_runtime():
        calls.append(True)
        return runtime

    monkeypatch.setattr(application_main, "build_operational_runtime", build_runtime)
    with TestClient(application_main.app):
        assert application_main.app.state.operational_runtime is runtime
        assert runtime.sessions._repository is repo
        assert runtime.conversations._repository is repo
        assert runtime.feedback._repository is repo
        assert runtime.audit._repository is repo
        assert runtime.history._repository is repo
        assert runtime.analytics._repository is repo
    assert calls == [True]


def test_pc01_persists_redacted_turns_and_citation_metadata():
    repo = FakeOperationalRepository()
    set_information_assistance_pipeline(InfoPipeline())
    client = app_with(info_router, repo)
    response = client.post(INFO_ROUTE, json={"request_id": "r1", "session_id": "s1", "message": "SĐT 0912345678 hỏi BHYT", "conversation_history": [], "client_context": {"channel": "web_page", "locale": "vi-VN", "timezone": "Asia/Bangkok"}})
    assert response.status_code == 200
    assert repo.sessions["s1"]["metadata"]["actor_tag"] == "anonymous"
    assert "0912345678" not in str(repo.sessions["s1"]["metadata"])
    assert repo.messages[0]["content"] == "SĐT [REDACTED] hỏi BHYT"
    assert repo.messages[1]["citations"][0]["chunk_id"] == "chunk-1"


def test_pc02_emergency_audit_has_no_raw_input_text():
    repo = FakeOperationalRepository()
    set_emergency_safety_pipeline(EmergencyPipeline())
    client = app_with(emg_router, repo)
    response = client.post(EMG_ROUTE, json={"request_id": "r2", "session_id": "s2", "message": "Tôi đau ngực số 0912345678", "conversation_history": [], "client_context": {}})
    assert response.status_code == 200
    assert repo.audits[0]["category"] == "emergency"
    assert "đau ngực" not in str(repo.audits[0])
    assert "0912345678" not in str(repo.audits[0])


def test_pc03_booking_confirm_audit_and_idempotency_required():
    repo = FakeOperationalRepository()
    set_appointment_booking_pipeline(BookingPipeline())
    client = app_with(book_router, repo)
    missing = client.post(BOOK_ROUTE, json={"request_id": "r3", "session_id": "s3", "message": "confirm", "conversation_history": [], "form_data": {"confirmed": True}})
    assert missing.status_code == 400
    response = client.post(BOOK_ROUTE, headers={"idempotency-key": "idem-1"}, json={"request_id": "r3", "session_id": "s3", "message": "confirm", "conversation_history": [], "form_data": {"confirmed": True}})
    assert response.status_code == 200
    assert [a["category"] for a in repo.audits] == ["security", "security"]
    assert [a["action"] for a in repo.audits] == ["appointment_create_attempt", "appointment_create_success"]
    assert repo.audits[0]["payload"]["idempotency_key_present"] is True


def test_pc04_persists_minimal_history_without_patient_pii():
    repo = FakeOperationalRepository()
    set_appointment_status_pipeline(StatusPipeline())
    client = app_with(status_router, repo)

    response = client.post(
        STATUS_ROUTE,
        json={
            "request_id": "r4-status",
            "session_id": "s4-status",
            "appointment_reference": {"appointment_id": "HEN-2026-0001"},
        },
    )

    assert response.status_code == 200
    assert repo.sessions["s4-status"]["metadata"]["actor_tag"] == "anonymous"
    assert [entry["role"] for entry in repo.messages] == ["user", "assistant"]
    assert repo.messages[0]["content"] == "appointment status lookup"
    assert "patient" not in str(repo.sessions["s4-status"]["metadata"]).lower()
    assert "patient" not in str(repo.messages).lower()


def test_non_emergency_logging_failure_is_non_blocking_but_no_memory_fallback():
    repo = FakeOperationalRepository(fail_messages=True)
    set_information_assistance_pipeline(InfoPipeline())
    client = app_with(info_router, repo)
    response = client.post(INFO_ROUTE, json={"request_id": "r4", "session_id": "s4", "message": "Xin chào", "conversation_history": [], "client_context": {}})
    assert response.status_code == 200
    assert repo.messages == []
    assert "s4" in repo.sessions


def test_emergency_audit_failure_returns_safe_response():
    repo = FakeOperationalRepository(fail_audit=True)
    set_emergency_safety_pipeline(EmergencyPipeline())
    client = app_with(emg_router, repo)
    response = client.post(EMG_ROUTE, json={"request_id": "r5", "session_id": "s5", "message": "đau ngực", "conversation_history": [], "client_context": {}})
    assert response.status_code == 200
    assert "115" in response.json()["result"]["message"]
    assert repo.audits == []

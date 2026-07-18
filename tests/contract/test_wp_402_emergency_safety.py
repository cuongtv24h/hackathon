# === TASK:WP-402:START ===
"""Contract tests for WP-402 PC-02 Emergency Safety gateway router."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.contracts import make_error_envelope, UnifiedErrorEnvelope
from apps.api.ai.orchestrator.emergency_safety.pipeline import (
    EmergencySafetyResponse,
    EmergencyProtocolDTO,
    OUTCOME_EMERGENCY_TRIGGERED,
    OUTCOME_CLARIFICATION_REQUIRED,
    OUTCOME_NOT_TRIGGERED,
    GENERAL_DISCLAIMER,
)
from apps.api.gateway.capabilities.emergency_safety.router import (
    CAPABILITY_NAME,
    CAPABILITY_ROUTE,
    router,
    set_emergency_safety_pipeline,
)


class FakePipeline:
    """Network/provider-free fake for gateway contract tests."""

    def __init__(self, response: EmergencySafetyResponse) -> None:
        self.response = response
        self.seen_request = None

    def execute(self, request):  # type: ignore[no-untyped-def]
        self.seen_request = request
        return self.response


def make_client(fake_pipeline: FakePipeline) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    set_emergency_safety_pipeline(fake_pipeline)  # type: ignore[arg-type]
    return TestClient(app)


def make_payload(**overrides):  # type: ignore[no-untyped-def]
    payload = {
        "request_id": "req-402",
        "session_id": "sess-402",
        "message": "Tôi bị đau ngực khó thở",
        "conversation_history": [],
        "response_mode": "sync",
        "client_context": {"channel": "web_widget", "locale": "vi-VN"},
    }
    payload.update(overrides)
    return payload


def emergency_triggered_level2_response() -> EmergencySafetyResponse:
    protocol = EmergencyProtocolDTO(
        protocol_id="proto-l2-001",
        level=2,
        version="1.0",
        response_text="Phát hiện dấu hiệu cấp cứu cấp độ 2.",
        channel_refs=["115"],
        emergency_address_ref="Bệnh viện Tim Hà Nội",
        banner_level="critical",
        allowed_actions=["call_115", "go_to_er"],
        prohibited_content=["self_medicate", "wait_and_see"],
        approval_status="approved",
        is_mock=True,
        effective_date="2026-01-01",
    )
    return EmergencySafetyResponse(
        outcome=OUTCOME_EMERGENCY_TRIGGERED,
        message=(
            "🚨 Phát hiện dấu hiệu cấp cứu cấp độ 2.\n\n"
            "KHẨN CẤP: Gọi 115 NGAY LẬP TỨC hoặc đến cấp cứu bệnh viện Tim Hà Nội: "
            "Bệnh viện Tim Hà Nội.\n"
            "Các đường dây hỗ trợ: 115\n\n"
            "Đây là mức độ nghiêm trọng (Level 2). Không tự xử lý, hãy gọi 115 ngay."
        ),
        level=2,
        protocol=protocol,
        hotlines=["115"],
        address="Bệnh viện Tim Hà Nội",
        banner=protocol.response_text,
        event_id="evt-402",
        matched_keywords=[{"keyword": "đau ngực", "level": "critical", "match_type": "exact"}],
        disclaimers=[GENERAL_DISCLAIMER],
    )


def emergency_triggered_level1_response() -> EmergencySafetyResponse:
    protocol = EmergencyProtocolDTO(
        protocol_id="proto-l1-001",
        level=1,
        version="1.0",
        response_text="Phát hiện dấu hiệu cần thận trọng.",
        channel_refs=["19001234", "115"],
        emergency_address_ref="Bệnh viện Tim Hà Nội",
        banner_level="caution",
        allowed_actions=["call_hotline", "schedule_appointment"],
        prohibited_content=["ignore_symptoms"],
        approval_status="approved",
        is_mock=True,
        effective_date="2026-01-01",
    )
    return EmergencySafetyResponse(
        outcome=OUTCOME_EMERGENCY_TRIGGERED,
        message=(
            "⚠️ Phát hiện dấu hiệu cần thận trọng.\n\n"
            "Hướng dẫn: Vui lòng liên hệ ngay với đường dây nóng: 19001234, 115.\n"
            "Địa chỉ bệnh viện: Bệnh viện Tim Hà Nội\n\n"
            "Đây là mức độ cảnh báo (Level 1). Không phải chẩn đoán y tế."
        ),
        level=1,
        protocol=protocol,
        hotlines=["19001234", "115"],
        address="Bệnh viện Tim Hà Nội",
        banner=protocol.response_text,
        event_id="evt-402-level1",
        matched_keywords=[{"keyword": "đau bụng", "level": "caution", "match_type": "exact"}],
        disclaimers=[GENERAL_DISCLAIMER],
    )


def not_triggered_response() -> EmergencySafetyResponse:
    return EmergencySafetyResponse(
        outcome=OUTCOME_NOT_TRIGGERED,
        message=(
            "Không phát hiện từ khóa khẩn cấp trong tin nhắn của bạn. "
            "Nếu bạn cảm thấy bất an về sức khỏe, vui lòng liên hệ 115 hoặc "
        ),
        level=None,
        protocol=None,
        hotlines=["115"],
        address="Bệnh viện Tim Hà Nội",
        banner=None,
        event_id=None,
        matched_keywords=[],
        disclaimers=[GENERAL_DISCLAIMER],
    )


def test_emergency_safety_sync_success_level2_contract_shape() -> None:
    fake_pipeline = FakePipeline(emergency_triggered_level2_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(),
        headers={"x-trace-id": "trace-402"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trace-402"
    assert body["request_id"] == "req-402"
    assert body["capability"] == CAPABILITY_NAME
    assert body["outcome"] == OUTCOME_EMERGENCY_TRIGGERED
    assert body["timestamp"]
    assert body["errors"] == []
    assert body["warnings"] == [GENERAL_DISCLAIMER]
    assert body["result"]["level"] == 2
    assert body["result"]["protocol"]["level"] == 2
    assert body["result"]["hotlines"] == ["115"]
    assert body["result"]["address"] == "Bệnh viện Tim Hà Nội"
    assert body["result"]["event_id"] == "evt-402"
    assert body["result"]["matched_keywords"][0]["keyword"] == "đau ngực"
    assert fake_pipeline.seen_request.request_id == "req-402"
    assert fake_pipeline.seen_request.client_context["channel"] == "web_widget"


def test_emergency_safety_sync_success_level1_contract_shape() -> None:
    fake_pipeline = FakePipeline(emergency_triggered_level1_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(message="Tôi bị đau bụng dữ dội"),
        headers={"x-trace-id": "trace-402-level1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trace-402-level1"
    assert body["outcome"] == OUTCOME_EMERGENCY_TRIGGERED
    assert body["result"]["level"] == 1
    assert body["result"]["protocol"]["level"] == 1
    assert body["result"]["hotlines"] == ["19001234", "115"]


def test_emergency_safety_sync_not_triggered_contract_shape() -> None:
    fake_pipeline = FakePipeline(not_triggered_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(message="Giờ làm việc của bệnh viện là gì?"),
        headers={"x-trace-id": "trace-402-not"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trace-402-not"
    assert body["outcome"] == OUTCOME_NOT_TRIGGERED
    assert body["result"]["level"] is None
    assert body["result"]["protocol"] is None
    assert body["result"]["event_id"] is None
    assert body["result"]["matched_keywords"] == []


def test_emergency_safety_stream_keeps_completed_envelope_semantics() -> None:
    fake_pipeline = FakePipeline(emergency_triggered_level2_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(response_mode="stream"),
        headers={"x-trace-id": "trace-stream-402"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: ack" in response.text
    assert "event: completed" in response.text
    completed_line = [
        line for line in response.text.splitlines() if line.startswith("data: {")
    ][-1]
    completed = json.loads(completed_line.removeprefix("data: "))
    assert completed["trace_id"] == "trace-stream-402"
    assert completed["capability"] == CAPABILITY_NAME
    assert completed["outcome"] == OUTCOME_EMERGENCY_TRIGGERED
    assert completed["result"]["level"] == 2
    assert completed["result"]["hotlines"] == ["115"]


def test_emergency_safety_validation_rejects_invalid_response_mode() -> None:
    fake_pipeline = FakePipeline(emergency_triggered_level2_response())
    client = make_client(fake_pipeline)

    response = client.post(CAPABILITY_ROUTE, json=make_payload(response_mode="xml"))

    assert response.status_code == 422
    assert fake_pipeline.seen_request is None


def test_emergency_safety_validation_rejects_empty_message() -> None:
    fake_pipeline = FakePipeline(emergency_triggered_level2_response())
    client = make_client(fake_pipeline)

    response = client.post(CAPABILITY_ROUTE, json=make_payload(message="   "))

    assert response.status_code == 422
    assert fake_pipeline.seen_request is None


def test_emergency_safety_validation_rejects_long_message() -> None:
    fake_pipeline = FakePipeline(emergency_triggered_level2_response())
    client = make_client(fake_pipeline)

    long_message = "x" * 4001
    response = client.post(CAPABILITY_ROUTE, json=make_payload(message=long_message))

    assert response.status_code == 422
    assert fake_pipeline.seen_request is None


def test_emergency_safety_validation_rejects_too_many_history_turns() -> None:
    fake_pipeline = FakePipeline(emergency_triggered_level2_response())
    client = make_client(fake_pipeline)

    history = [{"role": "user", "content": f"msg {i}"} for i in range(21)]
    response = client.post(CAPABILITY_ROUTE, json=make_payload(conversation_history=history))

    assert response.status_code == 422
    assert fake_pipeline.seen_request is None


def test_emergency_safety_clarification_required_enveloped() -> None:
    protocol = EmergencyProtocolDTO(
        protocol_id="proto-l2-001",
        level=2,
        version="1.0",
        response_text="Fallback protocol",
        channel_refs=["115"],
        emergency_address_ref="Bệnh viện Tim Hà Nội",
        banner_level="critical",
        allowed_actions=["call_115"],
        prohibited_content=["self_medicate"],
        approval_status="approved",
        is_mock=True,
        effective_date="2026-01-01",
    )
    clarification = EmergencySafetyResponse(
        outcome=OUTCOME_CLARIFICATION_REQUIRED,
        message="Hệ thống phát hiện tình huống khẩn cấp nhưng không tải được giao thức.",
        level=2,
        protocol=protocol,
        hotlines=["115"],
        disclaimers=[GENERAL_DISCLAIMER],
        matched_keywords=[{"keyword": "đau ngực", "level": "critical", "match_type": "exact"}],
        event_id="evt-402-clarify",
        error=make_error_envelope(
            code="PROTOCOL_NOT_FOUND",
            message="No emergency protocol found for level 2",
            category="safety",
            trace_id="trace-clarify",
            retryable=False,
            retry_after_seconds=None,
            fallback=None,
        ),
    )
    client = make_client(FakePipeline(clarification))

    response = client.post(CAPABILITY_ROUTE, json=make_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == OUTCOME_CLARIFICATION_REQUIRED
    assert body["result"]["error"]["error"]["code"] == "PROTOCOL_NOT_FOUND"
    assert body["errors"][0]["code"] == "PROTOCOL_NOT_FOUND"
    assert body["warnings"] == [GENERAL_DISCLAIMER]


def test_emergency_safety_pipeline_error_enveloped() -> None:
    error_response = EmergencySafetyResponse(
        outcome=OUTCOME_NOT_TRIGGERED,
        message=GENERAL_DISCLAIMER,
        disclaimers=[GENERAL_DISCLAIMER],
        error=make_error_envelope(
            code="EMERGENCY_PIPELINE_ERROR",
            message="Internal pipeline error",
            category="safety",
            trace_id="trace-error",
            retryable=True,
            retry_after_seconds=5,
            fallback=None,
        ),
    )
    client = make_client(FakePipeline(error_response))

    response = client.post(CAPABILITY_ROUTE, json=make_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == OUTCOME_NOT_TRIGGERED
    assert body["errors"][0]["code"] == "EMERGENCY_PIPELINE_ERROR"
    assert body["errors"][0]["retryable"] is True
    assert body["warnings"] == [GENERAL_DISCLAIMER]
# === TASK:WP-402:END ===
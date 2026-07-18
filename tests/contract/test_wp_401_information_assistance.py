# === TASK:WP-401:START ===
"""Contract tests for WP-401 PC-01 Information Assistance gateway router."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.ai.orchestrator.information_assistance.pipeline import (
    CitationDTO,
    ExplainabilityDTO,
    InformationAssistanceResponse,
    OUTCOME_ANSWERED,
    OUTCOME_FALLBACK,
)
from apps.api.gateway.capabilities.information_assistance.router import (
    CAPABILITY_NAME,
    CAPABILITY_ROUTE,
    router,
    set_information_assistance_pipeline,
)


class FakePipeline:
    """Network/provider-free fake for gateway contract tests."""

    def __init__(self, response: InformationAssistanceResponse) -> None:
        self.response = response
        self.seen_request = None

    def execute(self, request):  # type: ignore[no-untyped-def]
        self.seen_request = request
        return self.response


def make_client(fake_pipeline: FakePipeline) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    set_information_assistance_pipeline(fake_pipeline)  # type: ignore[arg-type]
    return TestClient(app)


def make_payload(**overrides):  # type: ignore[no-untyped-def]
    payload = {
        "request_id": "req-401",
        "session_id": "sess-401",
        "message": "Giờ làm việc của bệnh viện là gì?",
        "conversation_history": [],
        "response_mode": "sync",
        "client_context": {"channel": "web_widget", "locale": "vi-VN"},
    }
    payload.update(overrides)
    return payload


def answered_response() -> InformationAssistanceResponse:
    citation = CitationDTO(
        chunk_id="chunk-hours-1",
        content="Bệnh viện làm việc từ 07:00 đến 17:00.",
        domain="gio_lam_viec",
        source_section="Giờ làm việc",
        effective_date="2026-01-01",
        score=0.98,
    )
    return InformationAssistanceResponse(
        outcome=OUTCOME_ANSWERED,
        message="Bệnh viện làm việc từ 07:00 đến 17:00.",
        citations=[citation],
        suggested_actions=[{"type": "contact", "channel": "reception"}],
        disclaimers=["Đây là thông tin tham khảo và không thay thế tư vấn y tế trực tiếp."],
        conversation_state={"session_id": "sess-401"},
        explainability=ExplainabilityDTO(citations=[citation], confidence_band="high"),
    )


def test_information_assistance_sync_success_contract_shape() -> None:
    fake_pipeline = FakePipeline(answered_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(),
        headers={"x-trace-id": "trace-401"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trace-401"
    assert body["request_id"] == "req-401"
    assert body["capability"] == CAPABILITY_NAME
    assert body["outcome"] == OUTCOME_ANSWERED
    assert body["timestamp"]
    assert body["errors"] == []
    assert body["warnings"] == [
        "Đây là thông tin tham khảo và không thay thế tư vấn y tế trực tiếp."
    ]
    assert body["result"]["message"] == "Bệnh viện làm việc từ 07:00 đến 17:00."
    assert body["result"]["citations"][0]["chunk_id"] == "chunk-hours-1"
    assert body["explainability"]["confidence_band"] == "high"
    assert fake_pipeline.seen_request.request_id == "req-401"
    assert fake_pipeline.seen_request.client_context["channel"] == "web_widget"


def test_information_assistance_stream_keeps_completed_envelope_semantics() -> None:
    fake_pipeline = FakePipeline(answered_response())
    client = make_client(fake_pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload(response_mode="stream"),
        headers={"x-trace-id": "trace-stream-401"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: ack" in response.text
    assert "event: completed" in response.text
    completed_line = [
        line for line in response.text.splitlines() if line.startswith("data: {")
    ][-1]
    completed = json.loads(completed_line.removeprefix("data: "))
    assert completed["trace_id"] == "trace-stream-401"
    assert completed["capability"] == CAPABILITY_NAME
    assert completed["outcome"] == OUTCOME_ANSWERED
    assert completed["result"]["citations"][0]["domain"] == "gio_lam_viec"


def test_information_assistance_validation_rejects_invalid_response_mode() -> None:
    fake_pipeline = FakePipeline(answered_response())
    client = make_client(fake_pipeline)

    response = client.post(CAPABILITY_ROUTE, json=make_payload(response_mode="xml"))

    assert response.status_code == 422
    assert fake_pipeline.seen_request is None


def test_information_assistance_fallback_errors_are_enveloped() -> None:
    fallback = InformationAssistanceResponse(
        outcome=OUTCOME_FALLBACK,
        message="Xin lỗi, tôi không tìm thấy thông tin đủ căn cứ.",
        disclaimers=["Đây là thông tin tham khảo và không thay thế tư vấn y tế trực tiếp."],
        explainability=ExplainabilityDTO(
            confidence_band="low",
            fallback_reason="insufficient_grounding",
        ),
    )
    client = make_client(FakePipeline(fallback))

    response = client.post(CAPABILITY_ROUTE, json=make_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == OUTCOME_FALLBACK
    assert body["result"]["explainability"]["fallback_reason"] == "insufficient_grounding"
    assert body["warnings"] == [
        "Đây là thông tin tham khảo và không thay thế tư vấn y tế trực tiếp."
    ]
# === TASK:WP-401:END ===

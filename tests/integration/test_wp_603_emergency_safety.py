# === TASK:WP-603:START ===
"""WP-603 PC-02 safety, fault, and handoff integration tests.

These tests cover the R1 QA scope for Emergency Safety without provider or
network calls. They verify deterministic keyword handling, negative context,
LLM/provider outage resilience, and Level-1/Level-2 handoff behavior through the
FastAPI capability gateway.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.ai.orchestrator.emergency_safety.pipeline import (
    EmergencySafetyPipeline,
    GENERAL_DISCLAIMER,
    OUTCOME_EMERGENCY_TRIGGERED,
    OUTCOME_NOT_TRIGGERED,
)
from apps.api.capabilities.emergency.prefilter.tool import (
    EmergencyPrefilterTool,
    PrefilterRequest,
    PrefilterResult,
)
from apps.api.foundation.emergency.service import (
    EmergencyEventCreateRequest,
    EmergencyEventReceiptDTO,
    EmergencyFoundationService,
    EmergencyKeywordDTO,
    EmergencyKeywordSetDTO,
    EmergencyProtocolDTO,
)
from apps.api.gateway.capabilities.emergency_safety.router import (
    CAPABILITY_ROUTE,
    router,
    set_emergency_safety_pipeline,
)


class FakeEmergencyFoundation(EmergencyFoundationService):
    """Provider-free emergency foundation fake for WP-603 tests."""

    def __init__(self) -> None:
        self.created_events: List[EmergencyEventCreateRequest] = []
        self.keyword_set = EmergencyKeywordSetDTO(
            critical_keywords=[
                EmergencyKeywordDTO(
                    rule_id="ER-KW-CRITICAL-603",
                    level=2,
                    category="cardiac_arrest",
                    phrases=["ngưng tim", "bất tỉnh", "khó thở nặng"],
                    normalized_phrases=["ngung tim", "bat tinh", "kho tho nang"],
                    protocol_id="ERP-CRITICAL-603",
                )
            ],
            caution_keywords=[
                EmergencyKeywordDTO(
                    rule_id="ER-KW-CAUTION-603",
                    level=1,
                    category="chest_pain",
                    phrases=["đau ngực", "tức ngực"],
                    normalized_phrases=["dau nguc", "tuc nguc"],
                    protocol_id="ERP-CAUTION-603",
                )
            ],
            approval_status="mock_not_clinically_approved",
            effective_date="2026-07-18",
            version="wp-603-r1",
        )
        self.protocols: Dict[int, EmergencyProtocolDTO] = {
            1: EmergencyProtocolDTO(
                protocol_id="ERP-CAUTION-603",
                level=1,
                version="wp-603-r1",
                response_text="MOCK WARNING: Dấu hiệu cần được nhân viên y tế tiếp nhận.",
                channel_refs=["19001234", "115"],
                emergency_address_ref="Bệnh viện Tim Hà Nội",
                banner_level="caution",
                allowed_actions=["contact_hotline", "handoff_level_1"],
                prohibited_content=["medical_diagnosis", "treatment_recommendation"],
                approval_status="mock_not_clinically_approved",
                is_mock=True,
                effective_date="2026-07-18",
            ),
            2: EmergencyProtocolDTO(
                protocol_id="ERP-CRITICAL-603",
                level=2,
                version="wp-603-r1",
                response_text="MOCK WARNING: Tình huống cấp cứu cần liên hệ 115 ngay.",
                channel_refs=["115"],
                emergency_address_ref="Bệnh viện Tim Hà Nội",
                banner_level="critical",
                allowed_actions=["call_115_immediately", "handoff_level_2"],
                prohibited_content=["medical_diagnosis", "treatment_recommendation", "self_care"],
                approval_status="mock_not_clinically_approved",
                is_mock=True,
                effective_date="2026-07-18",
            ),
        }

    def get_emergency_keyword_set(self) -> EmergencyKeywordSetDTO:
        return self.keyword_set

    def get_emergency_protocol(self, level: int) -> Optional[EmergencyProtocolDTO]:
        return self.protocols.get(level)

    def create_emergency_event(
        self, request: EmergencyEventCreateRequest
    ) -> EmergencyEventReceiptDTO:
        self.created_events.append(request)
        return EmergencyEventReceiptDTO(
            event_id=f"evt-wp-603-{len(self.created_events)}",
            created_at="2026-07-18T07:00:00+00:00",
            level=request.level,
            protocol_id=request.protocol_id,
        )


class ExplodingProviderLikePrefilter:
    """Fake provider outage dependency that must not break critical fallback."""

    def prefilter(self, request: PrefilterRequest) -> PrefilterResult:
        raise RuntimeError("simulated all-LLM/provider outage")


class NegativeContextPrefilter:
    """Fake prefilter for context where emergency terms are quoted, not asserted."""

    def prefilter(self, request: PrefilterRequest) -> PrefilterResult:
        return PrefilterResult(
            is_emergency=False,
            level=0,
            matched_keywords=[],
            protocol_id="ERP-FALLBACK-V1",
            metadata={"elapsed_ms": 1.0, "timeout_ms": 100},
            event_receipt=None,
        )


def make_client(pipeline: EmergencySafetyPipeline) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    set_emergency_safety_pipeline(pipeline)
    return TestClient(app)


def make_payload(message: str) -> Dict[str, Any]:
    return {
        "request_id": "req-wp-603",
        "session_id": "sess-wp-603",
        "message": message,
        "conversation_history": [],
        "response_mode": "sync",
        "client_context": {"channel": "web_widget", "locale": "vi-VN"},
    }


def test_critical_keyword_path_bypasses_llm_and_returns_level2_handoff() -> None:
    foundation = FakeEmergencyFoundation()
    pipeline = EmergencySafetyPipeline(
        prefilter_tool=EmergencyPrefilterTool(foundation_service=foundation),
        foundation_service=foundation,
    )
    client = make_client(pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload("Người bệnh bất tỉnh và khó thở nặng"),
        headers={"x-trace-id": "trace-wp-603-critical"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trace-wp-603-critical"
    assert body["outcome"] == OUTCOME_EMERGENCY_TRIGGERED
    assert body["result"]["level"] == 2
    assert body["result"]["event_id"] == "evt-wp-603-1"
    assert body["result"]["hotlines"] == ["115"]
    assert "Gọi 115 NGAY LẬP TỨC" in body["result"]["message"]
    assert "MOCK WARNING" in body["result"]["protocol"]["response_text"]
    assert body["warnings"] == [GENERAL_DISCLAIMER]
    assert foundation.created_events[0].level == 2
    assert foundation.created_events[0].protocol_id == "ERP-CRITICAL-603"


def test_level1_caution_keyword_returns_contact_handoff_without_diagnosis() -> None:
    foundation = FakeEmergencyFoundation()
    pipeline = EmergencySafetyPipeline(
        prefilter_tool=EmergencyPrefilterTool(foundation_service=foundation),
        foundation_service=foundation,
    )
    client = make_client(pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload("Tôi bị tức ngực nhẹ và muốn hỏi nên liên hệ ai"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == OUTCOME_EMERGENCY_TRIGGERED
    assert body["result"]["level"] == 1
    assert body["result"]["hotlines"] == ["19001234", "115"]
    assert "Vui lòng liên hệ ngay với đường dây nóng" in body["result"]["message"]
    assert "Không phải chẩn đoán y tế" in body["result"]["message"]
    assert "MOCK WARNING" in body["result"]["protocol"]["response_text"]
    assert "chẩn đoán:" not in body["result"]["message"].lower()
    assert foundation.created_events[0].level == 1


def test_negative_context_does_not_trigger_emergency_or_event() -> None:
    foundation = FakeEmergencyFoundation()
    pipeline = EmergencySafetyPipeline(
        prefilter_tool=NegativeContextPrefilter(),
        foundation_service=foundation,
    )
    client = make_client(pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload("Tôi đang hỏi nghĩa của cụm từ 'đau ngực', hiện không có triệu chứng."),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == OUTCOME_NOT_TRIGGERED
    assert body["result"]["level"] is None
    assert body["result"]["event_id"] is None
    assert body["result"]["matched_keywords"] == []
    assert foundation.created_events == []


def test_prefilter_provider_outage_returns_static_hotline_warning() -> None:
    pipeline = EmergencySafetyPipeline(
        prefilter_tool=ExplodingProviderLikePrefilter(),
        foundation_service=FakeEmergencyFoundation(),
    )
    client = make_client(pipeline)

    response = client.post(
        CAPABILITY_ROUTE,
        json=make_payload("Người bệnh có dấu hiệu nguy hiểm"),
        headers={"x-trace-id": "trace-wp-603-outage"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trace-wp-603-outage"
    assert body["outcome"] == OUTCOME_NOT_TRIGGERED
    assert body["warnings"] == [GENERAL_DISCLAIMER]
    assert "115" in body["result"]["message"]
    assert body["errors"][0]["code"] == "EMERGENCY_PIPELINE_ERROR"
    assert body["errors"][0]["retryable"] is True
# === TASK:WP-603:END ===

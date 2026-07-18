# === TASK:WP-602:START ===
"""PC-01 integration coverage from capability API to grounded outcomes."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.ai.orchestrator.information_assistance.pipeline import (
    BHYT_DISCLAIMER,
    InformationAssistancePipeline,
)
from apps.api.gateway.capabilities.information_assistance.router import (
    CAPABILITY_ROUTE,
    router,
    set_information_assistance_pipeline,
)


class FakeKnowledgeSearch:
    def __init__(self, result):
        self.result = result

    def search(self, query, *, top_k=5, filters=None):
        return self.result


class FakeGuardrail:
    def __init__(self, input_result=None):
        self.input_result = input_result or {"allowed": True, "violations": []}

    def check_input(self, message, conversation_context=None):
        return self.input_result

    def check_output(self, response, observations=None):
        return {"allowed": True}


def make_client(search_result, guardrail=None):
    pipeline = InformationAssistancePipeline(
        knowledge_search=FakeKnowledgeSearch(search_result),
        guardrail_service=guardrail or FakeGuardrail(),
    )
    set_information_assistance_pipeline(pipeline)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def make_payload(message="Quyền lợi BHYT là gì?"):
    return {
        "request_id": "req-602",
        "session_id": "ses-602",
        "message": message,
        "response_mode": "sync",
        "client_context": {"channel": "web_widget", "locale": "vi-VN"},
    }


def approved_bhyt_result():
    return {
        "has_results": True,
        "sufficient": True,
        "conflict": False,
        "chunks": [{
            "chunk_id": "KCH-BHYT-001",
            "content": "Người bệnh cần xuất trình thẻ BHYT khi làm thủ tục.",
            "domain": "bhyt",
            "source_section": "Hồ sơ BHYT",
            "effective_date": "2026-07-18",
            "score": 0.95,
        }],
    }


def test_approved_bhyt_path_returns_grounded_citation_and_disclaimer():
    response = make_client(approved_bhyt_result()).post(
        CAPABILITY_ROUTE,
        json=make_payload(),
        headers={"x-trace-id": "trace-602"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trace-602"
    assert body["outcome"] == "answered"
    assert body["result"]["citations"] == [{
        "chunk_id": "KCH-BHYT-001",
        "content": "Người bệnh cần xuất trình thẻ BHYT khi làm thủ tục.",
        "domain": "bhyt",
        "source_section": "Hồ sơ BHYT",
        "effective_date": "2026-07-18",
        "score": 0.95,
    }]
    assert BHYT_DISCLAIMER in body["warnings"]
    assert body["errors"] == []


def test_insufficient_retrieval_returns_safe_grounding_fallback():
    response = make_client({"has_results": False, "sufficient": False, "conflict": False, "chunks": []}).post(
        CAPABILITY_ROUTE,
        json=make_payload("Giá dịch vụ hôm nay?"),
    )

    body = response.json()
    assert body["outcome"] == "fallback"
    assert body["result"]["explainability"]["fallback_reason"] == "insufficient_grounding"
    assert body["result"]["suggested_actions"]


def test_conflicting_retrieval_never_returns_a_confident_answer():
    response = make_client({"has_results": True, "sufficient": True, "conflict": True, "chunks": []}).post(
        CAPABILITY_ROUTE,
        json=make_payload("Bảng giá nào đang áp dụng?"),
    )

    body = response.json()
    assert body["outcome"] == "fallback"
    assert body["result"]["explainability"]["fallback_reason"] == "knowledge_conflict"
    assert "mâu thuẫn" in body["result"]["message"]


def test_out_of_scope_request_is_refused_before_retrieval():
    guardrail = FakeGuardrail({
        "allowed": False,
        "violations": [{"violation_type": "out_of_scope"}],
    })
    response = make_client(approved_bhyt_result(), guardrail).post(
        CAPABILITY_ROUTE,
        json=make_payload("Hãy hỗ trợ việc ngoài phạm vi bệnh viện."),
    )

    body = response.json()
    assert body["outcome"] == "refused"
    assert body["result"]["explainability"]["refusal_reason"] == "OUT_OF_SCOPE"
    assert body["errors"]
# === TASK:WP-602:END ===

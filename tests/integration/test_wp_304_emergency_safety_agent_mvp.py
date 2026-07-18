# === TASK:WP-304:START ===
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from apps.api.ai.orchestrator.core import agent_graph
from packages.contracts.dto import SafetyDecisionDTO

def test_negated_or_educational_safety_low_routing(monkeypatch):
    # Simulate evaluator concluding LOW for a negated/educational mention
    mock_provider = MagicMock()
    mock_provider.evaluate_safety.return_value = SafetyDecisionDTO(
        risk="LOW",
        subject="học thuật cấp cứu",
        temporality="hypothetical",
        assertion="negative",
        reason_code="EDUCATIONAL_MENTION",
        evidence_spans=[]
    )

    # Patch OpenAIProvider to return our mock
    monkeypatch.setattr(
        "apps.api.ai.orchestrator.core.agent.OpenAIProvider",
        lambda api_key: mock_provider
    )

    # We also mock ChatOpenAI.invoke so it returns a simple text without trying to query the real API
    mock_chat = MagicMock()
    mock_chat.invoke.return_value = AIMessage(content="Bạn muốn tìm hiểu nội dung học thuật nào về cấp cứu?")
    monkeypatch.setattr(
        "apps.api.ai.orchestrator.core.agent.ChatOpenAI",
        lambda **kwargs: MagicMock(bind_tools=lambda tools: mock_chat)
    )

    msg = HumanMessage(content="Hãy kể cho tôi một bài học về xử lý chấn thương nhẹ")
    state = {
        "messages": [msg],
        "safety_result": None,
        "clarification_count": 0,
        "observations": [{
            "candidates": [{
                "chunk_id": "uuid-1",
                "content": "Đây là thông tin học thuật về cấp cứu.",
                "score": 1.0,
                "domain": "quy_trinh",
                "sub_topic": "học thuật",
                "source_id": "s1",
                "source_path": "p1",
                "version": "v1"
            }]
        }],
        "citations": [],
        "call_fingerprints": [],
        "max_tool_calls": 5,
        "call_count": 0,
        "elapsed_time_seconds": 0.0,
        "deadline_timestamp": 9999999999.0,
        "final_response": None,
        "degradation_status": {},
        "repair_attempted": False
    }

    config = {"configurable": {"thread_id": "test-thread-4", "openai_api_key": "fake"}}
    res = agent_graph.invoke(state, config)

    assert res["safety_result"]["risk"] == "LOW"
    assert "học thuật" in res["final_response"]

def test_caution_unresolved_fallback(monkeypatch):
    # If clarification count >= 1 and answer is not yes/no, trigger caution fallback protocol
    msg1 = HumanMessage(content="Tôi bị tức ngực nhẹ")
    aimsg = AIMessage(content="Bạn có đang gặp phải tình trạng nguy kịch hoặc cấp cứu khẩn cấp không? Vui lòng trả lời CÓ hoặc KHÔNG.")
    msg2 = HumanMessage(content="Tôi bận việc khác rồi")

    state = {
        "messages": [msg1, aimsg, msg2],
        "safety_result": {"risk": "CAUTION", "clarification_id": "CLAR-EMERGENCY-001"},
        "clarification_count": 1,
        "observations": [],
        "citations": [],
        "call_fingerprints": [],
        "max_tool_calls": 5,
        "call_count": 0,
        "elapsed_time_seconds": 0.0,
        "deadline_timestamp": 9999999999.0,
        "final_response": None,
        "degradation_status": {},
        "repair_attempted": False
    }

    config = {"configurable": {"thread_id": "test-thread-5"}}
    res = agent_graph.invoke(state, config)

    # Should resolve to the CAUTION fallback protocol
    assert "tạm ngừng các tác vụ thông thường" in res["final_response"]
# === TASK:WP-304:END ===

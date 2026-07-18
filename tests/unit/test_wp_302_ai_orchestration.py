# === TASK:WP-302:START ===
import time
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from apps.api.ai.orchestrator.core import agent_graph
from apps.api.ai.orchestrator.core.agent import llm_node

def test_direct_high_safety_routing():
    # Composed Vietnamese emergency keyword to trigger direct rules
    msg = HumanMessage(content="Tôi bị ngừng tim rồi")
    state = {
        "messages": [msg],
        "safety_result": None,
        "clarification_count": 0,
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
    
    # Run graph with empty config
    config = {"configurable": {"thread_id": "test-thread-1"}}
    res = agent_graph.invoke(state, config)
    
    assert res["safety_result"]["risk"] == "HIGH"
    assert "CẢNH BÁO NGUY HIỂM" in res["final_response"]

def test_caution_flow_clarification():
    # Ambiguous message that fails evaluator but has safety hint
    # We simulate evaluator failing and falling back to caution
    msg = HumanMessage(content="Tôi bị sốt nhẹ")
    state = {
        "messages": [msg],
        "safety_result": None,
        "clarification_count": 0,
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
    
    # Mock evaluate_safety to raise error to trigger caution hint fallback
    config = {"configurable": {"thread_id": "test-thread-2", "openai_api_key": "fake"}}
    
    res = agent_graph.invoke(state, config)
    assert res["safety_result"]["risk"] == "CAUTION"
    assert "CÓ hoặc KHÔNG" in res["final_response"]
    assert res["clarification_count"] == 1

def test_caution_flow_resolves_to_high():
    # Simulate user answering CÓ to clarification
    msg1 = HumanMessage(content="Tôi bị sốt nhẹ")
    aimsg = AIMessage(content="Bạn có đang gặp phải tình trạng nguy kịch hoặc cấp cứu khẩn cấp không? Vui lòng trả lời CÓ hoặc KHÔNG.")
    msg2 = HumanMessage(content="Có, rất nguy kịch")
    
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
    
    config = {"configurable": {"thread_id": "test-thread-3"}}
    res = agent_graph.invoke(state, config)
    
    assert res["safety_result"]["risk"] == "HIGH"
    assert "CẢNH BÁO NGUY HIỂM" in res["final_response"]


def test_expired_deadline_stops_before_llm(monkeypatch):
    chat = MagicMock()
    monkeypatch.setattr(
        "apps.api.ai.orchestrator.core.agent.ChatOpenAI",
        chat
    )
    state = {
        "messages": [HumanMessage(content="Giờ làm việc?")],
        "max_tool_calls": 5,
        "call_count": 0,
        "elapsed_time_seconds": 0.0,
        "deadline_timestamp": time.time() - 1,
    }

    result = llm_node(state, {"configurable": {"openai_api_key": "fake"}})

    assert "vượt quá giới hạn" in result["final_response"]
    chat.assert_not_called()


def test_tool_batch_cannot_exceed_remaining_budget(monkeypatch):
    response = AIMessage(content="")
    response.tool_calls = [
        {"name": "search_hospital_information_tool", "args": {"query": "a"}, "id": "1"},
        {"name": "search_hospital_information_tool", "args": {"query": "b"}, "id": "2"},
    ]
    bound_model = MagicMock()
    bound_model.invoke.return_value = response
    monkeypatch.setattr(
        "apps.api.ai.orchestrator.core.agent.ChatOpenAI",
        lambda **kwargs: MagicMock(bind_tools=lambda tools: bound_model)
    )
    state = {
        "messages": [HumanMessage(content="Tìm thông tin")],
        "call_fingerprints": [],
        "max_tool_calls": 2,
        "call_count": 1,
        "elapsed_time_seconds": 0.0,
        "deadline_timestamp": time.time() + 30,
        "repair_attempted": False,
    }

    result = llm_node(state, {"configurable": {"openai_api_key": "fake"}})

    assert "vượt quá giới hạn" in result["final_response"]
# === TASK:WP-302:END ===

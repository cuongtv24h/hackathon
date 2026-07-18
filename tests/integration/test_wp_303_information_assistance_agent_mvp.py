# === TASK:WP-303:START ===
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from apps.api.ai.orchestrator.core import agent_graph
from packages.contracts.dto import SearchCandidateDTO

def test_grounded_response_happy_path(monkeypatch):
    # Mock database cursor fetchall for hybrid search
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        ("uuid-1", "Bệnh viện đa khoa mở cửa từ 8:00 đến 17:00 hàng ngày.", "giờ làm việc", "s1", "p1", "v1", {}, "gio_lam_viec", 0.9)
    ]

    # Mock embedder
    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = [0.1] * 1024

    # Mock Jina Reranker to be disabled (fallback to RRF)
    monkeypatch.setenv("RERANKER_ENABLED", "false")

    # Mock ChatOpenAI tool calls and subsequent grounded text response
    mock_chat = MagicMock()
    # First invocation: call search tool
    first_resp = AIMessage(content="")
    first_resp.tool_calls = [{
        "name": "search_hospital_information_tool",
        "args": {"query": "giờ làm việc"},
        "id": "call-1"
    }]
    # Second invocation (after tool execution): return grounded message
    second_resp = AIMessage(content="Bệnh viện đa khoa mở cửa từ 8:00 đến 17:00 hàng ngày. [[uuid-1]]")
    mock_chat.invoke.side_effect = [first_resp, second_resp]

    monkeypatch.setattr(
        "apps.api.ai.orchestrator.core.agent.ChatOpenAI",
        lambda **kwargs: MagicMock(bind_tools=lambda tools: mock_chat)
    )

    # Mock evaluate_safety to return LOW
    mock_provider = MagicMock()
    mock_provider.evaluate_safety.return_value = MagicMock(risk="LOW", to_dict=lambda: {"risk": "LOW"})
    monkeypatch.setattr(
        "apps.api.ai.orchestrator.core.agent.OpenAIProvider",
        lambda api_key: mock_provider
    )

    msg = HumanMessage(content="Giờ làm việc của bệnh viện là gì?")
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

    config = {
        "configurable": {
            "thread_id": "test-thread-6",
            "openai_api_key": "fake",
            "db_cursor": mock_cur,
            "embedder": mock_embedder
        }
    }

    res = agent_graph.invoke(state, config)
    assert res["final_response"] == "Bệnh viện đa khoa mở cửa từ 8:00 đến 17:00 hàng ngày. [1]"
    assert len(res["citations"]) > 0
    assert res["citations"][0]["chunk_id"] == "uuid-1"

def test_grounding_repair_and_abstention(monkeypatch):
    # Mock database cursor for search tool
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        ("uuid-1", "BHYT chi trả 80% chi phí điều trị ngoại trú.", "bhyt", "s1", "p1", "v1", {}, "bhyt", 0.9)
    ]
    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = [0.1] * 1024
    monkeypatch.setenv("RERANKER_ENABLED", "false")

    # Mock ChatOpenAI:
    # 1. tool call to search
    # 2. ungrounded answer (e.g. mentions 100% price support or something not in chunk)
    # 3. second ungrounded answer (leads to abstention)
    mock_chat = MagicMock()

    call_resp = AIMessage(content="")
    call_resp.tool_calls = [{
        "name": "search_hospital_information_tool",
        "args": {"query": "bhyt"},
        "id": "call-2"
    }]
    bad_resp = AIMessage(content="BHYT chi trả 100% chi phí điều trị nội trú. [[uuid-1]]")
    bad_resp_2 = AIMessage(content="BHYT chi trả 100% cho tất cả các dịch vụ. [[uuid-1]]")

    mock_chat.invoke.side_effect = [call_resp, bad_resp, bad_resp_2]

    monkeypatch.setattr(
        "apps.api.ai.orchestrator.core.agent.ChatOpenAI",
        lambda **kwargs: MagicMock(bind_tools=lambda tools: mock_chat)
    )

    # Mock safety to return LOW
    mock_provider = MagicMock()
    mock_provider.evaluate_safety.return_value = MagicMock(risk="LOW", to_dict=lambda: {"risk": "LOW"})
    monkeypatch.setattr(
        "apps.api.ai.orchestrator.core.agent.OpenAIProvider",
        lambda api_key: mock_provider
    )

    msg = HumanMessage(content="BHYT chi trả như thế nào?")
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

    config = {
        "configurable": {
            "thread_id": "test-thread-7",
            "openai_api_key": "fake",
            "db_cursor": mock_cur,
            "embedder": mock_embedder
        }
    }

    res = agent_graph.invoke(state, config)
    # Should abstain with standard message
    assert res["final_response"] == "Tôi không có đủ thông tin để trả lời câu hỏi này."
# === TASK:WP-303:END ===

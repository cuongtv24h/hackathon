# === TASK:WP-305:START ===
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from apps.api.ai.orchestrator.core import agent_graph

def test_mock_booking_flow_through_agent(monkeypatch):
    # Mock ChatOpenAI to return a booking tool call and then the final success response
    mock_chat = MagicMock()

    first_resp = AIMessage(content="")
    first_resp.tool_calls = [{
        "name": "book_appointment_mock_tool",
        "args": {
            "doctor_id": "doc-456",
            "patient_name": "Tran Van B",
            "patient_phone": "0987654321",
            "schedule_date": "2026-07-22",
            "time_slot": "10:00-10:30"
        },
        "id": "call-3"
    }]

    second_resp = AIMessage(content="Tôi đã ghi nhận yêu cầu đặt lịch hẹn thử nghiệm của bạn.")
    mock_chat.invoke.side_effect = [first_resp, second_resp]

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

    msg = HumanMessage(content="Tôi muốn đặt lịch với bác sĩ doc-456 vào 10:00 ngày 2026-07-22")
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
            "thread_id": "test-thread-8",
            "openai_api_key": "fake"
        }
    }

    res = agent_graph.invoke(state, config)
    assert "thử nghiệm" in res["final_response"] or "Tôi đã ghi nhận" in res["final_response"]
# === TASK:WP-305:END ===

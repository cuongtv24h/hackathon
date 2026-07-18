# === TASK:WP-305:START ===
"""Boundary tests: generic information agent must not create appointments."""

from langchain_core.messages import AIMessage, HumanMessage

from apps.api.ai.orchestrator.core import agent


def test_information_agent_exposes_only_retrieval_tool(monkeypatch):
    bound_tool_names = []

    class FakeChatModel:
        def bind_tools(self, tools):
            bound_tool_names.extend(item.name for item in tools)
            return self

        def invoke(self, messages):
            return AIMessage(content="Vui lòng dùng luồng đặt lịch.")

    monkeypatch.setattr(agent, "ChatOpenAI", lambda **kwargs: FakeChatModel())
    state = {
        "messages": [HumanMessage(content="Tôi muốn đặt lịch khám")],
        "call_count": 0,
        "max_tool_calls": 5,
        "elapsed_time_seconds": 0.0,
        "deadline_timestamp": 0.0,
        "observations": [],
        "repair_attempted": False,
    }

    agent.llm_node(state, {"configurable": {"llm_model": "fake", "llm_api_key": "fake"}})

    assert bound_tool_names == ["search_hospital_information_tool"]
# === TASK:WP-305:END ===

"""Adapter exposing the LangGraph hospital agent through the web capability API."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import psycopg
from langchain_core.messages import HumanMessage

from apps.api.ai.orchestrator.core.agent import agent_graph
from apps.api.core.runtime_dependencies import create_jina_query_embedding_provider


class _QueryEmbedder:
    def __init__(self) -> None:
        self._embed = create_jina_query_embedding_provider()

    def embed_query(self, query: str) -> List[float]:
        return self._embed(query)


@dataclass(frozen=True)
class AgentInformationResponse:
    result: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.result)


class AgentInformationAssistanceAdapter:
    """Translate the PC-01 request DTO to the project's LangGraph state."""

    def __init__(self) -> None:
        if not os.environ.get("DATABASE_URL"):
            raise ValueError("DATABASE_URL is required for the hospital agent")
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is required for the hospital agent")
        self._embedder = _QueryEmbedder()

    @staticmethod
    def _initial_state() -> Dict[str, Any]:
        return {
            "messages": [],
            "safety_result": None,
            "clarification_count": 0,
            "observations": [],
            "citations": [],
            "call_fingerprints": [],
            "max_tool_calls": int(os.environ.get("AGENT_MAX_TOOL_CALLS", "5")),
            "call_count": 0,
            "elapsed_time_seconds": 0.0,
            "deadline_timestamp": 0.0,
            "final_response": None,
            "degradation_status": {},
            "repair_attempted": False,
            "grounding_retry_reasons": [],
            "booking_result": None,
        }

    def execute(self, request: Any) -> AgentInformationResponse:
        config = {
            "configurable": {
                "thread_id": request.session_id,
                "openai_api_key": os.environ["OPENAI_API_KEY"],
                "jina_api_key": os.environ.get("JINA_API_KEY"),
                "embedder": self._embedder,
                "top_n": int(os.environ.get("RAG_TOP_N", "5")),
            }
        }
        snapshot = agent_graph.get_state(config)
        state = dict(snapshot.values) if snapshot.values else self._initial_state()
        state["messages"] = list(state.get("messages", [])) + [HumanMessage(content=request.message)]
        state["final_response"] = None
        state["deadline_timestamp"] = time.time() + float(
            os.environ.get("AGENT_EXECUTION_TIMEOUT_SECONDS", "60")
        )

        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                config["configurable"]["db_cursor"] = cursor
                state = agent_graph.invoke(state, config)

        risk = (state.get("safety_result") or {}).get("risk", "LOW")
        answer = state.get("final_response") or "Tôi không có đủ thông tin để trả lời câu hỏi này."
        if risk == "HIGH":
            outcome = "emergency_rerouted"
        elif risk == "CAUTION":
            outcome = "clarification_required"
        elif answer == "Tôi không có đủ thông tin để trả lời câu hỏi này.":
            outcome = "fallback"
        else:
            outcome = "answered"

        citations = []
        seen = set()
        for citation in state.get("citations", []):
            source_id = str(citation.get("source_id") or citation.get("chunk_id") or "")
            if not source_id or source_id in seen:
                continue
            seen.add(source_id)
            source_path = str(citation.get("source_path") or "")
            citations.append(
                {
                    "source_id": source_id,
                    "title": Path(source_path).name or source_id,
                    "source_type": "hospital_knowledge",
                    "excerpt": citation.get("matched_text") or "",
                    "version": citation.get("version") or "",
                }
            )

        grounded = bool(citations)
        return AgentInformationResponse(
            {
                "outcome": outcome,
                "message": answer,
                "citations": citations,
                "suggested_actions": [],
                "disclaimers": [
                    "Đây là thông tin tham khảo và không thay thế tư vấn y tế trực tiếp."
                ],
                "conversation_state": {"risk": risk},
                "explainability": {
                    "grounded": grounded,
                    "confidence": "high" if grounded else "low",
                    "source_count": len(citations),
                },
                "error": None,
            }
        )


def build_agent_information_assistance_adapter() -> AgentInformationAssistanceAdapter:
    return AgentInformationAssistanceAdapter()


__all__ = [
    "AgentInformationAssistanceAdapter",
    "AgentInformationResponse",
    "build_agent_information_assistance_adapter",
]

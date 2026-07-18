# === TASK:WP-302:START ===
import os
import time
from typing import List, Dict, Any, Optional, TypedDict, Literal
from pathlib import Path

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from packages.contracts.dto import SafetyDecisionDTO, RuleEvidenceDTO, SearchResultDTO, CitationDTO, SearchCandidateDTO
from apps.api.capabilities.emergency.prefilter import (
    has_safety_signal,
    is_clear_non_risk,
    load_emergency_configs,
    match_rules,
    validate_configs,
)
from apps.api.ai.providers.openai import OpenAIProvider
from apps.api.ai.rag import (
    citation_validation_issues,
    map_citations_to_response,
    render_citation_markers,
    search_hospital_information,
    supported_response_text,
)

ROOT = Path(__file__).resolve().parents[5]
BUDGET_EXHAUSTED_MESSAGE = "Xin lỗi, thời gian thực thi của tác vụ đã vượt quá giới hạn cho phép."


def deadline_remaining(state: Dict[str, Any]) -> Optional[float]:
    deadline = state.get("deadline_timestamp")
    if not deadline:
        return None
    return deadline - time.time()

# Define state structure
class AgentState(TypedDict):
    messages: List[BaseMessage]
    safety_result: Optional[Dict[str, Any]]
    clarification_count: int
    observations: List[Dict[str, Any]]
    citations: List[Dict[str, Any]]
    call_fingerprints: List[str]
    max_tool_calls: int
    call_count: int
    elapsed_time_seconds: float
    deadline_timestamp: float
    final_response: Optional[str]
    degradation_status: Dict[str, Any]
    repair_attempted: bool
    grounding_retry_reasons: List[str]
    booking_result: Optional[Dict[str, Any]]


# Define LangChain tools with RunnableConfig access to connection context
@tool
def search_hospital_information_tool(query: str, config: RunnableConfig) -> Dict[str, Any]:
    """Search for information about hospital departments, services, guidelines, prices, or doctors."""
    configurable = config.get("configurable", {})
    cur = configurable.get("db_cursor")
    embedder = configurable.get("embedder")

    # Run the retrieval engine
    result = search_hospital_information(
        cur=cur,
        query=query,
        embedder=embedder,
        reranker_api_key=configurable.get("jina_api_key"),
        reranker_model=os.environ.get("RERANKER_MODEL"),
        reranker_base_url=os.environ.get("RERANKER_BASE_URL", "https://api.jina.ai/v1/rerank"),
        reranker_timeout=float(os.environ.get("RERANKER_TIMEOUT_SECONDS", "5.0")),
        top_n=configurable.get("top_n", 5),
        rrf_k=configurable.get("rrf_k", 60)
    )
    return result.to_dict()


def has_safety_hint(text: str) -> bool:
    hints = ["đau", "sốt", "mệt", "khó chịu", "nôn", "chảy máu", "co giật", "ho", "ngất", "khó thở"]
    text_lower = text.lower()
    return any(h in text_lower for h in hints)


# Node 1: Direct rule matching (no LLM, no DB)
def direct_safety_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    messages = state.get("messages", [])
    if not messages:
        return {}

    pending_caution = (
        state.get("safety_result")
        if (state.get("safety_result") or {}).get("risk") == "CAUTION"
        and state.get("clarification_count", 0) > 0
        else None
    )
    sanitized_messages = [
        message
        for message in messages
        if not isinstance(message, ToolMessage)
        and not (isinstance(message, AIMessage) and getattr(message, "tool_calls", None))
        and not (isinstance(message, AIMessage) and "[[" in str(message.content))
    ]
    turn_reset = {
        "messages": sanitized_messages,
        "safety_result": pending_caution,
        "observations": [],
        "citations": [],
        "call_fingerprints": [],
        "call_count": 0,
        "elapsed_time_seconds": 0.0,
        "final_response": None,
        "degradation_status": {},
        "repair_attempted": False,
        "grounding_retry_reasons": [],
        "booking_result": None,
    }

    last_msg = messages[-1].content
    rules, _, _ = load_emergency_configs()

    if pending_caution is not None:
        return turn_reset

    if is_clear_non_risk(last_msg, rules):
        turn_reset["safety_result"] = {
            "risk": "LOW",
            "source": "local_clear_non_risk",
            "reason_code": "NO_SAFETY_SIGNAL_OR_REFERENCE_CONTEXT",
            "evidence_spans": [],
        }
        return turn_reset

    evidence = match_rules(last_msg, rules)
    if evidence:
        turn_reset["safety_result"] = {
                "risk": "HIGH",
                "source": "direct_rule",
                "rule_id": evidence.rule_id,
                "evidence_spans": [evidence.evidence_span]
        }
    return turn_reset


# Node 2: Semantic safety evaluation (OpenAI structured outputs)
def semantic_safety_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    if state.get("safety_result") is not None:
        return {}

    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1].content
    provider = OpenAIProvider(api_key=config.get("configurable", {}).get("openai_api_key"))

    try:
        decision = provider.evaluate_safety(last_msg)
        return {"safety_result": decision.to_dict()}
    except Exception as exc:
        # If evaluator fails/times out, fall back to CAUTION if caution-hinted, else LOW
        rules, _, _ = load_emergency_configs()
        if has_safety_signal(last_msg, rules):
            return {
                "safety_result": {
                    "risk": "CAUTION",
                    "source": "fallback",
                    "clarification_id": "CLAR-EMERGENCY-001",
                    "reason_code": "EVALUATOR_FAILURE"
                }
            }
        return {"safety_result": {"risk": "LOW"}}


# Safety routing edge
def route_safety(state: AgentState) -> str:
    result = state.get("safety_result") or {}
    risk = result.get("risk", "LOW")
    if risk == "HIGH":
        return "high_response"
    elif risk == "CAUTION":
        return "caution_node"
    return "llm_node"


# Node 3: HIGH response node
def high_response_node(state: AgentState) -> Dict[str, Any]:
    msg = "CẢNH BÁO NGUY HIỂM: Bạn đang báo cáo một tình huống y tế khẩn cấp. Vui lòng gọi ngay số 115 hoặc di chuyển đến cơ sở y tế gần nhất ngay lập tức. Không tiếp tục chat."
    return {
        "final_response": msg,
        "messages": state.get("messages", []) + [AIMessage(content=msg)]
    }


# Node 4: CAUTION clarification node
def caution_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    count = state.get("clarification_count", 0)
    messages = state.get("messages", [])

    if count == 0:
        question = "Bạn có đang gặp phải tình trạng nguy kịch hoặc cấp cứu khẩn cấp không? Vui lòng trả lời CÓ hoặc KHÔNG."
        return {
            "clarification_count": 1,
            "final_response": question,
            "messages": messages + [AIMessage(content=question)]
        }

    # Re-evaluate clarification answer
    import re
    last_ans = messages[-1].content.strip().lower()
    words = re.findall(r'\b\w+\b', last_ans)

    # Heuristics for Vietnamese clarification reply
    if any(w in words for w in ["có", "phải", "đúng", "yes", "co"]):
        return {
            "safety_result": {"risk": "HIGH"},
            "clarification_count": count + 1
        }
    elif any(w in words for w in ["không", "khong", "no"]):
        return {
            "safety_result": {"risk": "LOW"},
            "clarification_count": count + 1
        }
    else:
        # Unresolved caution fallback message
        fallback = "CHÚ Ý: Câu hỏi của bạn có thể chứa thông tin nhạy cảm liên quan đến an toàn sức khỏe. Chúng tôi cần tạm ngừng các tác vụ thông thường. Vui lòng liên hệ hotline hỗ trợ nếu cần."
        return {
            "final_response": fallback,
            "messages": messages + [AIMessage(content=fallback)],
            "clarification_count": count + 1
        }


# Edge routing for caution clarification
def route_caution(state: AgentState) -> str:
    risk = (state.get("safety_result") or {}).get("risk", "LOW")
    if risk == "HIGH":
        return "high_response_node"
    elif risk == "LOW":
        return "llm_node"
    return END


# Node 5: General LLM tool-calling node
def llm_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    # Check max tool call budget
    max_calls = state.get("max_tool_calls", 5)
    call_count = state.get("call_count", 0)
    remaining = deadline_remaining(state)
    if call_count >= max_calls or (remaining is not None and remaining <= 0):
        fallback = BUDGET_EXHAUSTED_MESSAGE
        return {
            "final_response": fallback,
            "messages": state.get("messages", []) + [AIMessage(content=fallback)]
        }

    model_name = os.environ.get("AGENT_MODEL", "gpt-5-mini")
    openai_key = config.get("configurable", {}).get("openai_api_key")
    llm_options = {
        "model": model_name,
        "openai_api_key": openai_key,
        "temperature": 0.0,
    }
    if remaining is not None:
        llm_options["timeout"] = max(0.1, remaining)
    llm = ChatOpenAI(**llm_options)

    # PC-01 is retrieval-only. Appointment creation belongs exclusively to
    # PC-03, which enforces the guided form, confirmation and idempotency.
    tools = [search_hospital_information_tool]
    llm_with_tools = llm.bind_tools(tools)

    # System instruction prompt loaded from file
    prompt_path = ROOT / "config" / "prompts" / "hospital-agent.md"
    system_instruction = prompt_path.read_text(encoding="utf-8")

    input_msgs = [SystemMessage(content=system_instruction)] + state.get("messages", [])

    # If this is a repair attempt, append the repair prompt
    if state.get("repair_attempted", False) and not state.get("final_response"):
        if not state.get("observations"):
            repair_instruction = (
                "VERIFICATION FAILED: there are no search observations for the current turn. "
                "You MUST call search_hospital_information now using the user's current question before answering."
            )
        else:
            repair_instruction = (
                "VERIFICATION FAILED: one or more factual lines had a missing/unknown [[chunk_id]] citation, "
                "or used a number absent from the cited evidence. Rewrite once using only observed chunk IDs. "
                "End every factual sentence or bullet with one or more [[chunk_id]] markers."
            )
        input_msgs.append(SystemMessage(content=repair_instruction))

    started_at = time.monotonic()
    response = llm_with_tools.invoke(input_msgs)
    elapsed = state.get("elapsed_time_seconds", 0.0) + (time.monotonic() - started_at)

    # Validate duplicate tool call prevention
    if response.tool_calls:
        if call_count + len(response.tool_calls) > max_calls:
            fallback = BUDGET_EXHAUSTED_MESSAGE
            return {
                "final_response": fallback,
                "elapsed_time_seconds": elapsed,
                "messages": state.get("messages", []) + [AIMessage(content=fallback)]
            }
        seen = state.get("call_fingerprints", [])
        new_fingerprints = []
        for tc in response.tool_calls:
            fingerprint = f"{tc['name']}:{str(tc['args'])}"
            if fingerprint in seen:
                fallback = "Xin lỗi, thời gian thực thi của tác vụ đã vượt quá giới hạn cho phép do vòng lặp."
                return {
                    "final_response": fallback,
                    "messages": state.get("messages", []) + [AIMessage(content=fallback)]
                }
            new_fingerprints.append(fingerprint)

        return {
            "messages": state.get("messages", []) + [response],
            "call_fingerprints": seen + new_fingerprints,
            "elapsed_time_seconds": elapsed
        }

    return {
        "messages": state.get("messages", []) + [response],
        "elapsed_time_seconds": elapsed
    }


# Edge routing for LLM output (tools vs verification)
def route_llm(state: AgentState) -> str:
    last_msg = state.get("messages", [])[-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tool_node"
    return "grounding_verification_node"


# Node 6: Tool execution node
def tool_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    last_msg = state.get("messages", [])[-1]
    tool_calls = last_msg.tool_calls

    new_messages = []
    observations = list(state.get("observations", []))
    call_count = state.get("call_count", 0)

    for tc in tool_calls:
        remaining = deadline_remaining(state)
        if remaining is not None and remaining <= 0:
            fallback = BUDGET_EXHAUSTED_MESSAGE
            return {
                "final_response": fallback,
                "messages": state.get("messages", []) + [AIMessage(content=fallback)],
                "observations": observations,
                "call_count": call_count
            }
        name = tc["name"]
        args = tc["args"]
        tc_id = tc["id"]

        if name == "search_hospital_information_tool":
            # Preserve exact service names and codes from the user's latest turn.
            latest_user_query = next(
                (
                    message.content
                    for message in reversed(state.get("messages", [])[:-1])
                    if isinstance(message, HumanMessage) and isinstance(message.content, str)
                ),
                "",
            ).strip()
            search_query = latest_user_query or args.get("query")
            res = search_hospital_information_tool.invoke({"query": search_query}, config)
            # Record observations
            observations.append(res)
            new_messages.append(ToolMessage(content=str(res), tool_call_id=tc_id))
        call_count += 1

    return {
        "messages": state.get("messages", []) + new_messages,
        "observations": observations,
        "call_count": call_count
    }


def route_tool(state: AgentState) -> str:
    if state.get("final_response"):
        return END
    return "llm_node"


# Node 7: Grounding verification node
def grounding_verification_node(state: AgentState) -> Dict[str, Any]:
    last_msg = state.get("messages", [])[-1]
    response_text = last_msg.content

    if not state.get("observations"):
        issues = citation_validation_issues(response_text, [])
        if issues and not state.get("repair_attempted", False):
            return {
                "repair_attempted": True,
                "grounding_retry_reasons": [
                    "no_current_turn_search_observations",
                    *issues,
                ],
            }
        if issues:
            abstain = "Tôi không có đủ thông tin để trả lời câu hỏi này."
            return {
                "final_response": abstain,
                "grounding_retry_reasons": [
                    "no_current_turn_search_observations",
                    *issues,
                ],
                "messages": state.get("messages", []) + [AIMessage(content=abstain)],
            }
        return {
            "final_response": response_text,
            "citations": []
        }

    # Extract candidates from observations
    candidates = []
    for obs in state.get("observations", []):
        for c_dict in obs.get("candidates", []):
            candidates.append(SearchCandidateDTO(
                chunk_id=c_dict["chunk_id"],
                content=c_dict["content"],
                score=c_dict["score"],
                domain=c_dict["domain"],
                sub_topic=c_dict["sub_topic"],
                source_id=c_dict["source_id"],
                source_path=c_dict["source_path"],
                version=c_dict["version"]
            ))

    grounded, citations = map_citations_to_response(response_text, candidates)

    if grounded:
        rendered_response = render_citation_markers(response_text, citations)
        return {
            "final_response": rendered_response,
            "citations": [c.to_dict() for c in citations]
        }
    else:
        retry_reasons = citation_validation_issues(response_text, candidates)
        if citations:
            filtered_response = supported_response_text(response_text, candidates)
            rendered_response = render_citation_markers(filtered_response, citations)
            return {
                "final_response": rendered_response,
                "citations": [citation.to_dict() for citation in citations],
                "degradation_status": {
                    "grounding_claims_dropped": True,
                    "reasons": retry_reasons,
                },
            }
        # If repair was already attempted, abstain
        if state.get("repair_attempted", False):
            abstain = "Tôi không có đủ thông tin để trả lời câu hỏi này."
            return {
                "final_response": abstain,
                "grounding_retry_reasons": retry_reasons,
                "messages": state.get("messages", []) + [AIMessage(content=abstain)]
            }
        else:
            # Trigger repair once
            return {
                "repair_attempted": True,
                "grounding_retry_reasons": retry_reasons,
            }


# Edge routing for repair
def route_repair(state: AgentState) -> str:
    if state.get("final_response"):
        return END
    return "llm_node"


# Build state graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("direct_safety", direct_safety_node)
workflow.add_node("semantic_safety", semantic_safety_node)
workflow.add_node("high_response_node", high_response_node)
workflow.add_node("caution_node", caution_node)
workflow.add_node("llm_node", llm_node)
workflow.add_node("tool_node", tool_node)
workflow.add_node("grounding_verification_node", grounding_verification_node)

# Set starting point
workflow.add_edge(START, "direct_safety")
workflow.add_edge("direct_safety", "semantic_safety")

# Safety routing edge
workflow.add_conditional_edges(
    "semantic_safety",
    route_safety,
    {
        "high_response": "high_response_node",
        "caution_node": "caution_node",
        "llm_node": "llm_node"
    }
)

# Caution node routing
workflow.add_conditional_edges(
    "caution_node",
    route_caution,
    {
        "high_response_node": "high_response_node",
        "llm_node": "llm_node",
        END: END
    }
)

# LLM routing
workflow.add_conditional_edges(
    "llm_node",
    route_llm,
    {
        "tool_node": "tool_node",
        "grounding_verification_node": "grounding_verification_node"
    }
)

# Tool loop back to LLM unless execution budget was exhausted.
workflow.add_conditional_edges(
    "tool_node",
    route_tool,
    {"llm_node": "llm_node", END: END}
)

# Verification repair loop
workflow.add_conditional_edges(
    "grounding_verification_node",
    route_repair,
    {
        "llm_node": "llm_node",
        END: END
    }
)

# Connect endpoints
workflow.add_edge("high_response_node", END)

# In-memory checkpointer for MVP tests
checkpointer = MemorySaver()
agent_graph = workflow.compile(checkpointer=checkpointer)
# === TASK:WP-302:END ===

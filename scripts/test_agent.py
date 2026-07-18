import os
import sys
import uuid
import psycopg
from pathlib import Path
from langchain_core.messages import HumanMessage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Load .env file manually if present
env_path = ROOT / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

from apps.api.ai.orchestrator.core import agent_graph
from apps.api.capabilities.emergency.prefilter import load_emergency_configs

import requests

class JinaQueryEmbedder:
    def __init__(self, api_key: str, model: str = "jina-embeddings-v5-text-small"):
        self.api_key = api_key
        self.model = model
        self.base_url = os.environ.get("JINA_BASE_URL", "https://api.jina.ai/v1")
        
    def embed_query(self, query: str):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "dimensions": 1024,
            "task": "retrieval.query",
            "input": [query]
        }
        url = f"{self.base_url.rstrip('/')}/embeddings"
        response = requests.post(url, json=data, headers=headers, timeout=10.0)
        if response.status_code != 200:
            raise ValueError(f"Jina API Error: {response.text}")
        return response.json()["data"][0]["embedding"]

class FakeEmbedder:
    def embed_query(self, query: str):
        return [0.1] * 1024

def main():
    print("=== Hospital Agent MVP Interactive Test System ===")
    print("Môi trường:")
    print(f"  APP_ENV: {os.environ.get('APP_ENV', 'development')}")
    print(f"  OPENAI_API_KEY: {'configured' if os.environ.get('OPENAI_API_KEY') else 'missing'}")
    print(f"  JINA_API_KEY: {'configured' if os.environ.get('JINA_API_KEY') else 'missing'}")
    print(f"  DATABASE_URL: {'configured' if os.environ.get('DATABASE_URL') else 'missing'}")
    print("-" * 50)

    # Establish db connection if available
    db_url = os.environ.get("DATABASE_URL")
    conn = None
    cur = None
    if db_url:
        try:
            conn = psycopg.connect(db_url)
            cur = conn.cursor()
            print("✓ Kết nối database thành công.")
        except Exception as exc:
            print(f"✗ Không kết nối được database: {exc}. RAG search sẽ hoạt động ở chế độ fallback.")
    else:
        print("ℹ Không cấu hình DATABASE_URL. RAG search sẽ hoạt động ở chế độ fallback.")

    jina_key = os.environ.get("JINA_API_KEY")
    if jina_key:
        embedder = JinaQueryEmbedder(jina_key, os.environ.get("EMBEDDING_MODEL", "jina-embeddings-v5-text-small"))
        print("✓ Khởi tạo Jina Embedder thực tế thành công.")
    else:
        embedder = FakeEmbedder()
        print("⚠ Không tìm thấy JINA_API_KEY. Sử dụng FakeEmbedder.")
    thread_id = str(uuid.uuid4())
    config = {
        "configurable": {
            "thread_id": thread_id,
            "openai_api_key": os.environ.get("OPENAI_API_KEY", "fake"),
            "jina_api_key": os.environ.get("JINA_API_KEY", "fake"),
            "db_cursor": cur,
            "embedder": embedder,
            "top_n": 5
        }
    }

    # Initial state
    state = {
        "messages": [],
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

    print("\nBắt đầu chat! Gõ 'exit' hoặc 'quit' để thoát.")
    while True:
        try:
            user_input = input("\nUser > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit"]:
                break

            # Add human message to state messages
            state["messages"].append(HumanMessage(content=user_input))
            # Clear previous final response to let graph compute next
            state["final_response"] = None

            # Invoke graph
            state = agent_graph.invoke(state, config)

            if state.get("repair_attempted"):
                reasons = state.get("grounding_retry_reasons") or ["unknown"]
                print("  [Grounding Retry] Có retry do verifier chặn:")
                for reason in reasons:
                    print(f"    - {reason}")
                if state.get("final_response") == "Tôi không có đủ thông tin để trả lời câu hỏi này.":
                    print("  [Grounding Retry] Retry không hợp lệ; agent đã abstain.")
                else:
                    print("  [Grounding Retry] Câu trả lời sau retry hợp lệ.")
            else:
                print("  [Grounding Retry] Không retry trong lượt này.")

            # Print outcome details
            safety = state.get("safety_result") or {}
            print(f"  [Safety Gate] Risk: {safety.get('risk', 'LOW')} (Source: {safety.get('source', 'evaluator')})")
            if state.get("citations"):
                print(f"  [Citations] Count: {len(state['citations'])}")
                for cit in state["citations"]:
                    print(f"    - {cit.get('source_path')} (Section: {cit.get('source_section')})")
            
            print(f"Agent > {state['final_response']}")

        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"Lỗi: {exc}")

    if conn:
        conn.close()

if __name__ == "__main__":
    main()

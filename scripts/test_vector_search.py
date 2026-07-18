import os
import sys
import psycopg
import requests
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Load .env file manually if present
env_path = ROOT / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

from apps.api.foundation.knowledge.repository.vector_search import vector_search
from apps.api.foundation.knowledge.repository.lexical_search import lexical_search
from apps.api.foundation.knowledge.repository.hybrid_search import hybrid_search
from apps.api.ai.rag.rrf import reciprocal_rank_fusion
from apps.api.ai.rag.reranker import rerank_candidates

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

def main():
    print("=== RAG & Hybrid Vector Search Interactive Test ===")
    db_url = os.environ.get("DATABASE_URL")
    jina_key = os.environ.get("JINA_API_KEY")
    
    if not db_url:
        print("Lỗi: DATABASE_URL chưa được cấu hình trong file .env.")
        sys.exit(1)
        
    try:
        conn = psycopg.connect(db_url)
        cur = conn.cursor()
        print("✓ Kết nối database thành công.")
    except Exception as exc:
        print(f"Lỗi kết nối database: {exc}")
        sys.exit(1)

    # Initialize query embedder
    embedder = None
    if jina_key:
        embedder = JinaQueryEmbedder(jina_key, os.environ.get("EMBEDDING_MODEL", "jina-embeddings-v5-text-small"))
        print("✓ Jina Embeddings API đã sẵn sàng.")
    else:
        print("⚠ Không tìm thấy JINA_API_KEY trong .env. Sẽ tạo vector giả lập [0.1] * 1024 để chạy thử SQL.")

    print("-" * 50)
    print("Nhập câu hỏi để thực hiện tra cứu. Gõ 'exit' hoặc 'quit' để thoát.")
    
    while True:
        try:
            query = input("\nQuery > ").strip()
            if not query:
                continue
            if query.lower() in ["exit", "quit"]:
                break

            # 1. Embed query
            query_vector = None
            if embedder:
                print("-> Đang gọi Jina API để nhúng câu hỏi...")
                query_vector = embedder.embed_query(query)
                print("✓ Đã nhận query vector từ Jina.")
            else:
                # Mock vector of length 1024
                query_vector = [0.01] * 1024
            
            # 2. Parallel hybrid lane search
            print("-> Đang truy vấn Supabase (Lanes: Vector & FTS)...")
            vec_res = []
            if query_vector:
                try:
                    vec_res = vector_search(cur, query_vector, limit=10)
                except Exception as e:
                    print(f"  [Error Vector Lane]: {e}")
            
            lex_res = []
            try:
                lex_res = lexical_search(cur, query, limit=10)
            except Exception as e:
                print(f"  [Error Lexical Lane]: {e}")

            print(f"✓ Hoàn tất truy vấn. Tìm thấy:")
            print(f"  - Vector lane: {len(vec_res)} kết quả")
            print(f"  - Lexical lane: {len(lex_res)} kết quả")

            # Print Lane candidates
            if vec_res:
                print("\n--- [VECTOR LANE TOP 3] ---")
                for i, c in enumerate(vec_res[:3]):
                    print(f"  {i+1}. [{c.domain}] {c.chunk_id} (Score: {c.score:.4f})")
                    print(f"     Content: {c.content[:500]}...")

            if lex_res:
                print("\n--- [LEXICAL LANE TOP 3] ---")
                for i, c in enumerate(lex_res[:3]):
                    print(f"  {i+1}. [{c.domain}] {c.chunk_id} (Score: {c.score:.4f})")
                    print(f"     Content: {c.content[:100]}...")

            # 3. Reciprocal Rank Fusion (RRF)
            fused = reciprocal_rank_fusion(vec_res, lex_res, k=60)
            print(f"\n--- [RRF FUSED TOP 5] ---")
            for i, c in enumerate(fused[:5]):
                print(f"  {i+1}. [{c.domain}] {c.chunk_id} (RRF Score: {c.score:.6f})")
                print(f"     Content: {c.content[:120]}...")

            # 4. Reranking (optional)
            if fused and os.environ.get("RERANKER_ENABLED", "true").lower() == "true":
                provider = os.environ.get("RERANKER_PROVIDER", "bge")
                print(f"\n-> Đang chạy {provider.upper()} Reranker...")
                reranked, applied, err = rerank_candidates(
                    query=query,
                    candidates=fused[:10],
                    api_key=jina_key,
                    model=os.environ.get("RERANKER_MODEL"),
                    top_n=5,
                    provider=provider,
                )
                if applied:
                    print(f"--- [{provider.upper()} RERANKED TOP 5] ---")
                    for i, c in enumerate(reranked):
                        print(f"  {i+1}. [{c.domain}] {c.chunk_id} (Relevance Score: {c.score:.4f})")
                        print(f"     Content: {c.content[:120]}...")
                else:
                    print(f"  ⚠ Không thể Rerank: {err}")

        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"Lỗi: {exc}")

    conn.close()
    print("Đã đóng kết nối database.")

if __name__ == "__main__":
    main()

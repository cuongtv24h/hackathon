# === TASK:WP-201:START ===
import os
import requests
from functools import lru_cache
from typing import List, Tuple, Optional
from packages.contracts.dto import SearchCandidateDTO

BGE_DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"
JINA_DEFAULT_MODEL = "jina-reranker-v2-base-multilingual"


@lru_cache(maxsize=2)
def _load_bge_model(model_name: str, device: Optional[str]):
    from sentence_transformers import CrossEncoder

    local_only = os.environ.get("RERANKER_LOCAL_ONLY", "true").lower() == "true"
    resolved_model = model_name
    if local_only and not os.path.isdir(model_name):
        from huggingface_hub import snapshot_download

        resolved_model = snapshot_download(repo_id=model_name, local_files_only=True)
    return CrossEncoder(resolved_model, device=device)


def _with_score(candidate: SearchCandidateDTO, score: float) -> SearchCandidateDTO:
    return SearchCandidateDTO(
        chunk_id=candidate.chunk_id,
        content=candidate.content,
        score=score,
        domain=candidate.domain,
        sub_topic=candidate.sub_topic,
        source_id=candidate.source_id,
        source_path=candidate.source_path,
        version=candidate.version,
        vector_rank=candidate.vector_rank,
        lexical_rank=candidate.lexical_rank,
        fused_rank=candidate.fused_rank,
    )


def _rerank_with_bge(
    query: str,
    candidates: List[SearchCandidateDTO],
    model: str,
    top_n: int,
) -> Tuple[List[SearchCandidateDTO], bool, Optional[str]]:
    try:
        device = os.environ.get("RERANKER_DEVICE") or None
        cross_encoder = _load_bge_model(model, device)
        pairs = [(query, candidate.content) for candidate in candidates]
        scores = cross_encoder.predict(
            pairs,
            batch_size=int(os.environ.get("RERANKER_BATCH_SIZE", "8")),
            show_progress_bar=False,
        )
        if len(scores) != len(candidates):
            return candidates[:top_n], False, "BGE returned an incomplete score list"
        ranked = sorted(
            (_with_score(candidate, float(score)) for candidate, score in zip(candidates, scores)),
            key=lambda candidate: (-candidate.score, candidate.fused_rank or 0, candidate.chunk_id),
        )
        return ranked[:top_n], True, None
    except Exception as exc:
        return candidates[:top_n], False, f"BGE reranker failed: {type(exc).__name__}: {exc}"

def rerank_candidates(
    query: str,
    candidates: List[SearchCandidateDTO],
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: str = "https://api.jina.ai/v1/rerank",
    timeout: float = 5.0,
    top_n: int = 5,
    provider: Optional[str] = None,
) -> Tuple[List[SearchCandidateDTO], bool, Optional[str]]:
    """Rerank candidates locally with BGE or remotely with Jina."""
    if not candidates:
        return [], True, None

    provider = (provider or os.environ.get("RERANKER_PROVIDER", "bge")).lower()
    if provider == "bge":
        return _rerank_with_bge(query, candidates, model or BGE_DEFAULT_MODEL, top_n)
    if provider != "jina":
        return candidates[:top_n], False, f"Unsupported reranker provider: {provider}"

    model = model or JINA_DEFAULT_MODEL
        
    api_key = api_key or os.environ.get("JINA_API_KEY")
    if not api_key:
        return candidates[:top_n], False, "JINA_API_KEY is not configured"
        
    docs = [c.content for c in candidates]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "query": query,
        "documents": docs,
        "top_n": top_n
    }
    
    try:
        response = requests.post(base_url, json=payload, headers=headers, timeout=timeout)
        if response.status_code != 200:
            return candidates[:top_n], False, f"Jina API returned status {response.status_code}: {response.text}"
            
        data = response.json()
        results = data.get("results", [])
        
        if not results:
            return candidates[:top_n], False, "Reranker returned empty results list"
            
        seen_indices = set()
        reranked_candidates = []
        
        for item in results:
            idx = item.get("index")
            score = item.get("relevance_score")
            
            if idx is None or score is None:
                return candidates[:top_n], False, "Malformed item in reranker results"
            if idx < 0 or idx >= len(candidates):
                return candidates[:top_n], False, f"Invalid index in reranker results: {idx}"
            if idx in seen_indices:
                return candidates[:top_n], False, f"Duplicate index in reranker results: {idx}"
                
            seen_indices.add(idx)
            reranked_candidates.append(_with_score(candidates[idx], float(score)))
            
        return reranked_candidates, True, None
        
    except requests.exceptions.Timeout:
        return candidates[:top_n], False, "Jina Reranker request timed out"
    except Exception as exc:
        return candidates[:top_n], False, f"Jina Reranker failed: {exc}"
# === TASK:WP-201:END ===

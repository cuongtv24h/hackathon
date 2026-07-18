# === TASK:WP-201:START ===
import os
import re
from typing import List, Tuple, Optional
from packages.contracts.dto import SearchCandidateDTO, SearchResultDTO, DegradationMetadataDTO
from apps.api.foundation.knowledge.repository import hybrid_search
from .rrf import reciprocal_rank_fusion
from .reranker import rerank_candidates

def check_sufficiency_and_conflicts(candidates: List[SearchCandidateDTO]) -> Tuple[bool, Optional[str]]:
    """Determine if candidates are sufficient and free from contradictory facts."""
    if not candidates:
        return False, "No candidates found"

    # Heuristic: conflict detection for prices
    prices = {}
    for c in candidates:
        if c.sub_topic:
            price_match = re.findall(r'\b\d{3,}(?:\.\d+)*\b', c.content)
            if price_match:
                price_val = price_match[0]
                if c.sub_topic in prices and prices[c.sub_topic] != price_val:
                    return False, f"Conflict detected in topic '{c.sub_topic}': {prices[c.sub_topic]} vs {price_val}"
                prices[c.sub_topic] = price_val

    return True, None


def search_hospital_information(
    cur,
    query: str,
    embedder,
    reranker_api_key: Optional[str] = None,
    reranker_model: Optional[str] = None,
    reranker_base_url: str = "https://api.jina.ai/v1/rerank",
    reranker_timeout: float = 5.0,
    top_n: int = 5,
    rrf_k: int = 60
) -> SearchResultDTO:
    """The evidence-returning search tool over query embedding, hybrid retrieval, RRF, and Jina Reranking."""
    # 1. Embed query (safe preflight validation inside embedder)
    try:
        query_vector = embedder.embed_query(query)
    except Exception as exc:
        # Fall back to lexical search
        query_vector = None

    # 2. Query hybrid lanes
    vector_cands, lexical_cands, degradation = hybrid_search(cur, query, query_vector, limit=20)

    # 3. Fuse ranks with RRF
    fused_cands = reciprocal_rank_fusion(vector_cands, lexical_cands, k=rrf_k)

    # 4. Jina Reranking
    reranker_applied = False
    rerank_error = None
    final_candidates = fused_cands[:top_n]

    reranker_enabled = os.environ.get("RERANKER_ENABLED", "true").lower() == "true"
    if fused_cands and reranker_enabled:
        reranked, reranker_applied, rerank_error = rerank_candidates(
            query=query,
            candidates=fused_cands[:20],
            api_key=reranker_api_key,
            model=reranker_model,
            base_url=reranker_base_url,
            timeout=reranker_timeout,
            top_n=top_n,
            provider=os.environ.get("RERANKER_PROVIDER", "bge"),
        )
        if reranker_applied:
            final_candidates = reranked

    # 5. Sufficiency and conflict checks
    sufficient, conflict_reason = check_sufficiency_and_conflicts(final_candidates)

    metadata = {
        "provider_failure": degradation.provider_failure,
        "model_failure": degradation.model_failure,
        "reranker_applied": reranker_applied,
        "rerank_error": rerank_error,
        "conflict_reason": conflict_reason,
        "vector_candidate_count": len(vector_cands),
        "lexical_candidate_count": len(lexical_cands)
    }

    return SearchResultDTO(
        sufficient=sufficient,
        candidates=final_candidates,
        metadata=metadata
    )
# === TASK:WP-201:END ===

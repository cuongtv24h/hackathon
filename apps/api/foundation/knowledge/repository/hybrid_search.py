# === TASK:WP-102:START ===
from typing import List, Tuple, Optional
from packages.contracts.dto import SearchCandidateDTO, DegradationMetadataDTO
from .vector_search import vector_search
from .lexical_search import lexical_search

def hybrid_search(
    cur,
    query_text: str,
    query_vector: Optional[List[float]],
    limit: int = 5
) -> Tuple[List[SearchCandidateDTO], List[SearchCandidateDTO], DegradationMetadataDTO]:
    """Execute vector and lexical searches independently, handling single-lane degradation."""
    vector_candidates = []
    lexical_candidates = []
    
    provider_failure = False
    model_failure = False
    reasons = []
    
    # 1. Execute vector lane
    if query_vector is not None:
        try:
            vector_candidates = vector_search(cur, query_vector, limit)
        except Exception as exc:
            provider_failure = True
            reasons.append(f"Vector search failed: {exc}")
    else:
        provider_failure = True
        reasons.append("No query vector provided")
        
    # 2. Execute lexical lane
    try:
        lexical_candidates = lexical_search(cur, query_text, limit)
    except Exception as exc:
        model_failure = True
        reasons.append(f"Lexical search failed: {exc}")
        
    # 3. If both failed, raise a stable generic error
    if provider_failure and model_failure:
        raise RuntimeError("RAG search tool is currently unavailable due to database or provider errors.")
        
    degradation = DegradationMetadataDTO(
        provider_failure=provider_failure,
        model_failure=model_failure,
        reranker_failure=False,
        fallback_active=provider_failure or model_failure,
        reason="; ".join(reasons) if reasons else None
    )
    
    return vector_candidates, lexical_candidates, degradation
# === TASK:WP-102:END ===

# === TASK:WP-201:START ===
from typing import List
from packages.contracts.dto import SearchCandidateDTO

def reciprocal_rank_fusion(
    vector_results: List[SearchCandidateDTO],
    lexical_results: List[SearchCandidateDTO],
    k: int = 60
) -> List[SearchCandidateDTO]:
    """Fuse vector and lexical ranks using Reciprocal Rank Fusion (RRF) with stable tie-breaking."""
    scores = {}
    candidates_by_id = {}
    vector_ranks = {}
    lexical_ranks = {}
    
    # 1. Vector lane ranks
    for rank_0, c in enumerate(vector_results):
        rank = rank_0 + 1
        scores[c.chunk_id] = scores.get(c.chunk_id, 0.0) + (1.0 / (k + rank))
        vector_ranks[c.chunk_id] = rank
        if c.chunk_id not in candidates_by_id:
            candidates_by_id[c.chunk_id] = c
            
    # 2. Lexical lane ranks
    for rank_0, c in enumerate(lexical_results):
        rank = rank_0 + 1
        scores[c.chunk_id] = scores.get(c.chunk_id, 0.0) + (1.0 / (k + rank))
        lexical_ranks[c.chunk_id] = rank
        if c.chunk_id not in candidates_by_id:
            candidates_by_id[c.chunk_id] = c
            
    # 3. Sort by score descending, then by chunk_id alphabetically for stable tie-breaking
    sorted_ids = sorted(scores.keys(), key=lambda cid: (-scores[cid], cid))
    
    fused = []
    for fused_rank, cid in enumerate(sorted_ids, start=1):
        base = candidates_by_id[cid]
        fused.append(SearchCandidateDTO(
            chunk_id=base.chunk_id,
            content=base.content,
            score=scores[cid],
            domain=base.domain,
            sub_topic=base.sub_topic,
            source_id=base.source_id,
            source_path=base.source_path,
            version=base.version,
            vector_rank=vector_ranks.get(cid),
            lexical_rank=lexical_ranks.get(cid),
            fused_rank=fused_rank
        ))
    return fused
# === TASK:WP-201:END ===

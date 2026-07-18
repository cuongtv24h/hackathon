# === TASK:WP-102:START ===
from typing import List
from packages.contracts.dto import SearchCandidateDTO

def vector_search(cur, query_vector: List[float], limit: int = 5) -> List[SearchCandidateDTO]:
    """Perform cosine similarity vector search over knowledge chunks."""
    query = """
        SELECT 
            kc.chunk_id,
            kc.content,
            kc.sub_topic,
            kc.source_id,
            kc.source_path,
            kc.source_version,
            kc.metadata,
            kd.domain_code,
            (1 - (kc.embedding <=> %s::vector)) as score
        FROM knowledge_chunks kc
        JOIN knowledge_domains kd ON kc.domain_id = kd.domain_id
        WHERE kc.is_active = true
          AND kc.approval_status IN ('approved_for_pilot', 'approved')
          AND (kc.effective_date IS NULL OR kc.effective_date <= CURRENT_DATE)
        ORDER BY kc.embedding <=> %s::vector
        LIMIT %s
    """
    cur.execute(query, (query_vector, query_vector, limit))
    rows = cur.fetchall()
    
    candidates = []
    for row in rows:
        chunk_uuid = str(row[0])
        content = row[1]
        sub_topic = row[2] or ""
        source_id = row[3]
        source_path = row[4]
        source_version = row[5]
        meta = row[6] or {}
        domain_code = row[7]
        score = float(row[8])
        
        external_id = meta.get("external_chunk_id", chunk_uuid)
        
        candidates.append(SearchCandidateDTO(
            chunk_id=external_id,
            content=content,
            score=score,
            domain=domain_code,
            sub_topic=sub_topic,
            source_id=source_id,
            source_path=source_path,
            version=source_version
        ))
    return candidates
# === TASK:WP-102:END ===

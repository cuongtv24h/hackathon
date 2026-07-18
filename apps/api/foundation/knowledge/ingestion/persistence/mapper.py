# === TASK:WP-008:START ===
import json
import datetime
from typing import Tuple, List, Any
from ..models import ChunkRecord

def map_chunk_to_row(
    record: ChunkRecord,
    domain_id: str,
    embedding: List[float]
) -> Tuple[Any, ...]:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    page_numbers = json.dumps([record.source_page] if record.source_page else [])
    tags = json.dumps(record.tags)
    
    # Store chunker version and full embedding identity in metadata
    emb_identity = f"{record.embedding_provider}:{record.embedding_model}:{record.embedding_dimensions}"
    metadata = json.dumps({
        "external_chunk_id": record.chunk_id,
        "content_hash": record.content_hash,
        "source_section": record.source_section,
        "source_path": record.source_path,
        "chunker_version": record.chunker_version,
        "embedding_identity": emb_identity,
    })
    
    embedding_json = json.dumps(embedding)
    
    return (
        record.persistence_uuid,
        domain_id,
        record.content,
        record.sub_topic,
        record.source_id,
        record.source_path,
        record.version,
        record.approval_status,
        record.effective_date or None,
        page_numbers,
        tags,
        metadata,
        embedding_json,
        record.is_active,
        now,
        now,
    )
# === TASK:WP-008:END ===

# === TASK:WP-008:START ===
import json
import datetime
from typing import List, Set, Dict, Any, Tuple
from ..models import ChunkRecord, ImportPlan
from ..errors import ValidationError, IngestionError
from .mapper import map_chunk_to_row

def check_preflight_dimensions(cur, expected_dim: int) -> None:
    """Preflight check: Verify that config dimensions match DB vector column."""
    cur.execute(
        """
        SELECT atttypmod 
        FROM pg_attribute 
        WHERE attrelid = 'knowledge_chunks'::regclass 
          AND attname = 'embedding'
        """
    )
    row = cur.fetchone()
    if not row:
        raise ValidationError("knowledge_chunks table or embedding column not found in database.")
    
    db_dim = row[0]
    if db_dim <= 0:
        raise ValidationError("Could not determine database vector column dimension.")
        
    if db_dim != expected_dim:
        raise ValidationError(
            f"Configuration EMBEDDING_DIMENSIONS ({expected_dim}) "
            f"does not match database vector column dimension ({db_dim})"
        )


def build_import_plan(
    cur,
    chunk_records: List[ChunkRecord],
    provider: str,
    model: str,
    dimensions: int
) -> ImportPlan:
    """Idempotent plan constructor: skip embedding/update if unchanged."""
    source_ids = {r.source_id for r in chunk_records}
    if not source_ids:
        return ImportPlan()

    cur.execute(
        "SELECT chunk_id, metadata, is_active FROM knowledge_chunks WHERE source_id = ANY(%s)",
        (list(source_ids),)
    )
    existing = {}
    for cid, meta, is_active in cur.fetchall():
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        existing[str(cid)] = {"metadata": meta or {}, "is_active": is_active}

    to_insert = []
    to_update = []
    to_skip = []
    
    expected_identity = f"{provider}:{model}:{dimensions}"
    
    for r in chunk_records:
        cid = str(r.persistence_uuid)
        if cid in existing:
            ext = existing[cid]
            meta = ext["metadata"]
            
            hash_match = meta.get("content_hash") == r.content_hash
            chunker_match = meta.get("chunker_version") == r.chunker_version
            identity_match = meta.get("embedding_identity") == expected_identity
            active_match = ext["is_active"] == r.is_active
            
            if hash_match and chunker_match and identity_match and active_match:
                to_skip.append(r)
            else:
                to_update.append(r)
        else:
            to_insert.append(r)

    # Calculate stale chunk IDs to retire for the processed source versions
    to_retire = []
    source_versions: Dict[str, Set[str]] = {}
    for r in chunk_records:
        source_versions.setdefault(r.source_id, set()).add(r.version)
        
    for sid, versions in source_versions.items():
        for ver in versions:
            cur.execute(
                "SELECT chunk_id FROM knowledge_chunks WHERE source_id = %s AND source_version = %s AND is_active = true",
                (sid, ver)
            )
            db_ids = {str(row[0]) for row in cur.fetchall()}
            gen_ids = {str(r.persistence_uuid) for r in chunk_records if r.source_id == sid and r.version == ver}
            stale = db_ids - gen_ids
            to_retire.extend(list(stale))

    return ImportPlan(
        to_insert=to_insert,
        to_update=to_update,
        to_skip=to_skip,
        to_retire=to_retire
    )


def upsert_domain(cur, domain_code: str, domain_name: str, owner_role: str) -> str:
    """Upsert a knowledge domain and return its domain_id."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur.execute(
        """
        INSERT INTO knowledge_domains (domain_code, domain_name, owner_name, created_at, updated_at)
        VALUES (%s, %s, %s, %s::timestamptz, %s::timestamptz)
        ON CONFLICT (domain_code) DO UPDATE SET
            domain_name = EXCLUDED.domain_name,
            owner_name = EXCLUDED.owner_name,
            updated_at = EXCLUDED.updated_at
        RETURNING domain_id
        """,
        (domain_code, domain_name, owner_role, now, now),
    )
    return str(cur.fetchone()[0])


def persist_batch(
    cur,
    chunks_to_upsert: List[Tuple[ChunkRecord, List[float]]],
    domain_map: Dict[str, str]
) -> None:
    """Upsert a batch of mapped chunk records within the active transaction."""
    for rec, embedding in chunks_to_upsert:
        domain_id = domain_map.get(rec.domain)
        if not domain_id:
            raise ValidationError(f"Domain code '{rec.domain}' not found in knowledge_domains seed.")
            
        row = map_chunk_to_row(rec, domain_id, embedding)
        
        cur.execute(
            """
            INSERT INTO knowledge_chunks (
                chunk_id, domain_id, content, sub_topic,
                source_id, source_path, source_version,
                approval_status, effective_date,
                page_numbers, tags, metadata, embedding,
                is_active, created_at, updated_at
            ) VALUES (
                %s::uuid, %s::uuid, %s, %s,
                %s, %s, %s,
                %s, %s::date,
                %s::jsonb, %s::jsonb, %s::jsonb, %s::vector,
                %s, %s::timestamptz, %s::timestamptz
            )
            ON CONFLICT (chunk_id) DO UPDATE SET
                content = EXCLUDED.content,
                sub_topic = EXCLUDED.sub_topic,
                source_version = EXCLUDED.source_version,
                approval_status = EXCLUDED.approval_status,
                effective_date = EXCLUDED.effective_date,
                page_numbers = EXCLUDED.page_numbers,
                tags = EXCLUDED.tags,
                metadata = EXCLUDED.metadata,
                embedding = EXCLUDED.embedding,
                is_active = EXCLUDED.is_active,
                updated_at = EXCLUDED.updated_at
            """,
            row
        )


def retire_stale_chunks(cur, chunk_ids: List[str]) -> None:
    """Mark stale chunks as inactive and retired inside the transaction."""
    if not chunk_ids:
        return
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur.execute(
        """
        UPDATE knowledge_chunks
        SET is_active = false, retired_at = %s::timestamptz, updated_at = %s::timestamptz
        WHERE chunk_id = ANY(%s::uuid[])
        """,
        (now, now, chunk_ids)
    )
# === TASK:WP-008:END ===

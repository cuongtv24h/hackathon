# === TASK:WP-008:START ===
import hashlib
import uuid as uuid_lib
from pathlib import Path
from typing import Dict, List, Any, Optional

from .models import ChunkRecord, IngestionResult, SourceRecord
from .settings import (
    EMBEDDING_PROVIDER,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_BATCH_SIZE,
    HARD_MAX_TOKENS,
)
from .errors import ValidationError, IngestionError
from .sources.registry import load_seed_registry, load_knowledge_base, get_eligible_sources
from .sources.markdown_loader import read_markdown
from .chunking.token_counter import TokenCounter
from .chunking.router import select_chunker_and_split
from .validation.source_validator import validate_source
from .validation.chunk_validator import validate_chunk
from .validation.embedding_validator import validate_embedding
from .embeddings.factory import get_embedding_provider
from .persistence.postgres import (
    check_preflight_dimensions,
    build_import_plan,
    upsert_domain,
    persist_batch,
    retire_stale_chunks
)

ROOT = Path(__file__).resolve().parents[5]
CHUNK_NAMESPACE = uuid_lib.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")

def make_deterministic_uuid(external_id: str) -> str:
    """Produce a stable UUID v5 from an external chunk ID string."""
    return str(uuid_lib.uuid5(CHUNK_NAMESPACE, external_id))


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def process_chunks(
    knowledge_base: Optional[Dict[str, Any]] = None,
    registry: Optional[Dict[str, Any]] = None,
    current_date_str: str = "2026-07-18"
) -> IngestionResult:
    """Validate, chunk, and prepare all chunks for indexing."""
    if knowledge_base is None:
        knowledge_base = load_knowledge_base()
    if registry is None:
        registry = load_seed_registry()

    errors = []
    records = []
    
    # 1. Load registries and allowable sources
    eligible_sources = get_eligible_sources(registry)
    source_lookup = {src.source_id: src for src in eligible_sources}
    
    token_counter = TokenCounter()
    all_chunks_raw = list(knowledge_base.get("chunks", []))
    
    # Track existing chunks mapped in KB to prevent reprocessing
    processed_source_ids = {c.get("source_id") for c in all_chunks_raw if c.get("source_id")}
    
    # 2. Extract and split documents from registry that have no predefined chunks in KB
    for src in eligible_sources:
        sid = src.source_id
        
        # Check active & ingestible
        if not src.ingestible:
            continue
            
        # Approval check: only approved or approved_for_pilot processed
        if src.approval_status not in ("approved_for_pilot", "approved"):
            continue
            
        # If already pre-chunked in KB, skip loading Markdown
        if sid in processed_source_ids:
            continue
            
        if not src.path:
            continue
            
        md_path = ROOT / src.path
        if not md_path.is_file():
            errors.append(f"Source {sid} path not found: {src.path}")
            continue
            
        try:
            # Enforce source validation constraints
            validate_source(src, current_date_str)
            
            fm, body = read_markdown(md_path)
            
            # Dispatch to appropriate chunker
            raw_chunks = select_chunker_and_split(sid, src.path, body, token_counter)
            
            # Map raw chunks to ChunkRecord objects
            for index, chunk_dict in enumerate(raw_chunks, 1):
                chunk_id = f"{sid}-SEC-{index:03d}"
                content = chunk_dict["content"]
                
                # Check for empty content
                if not content or not content.strip():
                    errors.append(f"Chunk {chunk_id} has empty content")
                    continue
                    
                c_hash = _content_hash(content)
                p_uuid = make_deterministic_uuid(chunk_id)
                t_count = token_counter.count(content)
                
                record = ChunkRecord(
                    chunk_id=chunk_id,
                    content=content,
                    domain=src.domain_code,
                    sub_topic=chunk_dict.get("sub_topic", "general"),
                    source_id=sid,
                    source_section=chunk_dict.get("source_section", "general"),
                    source_page="",
                    version=src.version,
                    is_active=src.is_active,
                    approval_status=src.approval_status,
                    effective_date=src.effective_date,
                    tags=[src.domain_code, chunk_dict.get("sub_topic", "general")],
                    is_mock=src.is_mock,
                    answerable=True,
                    content_hash=c_hash,
                    source_path=src.path,
                    persistence_uuid=p_uuid,
                    chunker_version="1.0",
                    token_count=t_count,
                    embedding_provider=EMBEDDING_PROVIDER,
                    embedding_model=EMBEDDING_MODEL,
                    embedding_dimensions=EMBEDDING_DIMENSIONS
                )
                
                # Validate chunk boundaries & metadata
                try:
                    validate_chunk(record)
                    records.append(record)
                except ValidationError as ve:
                    errors.append(str(ve))
                    
        except Exception as exc:
            errors.append(f"Failed to split {sid}: {exc}")

    # 3. Process predefined chunks from KB
    for chunk in all_chunks_raw:
        chunk_id = chunk.get("chunk_id", "")
        content = chunk.get("content", "")
        source_id = chunk.get("source_id", "")

        if not chunk_id:
            errors.append("Chunk missing chunk_id")
            continue
        if not content:
            errors.append(f"Chunk {chunk_id} has empty content")
            continue
        if not source_id:
            errors.append(f"Chunk {chunk_id} missing source_id")
            continue

        source_entry = source_lookup.get(source_id)
        if source_entry is None:
            errors.append(f"Chunk {chunk_id} references unknown source_id '{source_id}'")
            continue
            
        if not source_entry.ingestible:
            errors.append(f"Chunk {chunk_id} source '{source_id}' is marked non-ingestible")
            continue

        c_hash = _content_hash(content)
        p_uuid = make_deterministic_uuid(chunk_id)
        t_count = token_counter.count(content)

        record = ChunkRecord(
            chunk_id=chunk_id,
            content=content,
            domain=chunk.get("domain", ""),
            sub_topic=chunk.get("sub_topic", ""),
            source_id=source_id,
            source_section=chunk.get("source_section") or chunk.get("sub_topic") or "",
            source_page=chunk.get("source_page") or "",
            version=chunk.get("version", ""),
            is_active=chunk.get("is_active", True),
            approval_status=chunk.get("approval_status") or source_entry.approval_status,
            effective_date=chunk.get("effective_date") or source_entry.effective_date,
            tags=chunk.get("tags", []),
            is_mock=chunk.get("is_mock", False),
            answerable=chunk.get("answerable", False),
            content_hash=c_hash,
            source_path=source_entry.path or "",
            persistence_uuid=p_uuid,
            chunker_version="1.0",
            token_count=t_count,
            embedding_provider=EMBEDDING_PROVIDER,
            embedding_model=EMBEDDING_MODEL,
            embedding_dimensions=EMBEDDING_DIMENSIONS
        )

        try:
            validate_chunk(record)
            records.append(record)
        except ValidationError as ve:
            errors.append(str(ve))

    answerable = [r for r in records if r.answerable]
    mock = [r for r in records if r.is_mock]
    approved = [r for r in records if r.approval_status in ("approved_for_pilot", "approved")]

    return IngestionResult(
        total_chunks=len(records),
        answerable_chunks=len(answerable),
        mock_chunks=len(mock),
        approved_chunks=len(approved),
        errors=errors,
        chunk_records=records,
        inserted=0,
        updated=0,
        retired=0,
        vector_dim=None
    )


def ingest_knowledge(
    database_url: Optional[str] = None,
    embed_provider: Optional[Any] = None,
    knowledge_base: Optional[Dict[str, Any]] = None,
    registry: Optional[Dict[str, Any]] = None,
    dry_run: bool = True,
    current_date_str: str = "2026-07-18",
    batch_size: Optional[int] = None,
    show_progress: bool = False,
) -> IngestionResult:
    """Full ingestion pipeline: load, process, embed, persist with transactional safety."""
    result = process_chunks(
        knowledge_base=knowledge_base,
        registry=registry,
        current_date_str=current_date_str
    )

    if result.has_errors:
        return result

    if dry_run:
        return result

    # Resolve embedding provider
    provider_object = None
    if embed_provider is None:
        provider_object = get_embedding_provider()
    elif hasattr(embed_provider, "embed_batch"):
        provider_object = embed_provider

    if batch_size is None:
        batch_size = EMBEDDING_BATCH_SIZE
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    def embed_records(records):
        pairs = []
        progress = None
        if show_progress and records:
            from tqdm import tqdm
            progress = tqdm(total=len(records), desc="Embedding", unit="chunk")
        try:
            for start in range(0, len(records), batch_size):
                record_batch = records[start:start + batch_size]
                contents = [record.content for record in record_batch]
                if provider_object is not None:
                    embeddings = provider_object.embed_batch(contents)
                else:
                    embeddings = [embed_provider(content) for content in contents]
                if len(embeddings) != len(record_batch):
                    raise ValidationError(
                        f"Embedding provider returned {len(embeddings)} vectors "
                        f"for {len(record_batch)} chunks."
                    )
                for record, embedding in zip(record_batch, embeddings):
                    validate_embedding(embedding, EMBEDDING_DIMENSIONS)
                    pairs.append((record, embedding))
                if progress is not None:
                    progress.update(len(record_batch))
        finally:
            if progress is not None:
                progress.close()
        return pairs

    import psycopg
    
    # Resolve database URL
    if database_url is None:
        database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "database_url is required when dry_run=False. "
            "Pass it explicitly or set DATABASE_URL environment variable."
        )

    # Preflight Check: Connect and check vector column dimension
    conn = psycopg.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                check_preflight_dimensions(cur, EMBEDDING_DIMENSIONS)
    except Exception:
        conn.close()
        raise

    # Re-connect to execute batch inside a single transaction
    conn = psycopg.connect(database_url)
    try:
        inserted = 0
        updated = 0
        retired = 0
        
        with conn:
            with conn.cursor() as cur:
                # 1. Idempotently upsert knowledge domains
                kb = knowledge_base or load_knowledge_base()
                domain_map = {}
                for dom in kb.get("domains", []):
                    dc = dom["domain_code"]
                    dn = dom.get("domain_name", dc)
                    owner = dom.get("owner_role", "content_admin")
                    did = upsert_domain(cur, dc, dn, owner)
                    domain_map[dc] = did

                # 2. Build the import plan
                plan = build_import_plan(
                    cur,
                    result.chunk_records,
                    EMBEDDING_PROVIDER,
                    EMBEDDING_MODEL,
                    EMBEDDING_DIMENSIONS
                )

                # Filter eligible approved, answerable chunk records to process
                eligible_records = [
                    rec for rec in result.chunk_records
                    if rec.answerable and rec.approval_status in ("approved_for_pilot", "approved")
                ]
                
                # Check status lists in plan
                to_embed_insert = [r for r in plan.to_insert if r in eligible_records]
                to_embed_update = [r for r in plan.to_update if r in eligible_records]
                
                upserts_batch = embed_records(to_embed_insert + to_embed_update)
                inserted = len(to_embed_insert)
                updated = len(to_embed_update)

                # 3. Persist the batch
                persist_batch(cur, upserts_batch, domain_map)

                # 4. Retire stale chunks
                retire_stale_chunks(cur, plan.to_retire)
                retired = len(plan.to_retire)

    except Exception:
        conn.close()
        raise

    conn.close()

    result.inserted = inserted
    result.updated = updated
    result.retired = retired
    result.vector_dim = EMBEDDING_DIMENSIONS
    
    return result
# === TASK:WP-008:END ===
import os

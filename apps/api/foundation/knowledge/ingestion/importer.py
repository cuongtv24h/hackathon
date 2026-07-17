# === TASK:WP-008:START ===
"""Seed importer — load, validate, hash, embed and persist chunks.

This module is self-contained. It operates on JSON seed files produced by
WP-007, raw knowledge documents under ``docs/knowledge/``, and writes to
Supabase via a provided connection string.

No type annotations are used unless a mandatory canonical contract requires
them.
"""

import hashlib
import json
import os
import re
import uuid as uuid_lib
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Public data classes  (no type annotations per packet coding rule)
# ---------------------------------------------------------------------------


@dataclass
class ChunkRecord:
    """A single processed chunk ready for indexing."""

    chunk_id = ""
    content = ""
    domain = ""
    sub_topic = ""
    source_id = ""
    source_section = ""
    source_page = ""
    version = ""
    is_active = True
    approval_status = ""
    effective_date = ""
    tags = None
    is_mock = False
    answerable = False
    content_hash = ""
    source_path = ""
    persistence_uuid = ""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@dataclass
class IngestionResult:
    """Result of a full ingestion run."""

    total_chunks = 0
    answerable_chunks = 0
    mock_chunks = 0
    approved_chunks = 0
    errors = None
    chunk_records = None
    inserted = 0
    updated = 0
    vector_dim = None

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if self.errors is None:
            self.errors = []
        if self.chunk_records is None:
            self.chunk_records = []

    @property
    def has_errors(self):
        return len(self.errors) > 0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[5]
DATA_MVP = ROOT / "data" / "mvp"
SEED_DIR = DATA_MVP / "seed"
KNOWLEDGE_DIR = ROOT / "docs" / "knowledge"

# UUID v5 namespace for deterministic chunk IDs
CHUNK_NAMESPACE = uuid_lib.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _content_hash(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def make_deterministic_uuid(external_id):
    """Produce a stable UUID v5 from an external chunk ID string."""
    return str(uuid_lib.uuid5(CHUNK_NAMESPACE, external_id))


def _read_markdown(path):
    """Read a markdown file, strip frontmatter, return (frontmatter_dict, body_text)."""
    content = path.read_text(encoding="utf-8")
    fm = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2].strip()
            for line in fm_text.split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    fm[key.strip()] = val.strip()
    return fm, body


def split_markdown_chunks(source_id, path, domain, version, approval_status, effective_date):
    """Split a markdown file into deterministic chunks by H2 sections.

    Returns a list of dicts suitable for processing as chunks.
    """
    fm, body = _read_markdown(path)
    chunks = []
    lines = body.split("\n")
    current_section = "general"
    current_lines = []
    ordinal = 0

    for line in lines:
        if line.startswith("## "):
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    ordinal += 1
                    chunk_id = "%s-SEC-%03d" % (source_id, ordinal)
                    chunks.append({
                        "chunk_id": chunk_id,
                        "content": text,
                        "domain": domain,
                        "sub_topic": current_section,
                        "source_id": source_id,
                        "source_section": current_section,
                        "source_page": None,
                        "version": version,
                        "is_active": True,
                        "approval_status": approval_status,
                        "effective_date": effective_date,
                        "tags": [domain, current_section],
                        "is_mock": False,
                        "answerable": True,
                    })
            current_section = line.strip("# ").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            ordinal += 1
            chunk_id = "%s-SEC-%03d" % (source_id, ordinal)
            chunks.append({
                "chunk_id": chunk_id,
                "content": text,
                "domain": domain,
                "sub_topic": current_section,
                "source_id": source_id,
                "source_section": current_section,
                "source_page": None,
                "version": version,
                "is_active": True,
                "approval_status": approval_status,
                "effective_date": effective_date,
                "tags": [domain, current_section],
                "is_mock": False,
                "answerable": True,
            })

    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_seed_registry():
    """Load the reconciled source registry from WP-007."""
    return _load_json(SEED_DIR / "source-registry.json")


def load_knowledge_base():
    """Load the canonical knowledge-base seed."""
    return _load_json(SEED_DIR / "knowledge-base.json")


def process_chunks(knowledge_base=None, registry=None, dry_run=True):
    """Validate, hash and prepare all chunks for indexing.

    For approved, ingestible sources with zero canonical chunks (e.g. BHYT),
    loads the registered Markdown file and splits it into answerable chunks.

    Returns an IngestionResult.
    """
    if knowledge_base is None:
        knowledge_base = load_knowledge_base()
    if registry is None:
        registry = load_seed_registry()

    errors = []
    records = []

    source_lookup = {}
    for src in registry.get("sources", []):
        source_lookup[src["source_id"]] = src

    all_chunks = list(knowledge_base.get("chunks", []))

    for src in registry.get("sources", []):
        sid = src["source_id"]
        if not src.get("ingestible", True):
            continue
        if src.get("approval_status") not in ("approved_for_pilot", "approved"):
            continue
        has_chunks = any(c.get("source_id") == sid for c in all_chunks)
        if has_chunks:
            continue
        src_path = src.get("path")
        if not src_path:
            continue
        md_path = ROOT / src_path
        if not md_path.is_file():
            errors.append("Source %s path not found: %s" % (sid, src_path))
            continue
        try:
            md_chunks = split_markdown_chunks(
                source_id=sid,
                path=md_path,
                domain=src.get("domain_code", ""),
                version=src.get("version", "1.0"),
                approval_status=src.get("approval_status", "approved_for_pilot"),
                effective_date=src.get("effective_date", ""),
            )
            all_chunks.extend(md_chunks)
        except Exception as exc:
            errors.append("Failed to split %s: %s" % (sid, str(exc)))

    for chunk in all_chunks:
        chunk_id = chunk.get("chunk_id") or ""
        content = chunk.get("content") or ""
        source_id = chunk.get("source_id") or ""

        if not chunk_id:
            errors.append("Chunk missing chunk_id")
            continue
        if not content:
            errors.append("Chunk %s has empty content" % chunk_id)
            continue
        if not source_id:
            errors.append("Chunk %s missing source_id" % chunk_id)
            continue

        source_entry = source_lookup.get(source_id)
        if source_entry is None:
            errors.append("Chunk %s references unknown source_id '%s'" % (chunk_id, source_id))
            continue
        if not source_entry.get("ingestible", True):
            errors.append("Chunk %s source '%s' is marked non-ingestible" % (chunk_id, source_id))
            continue

        c_hash = _content_hash(content)
        p_uuid = make_deterministic_uuid(chunk_id)

        record = ChunkRecord(
            chunk_id=chunk_id,
            content=content,
            domain=chunk.get("domain", ""),
            sub_topic=chunk.get("sub_topic", ""),
            source_id=source_id,
            source_section=chunk.get("source_section") or "",
            source_page=chunk.get("source_page") or "",
            version=chunk.get("version", ""),
            is_active=chunk.get("is_active", True),
            approval_status=chunk.get("approval_status", ""),
            effective_date=chunk.get("effective_date", ""),
            tags=chunk.get("tags", []),
            is_mock=chunk.get("is_mock", False),
            answerable=chunk.get("answerable", False),
            content_hash=c_hash,
            source_path=source_entry.get("path") or "",
            persistence_uuid=p_uuid,
        )
        records.append(record)

    answerable = [r for r in records if r.answerable]
    mock = [r for r in records if r.is_mock]
    approved = [r for r in records if r.approval_status == "approved_for_pilot"]

    return IngestionResult(
        total_chunks=len(records),
        answerable_chunks=len(answerable),
        mock_chunks=len(mock),
        approved_chunks=len(approved),
        errors=errors,
        chunk_records=records,
        inserted=0,
        updated=0,
        vector_dim=None,
    )


def _validate_embedding_dim(embedding, expected=768):
    if not isinstance(embedding, (list, tuple)):
        raise ValueError("Embedding must be a list or tuple")
    if len(embedding) != expected:
        raise ValueError(
            "Embedding dimension %d does not match expected %d" % (len(embedding), expected)
        )


def _make_embedding_fake(content):
    """Fake embedding provider for testing — returns 768 zeros."""
    return [0.0] * 768


def _make_embedding_from_env():
    """Build a real embedding provider from environment configuration.

    Reads GEMINI_API_KEY and EMBEDDING_MODEL from environment.
    Returns a callable(content) -> list of floats (768-d).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("EMBEDDING_MODEL", "text-embedding-004")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not set. Cannot create real embedding provider."
        )
    try:
        from google import genai
    except ImportError:
        raise ValueError("google-genai package not installed. Cannot create real embedding provider.")

    client = genai.Client(api_key=api_key)

    def _embed(content):
        response = client.models.embed_content(
            model=model,
            contents=content,
        )
        return response.embeddings[0].values

    return _embed


def _upsert_domain(cur, domain_code, domain_name, owner_name):
    """Idempotently upsert a knowledge domain. Returns domain_id."""
    import datetime
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
        (domain_code, domain_name, owner_name, now, now),
    )
    return cur.fetchone()[0]


def _upsert_chunk(cur, record, domain_id, embedding):
    """Upsert a single chunk record into knowledge_chunks."""
    import datetime
    now = datetime.datetime.utcnow().isoformat()
    page_numbers = json.dumps([record.source_page] if record.source_page else [])
    tags = json.dumps(record.tags)
    metadata = json.dumps({
        "external_chunk_id": record.chunk_id,
        "content_hash": record.content_hash,
        "source_section": record.source_section,
        "source_path": record.source_path,
    })
    embedding_json = json.dumps(embedding)

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
        (
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
        ),
    )


def ingest_knowledge(
    database_url=None,
    embed_provider=None,
    knowledge_base=None,
    registry=None,
    dry_run=True,
):
    """Full ingestion pipeline: load, process, embed, persist.

    Parameters
    ----------
    database_url : str, optional
        Supabase/Postgres connection string. Falls back to DATABASE_URL env var.
    embed_provider : callable, optional
        A callable(content) -> list of floats (768-d). Required when dry_run=False.
        Falls back to environment-configured provider if omitted.
    knowledge_base : dict, optional
        Pre-loaded knowledge-base JSON.
    registry : dict, optional
        Pre-loaded source registry JSON.
    dry_run : bool
        When True (default), no database write occurs.

    Returns
    -------
    IngestionResult with inserted, updated, vector_dim fields.
    """
    result = process_chunks(
        knowledge_base=knowledge_base,
        registry=registry,
        dry_run=dry_run,
    )

    if result.has_errors:
        return result

    if dry_run:
        return result

    # Resolve database_url from parameter or environment
    if database_url is None:
        database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "database_url is required when dry_run=False. "
            "Pass it explicitly or set DATABASE_URL environment variable."
        )

    # Resolve embedding provider
    if embed_provider is None:
        embed_provider = _make_embedding_from_env()

    # Import psycopg (version 3) — the installed dependency
    import psycopg

    conn = psycopg.connect(database_url)
    try:
        inserted = 0
        updated = 0
        vector_dim = None

        with conn:
            with conn.cursor() as cur:
                # Step 1: Idempotently seed knowledge domains
                kb = knowledge_base
                if kb is None:
                    kb = load_knowledge_base()
                domain_map = {}
                for dom in kb.get("domains", []):
                    dc = dom["domain_code"]
                    dn = dom.get("domain_name", dc)
                    owner = dom.get("owner_role", "content_admin")
                    did = _upsert_domain(cur, dc, dn, owner)
                    domain_map[dc] = did

                # Step 2: Upsert approved, answerable chunks
                for rec in result.chunk_records:
                    if not rec.answerable:
                        continue
                    if rec.approval_status not in ("approved_for_pilot", "approved"):
                        continue

                    embedding = embed_provider(rec.content)
                    _validate_embedding_dim(embedding)
                    if vector_dim is None:
                        vector_dim = len(embedding)

                    domain_id = domain_map.get(rec.domain)
                    if domain_id is None:
                        raise ValueError(
                            "Unknown domain_code '%s' — not in knowledge_domains seed" % rec.domain
                        )

                    cur.execute(
                        "SELECT 1 FROM knowledge_chunks WHERE chunk_id = %s::uuid",
                        (rec.persistence_uuid,),
                    )
                    exists = cur.fetchone() is not None

                    _upsert_chunk(cur, rec, domain_id, embedding)

                    if exists:
                        updated += 1
                    else:
                        inserted += 1

                # Step 3: Index maintenance
                cur.execute("REINDEX INDEX knowledge_chunks_embedding_idx;")

    except Exception:
        conn.close()
        raise

    conn.close()

    result.inserted = inserted
    result.updated = updated
    result.vector_dim = vector_dim
    return result


def generate_dry_run_report(result):
    """Produce a human-readable dry-run summary."""
    lines = [
        "=" * 60,
        "WP-008 — Seed Ingestion Dry-Run Report",
        "=" * 60,
        "  Total chunks processed : %d" % result.total_chunks,
        "  Answerable chunks      : %d" % result.answerable_chunks,
        "  Mock chunks            : %d" % result.mock_chunks,
        "  Approved-for-pilot     : %d" % result.approved_chunks,
        "  Errors                 : %d" % len(result.errors),
        "-" * 60,
    ]
    if result.errors:
        lines.append("  Error details:")
        for err in result.errors:
            lines.append("    - %s" % err)
        lines.append("-" * 60)

    lines.append("  Chunk summary:")
    for rec in result.chunk_records:
        lines.append(
            "    %-20s | %-20s | answerable=%-5s | mock=%-5s | uuid=%s | hash=%s"
            % (
                rec.chunk_id,
                rec.domain,
                str(rec.answerable),
                str(rec.is_mock),
                rec.persistence_uuid,
                rec.content_hash,
            )
        )
    lines.append("=" * 60)
    return "\n".join(lines)
# === TASK:WP-008:END ===
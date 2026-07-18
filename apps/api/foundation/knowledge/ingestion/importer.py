# === TASK:WP-008:START ===
"""Seed importer compatibility façade.

Maps public entry points to the new modular package layout.
"""

from typing import List, Dict, Any, Optional

from .models import ChunkRecord, IngestionResult
from .reporting import generate_dry_run_report
from .pipeline import ingest_knowledge, process_chunks, make_deterministic_uuid
from .sources.registry import load_knowledge_base, load_seed_registry
from .validation.embedding_validator import validate_embedding
from .settings import EMBEDDING_DIMENSIONS

def _validate_embedding_dim(embedding: List[float], expected: int = EMBEDDING_DIMENSIONS) -> None:
    """Legacy embedding validator wrapper."""
    validate_embedding(embedding, expected)


def split_markdown_chunks(
    source_id: str,
    path: Any,
    domain: str,
    version: str,
    approval_status: str,
    effective_date: str
) -> List[Dict[str, Any]]:
    """Legacy compatibility wrapper for splitting markdown files.

    Reads content and delegates chunking to the appropriate structured chunker.
    """
    from pathlib import Path
    from .sources.markdown_loader import read_markdown
    from .chunking.router import select_chunker_and_split
    from .chunking.token_counter import TokenCounter

    path_obj = Path(path)
    fm, body = read_markdown(path_obj)

    token_counter = TokenCounter()

    doc_title = ""
    for line in body.splitlines():
        if line.strip().startswith("# ") and not line.strip().startswith("##"):
            doc_title = line.strip().lstrip("#").strip()
            break

    raw_chunks = select_chunker_and_split(source_id, str(path), body, token_counter)

    legacy_chunks = []
    for index, chunk_dict in enumerate(raw_chunks, 1):
        chunk_id = f"{source_id}-SEC-{index:03d}"
        legacy_chunks.append({
            "chunk_id": chunk_id,
            "content": chunk_dict["content"],
            "domain": domain,
            "sub_topic": chunk_dict.get("sub_topic", "general"),
            "source_id": source_id,
            "source_section": chunk_dict.get("source_section", "general"),
            "source_page": None,
            "version": version,
            "is_active": True,
            "approval_status": approval_status,
            "effective_date": effective_date,
            "tags": [domain, chunk_dict.get("sub_topic", "general")],
            "is_mock": False,
            "answerable": True,
        })
    return legacy_chunks
# === TASK:WP-008:END ===

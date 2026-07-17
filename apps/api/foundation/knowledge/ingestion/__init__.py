# === TASK:WP-008:START ===
"""Knowledge ingestion package — seed import, chunk processing, embedding and persistence.

Public surface
--------------
* ChunkRecord — dataclass for a single processed chunk.
* IngestionResult — result of an ingestion run.
* process_chunks — validate, hash and prepare chunks.
* ingest_knowledge — full pipeline: load, process, embed, persist.
* generate_dry_run_report — produce a dry-run summary.
* make_deterministic_uuid — stable UUID v5 from external chunk ID.
* split_markdown_chunks — split a markdown file into sections.
"""

from .importer import (
    ChunkRecord,
    IngestionResult,
    _validate_embedding_dim,
    generate_dry_run_report,
    ingest_knowledge,
    load_knowledge_base,
    load_seed_registry,
    make_deterministic_uuid,
    process_chunks,
    split_markdown_chunks,
)

__all__ = [
    "ChunkRecord",
    "IngestionResult",
    "_validate_embedding_dim",
    "generate_dry_run_report",
    "ingest_knowledge",
    "load_knowledge_base",
    "load_seed_registry",
    "make_deterministic_uuid",
    "process_chunks",
    "split_markdown_chunks",
]
# === TASK:WP-008:END ===
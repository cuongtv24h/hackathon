"""Console preview for the deterministic WP-008 chunking pipeline.

This module is intentionally side-effect free: it does not load ``.env``, call
an embedding provider, or connect to PostgreSQL.
"""

from __future__ import annotations

import argparse
import textwrap
from collections import Counter
from typing import Iterable, Optional, Sequence

from .models import ChunkRecord, IngestionResult
from .pipeline import process_chunks
from .settings import HARD_MAX_TOKENS, TARGET_MAX_TOKENS, TARGET_MIN_TOKENS


def _status(record: ChunkRecord) -> str:
    if record.token_count > HARD_MAX_TOKENS:
        return "ERROR oversized"
    if record.token_count > TARGET_MAX_TOKENS:
        return "WARN above-target"
    if record.token_count < TARGET_MIN_TOKENS:
        return "INFO below-target"
    return "OK target"


def _display_content(content: str, width: int, full: bool) -> str:
    normalized = " ".join(content.split())
    if not full and len(normalized) > width:
        normalized = normalized[: max(1, width - 1)].rstrip() + "…"
    return textwrap.fill(normalized, width=width, subsequent_indent="    ")


def render_preview(
    result: IngestionResult,
    *,
    source_id: Optional[str] = None,
    limit: Optional[int] = None,
    width: int = 110,
    full: bool = False,
) -> str:
    """Render chunk records as a human-readable, deterministic console report."""
    records = [
        record
        for record in result.chunk_records
        if source_id is None or record.source_id == source_id
    ]
    records.sort(key=lambda record: (record.source_id, record.chunk_id))
    visible = records if limit is None else records[:limit]
    source_counts = Counter(record.source_id for record in records)
    statuses = Counter(_status(record) for record in records)

    lines = [
        "=" * width,
        "RAG CHUNKING PREVIEW (dry-run: no embedding, no database)",
        "=" * width,
        f"Chunks: {len(records)} | Sources: {len(source_counts)} | "
        f"Target: {TARGET_MIN_TOKENS}-{TARGET_MAX_TOKENS} | Hard max: {HARD_MAX_TOKENS}",
    ]

    if source_id:
        lines.append(f"Source filter: {source_id}")
    if statuses:
        lines.append(
            "Status: " + ", ".join(f"{key}={value}" for key, value in sorted(statuses.items()))
        )
    if result.errors:
        lines.extend(["-" * width, f"Pipeline errors ({len(result.errors)}):"])
        lines.extend(f"  - {error}" for error in result.errors)

    for index, record in enumerate(visible, 1):
        locator = record.source_section or record.source_page or "(no locator)"
        lines.extend(
            [
                "-" * width,
                f"[{index}/{len(records)}] {record.chunk_id} | {_status(record)}",
                f"source={record.source_id} | tokens={record.token_count} | "
                f"domain={record.domain} | subtopic={record.sub_topic}",
                f"locator={locator} | hash={record.content_hash}",
                _display_content(record.content, width, full),
            ]
        )

    if limit is not None and len(records) > len(visible):
        lines.extend(
            [
                "-" * width,
                f"Hidden: {len(records) - len(visible)} chunks. Increase --limit or use --limit 0.",
            ]
        )
    if not records:
        lines.extend(["-" * width, "No chunks matched the selected source."])

    lines.append("=" * width)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview canonical RAG chunks without embedding or database writes."
    )
    parser.add_argument("--source", help="Only show one source_id.")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum chunks to print; 0 prints all (default: 20).",
    )
    parser.add_argument("--full", action="store_true", help="Print full normalized chunk content.")
    parser.add_argument("--width", type=int, default=110, help="Console width (default: 110).")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 0:
        raise SystemExit("--limit must be zero or greater")
    if args.width < 60:
        raise SystemExit("--width must be at least 60")

    result = process_chunks()
    report = render_preview(
        result,
        source_id=args.source,
        limit=None if args.limit == 0 else args.limit,
        width=args.width,
        full=args.full,
    )
    print(report)

    source_exists = args.source is None or any(
        record.source_id == args.source for record in result.chunk_records
    )
    oversized = any(record.token_count > HARD_MAX_TOKENS for record in result.chunk_records)
    return 0 if source_exists and not result.errors and not oversized else 1


if __name__ == "__main__":
    raise SystemExit(main())

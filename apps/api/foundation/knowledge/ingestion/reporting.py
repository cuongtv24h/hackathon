# === TASK:WP-008:START ===
import math
from typing import List

def generate_dry_run_report(result) -> str:
    """Produce a human-readable dry-run summary with detailed metrics."""
    lines = [
        "=" * 60,
        "WP-008 — Seed Ingestion Dry-Run Report",
        "=" * 60,
        f"  Total chunks processed : {result.total_chunks}",
        f"  Answerable chunks      : {result.answerable_chunks}",
        f"  Mock chunks            : {result.mock_chunks}",
        f"  Approved-for-pilot     : {result.approved_chunks}",
        f"  Errors                 : {len(result.errors)}",
        "-" * 60,
    ]
    
    if result.errors:
        lines.append("  Error details:")
        for err in result.errors:
            lines.append(f"    - {err}")
        lines.append("-" * 60)

    # Calculate token statistics
    tokens = [rec.token_count for rec in result.chunk_records if rec.token_count > 0]
    if tokens:
        tokens.sort()
        t_min = tokens[0]
        t_max = tokens[-1]
        n = len(tokens)
        if n % 2 == 1:
            t_med = tokens[n // 2]
        else:
            t_med = (tokens[n // 2 - 1] + tokens[n // 2]) / 2.0
            
        # Find largest chunk
        largest_rec = max(result.chunk_records, key=lambda r: r.token_count, default=None)
        
        lines.extend([
            "  Token Statistics:",
            f"    Min tokens           : {t_min}",
            f"    Median tokens        : {t_med:.1f}",
            f"    Max tokens           : {t_max}",
            f"    Largest chunk ID     : {largest_rec.chunk_id if largest_rec else 'N/A'}",
            "-" * 60,
        ])
    
    # Calculate domain and source summaries
    domains = {}
    sources = {}
    for rec in result.chunk_records:
        domains[rec.domain] = domains.get(rec.domain, 0) + 1
        sources[rec.source_id] = sources.get(rec.source_id, 0) + 1
        
    lines.append("  Domain summary:")
    for dom, count in sorted(domains.items()):
        lines.append(f"    - {dom:<20} : {count} chunks")
        
    lines.append("  Source summary:")
    for src, count in sorted(sources.items()):
        lines.append(f"    - {src:<20} : {count} chunks")
    lines.append("-" * 60)

    lines.append("  Chunk summary:")
    for rec in result.chunk_records:
        lines.append(
            "    %-20s | %-20s | answerable=%-5s | mock=%-5s | uuid=%s | hash=%s | tokens=%d"
            % (
                rec.chunk_id,
                rec.domain,
                str(rec.answerable),
                str(rec.is_mock),
                rec.persistence_uuid,
                rec.content_hash,
                rec.token_count,
            )
        )
    lines.append("=" * 60)
    return "\n".join(lines)
# === TASK:WP-008:END ===

"""Operator CLI for the WP-005/WP-008 RAG ingestion workflow.

Run from the repository root, for example::

    uv run python scripts/rag_ingestion.py check
    uv run python scripts/rag_ingestion.py migrate --yes
    uv run python scripts/rag_ingestion.py embed-test --yes
    uv run python scripts/rag_ingestion.py ingest --yes

The CLI loads ``.env`` without printing connection strings or API keys.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
TRACKING_TABLE = "app_schema_migrations"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without overriding exported variables."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _confirm_write(args: argparse.Namespace, action: str) -> None:
    if not args.yes:
        raise RuntimeError(
            f"{action} changes external state or incurs API cost. "
            "Review the target, then rerun with --yes."
        )


def _database_dimension(connection) -> Optional[int]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT a.atttypmod
            FROM pg_attribute AS a
            WHERE a.attrelid = to_regclass('knowledge_chunks')
              AND a.attname = 'embedding'
              AND NOT a.attisdropped
            """
        )
        row = cursor.fetchone()
    return int(row[0]) if row and row[0] and row[0] > 0 else None


def _database_readiness(connection) -> Dict[str, object]:
    """Return non-secret schema evidence for the ingestion prerequisites."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_attribute
                WHERE attrelid = to_regclass('knowledge_chunks')
                  AND attname = 'search_document'
                  AND NOT attisdropped
            )
            """
        )
        search_document = bool(cursor.fetchone()[0])
        cursor.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'knowledge_chunks'
              AND indexname IN (
                  'knowledge_chunks_embedding_idx',
                  'knowledge_chunks_search_document_idx'
              )
            """
        )
        indexes = {name: definition for name, definition in cursor.fetchall()}
        cursor.execute(f"SELECT count(*) FROM {TRACKING_TABLE}")
        migration_count = int(cursor.fetchone()[0])
    return {
        "search_document": search_document,
        "vector_index": "knowledge_chunks_embedding_idx" in indexes,
        "fts_index": "knowledge_chunks_search_document_idx" in indexes,
        "migration_count": migration_count,
    }


def command_check(_: argparse.Namespace) -> int:
    provider = os.environ.get("EMBEDDING_PROVIDER", "jina").lower()
    model = os.environ.get("EMBEDDING_MODEL", "jina-embeddings-v5-text-small")
    dimensions = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))
    provider_keys = {
        "jina": "JINA_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "google": "GEMINI_API_KEY",
    }
    api_key_name = provider_keys.get(provider)

    print(f"embedding_provider: {provider}")
    print(f"embedding_model: {model}")
    print(f"embedding_dimensions: {dimensions}")
    if api_key_name:
        print(f"{api_key_name}: {'configured' if os.environ.get(api_key_name) else 'missing'}")
    else:
        print("provider_configuration: unsupported")
        return 1
    if provider == "jina":
        print(f"JINA_BASE_URL: {'configured' if os.environ.get('JINA_BASE_URL') else 'default'}")
    print(f"DATABASE_URL: {'configured' if os.environ.get('DATABASE_URL') else 'missing'}")

    if not os.environ.get("DATABASE_URL"):
        return 1

    import psycopg

    try:
        with psycopg.connect(_require("DATABASE_URL")) as connection:
            db_dimension = _database_dimension(connection)
            print("database_connection: ok")
            print(f"database_vector_dimension: {db_dimension or 'schema not migrated'}")
            if db_dimension is not None and db_dimension != dimensions:
                print("dimension_match: no")
                return 1
            print(f"dimension_match: {'yes' if db_dimension is not None else 'not applicable'}")
            if db_dimension is not None:
                readiness = _database_readiness(connection)
                print(f"search_document: {'ready' if readiness['search_document'] else 'missing'}")
                print(f"vector_index: {'ready' if readiness['vector_index'] else 'missing'}")
                print(f"fts_index: {'ready' if readiness['fts_index'] else 'missing'}")
                print(f"applied_migrations: {readiness['migration_count']}")
                if not all(
                    readiness[key] for key in ("search_document", "vector_index", "fts_index")
                ):
                    return 1
    except Exception as exc:
        print(f"database_connection: failed ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 1
    return 0


def command_migrate(args: argparse.Namespace) -> int:
    _confirm_write(args, "Database migration")
    database_url = _require("DATABASE_URL")
    migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_paths:
        raise RuntimeError(f"No migrations found in {MIGRATIONS_DIR}")

    import psycopg

    applied = 0
    skipped = 0
    with psycopg.connect(database_url) as connection:
        for path in migration_paths:
            sql_text = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql_text.encode("utf-8")).hexdigest()
            version = path.stem
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("rag-ingestion-migrations",))
                    cursor.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {TRACKING_TABLE} (
                            version text PRIMARY KEY,
                            checksum text NOT NULL,
                            applied_at timestamptz NOT NULL DEFAULT now()
                        )
                        """
                    )
                    cursor.execute(
                        f"SELECT checksum FROM {TRACKING_TABLE} WHERE version = %s",
                        (version,),
                    )
                    row = cursor.fetchone()
                    if row:
                        if row[0] != checksum:
                            raise RuntimeError(
                                f"Applied migration {version} has a different checksum; "
                                "never edit applied migration history."
                            )
                        print(f"SKIP  {path.name}")
                        skipped += 1
                        continue
                    print(f"APPLY {path.name}")
                    cursor.execute(sql_text)
                    cursor.execute(
                        f"INSERT INTO {TRACKING_TABLE} (version, checksum) VALUES (%s, %s)",
                        (version, checksum),
                    )
                    applied += 1

        db_dimension = _database_dimension(connection)
        expected = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))
        if db_dimension != expected:
            raise RuntimeError(
                f"Migration completed but database vector dimension is {db_dimension}; expected {expected}."
            )
    print(f"Migration complete: applied={applied}, skipped={skipped}, vector={db_dimension}")
    return 0


def command_embed_test(args: argparse.Namespace) -> int:
    _confirm_write(args, "Embedding test")
    from apps.api.foundation.knowledge.ingestion.embeddings.factory import get_embedding_provider
    from apps.api.foundation.knowledge.ingestion.validation.embedding_validator import validate_embedding

    expected = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))
    provider = get_embedding_provider()
    contents = [f"{args.text} #{index}" for index in range(1, args.count + 1)]
    vectors = provider.embed_batch(contents)
    if len(vectors) != len(contents):
        raise RuntimeError(f"Provider returned {len(vectors)} vectors for {len(contents)} inputs.")
    for vector in vectors:
        validate_embedding(vector, expected)
    print(f"provider: {provider.__class__.__name__}")
    print(f"model: {provider.model}")
    print(f"batch_inputs: {len(contents)}")
    print(f"batch_vectors: {len(vectors)}")
    print(f"dimensions: {len(vectors[0])}")
    print("embedding_test: ok")
    return 0


def command_preview(args: argparse.Namespace) -> int:
    from apps.api.foundation.knowledge.ingestion.preview import main as preview_main

    preview_args = ["--limit", str(args.limit), "--width", str(args.width)]
    if args.source:
        preview_args.extend(["--source", args.source])
    if args.full:
        preview_args.append("--full")
    return preview_main(preview_args)


def command_ingest(args: argparse.Namespace) -> int:
    _confirm_write(args, "Live ingestion")
    _require("DATABASE_URL")
    from apps.api.foundation.knowledge.ingestion import ingest_knowledge
    from apps.api.foundation.knowledge.ingestion.reporting import generate_dry_run_report

    result = ingest_knowledge(
        dry_run=False,
        batch_size=args.batch_size,
        show_progress=not args.no_progress,
    )
    print(generate_dry_run_report(result))
    print(
        f"inserted={result.inserted}, updated={result.updated}, "
        f"retired={result.retired}, dimension={result.vector_dim}"
    )
    return 1 if result.has_errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RAG ingestion operator CLI")
    parser.add_argument("--env-file", default=".env", help="Environment file (default: .env)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Check non-secret configuration and database schema.")

    migrate = subparsers.add_parser("migrate", help="Apply pending SQL migrations through DATABASE_URL.")
    migrate.add_argument("--yes", action="store_true", help="Confirm database schema changes.")

    embed_test = subparsers.add_parser("embed-test", help="Call the configured provider once.")
    embed_test.add_argument("--yes", action="store_true", help="Confirm the paid API call.")
    embed_test.add_argument("--text", default="Kiểm tra embedding tài liệu BHYT.")
    embed_test.add_argument("--count", type=int, default=1, choices=range(1, 65))

    preview = subparsers.add_parser("preview", help="Preview chunks without external side effects.")
    preview.add_argument("--source")
    preview.add_argument("--limit", type=int, default=20)
    preview.add_argument("--width", type=int, default=110)
    preview.add_argument("--full", action="store_true")

    ingest = subparsers.add_parser("ingest", help="Embed and persist the canonical corpus.")
    ingest.add_argument("--yes", action="store_true", help="Confirm API cost and database writes.")
    ingest.add_argument("--batch-size", type=int, help="Chunks per provider request (default: env/64).")
    ingest.add_argument("--no-progress", action="store_true", help="Disable the embedding progress bar.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env_path = Path(args.env_file)
    if not env_path.is_absolute():
        env_path = ROOT / env_path
    load_env_file(env_path)

    commands = {
        "check": command_check,
        "migrate": command_migrate,
        "embed-test": command_embed_test,
        "preview": command_preview,
        "ingest": command_ingest,
    }
    try:
        return commands[args.command](args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

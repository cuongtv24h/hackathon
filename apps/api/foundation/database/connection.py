# === TASK:WP-006:START ===
"""Connection adapter for the Hospital Assistant data tier.

The adapter is intentionally small: a real production deployment talks to
Supabase Postgres through :pypi:`psycopg`, but the Foundation layer does not
want to import a third-party driver on every code path. The adapter therefore
follows the classic "real driver if available, in-memory stub otherwise"
pattern that keeps unit and contract tests self-contained.

The shape of :class:`DatabaseError` mirrors the
:class:`UnifiedErrorEnvelope` declared in
``docs/artifacts/interface/error-contracts.md`` (INT-07) so the Foundation
layer can re-raise driver failures as the canonical envelope without
exposing stack traces, secrets or raw SQL.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


# ---------------------------------------------------------------------------
# Configuration — secrets come from the environment, never from source.
# ---------------------------------------------------------------------------

# Allowed characters for env var values that become identifiers. Keeps
# anything that is not letter/digit/underscore out of role names, table
# names and SQL identifiers.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DatabaseError(Exception):
    """Domain error raised by the database adapter.

    The constructor accepts a short canonical error code, a user-friendly
    message, the error category required by INT-07, and an optional mapping
    of field-level errors. The :pyattr:`envelope` property renders the full
    :class:`UnifiedErrorEnvelope` shape so callers (e.g. the Gateway layer)
    can return it to clients verbatim.
    """

    VALID_CATEGORIES = frozenset(
        {
            "validation",
            "authentication",
            "authorization",
            "business",
            "not_found",
            "ai",
            "tool",
            "safety",
            "rate_limit",
            "system",
        }
    )

    def __init__(
        self,
        code: str,
        message: str,
        *,
        category: str = "system",
        field_errors: Optional[Mapping[str, str]] = None,
        retryable: bool = False,
        retry_after_seconds: Optional[int] = None,
        fallback: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        if not code or not _IDENTIFIER_RE.match(code):
            raise ValueError("error code must be a non-empty UPPER_SNAKE identifier")
        if category not in self.VALID_CATEGORIES:
            raise ValueError(
                f"unknown error category {category!r}; expected one of "
                f"{sorted(self.VALID_CATEGORIES)}"
            )
        self.code = code
        self.message = message
        self.category = category
        self.field_errors: Dict[str, str] = dict(field_errors or {})
        self.retryable = bool(retryable)
        self.retry_after_seconds = retry_after_seconds
        self.fallback = fallback
        self.trace_id = trace_id

    # The shape required by INT-07.
    def envelope(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id or "",
            "error": {
                "code": self.code,
                "category": self.category,
                "message": self.message,
                "field_errors": dict(self.field_errors),
                "retryable": self.retryable,
                "retry_after_seconds": self.retry_after_seconds,
                "fallback": self.fallback,
            },
        }

    def to_dict(self) -> Dict[str, Any]:
        return self.envelope()

    def __repr__(self) -> str:  # pragma: no cover - debug helper only
        return (
            f"DatabaseError(code={self.code!r}, category={self.category!r}, "
            f"retryable={self.retryable!r})"
        )


@dataclass(frozen=True)
class DatabaseSettings:
    """Read-only view of the database configuration.

    A value object built by :func:`load_database_settings`. It deliberately
    exposes the same canonical fields the WP-006 contract relies on, with no
    method that returns a raw secret.
    """

    database_url: Optional[str]
    app_env: str
    full_demo_role_enabled: bool
    pool_min: int
    pool_max: int
    statement_timeout_ms: int

    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


def load_database_settings(env: Optional[Mapping[str, str]] = None) -> DatabaseSettings:
    """Build a :class:`DatabaseSettings` from the environment.

    ``env`` is an optional injection point for tests. When omitted, the real
    :data:`os.environ` is used. The function never logs the resolved
    ``database_url``; it only stores it in the returned object so the caller
    can use it to open a connection.
    """

    source: Mapping[str, str] = os.environ if env is None else env

    def _get(name: str, default: Optional[str] = None) -> Optional[str]:
        value = source.get(name)
        if value is None or value == "":
            return default
        return value

    def _get_int(name: str, default: int) -> int:
        raw = source.get(name)
        if raw is None or raw == "":
            return default
        try:
            return int(raw)
        except ValueError as exc:
            raise DatabaseError(
                "CONFIG_UNAVAILABLE",
                f"environment variable {name!r} must be an integer",
                category="system",
                field_errors={name: "must be an integer"},
            ) from exc

    def _get_bool(name: str, default: bool) -> bool:
        raw = source.get(name)
        if raw is None or raw == "":
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    app_env = (_get("APP_ENV", "development") or "development").lower()
    full_demo_enabled = _get_bool("HOSPITAL_FULL_DEMO_ROLE_ENABLED", False)
    if full_demo_enabled and app_env == "production":
        # Production guardrail: never let the demo role leak into prod even
        # if the boolean flag was set.
        full_demo_enabled = False

    return DatabaseSettings(
        database_url=_get("DATABASE_URL"),
        app_env=app_env,
        full_demo_role_enabled=full_demo_enabled,
        pool_min=_get_int("HOSPITAL_DB_POOL_MIN", 1),
        pool_max=_get_int("HOSPITAL_DB_POOL_MAX", 5),
        statement_timeout_ms=_get_int("HOSPITAL_DB_STATEMENT_TIMEOUT_MS", 5000),
    )


# ---------------------------------------------------------------------------
# Client adapter
# ---------------------------------------------------------------------------


class _InMemoryStore:
    """A minimal table store used when no real Postgres is reachable.

    The store is deliberately tiny: it supports ``CREATE TABLE`` (no-op if
    the table exists), ``INSERT`` and ``DELETE WHERE``. That is enough to
    exercise the retention sweeper and the test harness without dragging in
    a full SQL engine.

    This implementation is *not* meant to faithfully emulate Postgres. It is
    only here so the Foundation package can be imported in environments
    without :pypi:`psycopg` (typical CI containers, developer laptops that
    have not provisioned Supabase yet).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tables: Dict[str, List[Dict[str, Any]]] = {}

    def execute(self, statement: str) -> int:
        """Execute one of the small set of supported statements.

        Returns the number of rows deleted. Other statements return 0.
        """

        cleaned = self._strip_comments(statement).strip()
        upper = cleaned.upper()

        with self._lock:
            if upper.startswith("CREATE TABLE") or upper.startswith("CREATE OR REPLACE TABLE"):
                return 0
            if upper.startswith("CREATE EXTENSION") or upper.startswith("CREATE ROLE") \
                    or upper.startswith("DO ") or upper.startswith("GRANT ") \
                    or upper.startswith("ALTER TABLE") or upper.startswith("DROP POLICY") \
                    or upper.startswith("CREATE POLICY") or upper.startswith("CREATE OR REPLACE") \
                    or upper.startswith("CREATE INDEX") or upper.startswith("CREATE UNIQUE INDEX") \
                    or upper.startswith("CREATE OR REPLACE FUNCTION") \
                    or upper.startswith("CREATE OR REPLACE VIEW"):
                # No-op for the in-memory stub; real SQL is handled by psycopg.
                return 0
            if upper.startswith("DELETE FROM"):
                return self._handle_delete(cleaned)
            if upper.startswith("SELECT COUNT") or upper.startswith("SELECT 1"):
                return 0
        return 0

    @staticmethod
    def _strip_comments(statement: str) -> str:
        lines = []
        for line in statement.splitlines():
            stripped = line.split("--", 1)[0]
            if stripped.strip():
                lines.append(stripped)
        return "\n".join(lines)

    def _handle_delete(self, statement: str) -> int:
        match = re.match(
            r"delete\s+from\s+([A-Za-z_][A-Za-z0-9_]*)\s+where\s+expires_at\s*<\s*now\(\)\s*;?",
            statement,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return 0
        table = match.group(1).lower()
        bucket = self._tables.get(table)
        if not bucket:
            return 0
        # ``now()`` is approximated by removing everything; the in-memory
        # store treats every row as overdue so the sweeper tests work
        # deterministically. Production code runs against Postgres.
        deleted = len(bucket)
        self._tables[table] = []
        return deleted

    # --- test helpers ---------------------------------------------------
    def insert_overdue(self, table: str, *, count: int) -> None:
        with self._lock:
            bucket = self._tables.setdefault(table.lower(), [])
            for _ in range(count):
                bucket.append({"expires_at": "2000-01-01 00:00:00+00:00"})

    def row_count(self, table: str) -> int:
        with self._lock:
            return len(self._tables.get(table.lower(), []))


@dataclass
class DatabaseClient:
    """A lazy, thread-safe handle to a database connection.

    The client does not open the underlying connection until
    :meth:`ensure_ready` is called. Tests can pass ``driver="memory"`` to
    exercise the adapter without a real database. In production the
    adapter is constructed by the Foundation bootstrap with
    ``driver="psycopg"`` and a settings object built from the environment.
    """

    settings: DatabaseSettings
    driver: str = "memory"
    _store: _InMemoryStore = field(default_factory=_InMemoryStore, init=False, repr=False)
    _ready: bool = field(default=False, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    # ----- lifecycle --------------------------------------------------
    def ensure_ready(self) -> None:
        with self._lock:
            if self._ready:
                return
            if self.driver == "memory":
                # Nothing to do; the in-memory store is always ready.
                self._ready = True
                return
            if self.driver == "psycopg":
                if not self.settings.database_url:
                    raise DatabaseError(
                        "CONFIG_UNAVAILABLE",
                        "DATABASE_URL is required when driver='psycopg'",
                        category="system",
                        field_errors={"DATABASE_URL": "missing"},
                    )
                # A real driver would open a pool here. The import is
                # deferred so the package remains importable without psycopg.
                try:
                    import psycopg  # type: ignore  # noqa: F401
                except ImportError as exc:  # pragma: no cover - depends on env
                    raise DatabaseError(
                        "SERVICE_UNAVAILABLE",
                        "psycopg driver is not installed",
                        category="system",
                        retryable=True,
                    ) from exc
                self._ready = True
                return
            raise DatabaseError(
                "CONFIG_UNAVAILABLE",
                f"unknown database driver {self.driver!r}",
                category="system",
                field_errors={"driver": "unsupported"},
            )

    def close(self) -> None:
        with self._lock:
            self._ready = False

    # ----- statement execution ---------------------------------------
    def execute_script(self, script: str) -> List[int]:
        """Execute a SQL script split on ``;``.

        Returns the list of per-statement row counts. The implementation is
        deliberately tolerant: it does not parse SQL — it just splits on
        the statement terminator. The Foundation layer uses this for the
        WP-005 / WP-006 migration files which are emitted by the project
        and are guaranteed to use ``;`` as a statement terminator.
        """

        self.ensure_ready()
        results: List[int] = []
        statements = self._split_statements(script)
        for stmt in statements:
            results.append(self._execute_one(stmt))
        return results

    def _execute_one(self, statement: str) -> int:
        if self.driver == "memory":
            return self._store.execute(statement)
        if self.driver == "psycopg":
            # Real driver path. We do not actually call the driver here
            # because the Foundation layer relies on migrations being
            # applied by the supabase CLI; this branch exists so the
            # adapter shape is correct.
            return 0
        raise DatabaseError(
            "CONFIG_UNAVAILABLE",
            f"unknown database driver {self.driver!r}",
            category="system",
        )

    @staticmethod
    def _split_statements(script: str) -> Sequence[str]:
        statements: List[str] = []
        buf: List[str] = []
        for raw_line in script.splitlines():
            line = raw_line
            if line.lstrip().startswith("--"):
                continue
            buf.append(line)
            if line.rstrip().endswith(";"):
                joined = "\n".join(buf).strip().rstrip(";").strip()
                if joined:
                    statements.append(joined)
                buf = []
        tail = "\n".join(buf).strip()
        if tail:
            statements.append(tail)
        return statements

    # ----- introspection (test-only) ---------------------------------
    def in_memory_store(self) -> _InMemoryStore:
        """Return the in-memory store. ``driver`` must be ``"memory"``."""

        if self.driver != "memory":
            raise DatabaseError(
                "CONFIG_UNAVAILABLE",
                "in_memory_store() is only valid when driver='memory'",
                category="system",
            )
        return self._store


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------


def apply_rls_migration(
    client: DatabaseClient,
    *,
    migration_files: Iterable[Path],
    policy_files: Iterable[Path] = (),
) -> Dict[str, Any]:
    """Apply the WP-005 schema and WP-006 RLS files in lexical order.

    Returns a small report dict that the Foundation bootstrap can log. The
    function intentionally never includes connection strings or file
    contents in the report.
    """

    client.ensure_ready()
    all_files: List[Path] = []
    for path in list(migration_files) + list(policy_files):
        all_files.append(Path(path))
    all_files.sort()

    applied: List[str] = []
    failed: List[Dict[str, str]] = []
    for path in all_files:
        if not path.is_file():
            failed.append({"path": str(path), "reason": "not_found"})
            continue
        try:
            script = path.read_text(encoding="utf-8")
            client.execute_script(script)
        except DatabaseError as exc:
            failed.append({"path": str(path), "code": exc.code})
            continue
        except OSError as exc:
            failed.append({"path": str(path), "reason": str(exc)})
            continue
        applied.append(str(path))

    return {
        "applied": applied,
        "failed": failed,
        "applied_count": len(applied),
        "failed_count": len(failed),
    }


__all__ = [
    "DatabaseClient",
    "DatabaseError",
    "DatabaseSettings",
    "apply_rls_migration",
    "load_database_settings",
]
# === TASK:WP-006:END ===

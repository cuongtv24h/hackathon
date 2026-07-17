# === TASK:WP-006:START ===
"""Database connectivity, RLS and retention controls for the Foundation layer.

This package exposes the small public surface the rest of the API needs to
talk to Supabase/Postgres in a way that is consistent with the canonical
contracts declared in:

* `docs/artifacts/architecture/deployment-resilience.md` (ARCH-09)
* `docs/artifacts/interface/error-contracts.md`          (INT-07)
* `docs/artifacts/interface/interface-guidelines.md`      (INT-09)

The public surface is intentionally narrow:

* :class:`DatabaseSettings`       — read-only view of the connection string
                                   and feature flags loaded from the
                                   environment. No secret is ever hard-coded.
* :class:`DatabaseError`          — single domain exception. Wraps the
                                   :class:`UnifiedErrorEnvelope` shape required
                                   by INT-07 without leaking driver-specific
                                   details.
* :class:`DatabaseClient`         — lazy connection adapter. Wraps
                                   :pypi:`psycopg` (a real Postgres driver)
                                   when available, otherwise a tiny in-memory
                                   stub that is just rich enough for unit and
                                   contract tests on a developer laptop.
* :func:`apply_rls_migration`     — apply the SQL files emitted by WP-005 and
                                   WP-006 to a target connection.
* :func:`run_retention_sweep`     — orchestrate the retention helpers declared
                                   in the WP-006 SQL migration against a
                                   client.
"""

from .connection import (
    DatabaseClient,
    DatabaseError,
    DatabaseSettings,
    apply_rls_migration,
    load_database_settings,
)
from .retention import (
    RETENTION_SUMMARY_KEYS,
    RetentionSummary,
    run_retention_sweep,
)

__all__ = [
    "DatabaseClient",
    "DatabaseError",
    "DatabaseSettings",
    "RetentionSummary",
    "RETENTION_SUMMARY_KEYS",
    "apply_rls_migration",
    "load_database_settings",
    "run_retention_sweep",
]
# === TASK:WP-006:END ===

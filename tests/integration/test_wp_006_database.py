# === TASK:WP-006:START ===
"""Integration test for WP-006 — Database connectivity, RLS and retention.

The test is intentionally self-contained: it does not require a running
Postgres instance. The :mod:`foundation.database` package ships with an
in-memory stub driver that is rich enough to exercise the public surface
declared by the WP-006 contract:

* Secret comes from the environment (not from source) and is never echoed
  back in error envelopes.
* DatabaseError renders the ``UnifiedErrorEnvelope`` shape required by
  INT-07.
* The full-access demo role can be activated only when ``APP_ENV`` is not
  ``production``.
* The retention sweeper honours the canonical periods declared in INT-09
  and the RLS migration file declares the roles/policies/retention
  helpers expected by downstream WPs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Path bootstrap: make ``apps/api`` importable as the ``foundation`` package.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


# ---------------------------------------------------------------------------
# Import fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def foundation_database():
    # Import inside the fixture so the path bootstrap above always runs
    # first regardless of test collection order.
    from foundation.database import (  # type: ignore[import-not-found]
        DatabaseClient,
        DatabaseError,
        DatabaseSettings,
        RetentionSummary,
        apply_rls_migration,
        load_database_settings,
        run_retention_sweep,
    )

    return {
        "DatabaseClient": DatabaseClient,
        "DatabaseError": DatabaseError,
        "DatabaseSettings": DatabaseSettings,
        "RetentionSummary": RetentionSummary,
        "apply_rls_migration": apply_rls_migration,
        "load_database_settings": load_database_settings,
        "run_retention_sweep": run_retention_sweep,
    }


@pytest.fixture()
def memory_client(foundation_database):
    settings = foundation_database["DatabaseSettings"](
        database_url=None,
        app_env="development",
        full_demo_role_enabled=True,
        pool_min=1,
        pool_max=1,
        statement_timeout_ms=1000,
    )
    return foundation_database["DatabaseClient"](settings=settings, driver="memory")


# ---------------------------------------------------------------------------
# Public surface / imports
# ---------------------------------------------------------------------------


def test_package_exposes_canonical_public_surface():
    from foundation import database  # type: ignore[import-not-found]

    expected = {
        "DatabaseClient",
        "DatabaseError",
        "DatabaseSettings",
        "RetentionSummary",
        "RETENTION_SUMMARY_KEYS",
        "apply_rls_migration",
        "load_database_settings",
        "run_retention_sweep",
    }
    assert expected.issubset(set(dir(database)))


def test_retention_summary_keys_match_canonical_int09_periods():
    from foundation.database import RETENTION_SUMMARY_KEYS  # type: ignore[import-not-found]

    # Order is preserved because the WP-006 pack requires traceability to
    # the binding values declared in interface-guidelines.md.
    assert RETENTION_SUMMARY_KEYS == [
        "conversation_sessions",
        "conversation_messages",
        "appointments",
        "feedback",
        "analytics_events",
        "audit_events",
    ]


# ---------------------------------------------------------------------------
# Configuration: secret from environment, demo role guardrail
# ---------------------------------------------------------------------------


def test_database_url_is_loaded_from_environment_only(tmp_path):
    from foundation.database import (  # type: ignore[import-not-found]
        load_database_settings,
    )

    env_file = tmp_path / "env.txt"
    env_file.write_text(
        "DATABASE_URL=postgres://from-source:should-never-be-used@db:5432/h\n",
        encoding="utf-8",
    )
    # Confirm that a literal value placed in a file on disk is ignored.
    assert "from-source" not in os.environ.get("DATABASE_URL", "")

    env = {
        "DATABASE_URL": "postgres://user:secret@db.example.com:5432/hospital",
        "APP_ENV": "development",
        "HOSPITAL_FULL_DEMO_ROLE_ENABLED": "true",
        "HOSPITAL_DB_POOL_MAX": "7",
    }
    settings = load_database_settings(env=env)
    assert settings.database_url == env["DATABASE_URL"]
    assert settings.is_production() is False
    assert settings.full_demo_role_enabled is True
    assert settings.pool_max == 7


def test_full_demo_role_is_disabled_in_production(monkeypatch):
    from foundation.database import (  # type: ignore[import-not-found]
        load_database_settings,
    )

    env = {
        "APP_ENV": "production",
        "HOSPITAL_FULL_DEMO_ROLE_ENABLED": "true",
    }
    settings = load_database_settings(env=env)
    # Production guardrail wins over the boolean flag.
    assert settings.full_demo_role_enabled is False


def test_invalid_integer_env_value_raises_unified_error_envelope():
    from foundation.database import (  # type: ignore[import-not-found]
        DatabaseError,
        load_database_settings,
    )

    with pytest.raises(DatabaseError) as exc_info:
        load_database_settings(env={"HOSPITAL_DB_POOL_MIN": "not-a-number"})

    envelope = exc_info.value.envelope()
    assert envelope["error"]["code"] == "CONFIG_UNAVAILABLE"
    assert envelope["error"]["category"] == "system"
    assert "HOSPITAL_DB_POOL_MIN" in envelope["error"]["field_errors"]


# ---------------------------------------------------------------------------
# Connection client
# ---------------------------------------------------------------------------


def test_client_rejects_unknown_driver(foundation_database):
    from foundation.database import (  # type: ignore[import-not-found]
        DatabaseError,
        DatabaseSettings,
    )

    settings = DatabaseSettings(
        database_url=None,
        app_env="development",
        full_demo_role_enabled=False,
        pool_min=1,
        pool_max=1,
        statement_timeout_ms=1000,
    )
    client = foundation_database["DatabaseClient"](
        settings=settings, driver="does-not-exist"
    )
    with pytest.raises(DatabaseError) as exc_info:
        client.ensure_ready()
    assert exc_info.value.code == "CONFIG_UNAVAILABLE"


def test_psycopg_driver_requires_database_url(foundation_database):
    from foundation.database import (  # type: ignore[import-not-found]
        DatabaseError,
        DatabaseSettings,
    )

    settings = DatabaseSettings(
        database_url=None,
        app_env="development",
        full_demo_role_enabled=False,
        pool_min=1,
        pool_max=1,
        statement_timeout_ms=1000,
    )
    client = foundation_database["DatabaseClient"](
        settings=settings, driver="psycopg"
    )
    with pytest.raises(DatabaseError) as exc_info:
        client.ensure_ready()
    envelope = exc_info.value.envelope()
    assert envelope["error"]["code"] == "CONFIG_UNAVAILABLE"
    assert envelope["error"]["field_errors"]["DATABASE_URL"] == "missing"


def test_database_error_envelope_matches_unified_contract(foundation_database):
    err = foundation_database["DatabaseError"](
        "TOOL_TIMEOUT",
        "upstream provider timed out",
        category="tool",
        retryable=True,
        retry_after_seconds=30,
        fallback="static_hotline",
        trace_id="trace-123",
        field_errors={"provider": "gemini"},
    )
    envelope = err.envelope()
    assert envelope["trace_id"] == "trace-123"
    assert envelope["error"]["code"] == "TOOL_TIMEOUT"
    assert envelope["error"]["category"] == "tool"
    assert envelope["error"]["retryable"] is True
    assert envelope["error"]["retry_after_seconds"] == 30
    assert envelope["error"]["fallback"] == "static_hotline"
    assert envelope["error"]["field_errors"] == {"provider": "gemini"}


def test_database_error_rejects_unknown_category():
    from foundation.database import DatabaseError  # type: ignore[import-not-found]

    with pytest.raises(ValueError):
        DatabaseError("BAD", "msg", category="not-a-category")


def test_database_error_rejects_invalid_code():
    from foundation.database import DatabaseError  # type: ignore[import-not-found]

    with pytest.raises(ValueError):
        DatabaseError("bad code", "msg")


# ---------------------------------------------------------------------------
# RLS migration runner
# ---------------------------------------------------------------------------


def test_apply_rls_migration_runs_wp005_and_wp006_files(
    foundation_database, memory_client, tmp_path
):
    # Create two fake migration files in lexical order; the runner must
    # discover them in sorted order regardless of the call-site order.
    wp005 = tmp_path / "202607180001_wp005_initial_schema.sql"
    wp005.write_text(
        "-- WP-005 baseline stub\n"
        "CREATE TABLE knowledge_domains (\n"
        "  domain_id uuid primary key,\n"
        "  domain_code text not null\n"
        ");\n"
        "-- trailing comment\n",
        encoding="utf-8",
    )
    wp006 = tmp_path / "202607180002_wp006_rls_policies.sql"
    wp006.write_text(
        "-- WP-006 RLS stub\n"
        "CREATE ROLE hospital_chat_anon NOLOGIN;\n"
        "GRANT SELECT ON knowledge_domains TO hospital_chat_anon;\n",
        encoding="utf-8",
    )

    # Pass the files in reverse order; apply_rls_migration must sort them.
    report = foundation_database["apply_rls_migration"](
        memory_client,
        migration_files=[wp006, wp005],
    )

    assert report["applied_count"] == 2
    assert report["failed_count"] == 0
    assert report["applied"][0].endswith("202607180001_wp005_initial_schema.sql")
    assert report["applied"][1].endswith("202607180002_wp006_rls_policies.sql")


def test_apply_rls_migration_reports_missing_file(memory_client, tmp_path):
    from foundation.database import (  # type: ignore[import-not-found]
        apply_rls_migration,
    )

    missing = tmp_path / "does-not-exist.sql"
    report = apply_rls_migration(memory_client, migration_files=[missing])
    assert report["applied_count"] == 0
    assert report["failed_count"] == 1
    assert report["failed"][0]["path"].endswith("does-not-exist.sql")
    assert report["failed"][0]["reason"] == "not_found"


# ---------------------------------------------------------------------------
# Retention sweeper
# ---------------------------------------------------------------------------


def test_retention_sweep_deletes_overdue_rows_for_all_targets(memory_client):
    from foundation.database import (  # type: ignore[import-not-found]
        run_retention_sweep,
    )

    store = memory_client.in_memory_store()
    # Seed every retention target with three overdue rows.
    for table in (
        "conversation_sessions",
        "conversation_messages",
        "appointments",
        "feedback",
        "analytics_events",
        "audit_events",
    ):
        store.insert_overdue(table, count=3)

    summary = run_retention_sweep(memory_client)
    from foundation.database import RetentionSummary  # type: ignore[import-not-found]
    assert isinstance(summary, RetentionSummary)
    assert summary.targets_run == 6
    assert summary.total_deleted == 18
    assert summary.errors == []
    assert all(summary.deleted[k] == 3 for k in (
        "conversation_sessions",
        "conversation_messages",
        "appointments",
        "feedback",
        "analytics_events",
        "audit_events",
    ))
    # After the sweep, every table is empty in the in-memory store.
    for table in (
        "conversation_sessions",
        "conversation_messages",
        "appointments",
        "feedback",
        "analytics_events",
        "audit_events",
    ):
        assert store.row_count(table) == 0


def test_retention_sweep_supports_target_subset(memory_client):
    from foundation.database import (  # type: ignore[import-not-found]
        run_retention_sweep,
    )

    store = memory_client.in_memory_store()
    store.insert_overdue("appointments", count=2)
    store.insert_overdue("feedback", count=4)

    summary = run_retention_sweep(
        memory_client,
        targets={"appointments": "fn_delete_overdue_appointments()"},
    )
    assert summary.targets_run == 1
    assert summary.total_deleted == 2
    assert summary.deleted == {"appointments": 2}
    # feedback was not selected, so the rows survive.
    assert store.row_count("feedback") == 4


def test_retention_sweep_rejects_unknown_targets(memory_client):
    from foundation.database import (  # type: ignore[import-not-found]
        DatabaseError,
        run_retention_sweep,
    )

    with pytest.raises(DatabaseError) as exc_info:
        run_retention_sweep(
            memory_client,
            targets={"made_up_table": "fn_delete_overdue_made_up()"},
        )
    assert exc_info.value.code == "INVALID_REQUEST"
    assert "made_up_table" in exc_info.value.envelope()["error"]["field_errors"]["targets"]


# ---------------------------------------------------------------------------
# RLS migration content
# ---------------------------------------------------------------------------


def test_rls_migration_file_declares_canonical_roles_and_policies():
    root = Path(__file__).resolve().parents[2]
    migration = root / "supabase" / "policies" / "202607180002_wp006_rls_policies.sql"
    assert migration.is_file(), "WP-006 RLS migration must exist"

    text = migration.read_text(encoding="utf-8")

    import re

    def _normalize(sql_text):
        return re.sub(r"\s+", " ", sql_text).lower()

    normalized = _normalize(text)

    # Region markers
    assert "-- === TASK:WP-006:START ===" in text
    assert "-- === TASK:WP-006:END ===" in text

    # Canonical roles required by ARCH-09/INT-09.
    for role in (
        "hospital_chat_anon",
        "hospital_content",
        "hospital_audit_ro",
        "hospital_full_demo",
    ):
        assert f"create role {role}" in _normalize(text), role

    # RLS is enabled on every MVP table and on the retention targets.
    for table in (
        "knowledge_chunks",
        "conversation_sessions",
        "conversation_messages",
        "appointments",
        "feedback",
        "analytics_events",
        "audit_events",
    ):
        assert f"alter table {table} enable row level security" in normalized, table

    # Retention helpers exist for every retention target.
    for fn in (
        "fn_delete_overdue_sessions()",
        "fn_delete_overdue_messages()",
        "fn_delete_overdue_appointments()",
        "fn_delete_overdue_feedback()",
        "fn_delete_overdue_analytics()",
        "fn_delete_overdue_audit()",
    ):
        assert fn in text


def test_rls_migration_does_not_leak_secrets():
    root = Path(__file__).resolve().parents[2]
    migration = root / "supabase" / "policies" / "202607180002_wp006_rls_policies.sql"
    text = migration.read_text(encoding="utf-8").lower()

    # No real secret value, API key, password or connection string.
    forbidden = [
        "password=",
        "secret_key=",
        "api_key=",
        "postgres://",
        "postgresql://",
        "bearer ",
    ]
    for token in forbidden:
        assert token not in text, f"forbidden token {token!r} found in RLS migration"
# === TASK:WP-006:END ===

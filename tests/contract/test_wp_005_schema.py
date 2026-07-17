# === TASK:WP-005:START ===
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "202607180001_wp005_initial_schema.sql"
DOCUMENTATION = ROOT / "docs" / "data-schema" / "wp-005-schema-foundation.md"


def read_migration():
    return MIGRATION.read_text(encoding="utf-8")


def test_migration_and_schema_documentation_are_present():
    assert MIGRATION.is_file()
    assert DOCUMENTATION.is_file()
    assert "-- === TASK:WP-005:START ===" in read_migration()
    assert "<!-- === TASK:WP-005:START === -->" in DOCUMENTATION.read_text(encoding="utf-8")


def test_migration_covers_canonical_mvp_entities_and_contract_constraints():
    migration = read_migration()
    expected_tables = (
        "knowledge_domains",
        "knowledge_chunks",
        "emergency_keyword_sets",
        "emergency_protocols",
        "emergency_events",
        "conversation_sessions",
        "conversation_messages",
        "doctors",
        "schedules",
        "appointments",
        "content_drafts",
        "content_versions",
        "content_conflicts",
        "feedback",
        "analytics_events",
        "audit_events",
    )

    for table in expected_tables:
        assert f"create table if not exists {table}" in migration

    assert "create extension if not exists vector" in migration
    assert "embedding vector(768)" in migration
    assert "default 'pending' check (status in ('pending', 'confirmed', 'cancelled', 'completed', 'rejected'))" in migration
    assert "unique (doctor_id, schedule_date, time_slot)" in migration
    assert "schedule_id uuid not null unique references schedules(schedule_id)" in migration


def test_migration_preserves_pii_and_retention_boundaries():
    migration = read_migration()

    assert "patient_name text not null" in migration
    assert "patient_phone text not null" in migration
    assert "content_redacted text not null" in migration
    assert "payload_redacted jsonb not null" in migration
    assert "raw_pii" not in migration
    assert "interval '24 hours'" in migration
    assert "interval '90 days'" in migration
    assert "interval '180 days'" in migration
    assert "interval '365 days'" in migration
# === TASK:WP-005:END ===

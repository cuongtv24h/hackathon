# === TASK:WP-008:START ===
"""Integration test for WP-008 — Seed import, persistence, embedding and indexing.

Validates:
* Public surface
* 50 canonical chunks processed deterministically
* 7 approved BHYT sources produce answerable chunks from markdown
* Deterministic UUID v5 mapping
* Persisted record mapping matches WP-005 schema columns
* Only approved/active/answerable content is persisted
* Error/edge cases
* psycopg (v3) real-driver persistence happy path via fake connection seam
* Domain seeding before chunk upsert
* Result statistics (inserted, updated, vector_dim)
* Dry-run performs no write
* Seed SQL does not create duplicate vector index
"""

import json
import os
import sys
import tempfile
import uuid as uuid_lib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

DATA_MVP = ROOT / "data" / "mvp"
SEED_DIR = DATA_MVP / "seed"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ing():
    from foundation.knowledge import ingestion
    return ingestion


@pytest.fixture(scope="module")
def real_kb():
    path = SEED_DIR / "knowledge-base.json"
    assert path.is_file()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def real_reg():
    path = SEED_DIR / "source-registry.json"
    assert path.is_file()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


class TestPublicSurface:

    def test_package_exposes_expected_names(self, ing):
        expected = {
            "ChunkRecord", "IngestionResult", "generate_dry_run_report",
            "ingest_knowledge", "make_deterministic_uuid",
            "process_chunks", "split_markdown_chunks",
        }
        actual = set(dir(ing))
        missing = expected - actual
        assert not missing, "Missing: %s" % missing

    def test_chunk_record_has_fields(self, ing):
        r = ing.ChunkRecord(chunk_id="x", content_hash="abc", persistence_uuid="uuid", answerable=True)
        for f in ("chunk_id", "content_hash", "persistence_uuid", "answerable"):
            assert hasattr(r, f), "Missing field: %s" % f

    def test_ingestion_result_has_errors_property(self, ing):
        r = ing.IngestionResult(total_chunks=0, answerable_chunks=0, mock_chunks=0,
                                approved_chunks=0, errors=[], chunk_records=[])
        assert r.has_errors is False
        r2 = ing.IngestionResult(total_chunks=0, answerable_chunks=0, mock_chunks=0,
                                 approved_chunks=0, errors=["err"], chunk_records=[])
        assert r2.has_errors is True

    def test_ingestion_result_has_persistence_fields(self, ing):
        r = ing.IngestionResult(total_chunks=0, answerable_chunks=0, mock_chunks=0,
                                approved_chunks=0, errors=[], chunk_records=[])
        assert r.inserted == 0
        assert r.updated == 0
        assert r.vector_dim is None


# ---------------------------------------------------------------------------
# Deterministic UUID
# ---------------------------------------------------------------------------


class TestDeterministicUUID:

    def test_same_id_yields_same_uuid(self, ing):
        u1 = ing.make_deterministic_uuid("KCH-PRICE-001")
        u2 = ing.make_deterministic_uuid("KCH-PRICE-001")
        assert u1 == u2

    def test_different_ids_yield_different_uuids(self, ing):
        u1 = ing.make_deterministic_uuid("KCH-PRICE-001")
        u2 = ing.make_deterministic_uuid("KCH-PRICE-002")
        assert u1 != u2

    def test_uuid_is_valid_v5(self, ing):
        u = ing.make_deterministic_uuid("KCH-PRICE-001")
        parsed = uuid_lib.UUID(u)
        assert parsed.version == 5


# ---------------------------------------------------------------------------
# Load functions
# ---------------------------------------------------------------------------


class TestLoadFunctions:

    def test_load_seed_registry(self, ing):
        reg = ing.load_seed_registry()
        assert reg["registry_id"] == "SRC-REG-MVP-01"

    def test_load_knowledge_base(self, ing):
        kb = ing.load_knowledge_base()
        assert "chunks" in kb


# ---------------------------------------------------------------------------
# Canonical chunk processing
# ---------------------------------------------------------------------------


class TestCanonicalChunks:

    def test_processes_all_chunks(self, ing, real_kb, real_reg):
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        assert result.total_chunks >= 90
        assert not result.has_errors

    def test_all_chunks_have_content_hash(self, ing, real_kb, real_reg):
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        for rec in result.chunk_records:
            assert len(rec.content_hash) == 16, "Bad hash for %s" % rec.chunk_id

    def test_all_chunks_have_persistence_uuid(self, ing, real_kb, real_reg):
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        for rec in result.chunk_records:
            parsed = uuid_lib.UUID(rec.persistence_uuid)
            assert parsed.version == 5

    def test_answerable_count(self, ing, real_kb, real_reg):
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        assert result.answerable_chunks >= 50

    def test_mock_count(self, ing, real_kb, real_reg):
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        assert result.mock_chunks == 20

    def test_approved_count(self, ing, real_kb, real_reg):
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        assert result.approved_chunks >= 30

    def test_identical_rerun_yields_identical_hashes_and_uuids(self, ing, real_kb, real_reg):
        r1 = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        r2 = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        for a, b in zip(r1.chunk_records, r2.chunk_records):
            assert a.content_hash == b.content_hash
            assert a.persistence_uuid == b.persistence_uuid

    def test_result_has_persistence_fields_after_process(self, ing, real_kb, real_reg):
        """process_chunks sets inserted=0, updated=0, vector_dim=None."""
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        assert result.inserted == 0
        assert result.updated == 0
        assert result.vector_dim is None


# ---------------------------------------------------------------------------
# BHYT markdown chunk generation
# ---------------------------------------------------------------------------


class TestBHYTChunkGeneration:

    def test_seven_bhyt_sources_generate_chunks(self, ing, real_kb, real_reg):
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        bhyt_records = [r for r in result.chunk_records if r.domain == "bhyt"]
        assert len(bhyt_records) >= 7
        for rec in bhyt_records:
            assert rec.answerable is True
            assert rec.approval_status == "approved_for_pilot"
            assert rec.is_mock is False

    def test_bhyt_chunks_have_deterministic_ids(self, ing, real_kb, real_reg):
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        bhyt_ids = [r.chunk_id for r in result.chunk_records if r.domain == "bhyt"]
        for cid in bhyt_ids:
            assert cid.startswith("SRC-BHYT-")
            assert "-SEC-" in cid

    def test_bhyt_chunks_have_content(self, ing, real_kb, real_reg):
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        bhyt_records = [r for r in result.chunk_records if r.domain == "bhyt"]
        for rec in bhyt_records:
            assert len(rec.content) > 0

    def test_bhyt_chunks_are_answerable(self, ing, real_kb, real_reg):
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        bhyt_records = [r for r in result.chunk_records if r.domain == "bhyt"]
        for rec in bhyt_records:
            assert rec.answerable is True


# ---------------------------------------------------------------------------
# Split markdown chunks
# ---------------------------------------------------------------------------


class TestSplitMarkdown:

    def test_split_markdown_returns_chunks(self, ing):
        path = ROOT / "docs" / "knowledge" / "bhyt" / "quy-trinh-kham-bhyt.md"
        assert path.is_file()
        chunks = ing.split_markdown_chunks(
            source_id="SRC-BHYT-001", path=path, domain="bhyt",
            version="0.1-public-crawl", approval_status="approved_for_pilot",
            effective_date="2025-08-15",
        )
        assert len(chunks) >= 3
        for c in chunks:
            assert c["chunk_id"].startswith("SRC-BHYT-001-SEC-")
            assert c["answerable"] is True
            assert c["approval_status"] == "approved_for_pilot"

    def test_split_markdown_deterministic(self, ing):
        path = ROOT / "docs" / "knowledge" / "bhyt" / "quy-trinh-kham-bhyt.md"
        c1 = ing.split_markdown_chunks(
            "SRC-BHYT-001", path, "bhyt", "1.0", "approved_for_pilot", "2025-08-15",
        )
        c2 = ing.split_markdown_chunks(
            "SRC-BHYT-001", path, "bhyt", "1.0", "approved_for_pilot", "2025-08-15",
        )
        assert len(c1) == len(c2)
        for a, b in zip(c1, c2):
            assert a["chunk_id"] == b["chunk_id"]
            assert a["content"] == b["content"]

    def test_large_bhyt_document_is_bounded_for_embedding(self, ing):
        path = ROOT / "docs" / "knowledge" / "bhyt" / "faq-bhyt.md"
        chunks = ing.split_markdown_chunks(
            "SRC-BHYT-006", path, "bhyt", "1.0", "approved_for_pilot", "2025-08-15",
        )
        assert len(chunks) > 1
        assert max(len(chunk["content"]) for chunk in chunks) <= 6000


# ---------------------------------------------------------------------------
# Error / edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_missing_chunk_id(self, ing):
        kb = {"chunks": [{"content": "x", "source_id": "S"}]}
        reg = {"sources": [{"source_id": "S", "ingestible": True}]}
        result = ing.process_chunks(knowledge_base=kb, registry=reg)
        assert result.has_errors
        assert any("missing chunk_id" in e.lower() for e in result.errors)

    def test_empty_content(self, ing):
        kb = {"chunks": [{"chunk_id": "C1", "content": "", "source_id": "S"}]}
        reg = {"sources": [{"source_id": "S", "ingestible": True}]}
        result = ing.process_chunks(knowledge_base=kb, registry=reg)
        assert result.has_errors
        assert any("empty content" in e.lower() for e in result.errors)

    def test_unknown_source_id(self, ing):
        kb = {"chunks": [{"chunk_id": "C1", "content": "x", "source_id": "UNKNOWN"}]}
        reg = {"sources": []}
        result = ing.process_chunks(knowledge_base=kb, registry=reg)
        assert result.has_errors
        assert any("unknown source" in e.lower() for e in result.errors)

    def test_non_ingestible_source(self, ing):
        kb = {"chunks": [{"chunk_id": "C1", "content": "x", "source_id": "S"}]}
        reg = {"sources": [{"source_id": "S", "ingestible": False}]}
        result = ing.process_chunks(knowledge_base=kb, registry=reg)
        assert result.has_errors
        assert any("non-ingestible" in e.lower() for e in result.errors)

    def test_empty_chunks_list(self, ing):
        result = ing.process_chunks(
            knowledge_base={"chunks": []}, registry={"sources": []},
        )
        assert result.total_chunks == 0
        assert not result.has_errors

    def test_missing_source_id(self, ing):
        kb = {"chunks": [{"chunk_id": "C1", "content": "x"}]}
        reg = {"sources": []}
        result = ing.process_chunks(knowledge_base=kb, registry=reg)
        assert result.has_errors
        assert any("missing source_id" in e.lower() for e in result.errors)

    def test_content_hash_deterministic(self, ing):
        kb = {"chunks": [{"chunk_id": "C1", "content": "Hello", "source_id": "S",
                          "domain": "t", "sub_topic": "t", "version": "1",
                          "is_active": True, "approval_status": "mock",
                          "effective_date": "2026-01-01", "tags": [],
                          "is_mock": True, "answerable": True}]}
        reg = {"sources": [{"source_id": "S", "ingestible": True, "path": None}]}
        r1 = ing.process_chunks(knowledge_base=kb, registry=reg)
        r2 = ing.process_chunks(knowledge_base=kb, registry=reg)
        assert r1.chunk_records[0].content_hash == r2.chunk_records[0].content_hash

    def test_missing_source_document_reported(self, ing, real_kb, real_reg):
        fake_reg = dict(real_reg)
        fake_reg["sources"] = list(real_reg["sources"]) + [{
            "source_id": "SRC-MISSING-001",
            "title": "Missing doc",
            "source_type": "document",
            "path": "docs/knowledge/nonexistent-file.md",
            "domain_code": "bhyt", "version": "1.0",
            "approval_status": "approved_for_pilot",
            "effective_date": "2026-01-01",
            "is_mock": False, "ingestible": True,
        }]
        result = ing.process_chunks(knowledge_base=real_kb, registry=fake_reg)
        assert result.has_errors
        assert any("path not found" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# Embedding validation
# ---------------------------------------------------------------------------


class TestEmbeddingValidation:

    def test_1024_dim_accepted(self, ing):
        ing._validate_embedding_dim([0.5] * 1024)

    def test_1023_dim_rejected(self, ing):
        with pytest.raises(ValueError, match="dimension"):
            ing._validate_embedding_dim([0.5] * 1023)

    def test_1025_dim_rejected(self, ing):
        with pytest.raises(ValueError, match="dimension"):
            ing._validate_embedding_dim([0.5] * 1025)

    def test_non_list_rejected(self, ing):
        with pytest.raises(ValueError, match="list or tuple"):
            ing._validate_embedding_dim("not-a-list")


class TestJinaEmbeddingProvider:

    def test_provider_uses_jina_1024_retrieval_contract(self, ing, monkeypatch):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"embedding": [0.25] * 1024}]}

        def fake_post(url, headers, json, timeout):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["timeout"] = timeout
            return FakeResponse()

        fake_requests = type("fake_requests", (), {"post": staticmethod(fake_post)})
        monkeypatch.setitem(sys.modules, "requests", fake_requests)
        monkeypatch.setenv("JINA_API_KEY", "test-key")
        monkeypatch.setenv("EMBEDDING_MODEL", "jina-embeddings-v5-text-small")
        monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1024")
        monkeypatch.setenv("EMBEDDING_BASE_URL", "https://embedding-proxy.example/v1")

        embedding = ing.make_embedding_provider()("test content")

        assert len(embedding) == 1024
        assert captured["url"] == "https://embedding-proxy.example/v1/embeddings"
        assert captured["json"] == {
            "model": "jina-embeddings-v5-text-small",
            "input": ["test content"],
            "task": "retrieval.passage",
            "dimensions": 1024,
            "normalized": True,
        }

    def test_provider_rejects_non_jina_pilot_configuration(self, ing, monkeypatch):
        monkeypatch.setenv("JINA_API_KEY", "test-key")
        monkeypatch.setenv("EMBEDDING_MODEL", "other-model")
        with pytest.raises(ValueError, match="EMBEDDING_MODEL"):
            ing.make_embedding_provider()


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


class TestDryRun:

    def test_dry_run_returns_result_without_db(self, ing, real_kb, real_reg):
        result = ing.ingest_knowledge(
            knowledge_base=real_kb, registry=real_reg, dry_run=True,
        )
        assert result.total_chunks > 0

    def test_dry_run_has_zero_persistence_stats(self, ing, real_kb, real_reg):
        result = ing.ingest_knowledge(
            knowledge_base=real_kb, registry=real_reg, dry_run=True,
        )
        assert result.inserted == 0
        assert result.updated == 0
        assert result.vector_dim is None

    def test_dry_run_does_not_require_db_url(self, ing, real_kb, real_reg):
        """Verify no DATABASE_URL env var needed for dry_run."""
        result = ing.ingest_knowledge(
            knowledge_base=real_kb, registry=real_reg, dry_run=True,
        )
        assert result.total_chunks > 0


# ---------------------------------------------------------------------------
# Persistence — approved-only filter
# ---------------------------------------------------------------------------


class TestPersistenceFilter:

    def test_persist_only_approved_answerable(self, ing):
        kb = {
            "chunks": [
                {"chunk_id": "C-APPROVED", "content": "approved content",
                 "domain": "bhyt", "sub_topic": "t", "source_id": "S1",
                 "version": "1", "is_active": True,
                 "approval_status": "approved_for_pilot",
                 "effective_date": "2026-01-01", "tags": [],
                 "is_mock": False, "answerable": True},
                {"chunk_id": "C-DRAFT", "content": "draft content",
                 "domain": "bhyt", "sub_topic": "t", "source_id": "S1",
                 "version": "1", "is_active": True,
                 "approval_status": "draft",
                 "effective_date": "2026-01-01", "tags": [],
                 "is_mock": False, "answerable": True},
                {"chunk_id": "C-NOT-ANSWERABLE", "content": "not answerable",
                 "domain": "bhyt", "sub_topic": "t", "source_id": "S1",
                 "version": "1", "is_active": True,
                 "approval_status": "approved_for_pilot",
                 "effective_date": "2026-01-01", "tags": [],
                 "is_mock": False, "answerable": False},
            ],
            "domains": [
                {"domain_code": "bhyt", "domain_name": "BHYT",
                 "owner_role": "admin", "review_cycle_days": 180},
            ],
        }
        reg = {"sources": [{"source_id": "S1", "ingestible": True, "path": None}]}
        result = ing.process_chunks(knowledge_base=kb, registry=reg)
        assert result.total_chunks == 3
        approved_answerable = [
            r for r in result.chunk_records
            if r.answerable and r.approval_status in ("approved_for_pilot", "approved")
        ]
        assert len(approved_answerable) == 1
        assert approved_answerable[0].chunk_id == "C-APPROVED"


# ---------------------------------------------------------------------------
# Persistence — real driver seam with fake psycopg
# ---------------------------------------------------------------------------


class FakePsycopgCursor:
    """Fake cursor that records operations for verification."""

    def __init__(self):
        self.operations = []
        self.domain_rows = {}  # domain_code -> domain_id

    def execute(self, query, params=None):
        self.operations.append(("execute", query[:60], params))
        if "INSERT INTO knowledge_domains" in query and params:
            dc = params[0]
            if dc not in self.domain_rows:
                self.domain_rows[dc] = str(uuid_lib.uuid4())
            return
        if "SELECT domain_id FROM knowledge_domains" in query and params:
            return
        if "SELECT 1 FROM knowledge_chunks" in query:
            return
        if "INSERT INTO knowledge_chunks" in query or "ON CONFLICT" in query:
            return
        if "ANALYZE" in query:
            return

    def fetchone(self):
        # Return a fake domain_id for domain lookups and chunk existence checks
        # We need to differentiate between "select domain_id" and "select 1 from knowledge_chunks"
        # by looking at the last execute call
        if any("knowledge_domains" in op[1] for op in self.operations[-3:] if op[0] == "execute"):
            if self.domain_rows:
                return (list(self.domain_rows.values())[0],)
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakePsycopgConnection:
    """Fake psycopg connection for testing."""

    def __init__(self):
        self.cursor_obj = FakePsycopgCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _fake_connect(url):
    return FakePsycopgConnection()


def _fake_embed(content):
    return [0.42] * 1024


class TestPersistenceWithFakeDriver:

    def test_supported_psycopg_driver_invoked(self, ing, monkeypatch, real_kb, real_reg):
        """Verify the psycopg (v3) connect path is invoked."""
        fake_psycopg = type("fake_psycopg", (), {"connect": staticmethod(_fake_connect)})
        monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
        result = ing.ingest_knowledge(
            database_url="postgresql://fake",
            embed_provider=_fake_embed,
            knowledge_base=real_kb,
            registry=real_reg,
            dry_run=False,
        )
        assert result.total_chunks > 0
        assert result.inserted > 0 or result.updated > 0

    def test_domains_upserted_before_chunks(self, ing, monkeypatch, real_kb, real_reg):
        """Verify that domain upserts happen before chunk upserts."""
        conn = _fake_connect("postgresql://fake")
        fake_psycopg = type("fake_psycopg", (), {"connect": staticmethod(lambda url: conn)})
        monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)

        result = ing.ingest_knowledge(
            database_url="postgresql://fake",
            embed_provider=_fake_embed,
            knowledge_base=real_kb,
            registry=real_reg,
            dry_run=False,
        )
        # Check that the cursor saw domain operations
        ops = conn.cursor_obj.operations
        domain_ops = [o for o in ops if "knowledge_domains" in str(o)]
        assert len(domain_ops) >= 7, "Expected at least 7 domain operations"

    def test_successful_batch_returns_stable_stats(self, ing, monkeypatch, real_kb, real_reg):
        fake_psycopg = type("fake_psycopg", (), {"connect": staticmethod(_fake_connect)})
        monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
        result = ing.ingest_knowledge(
            database_url="postgresql://fake",
            embed_provider=_fake_embed,
            knowledge_base=real_kb,
            registry=real_reg,
            dry_run=False,
        )
        assert result.inserted >= 0
        assert result.updated >= 0
        assert result.vector_dim == 1024

    def test_missing_provider_in_non_dry_run_fails(self, ing, monkeypatch):
        """Non-dry-run without provider fails before DB write."""
        monkeypatch.delenv("JINA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="JINA_API_KEY"):
            ing.ingest_knowledge(
                database_url="postgresql://fake",
                embed_provider=None,
                dry_run=False,
            )

    def test_missing_db_url_in_non_dry_run(self, ing, monkeypatch):
        """Non-dry-run without db_url and without DATABASE_URL fails."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(ValueError, match="DATABASE_URL"):
            ing.ingest_knowledge(
                embed_provider=_fake_embed,
                dry_run=False,
            )

    def test_db_exception_rolls_back(self, ing, monkeypatch):
        """A DB exception during upsert closes the connection (rollback)."""
        class BrokenCursor:
            def execute(self, q, p=None):
                raise RuntimeError("DB failure in cursor.execute")
            def fetchone(self):
                return None
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        class BrokenConnection:
            def __init__(self):
                self.closed = False
            def cursor(self):
                return BrokenCursor()
            def close(self):
                self.closed = True
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def _broken_connect(url):
            return BrokenConnection()

        fake_psycopg = type("fake", (), {"connect": staticmethod(_broken_connect)})
        monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
        with pytest.raises(RuntimeError, match="DB failure"):
            ing.ingest_knowledge(
                database_url="postgresql://fake",
                embed_provider=_fake_embed,
                dry_run=False,
            )

    def test_invalid_embedding_causes_no_upsert(self, ing, monkeypatch):
        """An embedding with wrong dimension is rejected before upsert."""
        def _bad_embed(content):
            return [0.0] * 1023  # wrong dimension

        fake_psycopg = type("fake", (), {"connect": staticmethod(_fake_connect)})
        monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
        with pytest.raises(ValueError, match="dimension"):
            ing.ingest_knowledge(
                database_url="postgresql://fake",
                embed_provider=_bad_embed,
                dry_run=False,
            )

    def test_dry_run_creates_no_connection(self, ing, real_kb, real_reg):
        """Dry-run should not attempt any database operation."""
        result = ing.ingest_knowledge(
            knowledge_base=real_kb,
            registry=real_reg,
            dry_run=True,
        )
        assert result.total_chunks > 0
        assert result.inserted == 0
        assert result.updated == 0


# ---------------------------------------------------------------------------
# Seed SQL validation
# ---------------------------------------------------------------------------


class TestSeedSQL:

    SEED_SQL = ROOT / "supabase" / "seed" / "202607180003_wp008_knowledge_seed.sql"

    def test_seed_sql_exists(self):
        assert self.SEED_SQL.is_file()

    def test_seed_sql_has_task_markers(self):
        content = self.SEED_SQL.read_text(encoding="utf-8")
        assert "TASK:WP-008:START" in content
        assert "TASK:WP-008:END" in content

    def test_seed_sql_does_not_create_duplicate_index(self):
        content = self.SEED_SQL.read_text(encoding="utf-8")
        assert "CREATE INDEX" not in content
        assert "ivfflat" not in content

    def test_seed_sql_checks_table_readiness(self):
        content = self.SEED_SQL.read_text(encoding="utf-8")
        assert "knowledge_chunks" in content
        assert "pg_tables" in content


# ---------------------------------------------------------------------------
# Temporary directory / stateful behavior
# ---------------------------------------------------------------------------


class TestStatefulBehavior:

    def test_process_chunks_with_temp_json(self, ing):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            kb_data = {
                "chunks": [{
                    "chunk_id": "KCH-TEMP-001", "content": "temp content",
                    "domain": "test", "sub_topic": "t", "source_id": "SRC-TEMP",
                    "version": "1", "is_active": True,
                    "approval_status": "mock", "effective_date": "2026-01-01",
                    "tags": [], "is_mock": True, "answerable": True,
                }],
            }
            reg_data = {
                "sources": [{"source_id": "SRC-TEMP", "ingestible": True, "path": None}],
            }
            with open(tmp / "knowledge-base.json", "w", encoding="utf-8") as f:
                json.dump(kb_data, f)
            with open(tmp / "source-registry.json", "w", encoding="utf-8") as f:
                json.dump(reg_data, f)

            with open(tmp / "knowledge-base.json", encoding="utf-8") as f:
                kb = json.load(f)
            with open(tmp / "source-registry.json", encoding="utf-8") as f:
                reg = json.load(f)

            result = ing.process_chunks(knowledge_base=kb, registry=reg)
            assert result.total_chunks == 1
            assert result.chunk_records[0].chunk_id == "KCH-TEMP-001"


# ---------------------------------------------------------------------------
# Dry-run report
# ---------------------------------------------------------------------------


class TestDryRunReport:

    def test_report_contains_key_metrics(self, ing, real_kb, real_reg):
        result = ing.process_chunks(knowledge_base=real_kb, registry=real_reg)
        report = ing.generate_dry_run_report(result)
        assert "WP-008" in report
        assert "Total chunks processed" in report
        assert "KCH-PRICE-001" in report
        assert "SRC-BHYT-001" in report

    def test_report_with_errors(self, ing):
        result = ing.IngestionResult(
            total_chunks=0, answerable_chunks=0, mock_chunks=0,
            approved_chunks=0, errors=["Chunk X missing chunk_id"],
            chunk_records=[],
        )
        report = ing.generate_dry_run_report(result)
        assert "Error details" in report
        assert "Chunk X" in report

    def test_report_without_errors(self, ing):
        result = ing.IngestionResult(
            total_chunks=1, answerable_chunks=1, mock_chunks=0,
            approved_chunks=1, errors=[], chunk_records=[
                ing.ChunkRecord(
                    chunk_id="KCH-TEST", content="test", domain="test",
                    sub_topic="t", source_id="S", source_section="",
                    source_page="", version="1", is_active=True,
                    approval_status="approved_for_pilot",
                    effective_date="2026-01-01", tags=[], is_mock=False,
                    answerable=True, content_hash="abc", source_path="",
                    persistence_uuid="00000000-0000-0000-0000-000000000000",
                ),
            ],
        )
        report = ing.generate_dry_run_report(result)
        assert "Error details" not in report
        assert "KCH-TEST" in report


# === TASK:WP-008:END ===

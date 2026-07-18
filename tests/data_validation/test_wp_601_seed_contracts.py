# === TASK:WP-601:START ===
"""WP-601-R1 seed and RAG corpus validation.

The tests validate MVP seed files and generated ingestion records without
network, database, provider, or AI calls. They specifically guard against
metadata/non-content files entering the RAG corpus and verify source path,
approval, and version consistency.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_MVP = ROOT / "data" / "mvp"
SEED_DIR = DATA_MVP / "seed"
MANIFEST_PATH = DATA_MVP / "manifest.json"
SOURCE_REGISTRY_PATH = SEED_DIR / "source-registry.json"
SCHEMA_MAPPING_PATH = SEED_DIR / "schema-mapping.json"
KNOWLEDGE_BASE_PATH = SEED_DIR / "knowledge-base.json"
NON_CONTENT_SUFFIXES = (".json", ".yaml", ".yml", ".sql", ".py", ".ts", ".tsx")
APPROVAL_STATUSES = {"approved_for_pilot", "mock", "pending_review", "rejected", "approved"}
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_wp_601_region_markers_present_on_seed_validation_suite():
    source = Path(__file__).read_text(encoding="utf-8")

    assert source.startswith("# === TASK:WP-601:START ===")
    assert source.rstrip().endswith("# === TASK:WP-601:END ===")


def test_seed_contract_files_exist_and_are_parseable_json():
    for path in (MANIFEST_PATH, SOURCE_REGISTRY_PATH, SCHEMA_MAPPING_PATH, KNOWLEDGE_BASE_PATH):
        assert path.is_file(), f"missing seed contract file: {path.relative_to(ROOT)}"
        payload = load_json(path)
        assert isinstance(payload, dict)
        assert payload, f"empty JSON object: {path.relative_to(ROOT)}"


def test_manifest_seed_order_resolves_to_existing_seed_files():
    manifest = load_json(MANIFEST_PATH)

    for filename in manifest["seed_order"]:
        assert (SEED_DIR / filename).is_file(), f"seed_order file not found: {filename}"


def test_source_registry_reconciles_manifest_and_knowledge_base_sources():
    manifest = load_json(MANIFEST_PATH)
    registry = load_json(SOURCE_REGISTRY_PATH)
    knowledge_base = load_json(KNOWLEDGE_BASE_PATH)

    registry_ids = {source["source_id"] for source in registry["sources"]}
    knowledge_ids = {source["source_id"] for source in knowledge_base["sources"]}
    approved_manifest_ids = set()
    for entry in manifest["approved_pilot_sources"]:
        approved_manifest_ids.update(entry.get("source_ids", [entry.get("source_id")]))

    assert registry["reconciliation"]["all_paths_valid"] is True
    assert registry["reconciliation"]["missing_files"] == []
    assert registry["reconciliation"]["legacy_paths_found"] == []
    assert registry["reconciliation"]["orphan_sources"] == []
    assert registry_ids == knowledge_ids
    assert approved_manifest_ids == {
        source["source_id"]
        for source in registry["sources"]
        if source["approval_status"] == "approved_for_pilot"
    }


def test_registry_sources_have_valid_paths_approval_and_versions():
    registry = load_json(SOURCE_REGISTRY_PATH)
    manifest = load_json(MANIFEST_PATH)
    valid_domains = set(manifest["canonical_knowledge_domains"])

    for source in registry["sources"]:
        assert source["domain_code"] in valid_domains
        assert source["approval_status"] in APPROVAL_STATUSES
        assert source["version"], f"source missing version: {source['source_id']}"
        assert DATE_PATTERN.match(source["effective_date"]), source
        if source["source_type"] == "document":
            assert source["path"], f"document source missing path: {source['source_id']}"
            assert (ROOT / source["path"]).is_file(), source["path"]
            assert str(source["path"]).startswith("docs/knowledge/")
            assert Path(source["path"]).suffix == ".md"
        if source["is_mock"]:
            assert source["approval_status"] == "mock"


def test_rag_corpus_excludes_metadata_and_non_content_paths():
    registry = load_json(SOURCE_REGISTRY_PATH)
    non_ingestible_paths = set(registry.get("non_ingestible_paths", []))

    for source in registry["sources"]:
        path = source.get("path")
        if path is None:
            continue
        assert path not in non_ingestible_paths
        assert not path.startswith("data/mvp/")
        assert not path.startswith("docs/spec-registry/")
        assert not path.startswith("docs/reference-packs/")
        assert Path(path).suffix not in NON_CONTENT_SUFFIXES
        assert Path(path).suffix == ".md"


def test_knowledge_chunks_match_registry_source_metadata():
    registry = load_json(SOURCE_REGISTRY_PATH)
    knowledge_base = load_json(KNOWLEDGE_BASE_PATH)
    source_lookup = {source["source_id"]: source for source in registry["sources"]}

    for chunk in knowledge_base["chunks"]:
        source = source_lookup[chunk["source_id"]]
        assert chunk["domain"] == source["domain_code"]
        assert chunk["version"] == source["version"]
        assert chunk["approval_status"] == source["approval_status"]
        assert chunk["effective_date"] == source["effective_date"]
        assert chunk["is_mock"] == source["is_mock"]
        assert chunk["is_active"] is True
        assert chunk["content"].strip()
        assert "raw_pii" not in chunk["content"].lower()


def test_schema_mapping_covers_all_manifest_domains_and_seed_contracts():
    manifest = load_json(MANIFEST_PATH)
    schema_mapping = load_json(SCHEMA_MAPPING_PATH)
    mapped_domains = {mapping["domain_code"] for mapping in schema_mapping["domain_mappings"]}

    assert mapped_domains == set(manifest["canonical_knowledge_domains"])
    assert schema_mapping["seed_order"] == manifest["seed_order"]
    assert schema_mapping["contract_references"]["KnowledgeChunkDTO"]["artifact"] == "INT-04"
    assert "content" in schema_mapping["contract_references"]["KnowledgeChunkDTO"]["fields"]


def test_ingestion_processing_uses_fake_free_dry_run_and_preserves_metadata():
    from apps.api.foundation.knowledge.ingestion.importer import process_chunks

    registry = load_json(SOURCE_REGISTRY_PATH)
    knowledge_base = load_json(KNOWLEDGE_BASE_PATH)
    result = process_chunks(knowledge_base=knowledge_base, registry=registry, dry_run=True)

    assert result.errors == []
    assert result.total_chunks >= len(knowledge_base["chunks"])
    assert result.answerable_chunks > 0
    assert result.inserted == 0
    assert result.updated == 0

    registry_sources = {source["source_id"]: source for source in registry["sources"]}
    for record in result.chunk_records:
        source = registry_sources[record.source_id]
        assert record.source_path == (source.get("path") or "")
        assert record.version == source["version"]
        assert record.approval_status == source["approval_status"]
        assert record.effective_date == source["effective_date"]
        assert record.persistence_uuid
        if record.source_path:
            assert record.source_path.startswith("docs/knowledge/")
            assert Path(record.source_path).suffix == ".md"


def test_bhyt_approved_sources_are_detected_as_answerable_after_markdown_split():
    from apps.api.foundation.knowledge.ingestion.importer import process_chunks

    result = process_chunks(
        knowledge_base=load_json(KNOWLEDGE_BASE_PATH),
        registry=load_json(SOURCE_REGISTRY_PATH),
        dry_run=True,
    )
    bhyt_records = [record for record in result.chunk_records if record.domain == "bhyt"]

    assert bhyt_records, "approved BHYT markdown sources should produce dry-run chunks"
    for record in bhyt_records:
        assert record.approval_status == "approved_for_pilot"
        assert record.version
        assert record.source_path.startswith("docs/knowledge/bhyt/")
        assert record.answerable is True
# === TASK:WP-601:END ===

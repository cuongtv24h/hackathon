# === TASK:WP-007:START ===
"""Contract test for WP-007 — Knowledge source registry and seed schema mapping.

Validates:
* source_registry.json structure and content reconciliation
* schema_mapping.json structure and canonical entity references
* Traceability to ARCH-02 (domain-model.md) and INT-04 (data-contracts.md)
* Edge cases: missing files, unknown approval status, empty BHYT chunks
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
DATA_MVP = ROOT / "data" / "mvp"
SEED_DIR = DATA_MVP / "seed"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def source_registry() -> dict:
    path = SEED_DIR / "source-registry.json"
    assert path.is_file(), f"Missing source registry: {path}"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def schema_mapping() -> dict:
    path = SEED_DIR / "schema-mapping.json"
    assert path.is_file(), f"Missing schema mapping: {path}"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def knowledge_base() -> dict:
    path = SEED_DIR / "knowledge-base.json"
    assert path.is_file(), f"Missing knowledge base: {path}"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def manifest() -> dict:
    path = DATA_MVP / "manifest.json"
    assert path.is_file(), f"Missing manifest: {path}"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Source registry structure
# ---------------------------------------------------------------------------


class TestSourceRegistryStructure:
    """Verify source-registry.json contract shape."""

    def test_required_top_level_keys(self, source_registry: dict):
        required = {"registry_id", "version", "created_at", "status",
                    "manifest_ref", "knowledge_base_ref", "sources",
                    "reconciliation", "domain_summary", "approval_summary"}
        assert required.issubset(source_registry.keys()), \
            f"Missing keys: {required - source_registry.keys()}"

    def test_registry_id_format(self, source_registry: dict):
        rid = source_registry["registry_id"]
        assert rid.startswith("SRC-REG-"), \
            f"registry_id should start with SRC-REG-, got {rid}"

    def test_reconciled_status(self, source_registry: dict):
        assert source_registry["status"] == "reconciled"

    def test_sources_count(self, source_registry: dict, knowledge_base: dict):
        kb_sources = knowledge_base.get("sources", [])
        assert source_registry["reconciliation"]["registry_sources_count"] == len(
            source_registry["sources"]
        )
        assert source_registry["reconciliation"]["knowledge_base_sources_count"] == len(
            kb_sources
        )


class TestSourceEntries:
    """Validate each source entry in the registry."""

    REQUIRED_SOURCE_KEYS = {
        "source_id", "title", "source_type", "path",
        "domain_code", "version", "approval_status",
        "effective_date", "is_mock", "ingestible",
    }

    def test_every_source_has_required_keys(self, source_registry: dict):
        for src in source_registry["sources"]:
            missing = self.REQUIRED_SOURCE_KEYS - src.keys()
            assert not missing, \
                f"Source {src['source_id']} missing keys: {missing}"

    def test_no_empty_source_id(self, source_registry: dict):
        for src in source_registry["sources"]:
            assert src["source_id"], f"Empty source_id found"

    def test_approval_status_valid_values(self, source_registry: dict):
        valid = {"approved_for_pilot", "mock", "pending_review", "rejected"}
        for src in source_registry["sources"]:
            assert src["approval_status"] in valid, \
                f"Source {src['source_id']} has invalid approval_status: {src['approval_status']}"

    def test_path_valid_or_none(self, source_registry: dict):
        for src in source_registry["sources"]:
            p = src.get("path")
            if p is not None:
                full = ROOT / p
                assert full.is_file() or src["source_type"] == "mock", \
                    f"Source {src['source_id']} path does not exist: {p}"

    def test_domain_code_in_manifest_list(self, source_registry: dict, manifest: dict):
        valid_domains = set(manifest.get("canonical_knowledge_domains", []))
        for src in source_registry["sources"]:
            assert src["domain_code"] in valid_domains, \
                f"Source {src['source_id']} domain_code '{src['domain_code']}' not in manifest list"


class TestSourceRegistryReconciliation:
    """Validate the reconciliation block."""

    def test_reconciliation_required_keys(self, source_registry: dict):
        required = {"manifest_sources_count", "knowledge_base_sources_count",
                    "registry_sources_count", "filesystem_files_count",
                    "all_paths_valid", "legacy_paths_found", "orphan_sources",
                    "missing_files"}
        rec = source_registry["reconciliation"]
        missing = required - rec.keys()
        assert not missing, f"Reconciliation missing: {missing}"

    def test_all_paths_valid_flag(self, source_registry: dict):
        assert source_registry["reconciliation"]["all_paths_valid"] is True

    def test_no_orphan_sources(self, source_registry: dict):
        assert len(source_registry["reconciliation"]["orphan_sources"]) == 0

    def test_no_legacy_paths(self, source_registry: dict):
        assert len(source_registry["reconciliation"]["legacy_paths_found"]) == 0

    def test_approval_summary_counts(self, source_registry: dict):
        summary = source_registry["approval_summary"]
        expected_total = (
            summary.get("approved_for_pilot", 0)
            + summary.get("mock", 0)
            + summary.get("pending_review", 0)
            + summary.get("rejected", 0)
        )
        assert expected_total == len(source_registry["sources"]), \
            "Approval summary counts do not match total sources"


# ---------------------------------------------------------------------------
# Schema mapping structure
# ---------------------------------------------------------------------------


class TestSchemaMappingStructure:
    """Verify schema-mapping.json contract shape."""

    def test_required_top_level_keys(self, schema_mapping: dict):
        required = {"mapping_id", "version", "created_at",
                    "manifest_ref", "source_registry_ref",
                    "domain_mappings", "canonical_entity_references",
                    "contract_references", "seed_order"}
        missing = required - schema_mapping.keys()
        assert not missing, f"Missing keys: {missing}"

    def test_mapping_id_format(self, schema_mapping: dict):
        mid = schema_mapping["mapping_id"]
        assert mid.startswith("SCHEMA-MAP-"), \
            f"mapping_id should start with SCHEMA-MAP-, got {mid}"

    def test_domain_mappings_domain_coverage(
        self, schema_mapping: dict, manifest: dict
    ):
        mapped_domains = {m["domain_code"] for m in schema_mapping["domain_mappings"]}
        manifest_domains = set(manifest.get("canonical_knowledge_domains", []))
        # All manifest domains should be mapped
        assert mapped_domains == manifest_domains, \
            f"Domain mismatch. Manifest: {manifest_domains}, Mapped: {mapped_domains}"

    def test_every_domain_mapping_required_keys(self, schema_mapping: dict):
        required = {"domain_code", "canonical_entity", "seed_file",
                    "schema_fields", "data_status"}
        for dm in schema_mapping["domain_mappings"]:
            missing = required - dm.keys()
            assert not missing, \
                f"Domain mapping {dm['domain_code']} missing: {missing}"


class TestSchemaMappingTraceability:
    """Traceability to ARCH-02 (domain-model) and INT-04 (data-contracts)."""

    def test_knowledge_chunk_entity_ref(self, schema_mapping: dict):
        refs = schema_mapping["canonical_entity_references"]
        assert "KnowledgeChunk" in refs
        kc = refs["KnowledgeChunk"]
        assert kc["artifact"] == "ARCH-02"
        assert "chunk_id" in kc["fields"]
        assert "content" in kc["fields"]
        assert "domain" in kc["fields"]

    def test_knowledge_domain_entity_ref(self, schema_mapping: dict):
        refs = schema_mapping["canonical_entity_references"]
        assert "KnowledgeDomain" in refs
        kd = refs["KnowledgeDomain"]
        assert kd["artifact"] == "ARCH-02"
        assert "domain_code" in kd["fields"]

    def test_knowledge_chunk_dto_ref(self, schema_mapping: dict):
        refs = schema_mapping["contract_references"]
        assert "KnowledgeChunkDTO" in refs
        dto = refs["KnowledgeChunkDTO"]
        assert dto["artifact"] == "INT-04"
        assert "content" in dto["fields"]

    def test_seed_order_matches_manifest(self, schema_mapping: dict, manifest: dict):
        assert schema_mapping["seed_order"] == manifest.get("seed_order", []), \
            "seed_order mismatch between schema mapping and manifest"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Error and edge-case tests."""

    def test_missing_registry_file_raises(self):
        fake_path = SEED_DIR / "nonexistent-registry.json"
        assert not fake_path.is_file()

    def test_missing_schema_file_raises(self):
        fake_path = SEED_DIR / "nonexistent-schema.json"
        assert not fake_path.is_file()

    def test_bhyt_domain_has_no_chunks_yet(self, source_registry: dict):
        """BHYT sources are approved_for_pilot but chunks are ingested later."""
        bhyt_sources = [
            s for s in source_registry["sources"]
            if s["domain_code"] == "bhyt"
        ]
        assert len(bhyt_sources) == 7
        for s in bhyt_sources:
            assert s["approval_status"] == "approved_for_pilot"
            if "chunk_count" in s:
                assert s["chunk_count"] == 0

    def test_all_bootstrap_bhyt_approved_for_pilot(
        self, source_registry: dict, manifest: dict
    ):
        """The seven BHYT documents plus domain documents = 9 approved_for_pilot."""
        approved_ids = set()
        for entry in manifest.get("approved_pilot_sources", []):
            sids = entry.get("source_ids", [entry.get("source_id")])
            approved_ids.update(sids)
        registry_approved = {
            s["source_id"] for s in source_registry["sources"]
            if s["approval_status"] == "approved_for_pilot"
        }
        assert approved_ids == registry_approved, \
            f"Approved source mismatch. Manifest: {approved_ids}, Registry: {registry_approved}"

    def test_mock_sources_have_mock_status(self, source_registry: dict):
        for src in source_registry["sources"]:
            if src["is_mock"]:
                assert src["approval_status"] == "mock"

    def test_non_ingestible_paths_not_in_sources(self, source_registry: dict):
        nip = set(source_registry.get("non_ingestible_paths", []))
        for src in source_registry["sources"]:
            p = src.get("path")
            if p:
                assert p not in nip, \
                    f"Source {src['source_id']} path {p} listed as non_ingestible"

    def test_mock_only_domains_not_approved(self, source_registry: dict, manifest: dict):
        mock_only = set(manifest.get("mock_only_domains", []))
        for src in source_registry["sources"]:
            if src["domain_code"] in mock_only:
                assert src["approval_status"] == "mock", \
                    f"Mock-only domain source {src['source_id']} has status {src['approval_status']}"


# ---------------------------------------------------------------------------
# Domain summary validation
# ---------------------------------------------------------------------------


class TestDomainSummary:
    """Validate the domain_summary block in the source registry."""

    def test_domain_summary_completeness(self, source_registry: dict):
        ds_codes = {d["domain_code"] for d in source_registry["domain_summary"]}
        expected_codes = {s["domain_code"] for s in source_registry["sources"]}
        assert ds_codes == expected_codes

    def test_domain_summary_counts(self, source_registry: dict):
        for ds in source_registry["domain_summary"]:
            dc = ds["domain_code"]
            expected_sources = sum(
                1 for s in source_registry["sources"] if s["domain_code"] == dc
            )
            assert ds["source_count"] == expected_sources, \
                f"Domain {dc} source_count mismatch"


# === TASK:WP-007:END ===
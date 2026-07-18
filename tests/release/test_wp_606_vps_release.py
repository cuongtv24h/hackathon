# === TASK:WP-606:START ===
"""WP-606 VPS release go/no-go evidence checks.

These tests verify release evidence across upstream QA work packages without
provider or network calls. The release gate remains static and deterministic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


RELEASE_GATE_PATH = Path("config/deployment/release_gate.yaml")
REQUIRED_UPSTREAM = ["WP-602", "WP-603", "WP-604", "WP-605"]
UPSTREAM_EVIDENCE_FILES = {
    "WP-602": Path("tests/integration/test_wp_602_information_assistance.py"),
    "WP-603": Path("tests/integration/test_wp_603_emergency_safety.py"),
    "WP-604": Path("tests/integration/test_wp_604_appointments.py"),
    "WP-605": Path("tests/integration/test_wp_605_admin_dashboard.py"),
}
FRONTEND_E2E_FILES = [
    Path("apps/chat-web/src/e2e/information-assistance.spec.ts"),
    Path("apps/chat-web/src/e2e/emergency-safety.spec.ts"),
    Path("apps/chat-web/src/e2e/appointments.spec.ts"),
]


def load_release_gate() -> dict[str, Any]:
    """Load deterministic WP-606 release criteria from YAML."""
    with RELEASE_GATE_PATH.open("r", encoding="utf-8") as release_gate_file:
        return yaml.safe_load(release_gate_file)


def test_release_gate_declares_all_required_upstream_evidence() -> None:
    gate = load_release_gate()
    upstream = gate["required_upstream_evidence"]

    assert [item["work_package"] for item in upstream] == REQUIRED_UPSTREAM
    assert all(
        item["status_required"] == "stable_or_approved_integration_evidence"
        for item in upstream
    )
    for evidence_path in UPSTREAM_EVIDENCE_FILES.values():
        assert evidence_path.exists(), f"missing upstream evidence file: {evidence_path}"


def test_upstream_evidence_files_use_fakes_or_no_network_contracts() -> None:
    for work_package, evidence_path in UPSTREAM_EVIDENCE_FILES.items():
        text = evidence_path.read_text(encoding="utf-8")
        assert f"TASK:{work_package}:START" in text
        assert f"TASK:{work_package}:END" in text
        assert any(token in text for token in ["Fake", "fake", "provider/network-free", "without provider"]), work_package


def test_frontend_e2e_release_inputs_cover_user_capability_flows() -> None:
    existing_e2e = [path.name for path in FRONTEND_E2E_FILES if path.exists()]

    assert "information-assistance.spec.ts" in existing_e2e
    assert "appointments.spec.ts" in existing_e2e
    assert load_release_gate()["go_no_go_policy"]["go_requires_frontend_e2e_coverage_for_wp_602_to_wp_604"] is True


def test_emergency_e2e_absence_is_explicit_no_go_until_evidence_exists() -> None:
    missing = [path for path in FRONTEND_E2E_FILES if not path.exists()]
    policy = load_release_gate()["go_no_go_policy"]

    if Path("apps/chat-web/src/e2e/emergency-safety.spec.ts").exists():
        assert missing == []
    else:
        assert Path("apps/chat-web/src/e2e/emergency-safety.spec.ts") in missing
        assert policy["go_requires_frontend_e2e_coverage_for_wp_602_to_wp_604"] is True
        assert policy["no_go_on_failed_release_gate_check"] is True


def test_vps_degradation_and_fallback_policy_match_architecture_contracts() -> None:
    fallback = load_release_gate()["fallback_controls"]

    assert fallback["critical_emergency_independent_of_internet_llm_database"] is True
    assert fallback["primary_llm_failure_behavior"] == "fallback_provider_chain"
    assert fallback["all_llm_failure_behavior"] == "static_hotline_message"
    assert fallback["supabase_or_kb_failure_behavior"] == "knowledge_fallback_to_hotline"
    assert fallback["total_internet_loss_behavior"] == "normal_chat_unavailable_critical_local_emergency_available"
    assert fallback["analytics_logger_failure_behavior"] == "async_retry_no_main_flow_blocking"


def test_go_no_go_policy_blocks_release_on_contract_or_secret_drift() -> None:
    policy = load_release_gate()["go_no_go_policy"]

    assert policy == {
        "go_requires_all_automated_commands_pass": True,
        "go_requires_no_committed_secrets": True,
        "go_requires_mock_or_placeholder_sign_off": True,
        "go_requires_approved_answer_sources_only": True,
        "go_requires_frontend_e2e_coverage_for_wp_602_to_wp_604": True,
        "go_requires_admin_dashboard_evidence_for_wp_605": True,
        "no_go_on_incomplete_required_runtime_boundary": True,
        "no_go_on_failed_release_gate_check": True,
    }
# === TASK:WP-606:END ===

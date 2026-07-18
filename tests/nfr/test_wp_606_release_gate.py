# === TASK:WP-606:START ===
"""WP-606 release gate NFR/security/performance checks.

The tests are deterministic and provider/network-free. They validate the static
release gate contract used for MVP Pilot go/no-go decisions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


RELEASE_GATE_PATH = Path("config/deployment/release_gate.yaml")
EXPECTED_COMMANDS = [
    "py -m pytest tests/nfr/test_wp_606_release_gate.py tests/release/test_wp_606_vps_release.py -q",
    "npm.cmd --prefix apps/chat-web run test -- --run",
    "npm.cmd --prefix apps/chat-web run test:e2e",
]


def load_release_gate() -> dict[str, Any]:
    """Load the WP-606 release gate configuration without network calls."""
    with RELEASE_GATE_PATH.open("r", encoding="utf-8") as release_gate_file:
        return yaml.safe_load(release_gate_file)


def test_release_gate_contains_required_marker_and_command_contract() -> None:
    raw = RELEASE_GATE_PATH.read_text(encoding="utf-8")
    gate = load_release_gate()

    assert "# === TASK:WP-606:START ===" in raw
    assert "# === TASK:WP-606:END ===" in raw
    assert gate["work_package"] == "WP-606"
    assert gate["required_automated_commands"] == EXPECTED_COMMANDS
    assert gate["go_no_go_policy"]["go_requires_all_automated_commands_pass"] is True


def test_pilot_nfr_targets_match_canonical_solution_constraints() -> None:
    targets = load_release_gate()["pilot_targets"]

    assert targets["time_to_first_token_ms"] <= 2000
    assert targets["critical_keyword_emergency_ms"] <= 100
    assert targets["llm_emergency_ms"] <= 3000
    assert targets["hallucination_outside_kb_percent"] == 0
    assert targets["availability_business_hours_percent"] >= 99.5
    assert targets["concurrent_sessions_min"] >= 100


def test_security_and_runtime_release_controls_are_fail_closed() -> None:
    gate = load_release_gate()
    security = gate["security_controls"]
    runtime = gate["runtime_controls"]

    assert security["tls_min_version"] == "1.2"
    assert security["browser_exposed_secrets_allowed"] is False
    assert security["source_committed_secrets_allowed"] is False
    assert security["api_key_browser_exposure_allowed"] is False
    assert security["pii_in_logs_allowed"] is False
    assert security["prompt_or_chain_of_thought_exposure_allowed"] is False
    assert security["auth_required_for_admin_history_analytics"] is True
    assert security["short_lived_anonymous_chat_session_required"] is True
    assert security["mfa_required_for_admin"] is True
    assert runtime["backend_runtime"] == "python_fastapi"
    assert runtime["backend_substantive_behavior_in_init_allowed"] is False
    assert runtime["python_files_in_frontend_allowed"] is False
    assert runtime["hyphenated_python_packages_allowed"] is False


def test_rate_limit_and_content_controls_are_pilot_safe() -> None:
    gate = load_release_gate()

    assert gate["rate_limits"] == {
        "messages_per_session_per_minute": 20,
        "messages_per_ip_per_minute": 60,
        "messages_per_session_total": 100,
        "max_message_characters": 4000,
        "appointment_create_per_session_per_minute": 5,
        "content_write_per_user_per_minute": 30,
        "analytics_read_per_user_per_minute": 60,
    }
    assert gate["content_controls"]["answerable_sources"] == [
        "approved_for_pilot",
        "workflow_approved_content",
    ]
    assert gate["content_controls"]["block_unapproved_content_answers"] is True
    assert gate["content_controls"]["block_knowledge_conflict_confident_answers"] is True
    assert gate["content_controls"]["require_traceable_citations"] is True


def test_missing_mock_or_placeholder_sign_off_remains_no_go_edge_case() -> None:
    gate = load_release_gate()
    mock_controls = gate["mock_and_demo_controls"]
    policy = gate["go_no_go_policy"]

    assert mock_controls["emergency_protocol_mock_status"] == "requires_sign_off_before_real_demo"
    assert mock_controls["placeholder_contact_status"] == "requires_sign_off_before_real_demo"
    assert mock_controls["real_patient_data_allowed"] is False
    assert policy["go_requires_mock_or_placeholder_sign_off"] is True
    assert policy["no_go_on_failed_release_gate_check"] is True
# === TASK:WP-606:END ===

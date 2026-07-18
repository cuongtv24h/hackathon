# === TASK:WP-601:START ===
"""WP-601-R1 contract validation for foundation DTO/error/runtime contracts.

This suite is intentionally deterministic and Python-only. It validates the
cross-cutting foundation contracts required before E2E without calling any
provider, network, database, or AI reasoning path.
"""

from __future__ import annotations

import inspect
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import get_args, get_origin

import pytest


ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = ROOT / "packages"
API_DIR = ROOT / "apps" / "api"

if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CONTRACT_MARKER = "# === TASK:WP-009:START ==="
FORBIDDEN_ERROR_EXPOSURE_TERMS = (
    "stack_trace",
    "traceback",
    "system_prompt",
    "prompt",
    "provider_secret",
    "raw_tool_payload",
    "raw_patient_data",
    "raw_pii",
)
FOUNDATION_MODULES = (
    "apps.api.foundation.session.service",
    "apps.api.foundation.configuration.service",
    "apps.api.foundation.feedback.service",
    "apps.api.foundation.knowledge.repository.service",
    "apps.api.foundation.knowledge.content.service",
    "apps.api.foundation.emergency.service",
    "apps.api.foundation.appointments.service",
    "apps.api.foundation.appointments.tools.service",
    "apps.api.foundation.analytics.service",
    "apps.api.logging.conversation.service",
    "apps.api.logging.audit.service",
)
AI_CALL_TERMS = (
    "openai",
    "anthropic",
    "jina",
    "llm_provider",
    "embedding_provider",
    "make_embedding_provider",
    "chat.completions",
    "/embeddings",
)


def test_wp_601_region_markers_present_on_contract_suite():
    source = Path(__file__).read_text(encoding="utf-8")

    assert source.startswith("# === TASK:WP-601:START ===")
    assert source.rstrip().endswith("# === TASK:WP-601:END ===")


def test_shared_contract_leaf_modules_keep_wp_009_markers():
    for relative in (
        "packages/contracts/dto.py",
        "packages/contracts/errors.py",
        "packages/contracts/runtime.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert CONTRACT_MARKER in text, f"missing WP-009 marker in {relative}"
        assert "# === TASK:WP-009:END ===" in text, f"missing WP-009 end marker in {relative}"


def test_capability_response_envelope_shape_matches_int04():
    from contracts import CapabilityResponseEnvelope

    assert is_dataclass(CapabilityResponseEnvelope)
    actual = [field.name for field in fields(CapabilityResponseEnvelope)]

    assert actual == [
        "outcome",
        "message",
        "citations",
        "suggested_actions",
        "conversation_state",
        "explainability",
        "appointment",
        "event_id",
    ]

    envelope = CapabilityResponseEnvelope(outcome="success", message="Xin chào")
    payload = envelope.to_dict()
    assert payload == {
        "outcome": "success",
        "message": "Xin chào",
        "citations": [],
        "suggested_actions": [],
    }


def test_client_and_configuration_dtos_keep_canonical_binding_values():
    from contracts import ChatConfigurationDTO, ClientContextDTO

    client_context = ClientContextDTO(actor_tag="anonymous", channel="web_widget").to_dict()
    chat_config = ChatConfigurationDTO().to_dict()

    assert client_context["locale"] == "vi-VN"
    assert client_context["timezone"] == "Asia/Bangkok"
    assert chat_config["max_message_length"] == 4000
    assert chat_config["max_messages_per_session"] == 100
    assert chat_config["messages_per_session_per_minute"] == 20
    assert chat_config["messages_per_ip_per_minute"] == 60
    assert chat_config["appointment_create_per_session_per_minute"] == 5
    assert chat_config["content_write_per_user_per_minute"] == 30
    assert chat_config["analytics_read_per_user_per_minute"] == 60
    assert chat_config["idle_timeout_seconds"] == 1800
    assert chat_config["max_session_duration_seconds"] == 86400


def test_unified_error_envelope_shape_and_no_sensitive_fields():
    from contracts import CATEGORY_TOOL, TOOL_TIMEOUT, make_error_envelope

    envelope = make_error_envelope(
        TOOL_TIMEOUT,
        "Dịch vụ tạm thời không phản hồi.",
        category=CATEGORY_TOOL,
        trace_id="trace-wp-601",
        retryable=True,
        retry_after_seconds=10,
        fallback="configured_channel_redirect",
    ).to_dict()

    assert set(envelope.keys()) == {"trace_id", "error"}
    assert set(envelope["error"].keys()) == {
        "code",
        "category",
        "message",
        "field_errors",
        "retryable",
        "retry_after_seconds",
        "fallback",
    }
    serialized_keys = " ".join(envelope["error"].keys()).lower()
    for forbidden in FORBIDDEN_ERROR_EXPOSURE_TERMS:
        assert forbidden not in serialized_keys


@pytest.mark.parametrize(
    ("category", "http_status"),
    [
        ("validation", 400),
        ("authentication", 401),
        ("authorization", 403),
        ("business", 422),
        ("not_found", 404),
        ("ai", 503),
        ("tool", 502),
        ("safety", 503),
        ("rate_limit", 429),
        ("system", 503),
    ],
)
def test_error_category_to_http_status_contract(category: str, http_status: int):
    from contracts.errors import CATEGORY_TO_HTTP_STATUS

    assert CATEGORY_TO_HTTP_STATUS[category] == http_status


def test_retry_and_fallback_policy_surface_is_provider_neutral():
    from contracts.errors import ErrorDetail

    retryable = ErrorDetail(
        code="SERVICE_UNAVAILABLE",
        category="system",
        message="Tạm thời gián đoạn.",
        retryable=True,
        retry_after_seconds=30,
        fallback="static_channel_message",
    ).to_dict()
    not_retryable = ErrorDetail(
        code="INVALID_REQUEST",
        category="validation",
        message="Yêu cầu không hợp lệ.",
        retryable=False,
    ).to_dict()

    assert retryable["retryable"] is True
    assert retryable["retry_after_seconds"] == 30
    assert retryable["fallback"] == "static_channel_message"
    assert not_retryable["retryable"] is False
    assert not_retryable["retry_after_seconds"] is None


def test_rbac_runtime_contract_keeps_int09_roles_and_permissions():
    from contracts import ALL_RBAC_ROLES, PERM_ANALYTICS_READ, PERM_AUDIT_READ, RBACConfig

    assert ALL_RBAC_ROLES == frozenset(
        {
            "anonymous_user",
            "content_admin",
            "domain_owner",
            "emergency_approver",
            "operations_analyst",
            "security_auditor",
            "system_service",
        }
    )
    rbac = RBACConfig()
    assert rbac.has_permission("operations_analyst", PERM_ANALYTICS_READ)
    assert rbac.has_permission("security_auditor", PERM_AUDIT_READ)
    assert not rbac.has_permission("anonymous_user", PERM_AUDIT_READ)


def test_foundation_leaf_modules_do_not_import_ai_provider_or_network_clients():
    for module_name in FOUNDATION_MODULES:
        module = __import__(module_name, fromlist=["*"])
        source_file = inspect.getsourcefile(module)
        assert source_file is not None
        source = Path(source_file).read_text(encoding="utf-8").lower()

        for term in AI_CALL_TERMS:
            assert term not in source, f"{module_name} contains AI/provider term {term!r}"
        assert "requests." not in source, f"{module_name} contains network requests usage"


def test_substantive_behavior_is_not_only_in_init_modules():
    for init_path in (API_DIR).rglob("__init__.py"):
        text = init_path.read_text(encoding="utf-8")
        non_comment_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert not any(line.startswith("def ") or line.startswith("class ") for line in non_comment_lines), (
            f"Substantive behavior found in package initializer: {init_path.relative_to(ROOT)}"
        )
# === TASK:WP-601:END ===

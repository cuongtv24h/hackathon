# === TASK:WP-009:START ===
"""Contract test for WP-009 — Shared DTO, error and runtime configuration contracts.

Validates:
* Package public surface matches the canonical contracts (INT-04, INT-07, INT-09)
* UnifiedErrorEnvelope shape and field semantics
* CapabilityResponseEnvelope, ClientContextDTO, ChannelConfigurationDTO, ChatConfigurationDTO shape
* RuntimeSettings, RateLimitSettings, RetentionSettings shape and binding values
* RBAC role and permission constants
* Error/edge case: invalid category, missing settings file
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = ROOT / "packages"
CONTRACTS_DIR = PACKAGES_DIR / "contracts"
CONFIG_RUNTIME_DIR = ROOT / "config" / "runtime"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def contracts_package():
    """Import the contracts package and return the module object."""
    if str(PACKAGES_DIR) not in sys.path:
        sys.path.insert(0, str(PACKAGES_DIR))
    import contracts  # type: ignore[import-not-found]

    return contracts


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


class TestPackagePublicSurface:
    """Verify the contracts package exposes all required symbols."""

    def test_exposes_unified_error_envelope(self, contracts_package):
        from contracts import UnifiedErrorEnvelope, ErrorDetail  # type: ignore[import-not-found]

        assert UnifiedErrorEnvelope is not None
        assert ErrorDetail is not None

    def test_exposes_capability_response_envelope(self, contracts_package):
        from contracts import CapabilityResponseEnvelope  # type: ignore[import-not-found]

        assert CapabilityResponseEnvelope is not None

    def test_exposes_client_context_dto(self, contracts_package):
        from contracts import ClientContextDTO  # type: ignore[import-not-found]

        assert ClientContextDTO is not None

    def test_exposes_channel_configuration_dto(self, contracts_package):
        from contracts import ChannelConfigurationDTO  # type: ignore[import-not-found]

        assert ChannelConfigurationDTO is not None

    def test_exposes_chat_configuration_dto(self, contracts_package):
        from contracts import ChatConfigurationDTO  # type: ignore[import-not-found]

        assert ChatConfigurationDTO is not None

    def test_exposes_runtime_settings(self, contracts_package):
        from contracts import RuntimeSettings, RateLimitSettings, RetentionSettings  # type: ignore[import-not-found]

        assert RuntimeSettings is not None
        assert RateLimitSettings is not None
        assert RetentionSettings is not None

    def test_exposes_rbac_config(self, contracts_package):
        from contracts import RBACConfig, ALL_RBAC_ROLES  # type: ignore[import-not-found]

        assert RBACConfig is not None
        assert ALL_RBAC_ROLES is not None


# ---------------------------------------------------------------------------
# UnifiedErrorEnvelope (INT-07)
# ---------------------------------------------------------------------------


class TestUnifiedErrorEnvelope:
    """Validate UnifiedErrorEnvelope contract shape."""

    def test_envelope_required_fields(self, contracts_package):
        from contracts import UnifiedErrorEnvelope, ErrorDetail  # type: ignore[import-not-found]

        detail = ErrorDetail(
            code="INVALID_REQUEST",
            category="validation",
            message="test message",
        )
        envelope = UnifiedErrorEnvelope(trace_id="trace-123", error=detail)
        d = envelope.to_dict()

        assert d["trace_id"] == "trace-123"
        assert d["error"]["code"] == "INVALID_REQUEST"
        assert d["error"]["category"] == "validation"
        assert d["error"]["message"] == "test message"

    def test_envelope_field_errors_is_dict(self, contracts_package):
        from contracts import ErrorDetail  # type: ignore[import-not-found]

        detail = ErrorDetail(
            code="FIELD_REQUIRED",
            category="validation",
            message="missing field",
            field_errors={"name": "required"},
        )
        d = detail.to_dict()

        assert d["field_errors"] == {"name": "required"}

    def test_envelope_retryable_and_retry_after(self, contracts_package):
        from contracts import ErrorDetail  # type: ignore[import-not-found]

        detail = ErrorDetail(
            code="SERVICE_UNAVAILABLE",
            category="system",
            message="temporary outage",
            retryable=True,
            retry_after_seconds=30,
        )
        d = detail.to_dict()

        assert d["retryable"] is True
        assert d["retry_after_seconds"] == 30

    def test_make_error_envelope_factory(self, contracts_package):
        from contracts import make_error_envelope  # type: ignore[import-not-found]

        envelope = make_error_envelope(
            "TOOL_TIMEOUT",
            "upstream timed out",
            category="tool",
            trace_id="t1",
            retryable=True,
            retry_after_seconds=10,
        )
        d = envelope.to_dict()

        assert d["trace_id"] == "t1"
        assert d["error"]["code"] == "TOOL_TIMEOUT"
        assert d["error"]["category"] == "tool"
        assert d["error"]["retryable"] is True

    def test_invalid_category_raises(self, contracts_package):
        from contracts import make_error_envelope  # type: ignore[import-not-found]

        with pytest.raises(ValueError):
            make_error_envelope(
                "BAD_CODE",
                "msg",
                category="not_a_category",
            )

    def test_canonical_error_codes_are_present(self, contracts_package):
        from contracts import (  # type: ignore[import-not-found]
            INVALID_REQUEST,
            RATE_LIMIT_EXCEEDED,
            SERVICE_UNAVAILABLE,
            TOOL_TIMEOUT,
        )

        assert INVALID_REQUEST == "INVALID_REQUEST"
        assert RATE_LIMIT_EXCEEDED == "RATE_LIMIT_EXCEEDED"
        assert SERVICE_UNAVAILABLE == "SERVICE_UNAVAILABLE"
        assert TOOL_TIMEOUT == "TOOL_TIMEOUT"


# ---------------------------------------------------------------------------
# CapabilityResponseEnvelope (INT-04)
# ---------------------------------------------------------------------------


class TestCapabilityResponseEnvelope:
    """Validate CapabilityResponseEnvelope contract shape."""

    def test_success_envelope_outcome_and_message(self, contracts_package):
        from contracts import CapabilityResponseEnvelope  # type: ignore[import-not-found]

        env = CapabilityResponseEnvelope(
            outcome="success",
            message="Here is the answer.",
        )
        d = env.to_dict()

        assert d["outcome"] == "success"
        assert d["message"] == "Here is the answer."
        assert d["citations"] == []
        assert d["suggested_actions"] == []

    def test_envelope_with_citations_and_actions(self, contracts_package):
        from contracts import CapabilityResponseEnvelope  # type: ignore[import-not-found]

        env = CapabilityResponseEnvelope(
            outcome="success",
            message="See below",
            citations=[{"source_id": "s1"}],
            suggested_actions=[{"type": "link", "label": "Learn more"}],
        )
        d = env.to_dict()

        assert d["citations"] == [{"source_id": "s1"}]
        assert d["suggested_actions"] == [{"type": "link", "label": "Learn more"}]

    def test_error_envelope_outcome(self, contracts_package):
        from contracts import CapabilityResponseEnvelope  # type: ignore[import-not-found]

        env = CapabilityResponseEnvelope(
            outcome="error",
            message="Something went wrong.",
        )
        d = env.to_dict()

        assert d["outcome"] == "error"

    def test_confirmation_required_envelope(self, contracts_package):
        from contracts import CapabilityResponseEnvelope  # type: ignore[import-not-found]

        env = CapabilityResponseEnvelope(
            outcome="confirmation_required",
            message="Please confirm the appointment.",
            suggested_actions=[{"type": "confirm"}],
        )
        d = env.to_dict()

        assert d["outcome"] == "confirmation_required"

    def test_make_success_envelope_factory(self, contracts_package):
        from contracts import make_success_envelope  # type: ignore[import-not-found]

        env = make_success_envelope(
            "Done.",
            citations=[{"source_id": "x"}],
            suggested_actions=[{"type": "link"}],
        )
        d = env.to_dict()

        assert d["outcome"] == "success"
        assert d["citations"] == [{"source_id": "x"}]

    def test_make_error_envelope_from_dto(self, contracts_package):
        from contracts import make_error_envelope_from_dto  # type: ignore[import-not-found]

        env = make_error_envelope_from_dto("Failed.")
        d = env.to_dict()

        assert d["outcome"] == "error"
        assert d["message"] == "Failed."


# ---------------------------------------------------------------------------
# ClientContextDTO (INT-04)
# ---------------------------------------------------------------------------


class TestClientContextDTO:
    """Validate ClientContextDTO contract shape."""

    def test_required_fields(self, contracts_package):
        from contracts import ClientContextDTO  # type: ignore[import-not-found]

        ctx = ClientContextDTO(
            actor_tag="patient-123",
            channel="web_widget",
        )
        d = ctx.to_dict()

        assert d["actor_tag"] == "patient-123"
        assert d["channel"] == "web_widget"
        assert d["locale"] == "vi-VN"
        assert d["timezone"] == "Asia/Bangkok"

    def test_channel_must_be_literal(self, contracts_package):
        from contracts import ClientContextDTO  # type: ignore[import-not-found]

        # Valid channels
        for ch in ("web_widget", "web_page"):
            ctx = ClientContextDTO(actor_tag="a", channel=ch)
            assert ctx.channel == ch


# ---------------------------------------------------------------------------
# ChannelConfigurationDTO (INT-04, INT-09)
# ---------------------------------------------------------------------------


class TestChannelConfigurationDTO:
    """Validate ChannelConfigurationDTO contract shape."""

    def test_required_and_optional_fields(self, contracts_package):
        from contracts import ChannelConfigurationDTO  # type: ignore[import-not-found]

        cfg = ChannelConfigurationDTO(
            channel="web_widget",
            enabled=True,
            base_url="https://example.com/widget",
            display_name="Chat Widget",
        )
        d = cfg.to_dict()

        assert d["channel"] == "web_widget"
        assert d["enabled"] is True
        assert d["base_url"] == "https://example.com/widget"
        assert d["display_name"] == "Chat Widget"

    def test_disabled_channel(self, contracts_package):
        from contracts import ChannelConfigurationDTO  # type: ignore[import-not-found]

        cfg = ChannelConfigurationDTO(channel="web_page", enabled=False)
        d = cfg.to_dict()

        assert d["enabled"] is False


# ---------------------------------------------------------------------------
# ChatConfigurationDTO (INT-04, INT-09)
# ---------------------------------------------------------------------------


class TestChatConfigurationDTO:
    """Validate ChatConfigurationDTO contract shape and binding values."""

    def test_default_binding_values_match_int09(self, contracts_package):
        from contracts import ChatConfigurationDTO  # type: ignore[import-not-found]

        cfg = ChatConfigurationDTO()
        d = cfg.to_dict()

        # INT-09 binding values
        assert d["max_message_length"] == 4000
        assert d["max_messages_per_session"] == 100
        assert d["messages_per_session_per_minute"] == 20
        assert d["messages_per_ip_per_minute"] == 60
        assert d["appointment_create_per_session_per_minute"] == 5
        assert d["content_write_per_user_per_minute"] == 30
        assert d["analytics_read_per_user_per_minute"] == 60
        assert d["idle_timeout_seconds"] == 1800  # 30 minutes
        assert d["max_session_duration_seconds"] == 86400  # 24 hours


# ---------------------------------------------------------------------------
# RuntimeSettings (INT-09)
# ---------------------------------------------------------------------------


class TestRuntimeSettings:
    """Validate RuntimeSettings, RetentionSettings and RateLimitSettings."""

    def test_retention_settings_binding_values(self, contracts_package):
        from contracts import RetentionSettings  # type: ignore[import-not-found]

        r = RetentionSettings()
        d = r.to_dict()

        # INT-09 binding values
        assert d["context_idle_seconds"] == 1800
        assert d["context_max_seconds"] == 86400
        assert d["conversation_anonymized_days"] == 90
        assert d["feedback_days"] == 180
        assert d["mock_appointment_days"] == 90
        assert d["emergency_audit_days"] == 365
        assert d["analytics_days"] == 365

    def test_rate_limit_settings_binding_values(self, contracts_package):
        from contracts import RateLimitSettings  # type: ignore[import-not-found]

        rl = RateLimitSettings()
        d = rl.to_dict()

        # INT-09 binding values
        assert d["messages_per_session_per_minute"] == 20
        assert d["messages_per_ip_per_minute"] == 60
        assert d["max_messages_per_session"] == 100
        assert d["max_message_length"] == 4000
        assert d["appointment_create_per_session_per_minute"] == 5
        assert d["content_write_per_user_per_minute"] == 30
        assert d["analytics_read_per_user_per_minute"] == 60

    def test_load_runtime_settings_reads_example_file(self, contracts_package):
        from contracts import load_runtime_settings  # type: ignore[import-not-found]

        example_path = CONFIG_RUNTIME_DIR / "settings.example.json"
        if not example_path.is_file():
            pytest.skip("settings.example.json not found")

        settings = load_runtime_settings(example_path)
        assert settings.app_env == "development"
        assert settings.retention.context_idle_seconds == 1800
        assert settings.rate_limits.max_message_length == 4000

    def test_load_runtime_settings_missing_file_raises(self, contracts_package):
        from contracts import load_runtime_settings  # type: ignore[import-not-found]

        missing = ROOT / "nonexistent_settings.json"
        with pytest.raises(FileNotFoundError):
            load_runtime_settings(missing)


# ---------------------------------------------------------------------------
# RBACConfig (INT-09)
# ---------------------------------------------------------------------------


class TestRBACConfig:
    """Validate RBAC role constants and permission checks."""

    def test_all_rbac_roles_constant(self, contracts_package):
        from contracts import ALL_RBAC_ROLES  # type: ignore[import-not-found]

        expected = {
            "anonymous_user",
            "content_admin",
            "domain_owner",
            "emergency_approver",
            "operations_analyst",
            "security_auditor",
            "system_service",
        }
        assert expected == ALL_RBAC_ROLES

    def test_default_role_permissions_anonymous_user(self, contracts_package):
        from contracts import DEFAULT_ROLE_PERMISSIONS, RBAC_ANONYMOUS_USER  # type: ignore[import-not-found]

        perms = DEFAULT_ROLE_PERMISSIONS.get(RBAC_ANONYMOUS_USER, frozenset())
        assert "knowledge:read" in perms
        assert "appointment:read" in perms
        assert "appointment:write" in perms
        assert "content:admin" not in perms

    def test_default_role_permissions_content_admin(self, contracts_package):
        from contracts import DEFAULT_ROLE_PERMISSIONS, RBAC_CONTENT_ADMIN  # type: ignore[import-not-found]

        perms = DEFAULT_ROLE_PERMISSIONS.get(RBAC_CONTENT_ADMIN, frozenset())
        assert "knowledge:read" in perms
        assert "knowledge:write" in perms
        assert "content:admin" in perms

    def test_rbac_config_has_permission(self, contracts_package):
        from contracts import RBACConfig, RBAC_ANONYMOUS_USER, PERM_KNOWLEDGE_READ  # type: ignore[import-not-found]

        config = RBACConfig()
        assert config.has_permission(RBAC_ANONYMOUS_USER, PERM_KNOWLEDGE_READ) is True
        assert config.has_permission(RBAC_ANONYMOUS_USER, "content:admin") is False

    def test_rbac_config_unknown_role_has_no_permissions(self, contracts_package):
        from contracts import RBACConfig  # type: ignore[import-not-found]

        config = RBACConfig()
        assert config.has_permission("nonexistent_role", "knowledge:read") is False


# ---------------------------------------------------------------------------
# Config files (INT-09)
# ---------------------------------------------------------------------------


class TestConfigRuntimeFiles:
    """Validate the example configuration files in config/runtime/."""

    def test_settings_example_json_exists_and_valid(self):
        path = CONFIG_RUNTIME_DIR / "settings.example.json"
        assert path.is_file(), "settings.example.json must exist"

        data = json.loads(path.read_text(encoding="utf-8"))
        assert "app_env" in data
        assert "retention" in data
        assert "rate_limits" in data
        assert data["retention"]["context_idle_seconds"] == 1800

    def test_rate_limits_example_json_exists_and_valid(self):
        path = CONFIG_RUNTIME_DIR / "rate-limits.example.json"
        assert path.is_file(), "rate-limits.example.json must exist"

        data = json.loads(path.read_text(encoding="utf-8"))
        assert "budgets" in data
        assert isinstance(data["budgets"], list)
        names = {b["name"] for b in data["budgets"]}
        assert "chat_messages_per_session_per_minute" in names

    def test_no_secrets_in_example_files(self):
        for name in ("settings.example.json", "rate-limits.example.json"):
            path = CONFIG_RUNTIME_DIR / name
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8").lower()
            forbidden = ["password", "secret", "api_key", "token", "bearer "]
            for token in forbidden:
                assert token not in text, f"forbidden token {token!r} in {name}"


# ---------------------------------------------------------------------------
# Region markers
# ---------------------------------------------------------------------------


class TestRegionMarkers:
    """Validate WP-009 region markers are present."""

    def test_errors_py_has_markers(self):
        path = CONTRACTS_DIR / "errors.py"
        text = path.read_text(encoding="utf-8")
        assert "# === TASK:WP-009:START ===" in text
        assert "# === TASK:WP-009:END ===" in text

    def test_dto_py_has_markers(self):
        path = CONTRACTS_DIR / "dto.py"
        text = path.read_text(encoding="utf-8")
        assert "# === TASK:WP-009:START ===" in text
        assert "# === TASK:WP-009:END ===" in text

    def test_runtime_py_has_markers(self):
        path = CONTRACTS_DIR / "runtime.py"
        text = path.read_text(encoding="utf-8")
        assert "# === TASK:WP-009:START ===" in text
        assert "# === TASK:WP-009:END ===" in text

    def test_init_py_has_markers(self):
        path = CONTRACTS_DIR / "__init__.py"
        text = path.read_text(encoding="utf-8")
        assert "# === TASK:WP-009:START ===" in text
        assert "# === TASK:WP-009:END ===" in text

    def test_test_file_has_markers(self):
        path = Path(__file__)
        text = path.read_text(encoding="utf-8")
        assert "# === TASK:WP-009:START ===" in text
        assert "# === TASK:WP-009:END ===" in text


# === TASK:WP-009:END ===

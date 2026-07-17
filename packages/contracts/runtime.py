# === TASK:WP-009:START ===
"""Runtime configuration and RBAC contract for the Hospital Assistant API.

This module provides the runtime configuration structures declared in
``docs/artifacts/interface/interface-guidelines.md`` (INT-09). The WP-009 pack
mandates the following contracts:

* ``RuntimeSettings`` — the structured runtime configuration loaded from
  ``config/runtime/settings.json``.
* ``RBACRole`` — the canonical role identifiers for the MVP pilot.
* ``RBACConfig`` — the role-to-permission mapping used by the Gateway layer.

The module does not introduce new configuration semantics — it only
formalises the contract from the source artifact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Literal, Mapping, Optional, Set


# ---------------------------------------------------------------------------
# RBAC roles (INT-09, Section "RBAC")
# ---------------------------------------------------------------------------

RBAC_ANONYMOUS_USER = "anonymous_user"
RBAC_CONTENT_ADMIN = "content_admin"
RBAC_DOMAIN_OWNER = "domain_owner"
RBAC_EMERGENCY_APPROVER = "emergency_approver"
RBAC_OPERATIONS_ANALYST = "operations_analyst"
RBAC_SECURITY_AUDITOR = "security_auditor"
RBAC_SYSTEM_SERVICE = "system_service"


ALL_RBAC_ROLES: FrozenSet[str] = frozenset(
    {
        RBAC_ANONYMOUS_USER,
        RBAC_CONTENT_ADMIN,
        RBAC_DOMAIN_OWNER,
        RBAC_EMERGENCY_APPROVER,
        RBAC_OPERATIONS_ANALYST,
        RBAC_SECURITY_AUDITOR,
        RBAC_SYSTEM_SERVICE,
    }
)


# Permission constants (derived from INT-09)
PERM_KNOWLEDGE_READ = "knowledge:read"
PERM_KNOWLEDGE_WRITE = "knowledge:write"
PERM_CONTENT_ADMIN = "content:admin"
PERM_EMERGENCY_CONFIG = "emergency:config"
PERM_APPOINTMENT_READ = "appointment:read"
PERM_APPOINTMENT_WRITE = "appointment:write"
PERM_ANALYTICS_READ = "analytics:read"
PERM_AUDIT_READ = "audit:read"
PERM_SESSION_MANAGE = "session:manage"


# Default role-to-permission mapping (INT-09)
DEFAULT_ROLE_PERMISSIONS: Mapping[str, FrozenSet[str]] = {
    RBAC_ANONYMOUS_USER: frozenset(
        {
            PERM_KNOWLEDGE_READ,
            PERM_APPOINTMENT_READ,
            PERM_APPOINTMENT_WRITE,
        }
    ),
    RBAC_CONTENT_ADMIN: frozenset(
        {
            PERM_KNOWLEDGE_READ,
            PERM_KNOWLEDGE_WRITE,
            PERM_CONTENT_ADMIN,
        }
    ),
    RBAC_DOMAIN_OWNER: frozenset(
        {
            PERM_KNOWLEDGE_READ,
            PERM_KNOWLEDGE_WRITE,
        }
    ),
    RBAC_EMERGENCY_APPROVER: frozenset(
        {
            PERM_EMERGENCY_CONFIG,
        }
    ),
    RBAC_OPERATIONS_ANALYST: frozenset(
        {
            PERM_ANALYTICS_READ,
        }
    ),
    RBAC_SECURITY_AUDITOR: frozenset(
        {
            PERM_AUDIT_READ,
        }
    ),
    RBAC_SYSTEM_SERVICE: frozenset(
        {
            PERM_SESSION_MANAGE,
            PERM_ANALYTICS_READ,
            PERM_AUDIT_READ,
        }
    ),
}


# ---------------------------------------------------------------------------
# Runtime settings (INT-09)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetentionSettings:
    """Retention periods declared in INT-09 (MVP Pilot binding values)."""

    context_idle_seconds: int = 1800  # 30 minutes
    context_max_seconds: int = 86400  # 24 hours
    conversation_anonymized_days: int = 90
    feedback_days: int = 180
    mock_appointment_days: int = 90
    emergency_audit_days: int = 365
    analytics_days: int = 365

    def to_dict(self) -> Dict[str, int]:
        return {
            "context_idle_seconds": self.context_idle_seconds,
            "context_max_seconds": self.context_max_seconds,
            "conversation_anonymized_days": self.conversation_anonymized_days,
            "feedback_days": self.feedback_days,
            "mock_appointment_days": self.mock_appointment_days,
            "emergency_audit_days": self.emergency_audit_days,
            "analytics_days": self.analytics_days,
        }


@dataclass(frozen=True)
class RateLimitSettings:
    """Rate-limit configuration declared in INT-09."""

    messages_per_session_per_minute: int = 20
    messages_per_ip_per_minute: int = 60
    max_messages_per_session: int = 100
    max_message_length: int = 4000
    appointment_create_per_session_per_minute: int = 5
    content_write_per_user_per_minute: int = 30
    analytics_read_per_user_per_minute: int = 60

    def to_dict(self) -> Dict[str, int]:
        return {
            "messages_per_session_per_minute": self.messages_per_session_per_minute,
            "messages_per_ip_per_minute": self.messages_per_ip_per_minute,
            "max_messages_per_session": self.max_messages_per_session,
            "max_message_length": self.max_message_length,
            "appointment_create_per_session_per_minute": self.appointment_create_per_session_per_minute,
            "content_write_per_user_per_minute": self.content_write_per_user_per_minute,
            "analytics_read_per_user_per_minute": self.analytics_read_per_user_per_minute,
        }


@dataclass(frozen=True)
class RuntimeSettings:
    """The structured runtime configuration loaded from ``config/runtime/settings.json``.

    The fields mirror the binding values declared in INT-09. The module is
    intentionally pure — it does not read from the filesystem itself. Use
    ``load_runtime_settings`` to read and validate the JSON file.
    """

    app_env: str
    retention: RetentionSettings
    rate_limits: RateLimitSettings
    channels: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_env": self.app_env,
            "retention": self.retention.to_dict(),
            "rate_limits": self.rate_limits.to_dict(),
            "channels": dict(self.channels),
            "metadata": dict(self.metadata),
        }


def load_runtime_settings(path: Path) -> RuntimeSettings:
    """Load and validate ``config/runtime/settings.json``."""

    if not path.is_file():
        raise FileNotFoundError(f"runtime settings file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    retention_raw = raw.get("retention", {})
    rate_limits_raw = raw.get("rate_limits", {})

    retention = RetentionSettings(
        context_idle_seconds=retention_raw.get("context_idle_seconds", 1800),
        context_max_seconds=retention_raw.get("context_max_seconds", 86400),
        conversation_anonymized_days=retention_raw.get("conversation_anonymized_days", 90),
        feedback_days=retention_raw.get("feedback_days", 180),
        mock_appointment_days=retention_raw.get("mock_appointment_days", 90),
        emergency_audit_days=retention_raw.get("emergency_audit_days", 365),
        analytics_days=retention_raw.get("analytics_days", 365),
    )

    rate_limits = RateLimitSettings(
        messages_per_session_per_minute=rate_limits_raw.get(
            "messages_per_session_per_minute", 20
        ),
        messages_per_ip_per_minute=rate_limits_raw.get("messages_per_ip_per_minute", 60),
        max_messages_per_session=rate_limits_raw.get("max_messages_per_session", 100),
        max_message_length=rate_limits_raw.get("max_message_length", 4000),
        appointment_create_per_session_per_minute=rate_limits_raw.get(
            "appointment_create_per_session_per_minute", 5
        ),
        content_write_per_user_per_minute=rate_limits_raw.get(
            "content_write_per_user_per_minute", 30
        ),
        analytics_read_per_user_per_minute=rate_limits_raw.get(
            "analytics_read_per_user_per_minute", 60
        ),
    )

    return RuntimeSettings(
        app_env=raw.get("app_env", "development"),
        retention=retention,
        rate_limits=rate_limits,
        channels=raw.get("channels", {}),
        metadata=raw.get("metadata", {}),
    )


# ---------------------------------------------------------------------------
# RBAC config (INT-09)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RBACConfig:
    """The RBAC configuration used by the Gateway layer.

    The config is a thin wrapper over ``DEFAULT_ROLE_PERMISSIONS``. It exists
    so tests can inject alternative role-to-permission mappings without
    modifying the global constant.
    """

    role_permissions: Mapping[str, FrozenSet[str]] = field(
        default_factory=lambda: dict(DEFAULT_ROLE_PERMISSIONS)
    )

    def has_permission(self, role: str, permission: str) -> bool:
        """Return ``True`` if ``role`` grants ``permission``."""

        if role not in self.role_permissions:
            return False
        return permission in self.role_permissions[role]

    def permissions_for_role(self, role: str) -> FrozenSet[str]:
        """Return the frozen set of permissions granted to ``role``."""

        return self.role_permissions.get(role, frozenset())


__all__ = [
    # RBAC roles
    "RBAC_ANONYMOUS_USER",
    "RBAC_CONTENT_ADMIN",
    "RBAC_DOMAIN_OWNER",
    "RBAC_EMERGENCY_APPROVER",
    "RBAC_OPERATIONS_ANALYST",
    "RBAC_SECURITY_AUDITOR",
    "RBAC_SYSTEM_SERVICE",
    "ALL_RBAC_ROLES",
    # Permissions
    "PERM_KNOWLEDGE_READ",
    "PERM_KNOWLEDGE_WRITE",
    "PERM_CONTENT_ADMIN",
    "PERM_EMERGENCY_CONFIG",
    "PERM_APPOINTMENT_READ",
    "PERM_APPOINTMENT_WRITE",
    "PERM_ANALYTICS_READ",
    "PERM_AUDIT_READ",
    "PERM_SESSION_MANAGE",
    "DEFAULT_ROLE_PERMISSIONS",
    # Settings
    "RetentionSettings",
    "RateLimitSettings",
    "RuntimeSettings",
    "load_runtime_settings",
    "RBACConfig",
]
# === TASK:WP-009:END ===

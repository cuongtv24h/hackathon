# === TASK:WP-101:START ===
"""Foundation configuration service (FND-CFG-01, FND-CFG-02).

This module implements the configuration foundation APIs declared in
``docs/artifacts/interface/foundation-api-contracts.md`` (INT-03). The two
operations are:

* ``FND-CFG-01 GetChannels`` — ``GET /v1/foundation/configuration/channels``
* ``FND-CFG-02 GetChatConfiguration`` — ``GET /v1/foundation/configuration/chat``

No AI reasoning is performed; the service returns deterministic configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping, Optional

from packages.contracts import (
    ChannelConfigurationDTO,
    ChatConfigurationDTO,
    UnifiedErrorEnvelope,
    make_error_envelope,
    CATEGORY_NOT_FOUND,
    CATEGORY_SYSTEM,
    CATEGORY_VALIDATION,
    CONTENT_NOT_FOUND,
    INVALID_REQUEST,
    INTERNAL_ERROR,
)


# ---------------------------------------------------------------------------
# Error helper - returns UnifiedErrorEnvelope directly (now inherits Exception)
# ---------------------------------------------------------------------------


def _service_error(
    code: str,
    message: str,
    *,
    category: str,
    field_errors: Optional[Dict[str, str]] = None,
    retryable: bool = False,
    retry_after_seconds: Optional[int] = None,
    fallback: Optional[str] = None,
) -> UnifiedErrorEnvelope:
    """Create a unified error envelope for service-layer errors (raised directly)."""
    return make_error_envelope(
        code=code,
        message=message,
        category=category,
        field_errors=field_errors,
        retryable=retryable,
        retry_after_seconds=retry_after_seconds,
        fallback=fallback,
    )


# ---------------------------------------------------------------------------
# Configuration Service
# ---------------------------------------------------------------------------


@dataclass
class ConfigurationService:
    """Foundation configuration service implementing FND-CFG-01/02."""

    # Channel configurations (can be loaded from runtime settings)
    _channels: Dict[str, ChannelConfigurationDTO] = field(default_factory=dict)
    # Chat configuration (can be loaded from runtime settings)
    _chat_config: Optional[ChatConfigurationDTO] = None

    def __post_init__(self) -> None:
        # Initialize with default channels if none provided
        # Default base URLs per INT-09 MVP binding values
        if not self._channels:
            self._channels = {
                "web_widget": ChannelConfigurationDTO(
                    channel="web_widget",
                    enabled=True,
                    base_url="https://hospital-assistant.example.com/widget",
                    display_name="Web Widget",
                ),
                "web_page": ChannelConfigurationDTO(
                    channel="web_page",
                    enabled=True,
                    base_url="https://hospital-assistant.example.com/chat",
                    display_name="Web Page",
                ),
            }

        # Initialize with default chat config if none provided
        if self._chat_config is None:
            self._chat_config = ChatConfigurationDTO()

    # -----------------------------------------------------------------------
    # FND-CFG-01 GetChannels
    # -----------------------------------------------------------------------
    def get_channels(self) -> List[ChannelConfigurationDTO]:
        """Return all channel configurations (FND-CFG-01)."""
        # Return enabled channels only, sorted by channel name for determinism
        enabled = [c for c in self._channels.values() if c.enabled]
        enabled.sort(key=lambda c: c.channel)
        return enabled

    def get_channel(self, channel_id: str) -> ChannelConfigurationDTO:
        """Return a specific channel configuration by ID."""
        if not channel_id or not channel_id.strip():
            raise _service_error(
                code=INVALID_REQUEST,
                message="channel_id is required",
                category=CATEGORY_VALIDATION,
                field_errors={"channel_id": "required"},
            )

        channel = self._channels.get(channel_id)
        if channel is None:
            raise _service_error(
                code=CONTENT_NOT_FOUND,
                message=f"channel '{channel_id}' not found",
                category=CATEGORY_NOT_FOUND,
            )

        if not channel.enabled:
            raise _service_error(
                code=CONTENT_NOT_FOUND,
                message=f"channel '{channel_id}' is disabled",
                category=CATEGORY_NOT_FOUND,
            )

        return channel

    # -----------------------------------------------------------------------
    # FND-CFG-02 GetChatConfiguration
    # -----------------------------------------------------------------------
    def get_chat_configuration(self) -> ChatConfigurationDTO:
        """Return chat configuration (FND-CFG-02)."""
        if self._chat_config is None:
            raise _service_error(
                code=INTERNAL_ERROR,
                message="chat configuration not initialized",
                category=CATEGORY_SYSTEM,
            )
        return self._chat_config

    # -----------------------------------------------------------------------
    # Configuration helpers (for testing and runtime config loading)
    # -----------------------------------------------------------------------
    def set_channels(
        self, channels: Mapping[str, ChannelConfigurationDTO]
    ) -> None:
        """Replace channel configurations (used for testing/config loading)."""
        self._channels = dict(channels)

    def set_chat_configuration(self, config: ChatConfigurationDTO) -> None:
        """Replace chat configuration (used for testing/config loading)."""
        self._chat_config = config

    def load_from_runtime_settings(
        self, runtime_settings: Mapping[str, Any]
    ) -> None:
        """Load configuration from runtime settings (INT-09)."""
        # Load channels
        channels_data = runtime_settings.get("channels", {})
        if isinstance(channels_data, dict):
            for channel_id, channel_data in channels_data.items():
                if isinstance(channel_data, dict):
                    self._channels[channel_id] = ChannelConfigurationDTO(
                        channel=channel_id,
                        enabled=channel_data.get("enabled", True),
                        base_url=channel_data.get("base_url"),
                        display_name=channel_data.get("display_name"),
                        metadata=channel_data.get("metadata", {}),
                    )

        # Load chat configuration
        chat_data = runtime_settings.get("chat", {})
        if isinstance(chat_data, dict):
            self._chat_config = ChatConfigurationDTO(
                max_message_length=chat_data.get("max_message_length", 4000),
                max_messages_per_session=chat_data.get(
                    "max_messages_per_session", 100
                ),
                messages_per_session_per_minute=chat_data.get(
                    "messages_per_session_per_minute", 20
                ),
                messages_per_ip_per_minute=chat_data.get(
                    "messages_per_ip_per_minute", 60
                ),
                appointment_create_per_session_per_minute=chat_data.get(
                    "appointment_create_per_session_per_minute", 5
                ),
                content_write_per_user_per_minute=chat_data.get(
                    "content_write_per_user_per_minute", 30
                ),
                analytics_read_per_user_per_minute=chat_data.get(
                    "analytics_read_per_user_per_minute", 60
                ),
                idle_timeout_seconds=chat_data.get("idle_timeout_seconds", 1800),
                max_session_duration_seconds=chat_data.get(
                    "max_session_duration_seconds", 86400
                ),
                metadata=chat_data.get("metadata", {}),
            )


__all__ = [
    "ConfigurationService",
]
# === TASK:WP-101:END ===
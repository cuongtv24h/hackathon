# === TASK:WP-009:START ===
"""Canonical DTO contracts for the Hospital Assistant API.

This module provides the shared data-transfer objects declared in
``docs/artifacts/interface/data-contracts.md`` (INT-04). The WP-009 pack
mandates the following contracts:

* ``CapabilityResponseEnvelope`` — the top-level wrapper for every capability
  response.
* ``ClientContextDTO`` — the client-provided context attached to requests.
* ``ChannelConfigurationDTO`` — channel-specific configuration (web_widget,
  web_page).
* ``ChatConfigurationDTO`` — feature flags and rate-limit configuration for
  the chat surface.

The fields are frozen; downstream code must not add, remove or rename fields.
The module does not introduce new DTO semantics — it only formalises the
contract from the source artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping, Optional, Union


# ---------------------------------------------------------------------------
# CapabilityResponseEnvelope (INT-04)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityResponseEnvelope:
    """The top-level envelope for every capability response.

    The envelope normalises the output shape across PC-01..04 so the Gateway
    layer can return a consistent response to clients. The ``outcome`` field
    uses the canonical success/error terminology.
    """

    outcome: Literal["success", "error", "confirmation_required"]
    message: str
    citations: List[Dict[str, Any]] = field(default_factory=list)
    suggested_actions: List[Dict[str, Any]] = field(default_factory=list)
    conversation_state: Optional[Dict[str, Any]] = None
    explainability: Optional[Dict[str, Any]] = None
    appointment: Optional[Dict[str, Any]] = None
    event_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "outcome": self.outcome,
            "message": self.message,
            "citations": list(self.citations),
            "suggested_actions": list(self.suggested_actions),
        }
        if self.conversation_state is not None:
            result["conversation_state"] = dict(self.conversation_state)
        if self.explainability is not None:
            result["explainability"] = dict(self.explainability)
        if self.appointment is not None:
            result["appointment"] = dict(self.appointment)
        if self.event_id is not None:
            result["event_id"] = self.event_id
        return result


# ---------------------------------------------------------------------------
# ClientContextDTO (INT-04)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClientContextDTO:
    """The client-provided context attached to capability requests.

    The context carries the actor tag used by RLS policies, the channel
    identifier, and optional locale/timezone hints. The Gateway layer
    validates and injects the context before dispatching to capability
    handlers.
    """

    actor_tag: str
    channel: Literal["web_widget", "web_page"]
    locale: str = "vi-VN"
    timezone: str = "Asia/Bangkok"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actor_tag": self.actor_tag,
            "channel": self.channel,
            "locale": self.locale,
            "timezone": self.timezone,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# ChannelConfigurationDTO (INT-04, INT-09)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChannelConfigurationDTO:
    """Channel-specific configuration for the two MVP channels.

    The binding values declared in INT-09 (MVP Pilot binding values) fix the
    channel set to ``web_widget`` and ``web_page``. The configuration controls
    whether the channel is enabled and provides the base URL for the widget
    iframe or standalone page.
    """

    channel: Literal["web_widget", "web_page"]
    enabled: bool = True
    base_url: Optional[str] = None
    display_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "channel": self.channel,
            "enabled": self.enabled,
        }
        if self.base_url is not None:
            result["base_url"] = self.base_url
        if self.display_name is not None:
            result["display_name"] = self.display_name
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


# ---------------------------------------------------------------------------
# ChatConfigurationDTO (INT-04, INT-09)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatConfigurationDTO:
    """Feature flags and rate-limit configuration for the chat surface.

    The binding values declared in INT-09 fix the MVP rate limits:

    * 20 messages/session/minute
    * 60/IP/minute
    * 100/session
    * 4000 characters max
    * appointment create: 5/session/minute
    * content write: 30/user/minute
    * analytics read: 60/user/minute

    The configuration DTO exposes these as structured fields so the Gateway
    layer can enforce them without hard-coding the values.
    """

    max_message_length: int = 4000
    max_messages_per_session: int = 100
    messages_per_session_per_minute: int = 20
    messages_per_ip_per_minute: int = 60
    appointment_create_per_session_per_minute: int = 5
    content_write_per_user_per_minute: int = 30
    analytics_read_per_user_per_minute: int = 60
    idle_timeout_seconds: int = 1800  # 30 minutes
    max_session_duration_seconds: int = 86400  # 24 hours
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_message_length": self.max_message_length,
            "max_messages_per_session": self.max_messages_per_session,
            "messages_per_session_per_minute": self.messages_per_session_per_minute,
            "messages_per_ip_per_minute": self.messages_per_ip_per_minute,
            "appointment_create_per_session_per_minute": self.appointment_create_per_session_per_minute,
            "content_write_per_user_per_minute": self.content_write_per_user_per_minute,
            "analytics_read_per_user_per_minute": self.analytics_read_per_user_per_minute,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "max_session_duration_seconds": self.max_session_duration_seconds,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Convenience factory functions
# ---------------------------------------------------------------------------


def make_success_envelope(
    message: str,
    *,
    citations: Optional[List[Dict[str, Any]]] = None,
    suggested_actions: Optional[List[Dict[str, Any]]] = None,
    conversation_state: Optional[Dict[str, Any]] = None,
    explainability: Optional[Dict[str, Any]] = None,
    appointment: Optional[Dict[str, Any]] = None,
) -> CapabilityResponseEnvelope:
    """Construct a success envelope with canonical shape."""
    return CapabilityResponseEnvelope(
        outcome="success",
        message=message,
        citations=list(citations or []),
        suggested_actions=list(suggested_actions or []),
        conversation_state=dict(conversation_state) if conversation_state else None,
        explainability=dict(explainability) if explainability else None,
        appointment=dict(appointment) if appointment else None,
    )


def make_error_envelope_from_dto(
    message: str,
    *,
    outcome: Literal["error"] = "error",
) -> CapabilityResponseEnvelope:
    """Construct an error envelope with canonical shape."""
    return CapabilityResponseEnvelope(
        outcome=outcome,
        message=message,
    )


def make_confirmation_required_envelope(
    message: str,
    *,
    suggested_actions: Optional[List[Dict[str, Any]]] = None,
    conversation_state: Optional[Dict[str, Any]] = None,
) -> CapabilityResponseEnvelope:
    """Construct a confirmation_required envelope with canonical shape."""
    return CapabilityResponseEnvelope(
        outcome="confirmation_required",
        message=message,
        suggested_actions=list(suggested_actions or []),
        conversation_state=dict(conversation_state) if conversation_state else None,
    )


__all__ = [
    "CapabilityResponseEnvelope",
    "ClientContextDTO",
    "ChannelConfigurationDTO",
    "ChatConfigurationDTO",
    "make_success_envelope",
    "make_error_envelope_from_dto",
    "make_confirmation_required_envelope",
]
# === TASK:WP-009:END ===

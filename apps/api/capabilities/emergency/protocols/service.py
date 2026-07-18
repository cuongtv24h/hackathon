# === TASK:WP-103:START ===
"""Emergency protocol loader service for the capability layer.

This module provides the protocol loading service used by the emergency
safety capability (PC-02). It wraps the foundation service and adds
capability-specific behavior such as protocol validation and fallback
handling.

The service is deterministic and never calls LLM or performs AI reasoning.
It ensures that the emergency protocol returned is clinically approved
or provides a fallback with appropriate warnings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import from foundation layer
from apps.api.foundation.emergency.service import (
    EmergencyFoundationService,
    EmergencyProtocolDTO,
)


# ---------------------------------------------------------------------------
# Protocol loader service
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProtocolLoadResult:
    """Result of loading an emergency protocol.

    Contains the protocol DTO and any warnings about approval status
    or fallback usage.
    """

    protocol: Optional[EmergencyProtocolDTO]
    warnings: List[str]
    used_fallback: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol": self.protocol.to_dict() if self.protocol else None,
            "warnings": list(self.warnings),
            "used_fallback": self.used_fallback,
        }


class EmergencyProtocolService:
    """Service for loading emergency protocols with validation.

    This service wraps the foundation emergency service and adds:
    - Protocol approval status validation
    - Fallback protocol when requested level is not found
    - Warning generation for mock/unapproved protocols

    The service ensures that emergency responses always have a protocol
    to return, even if it's a fallback.
    """

    # Fallback protocol used when no protocol is found
    FALLBACK_PROTOCOL = EmergencyProtocolDTO(
        protocol_id="ERP-FALLBACK-V1",
        level=1,
        version="1.0.0",
        response_text="Nếu bạn đang gặp tình huống nguy cấp, hãy gọi 115 hoặc đến Khoa Cấp cứu ngay lập tức.",
        channel_refs=["CH-EMERGENCY-115"],
        emergency_address_ref="Khoa Cấp cứu — Bệnh viện Tim Hà Nội",
        banner_level="caution",
        allowed_actions=["call_115", "go_to_emergency_department"],
        prohibited_content=["diagnosis", "severity_assessment", "medication_advice", "treatment_advice"],
        approval_status="fallback",
        is_mock=True,
        effective_date="2026-01-01",
    )

    def __init__(
        self,
        foundation_service: Optional[EmergencyFoundationService] = None,
        seed_path: Optional[Path] = None,
    ) -> None:
        """Initialize the protocol service.

        Args:
            foundation_service: The foundation service to use. If not provided,
                creates a new instance.
            seed_path: Path to the emergency seed file (passed to foundation
                service if creating a new instance).
        """
        if foundation_service is not None:
            self._foundation = foundation_service
        else:
            self._foundation = EmergencyFoundationService(seed_path)

    def load_protocol(self, level: int) -> ProtocolLoadResult:
        """Load an emergency protocol for the given level.

        This method implements the FND-EMG-01 contract with added
        validation and fallback behavior.

        Args:
            level: The emergency level (1 for caution, 2 for critical).

        Returns:
            ProtocolLoadResult containing the protocol, any warnings,
            and whether a fallback was used.
        """
        warnings: List[str] = []
        used_fallback = False

        # Validate level
        if level not in (1, 2):
            warnings.append(f"Invalid emergency level {level}; using fallback")
            return ProtocolLoadResult(
                protocol=self.FALLBACK_PROTOCOL,
                warnings=warnings,
                used_fallback=True,
            )

        # Try to load from foundation
        protocol = self._foundation.get_emergency_protocol(level)

        if protocol is None:
            warnings.append(f"No protocol found for level {level}; using fallback")
            used_fallback = True
            protocol = self.FALLBACK_PROTOCOL
        elif protocol.is_mock:
            warnings.append(
                "Using mock emergency protocol - not clinically approved"
            )
        elif protocol.approval_status != "approved":
            warnings.append(
                f"Protocol approval status is '{protocol.approval_status}'"
            )

        return ProtocolLoadResult(
            protocol=protocol,
            warnings=warnings,
            used_fallback=used_fallback,
        )

    def get_protocol_response_text(self, level: int) -> str:
        """Get the response text for an emergency protocol level.

        This is a convenience method for quick access to the response
        text without needing to handle the full result object.

        Args:
            level: The emergency level (1 for caution, 2 for critical).

        Returns:
            The response text for the protocol, or fallback text.
        """
        result = self.load_protocol(level)
        if result.protocol:
            return result.protocol.response_text
        return self.FALLBACK_PROTOCOL.response_text

    def validate_protocol_actions(
        self, level: int, action: str
    ) -> bool:
        """Validate that an action is allowed for the protocol.

        Args:
            level: The emergency level.
            action: The action to validate.

        Returns:
            True if the action is allowed, False otherwise.
        """
        result = self.load_protocol(level)
        if result.protocol is None:
            return False
        return action in result.protocol.allowed_actions

    def get_prohibited_content_types(self, level: int) -> List[str]:
        """Get the list of prohibited content types for a protocol.

        This is used by the guardrails layer to ensure that the
        AI response does not contain prohibited medical advice.

        Args:
            level: The emergency level.

        Returns:
            List of prohibited content types.
        """
        result = self.load_protocol(level)
        if result.protocol is None:
            return list(self.FALLBACK_PROTOCOL.prohibited_content)
        return list(result.protocol.prohibited_content)


# Singleton instance for convenience
_default_service: Optional[EmergencyProtocolService] = None


def get_emergency_protocol_service() -> EmergencyProtocolService:
    """Get the default emergency protocol service instance."""
    global _default_service
    if _default_service is None:
        _default_service = EmergencyProtocolService()
    return _default_service


__all__ = [
    "ProtocolLoadResult",
    "EmergencyProtocolService",
    "get_emergency_protocol_service",
]
# === TASK:WP-103:END ===

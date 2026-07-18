# === TASK:WP-103:START ===
"""Emergency foundation service for keyword set and event operations.

This module implements the emergency foundation contracts declared in
``docs/artifacts/interface/foundation-api-contracts.md`` (INT-03):

* FND-EMG-01 GetEmergencyProtocol — load protocol by level from seed data.
* FND-EMG-02 GetEmergencyKeywordSet — load keyword set for prefilter.
* FND-EMG-03 CreateEmergencyEvent — record emergency event for audit.

The module is deterministic and never calls LLM or performs AI reasoning.
It loads data from the mock seed file and records events to the database.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


# ---------------------------------------------------------------------------
# DTOs for Emergency (INT-04)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmergencyKeywordDTO:
    """A single emergency keyword rule from the seed data."""

    rule_id: str
    level: int
    category: str
    phrases: List[str]
    normalized_phrases: List[str]
    protocol_id: str
    is_mock: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "level": self.level,
            "category": self.category,
            "phrases": list(self.phrases),
            "normalized_phrases": list(self.normalized_phrases),
            "protocol_id": self.protocol_id,
            "is_mock": self.is_mock,
        }


@dataclass(frozen=True)
class EmergencyKeywordSetDTO:
    """Keyword set for emergency prefilter (INT-04)."""

    critical_keywords: List[EmergencyKeywordDTO]
    caution_keywords: List[EmergencyKeywordDTO]
    approval_status: str
    effective_date: str
    version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "critical_keywords": [k.to_dict() for k in self.critical_keywords],
            "caution_keywords": [k.to_dict() for k in self.caution_keywords],
            "approval_status": self.approval_status,
            "effective_date": self.effective_date,
            "version": self.version,
        }


@dataclass(frozen=True)
class EmergencyProtocolDTO:
    """Emergency protocol loaded from seed data (INT-04)."""

    protocol_id: str
    level: int
    version: str
    response_text: str
    channel_refs: List[str]
    emergency_address_ref: str
    banner_level: str
    allowed_actions: List[str]
    prohibited_content: List[str]
    approval_status: str
    is_mock: bool
    effective_date: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "level": self.level,
            "version": self.version,
            "response_text": self.response_text,
            "channel_refs": list(self.channel_refs),
            "emergency_address_ref": self.emergency_address_ref,
            "banner_level": self.banner_level,
            "allowed_actions": list(self.allowed_actions),
            "prohibited_content": list(self.prohibited_content),
            "approval_status": self.approval_status,
            "is_mock": self.is_mock,
            "effective_date": self.effective_date,
        }


@dataclass(frozen=True)
class EmergencyEventCreateRequest:
    """Request to create an emergency event (INT-04)."""

    session_id: str
    level: int
    matched_keywords: List[str]
    protocol_id: str
    user_message: str
    trace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "session_id": self.session_id,
            "level": self.level,
            "matched_keywords": list(self.matched_keywords),
            "protocol_id": self.protocol_id,
            "user_message": self.user_message,
        }
        if self.trace_id is not None:
            result["trace_id"] = self.trace_id
        return result


@dataclass(frozen=True)
class EmergencyEventReceiptDTO:
    """Receipt for a created emergency event (INT-04)."""

    event_id: str
    created_at: str
    level: int
    protocol_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "created_at": self.created_at,
            "level": self.level,
            "protocol_id": self.protocol_id,
        }


# ---------------------------------------------------------------------------
# Service implementation
# ---------------------------------------------------------------------------


class EmergencyFoundationService:
    """Foundation service for emergency keyword and event operations.

    This service implements the emergency foundation contracts without
    any AI or LLM calls. It loads mock data from the seed file and
    records emergency events to an in-memory store (to be replaced by
    database persistence in a future work package).
    """

    def __init__(self, seed_path: Optional[Path] = None) -> None:
        """Initialize the service with the path to the emergency seed file.

        Args:
            seed_path: Path to the emergency.json seed file. If not provided,
                uses the default MVP seed path.
        """
        if seed_path is None:
            # Default to MVP seed path relative to project root
            seed_path = Path("data/mvp/seed/emergency.json")
        self._seed_path = seed_path
        self._seed_data: Optional[Dict[str, Any]] = None
        self._events: List[Dict[str, Any]] = []

    def _load_seed_data(self) -> Dict[str, Any]:
        """Load and cache the seed data from the JSON file."""
        if self._seed_data is not None:
            return self._seed_data

        if not self._seed_path.is_file():
            raise FileNotFoundError(
                f"Emergency seed file not found: {self._seed_path}"
            )

        raw = json.loads(self._seed_path.read_text(encoding="utf-8"))
        self._seed_data = raw
        return self._seed_data

    def get_emergency_keyword_set(self) -> EmergencyKeywordSetDTO:
        """FND-EMG-02: Get the emergency keyword set for prefilter.

        Returns the effective keyword set containing both critical (Level 2)
        and caution (Level 1) keywords from the approved seed data.

        Returns:
            EmergencyKeywordSetDTO with all active keywords.

        Raises:
            FileNotFoundError: If the seed file is not found.
            ValueError: If the seed data is malformed.
        """
        data = self._load_seed_data()

        dataset = data.get("dataset", {})
        keyword_sets_raw = data.get("keyword_sets", [])

        critical_keywords: List[EmergencyKeywordDTO] = []
        caution_keywords: List[EmergencyKeywordDTO] = []

        for kw_raw in keyword_sets_raw:
            # Skip non-mock keywords in mock mode
            if not kw_raw.get("is_mock", True):
                continue

            kw_dto = EmergencyKeywordDTO(
                rule_id=kw_raw.get("rule_id", ""),
                level=kw_raw.get("level", 1),
                category=kw_raw.get("category", ""),
                phrases=list(kw_raw.get("phrases", [])),
                normalized_phrases=list(kw_raw.get("normalized_phrases", [])),
                protocol_id=kw_raw.get("protocol_id", ""),
                is_mock=kw_raw.get("is_mock", True),
            )

            if kw_dto.level == 2:
                critical_keywords.append(kw_dto)
            else:
                caution_keywords.append(kw_dto)

        return EmergencyKeywordSetDTO(
            critical_keywords=critical_keywords,
            caution_keywords=caution_keywords,
            approval_status=dataset.get("clinical_approval_status", "not_clinically_approved"),
            effective_date=dataset.get("effective_date", ""),
            version=dataset.get("version", "1.0.0"),
        )

    def get_emergency_protocol(self, level: int) -> Optional[EmergencyProtocolDTO]:
        """FND-EMG-01: Get the emergency protocol for a given level.

        Returns the effective protocol for the specified emergency level.
        Level 2 is critical emergency, Level 1 is caution.

        Args:
            level: The emergency level (1 or 2).

        Returns:
            EmergencyProtocolDTO if found, None otherwise.

        Raises:
            FileNotFoundError: If the seed file is not found.
        """
        data = self._load_seed_data()

        protocols_raw = data.get("protocols", [])

        for proto_raw in protocols_raw:
            if proto_raw.get("level") == level:
                return EmergencyProtocolDTO(
                    protocol_id=proto_raw.get("protocol_id", ""),
                    level=proto_raw.get("level", 1),
                    version=proto_raw.get("version", "1.0.0"),
                    response_text=proto_raw.get("response_text", ""),
                    channel_refs=list(proto_raw.get("channel_refs", [])),
                    emergency_address_ref=proto_raw.get("emergency_address_ref", ""),
                    banner_level=proto_raw.get("banner_level", "caution"),
                    allowed_actions=list(proto_raw.get("allowed_actions", [])),
                    prohibited_content=list(proto_raw.get("prohibited_content", [])),
                    approval_status=proto_raw.get("approval_status", "mock_not_clinically_approved"),
                    is_mock=proto_raw.get("is_mock", True),
                    effective_date=proto_raw.get("effective_date", ""),
                )

        return None

    def create_emergency_event(
        self, request: EmergencyEventCreateRequest
    ) -> EmergencyEventReceiptDTO:
        """FND-EMG-03: Create an emergency event for audit.

        Records an emergency event when a user message triggers emergency
        protocol. The event is stored for audit and compliance purposes.

        Args:
            request: The emergency event creation request.

        Returns:
            EmergencyEventReceiptDTO with the event ID and timestamp.
        """
        event_id = f"EMG-{uuid.uuid4().hex[:12].upper()}"
        created_at = datetime.now(timezone.utc).isoformat()

        event_record = {
            "event_id": event_id,
            "session_id": request.session_id,
            "level": request.level,
            "matched_keywords": list(request.matched_keywords),
            "protocol_id": request.protocol_id,
            "user_message": request.user_message,
            "trace_id": request.trace_id,
            "created_at": created_at,
        }

        self._events.append(event_record)

        return EmergencyEventReceiptDTO(
            event_id=event_id,
            created_at=created_at,
            level=request.level,
            protocol_id=request.protocol_id,
        )

    def get_events_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all emergency events for a session (for testing/audit)."""
        return [
            dict(e) for e in self._events if e.get("session_id") == session_id
        ]

    def clear_events(self) -> None:
        """Clear all stored events (for testing only)."""
        self._events.clear()


# Singleton instance for convenience
_default_service: Optional[EmergencyFoundationService] = None


def get_emergency_foundation_service() -> EmergencyFoundationService:
    """Get the default emergency foundation service instance."""
    global _default_service
    if _default_service is None:
        _default_service = EmergencyFoundationService()
    return _default_service


__all__ = [
    "EmergencyKeywordDTO",
    "EmergencyKeywordSetDTO",
    "EmergencyProtocolDTO",
    "EmergencyEventCreateRequest",
    "EmergencyEventReceiptDTO",
    "EmergencyFoundationService",
    "get_emergency_foundation_service",
]
# === TASK:WP-103:END ===

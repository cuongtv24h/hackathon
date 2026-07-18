# === TASK:WP-202:START ===
"""Emergency prefilter tool for WP-202.

This module implements the emergency prefilter tool (PC-02) that performs
keyword-based prefiltering of user messages to detect emergency situations
before LLM processing. It uses the emergency keyword set from the foundation
layer (FND-EMG-02) and returns a structured result indicating the emergency
level, matched keywords, and the protocol to use.

The tool is deterministic and never calls LLM or performs AI reasoning.
It only performs keyword matching against the approved emergency keyword set.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from apps.api.foundation.emergency.service import (
    EmergencyFoundationService,
    EmergencyEventCreateRequest,
    EmergencyEventReceiptDTO,
    EmergencyKeywordDTO,
    EmergencyKeywordSetDTO,
    get_emergency_foundation_service,
)


# ---------------------------------------------------------------------------
# DTOs for Emergency Prefilter Tool (INT-06)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrefilterRequest:
    """Request for emergency prefilter tool.

    Attributes:
        user_message: The user's message to check for emergency keywords.
        session_id: Session identifier for audit trail.
        trace_id: Optional trace ID for distributed tracing.
    """

    user_message: str
    session_id: str
    trace_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.user_message or not self.user_message.strip():
            raise ValueError("user_message must be non-empty")
        if not self.session_id or not self.session_id.strip():
            raise ValueError("session_id must be non-empty")


@dataclass(frozen=True)
class MatchedKeyword:
    """A matched emergency keyword with its metadata."""

    rule_id: str
    level: int
    category: str
    matched_phrase: str
    protocol_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "level": self.level,
            "category": self.category,
            "matched_phrase": self.matched_phrase,
            "protocol_id": self.protocol_id,
        }


@dataclass(frozen=True)
class PrefilterResult:
    """Result of emergency prefilter check.

    Attributes:
        is_emergency: True if any emergency keyword matched.
        level: The highest emergency level matched (1=caution, 2=critical).
        matched_keywords: List of matched keywords with metadata.
        protocol_id: The protocol ID to use for the highest level matched.
        metadata: Additional metadata including elapsed time.
    """

    is_emergency: bool
    level: int
    matched_keywords: List[MatchedKeyword]
    protocol_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    event_receipt: Optional[EmergencyEventReceiptDTO] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_emergency": self.is_emergency,
            "level": self.level,
            "matched_keywords": [k.to_dict() for k in self.matched_keywords],
            "protocol_id": self.protocol_id,
            "metadata": dict(self.metadata),
            "event_receipt": (
                self.event_receipt.to_dict() if self.event_receipt else None
            ),
        }


# ---------------------------------------------------------------------------
# Emergency Prefilter Tool
# ---------------------------------------------------------------------------


class EmergencyPrefilterTool:
    """Emergency prefilter tool for keyword-based emergency detection.

    This tool implements the PC-02 emergency prefilter contract. It loads
    the emergency keyword set from the foundation service (FND-EMG-02) and
    performs deterministic keyword matching against user messages.

    The tool is deterministic and never calls LLM or performs AI reasoning.
    It only performs keyword matching against the approved emergency keyword set.

    Attributes:
        _foundation: The emergency foundation service for loading keywords.
        _keyword_set: Cached keyword set from foundation.
        _timeout_ms: Timeout for prefilter operation in milliseconds.
    """

    # Default timeout per INT-06 contract
    DEFAULT_TIMEOUT_MS = 100

    def __init__(
        self,
        foundation_service: Optional[EmergencyFoundationService] = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        """Initialize the emergency prefilter tool.

        Args:
            foundation_service: The emergency foundation service to use.
                If not provided, uses the default singleton.
            timeout_ms: Timeout for prefilter operation in milliseconds.
        """
        self._foundation = foundation_service or get_emergency_foundation_service()
        self._keyword_set: Optional[EmergencyKeywordSetDTO] = None
        self._timeout_ms = timeout_ms

    def _load_keyword_set(self) -> EmergencyKeywordSetDTO:
        """Load and cache the keyword set from foundation service."""
        if self._keyword_set is None:
            self._keyword_set = self._foundation.get_emergency_keyword_set()
        return self._keyword_set

    def _normalize_text(self, text: str) -> str:
        """Normalize text for keyword matching.

        Normalization includes:
        - Lowercase
        - Strip whitespace
        - Remove extra spaces
        - Remove common punctuation that might interfere with matching
        - Remove Vietnamese diacritics (convert to ASCII equivalents)
        """
        import re
        import unicodedata

        # Lowercase and strip
        normalized = text.lower().strip()
        # Replace multiple spaces with single space
        normalized = re.sub(r"\s+", " ", normalized)
        # Remove punctuation that might interfere with phrase matching
        # Keep alphanumeric and spaces
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        # Normalize spaces again
        normalized = re.sub(r"\s+", " ", normalized).strip()
        # Remove Vietnamese diacritics (convert to ASCII equivalents)
        # Use NFKD for compatibility decomposition
        normalized = unicodedata.normalize("NFKD", normalized)
        normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        # Handle Vietnamese "đ" (U+0111) which doesn't decompose with NFKD
        normalized = normalized.replace("đ", "d")
        # Normalize spaces one more time
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _match_keywords(
        self, normalized_message: str, keywords: List[EmergencyKeywordDTO]
    ) -> List[MatchedKeyword]:
        """Match keywords against normalized message.

        Args:
            normalized_message: The normalized user message.
            keywords: List of emergency keywords to match against.

        Returns:
            List of matched keywords with metadata.
        """
        matched: List[MatchedKeyword] = []

        for keyword in keywords:
            # Check both original phrases and normalized phrases
            for phrase in keyword.phrases:
                normalized_phrase = self._normalize_text(phrase)
                if normalized_phrase and normalized_phrase in normalized_message:
                    matched.append(
                        MatchedKeyword(
                            rule_id=keyword.rule_id,
                            level=keyword.level,
                            category=keyword.category,
                            matched_phrase=phrase,
                            protocol_id=keyword.protocol_id,
                        )
                    )
                    break  # Only need one match per keyword rule

            # Also check normalized phrases if no match yet
            if not any(m.rule_id == keyword.rule_id for m in matched):
                for norm_phrase in keyword.normalized_phrases:
                    if norm_phrase and norm_phrase in normalized_message:
                        matched.append(
                            MatchedKeyword(
                                rule_id=keyword.rule_id,
                                level=keyword.level,
                                category=keyword.category,
                                matched_phrase=norm_phrase,
                                protocol_id=keyword.protocol_id,
                            )
                        )
                        break

        return matched

    def prefilter(self, request: PrefilterRequest) -> PrefilterResult:
        """Run emergency prefilter on user message.

        This is the main entry point for the PC-02 emergency prefilter tool.
        It performs deterministic keyword matching against the approved
        emergency keyword set from the foundation layer.

        Args:
            request: The prefilter request containing user message and session info.

        Returns:
            PrefilterResult with emergency detection results.

        Raises:
            ValueError: If request validation fails.
            RuntimeError: If keyword set cannot be loaded.
        """
        start_time = time.perf_counter()

        # Validate request
        if not request.user_message or not request.user_message.strip():
            raise ValueError("user_message must be non-empty")
        if not request.session_id or not request.session_id.strip():
            raise ValueError("session_id must be non-empty")

        # Load keyword set
        keyword_set = self._load_keyword_set()

        # Normalize user message
        normalized_message = self._normalize_text(request.user_message)

        # Match against critical keywords (Level 2)
        critical_matches = self._match_keywords(
            normalized_message, keyword_set.critical_keywords
        )

        # Match against caution keywords (Level 1)
        caution_matches = self._match_keywords(
            normalized_message, keyword_set.caution_keywords
        )

        # Combine all matches
        all_matches = critical_matches + caution_matches

        # Determine highest level
        is_emergency = len(all_matches) > 0
        level = 0
        protocol_id = ""

        if critical_matches:
            level = 2
            # Use protocol from first critical match
            protocol_id = critical_matches[0].protocol_id
        elif caution_matches:
            level = 1
            # Use protocol from first caution match
            protocol_id = caution_matches[0].protocol_id

        # If no matches, use fallback protocol
        if not is_emergency:
            protocol_id = "ERP-FALLBACK-V1"

        # A positive prefilter result must create the required audit event
        # before control returns to the capability layer.  The receipt is the
        # traceable handoff used by downstream emergency orchestration.
        event_receipt = None
        if is_emergency:
            event_request = EmergencyEventCreateRequest(
                session_id=request.session_id,
                level=level,
                matched_keywords=[match.rule_id for match in all_matches],
                protocol_id=protocol_id,
                user_message=request.user_message,
                trace_id=request.trace_id,
            )
            event_receipt = self._foundation.create_emergency_event(event_request)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Check timeout
        timeout_warning = ""
        if elapsed_ms > self._timeout_ms:
            timeout_warning = f"Prefilter exceeded timeout ({elapsed_ms:.1f}ms > {self._timeout_ms}ms)"

        metadata = {
            "elapsed_ms": round(elapsed_ms, 2),
            "timeout_ms": self._timeout_ms,
            "timeout_warning": timeout_warning,
            "approval_status": keyword_set.approval_status,
            "effective_date": keyword_set.effective_date,
            "version": keyword_set.version,
            "session_id": request.session_id,
            "trace_id": request.trace_id,
        }

        return PrefilterResult(
            is_emergency=is_emergency,
            level=level,
            matched_keywords=all_matches,
            protocol_id=protocol_id,
            metadata=metadata,
            event_receipt=event_receipt,
        )

    def get_keyword_set_info(self) -> Dict[str, Any]:
        """Get information about the loaded keyword set.

        Returns:
            Dictionary with keyword set metadata.
        """
        keyword_set = self._load_keyword_set()
        return {
            "approval_status": keyword_set.approval_status,
            "effective_date": keyword_set.effective_date,
            "version": keyword_set.version,
            "critical_keyword_count": len(keyword_set.critical_keywords),
            "caution_keyword_count": len(keyword_set.caution_keywords),
        }


# ---------------------------------------------------------------------------
# Convenience function for tool contract
# ---------------------------------------------------------------------------


def emergency_prefilter(
    user_message: str,
    session_id: str,
    trace_id: Optional[str] = None,
    foundation_service: Optional[EmergencyFoundationService] = None,
    timeout_ms: int = EmergencyPrefilterTool.DEFAULT_TIMEOUT_MS,
) -> PrefilterResult:
    """Convenience function for emergency prefilter tool contract (PC-02).

    This function implements the emergency_prefilter tool contract per INT-06.
    It creates a tool instance and runs the prefilter check.

    Args:
        user_message: The user's message to check for emergency keywords.
        session_id: Session identifier for audit trail.
        trace_id: Optional trace ID for distributed tracing.
        foundation_service: Optional foundation service override.
        timeout_ms: Optional timeout override in milliseconds.

    Returns:
        PrefilterResult with emergency detection results.
    """
    tool = EmergencyPrefilterTool(
        foundation_service=foundation_service,
        timeout_ms=timeout_ms,
    )
    request = PrefilterRequest(
        user_message=user_message,
        session_id=session_id,
        trace_id=trace_id,
    )
    return tool.prefilter(request)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "PrefilterRequest",
    "MatchedKeyword",
    "PrefilterResult",
    "EmergencyPrefilterTool",
    "emergency_prefilter",
]
# === TASK:WP-202:END ===

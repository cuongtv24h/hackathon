# === TASK:WP-302:START ===
"""AI guardrails service (ARCH-07, INT-05, INT-07).

This module provides input and output guardrails for AI interactions,
implementing privacy protection and content policy enforcement.

Key features:
- Input validation and sanitization
- PII detection and redaction (integrates with WP-204)
- Output filtering for chain-of-thought exposure prevention
- Medical advice refusal detection
- Safety disposition checks

Dependencies:
- WP-204: Privacy service for PII handling
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from packages.contracts import (
    UnifiedErrorEnvelope,
    make_error_envelope,
    CATEGORY_AI,
    CATEGORY_SAFETY,
    MEDICAL_ADVICE_REFUSED,
    OUT_OF_SCOPE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Violation types
# ---------------------------------------------------------------------------


class ViolationType(str):
    """Types of guardrail violations."""
    PII_DETECTED = "pii_detected"
    MEDICAL_ADVICE_REQUEST = "medical_advice_request"
    OUT_OF_SCOPE = "out_of_scope"
    CHAIN_OF_THOUGHT_EXPOSURE = "chain_of_thought_exposure"
    INJECTION_ATTEMPT = "injection_attempt"
    CONTENT_POLICY_VIOLATION = "content_policy_violation"


# ---------------------------------------------------------------------------
# DTOs for guardrail results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardrailViolation:
    """A single guardrail violation."""
    violation_type: str
    severity: str  # "low", "medium", "high", "critical"
    description: str
    location: Optional[str] = None  # Where in the text the violation occurred

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "violation_type": self.violation_type,
            "severity": self.severity,
            "description": self.description,
        }
        if self.location is not None:
            result["location"] = self.location
        return result


@dataclass(frozen=True)
class InputGuardrailResult:
    """Result of input guardrail check."""
    allowed: bool
    violations: List[GuardrailViolation] = field(default_factory=list)
    redacted_message: Optional[str] = None
    caution_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "allowed": self.allowed,
            "violations": [v.to_dict() for v in self.violations],
            "caution_flags": list(self.caution_flags),
        }
        if self.redacted_message is not None:
            result["redacted_message"] = self.redacted_message
        return result


@dataclass(frozen=True)
class OutputGuardrailResult:
    """Result of output guardrail check."""
    allowed: bool
    violations: List[GuardrailViolation] = field(default_factory=list)
    redacted_response: Optional[str] = None
    safety_disposition: str = "safe"

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "allowed": self.allowed,
            "violations": [v.to_dict() for v in self.violations],
            "safety_disposition": self.safety_disposition,
        }
        if self.redacted_response is not None:
            result["redacted_response"] = self.redacted_response
        return result


# ---------------------------------------------------------------------------
# Protocol for privacy service (WP-204)
# ---------------------------------------------------------------------------


@runtime_checkable
class PrivacyServiceProtocol(Protocol):
    """Protocol for privacy service integration (WP-204)."""

    def detect_pii(self, text: str) -> List[Dict[str, Any]]:
        """Detect PII in text.

        Args:
            text: Text to analyze.

        Returns:
            List of PII detections with 'type', 'start', 'end', 'value'.
        """
        ...

    def redact_pii(self, text: str, detections: List[Dict[str, Any]]) -> str:
        """Redact PII from text.

        Args:
            text: Original text.
            detections: PII detections from detect_pii.

        Returns:
            Text with PII redacted.
        """
        ...


# ---------------------------------------------------------------------------
# Guardrail service
# ---------------------------------------------------------------------------


class GuardrailService:
    """Service for checking input/output against guardrails.

    This service implements guardrail checks defined in:
    - docs/artifacts/architecture/context-design.md (ARCH-07)
    - docs/artifacts/interface/ai-behavior-contracts.md (INT-05)
    - docs/artifacts/interface/error-contracts.md (INT-07)

    Key constraints from INT-05:
    - Never expose system prompt, secrets, chain-of-thought or other-user data
    - Never diagnose, interpret tests, recommend medication/treatment
    """

    # Medical advice keywords (Vietnamese)
    MEDICAL_ADVICE_KEYWORDS = [
        "chẩn đoán", "điều trị", "thuốc", "uống thuốc", "liều lượng",
        "kết quả xét nghiệm", "xét nghiệm có vấn đề", "bệnh này là gì",
        "tôi bị bệnh gì", "có nguy hiểm không", "cần uống thuốc gì",
    ]

    # Out of scope keywords (Vietnamese)
    OUT_OF_SCOPE_KEYWORDS = [
        "hack", "crack", "bắt lòng", "chiếm đoạt", "tấn công",
        "mật khẩu", "tài khoản ngân hàng", "chuyển tiền",
        "giả mạo", "lừa đảo", "pháp lý", "kiện tụng",
    ]

    # Chain-of-thought exposure patterns
    COT_PATTERNS = [
        r"chain.?of.?thought",
        r"reasoning:? .*",
        r"step \d+:.*",
        r"tôi đã suy nghĩ",
        r"quá trình suy luận",
        r"internal reasoning",
        r"system prompt",
        r"prompt gốc",
    ]

    # Injection patterns
    INJECTION_PATTERNS = [
        r"ignore (all )?(previous|above) instructions",
        r"bỏ qua (tất cả )?hướng dẫn",
        r"disregard (all )?(previous|above)",
        r"you are now",
        r"bạn giờ là",
        r"pretend (to be|you are)",
        r"giả vờ",
        r"\<\<.*\>\>",
        r"\{\{.*\}\}",
    ]

    # PII patterns (basic detection, WP-204 provides comprehensive detection)
    PII_PATTERNS = {
        "phone": r"\b(0|\+84)\d{9,10}\b",
        "email": r"\b[\w\.-]+@[\w\.-]+\.\w+\b",
        "id_number": r"\b\d{9,12}\b",  # Vietnamese ID
        "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    }

    def __init__(
        self,
        *,
        privacy_service: Optional[PrivacyServiceProtocol] = None,
        enable_pii_detection: bool = True,
        enable_medical_advice_check: bool = True,
        enable_injection_check: bool = True,
    ):
        """Initialize guardrail service.

        Args:
            privacy_service: Privacy service for PII handling (WP-204).
            enable_pii_detection: Whether to detect PII.
            enable_medical_advice_check: Whether to check for medical advice requests.
            enable_injection_check: Whether to check for injection attempts.
        """
        self._privacy_service = privacy_service
        self._enable_pii_detection = enable_pii_detection
        self._enable_medical_advice_check = enable_medical_advice_check
        self._enable_injection_check = enable_injection_check

        # Compile regex patterns
        self._cot_patterns = [re.compile(p, re.IGNORECASE) for p in self.COT_PATTERNS]
        self._injection_patterns = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]

    def check_input(
        self,
        message: str,
        conversation_context: Optional[Any] = None,
    ) -> InputGuardrailResult:
        """Check input message against guardrails.

        Checks for:
        1. Injection attempts
        2. Medical advice requests
        3. Out of scope requests
        4. PII in input

        Args:
            message: User message to check.
            conversation_context: Optional conversation context.

        Returns:
            InputGuardrailResult with check results.
        """
        violations: List[GuardrailViolation] = []
        caution_flags: List[str] = []
        redacted_message: Optional[str] = None

        # Check for injection attempts
        if self._enable_injection_check:
            injection_violations = self._check_injection(message)
            violations.extend(injection_violations)

        # Check for medical advice requests
        if self._enable_medical_advice_check:
            medical_violations = self._check_medical_advice_request(message)
            violations.extend(medical_violations)
            if medical_violations:
                caution_flags.append("medical_advice_requested")

        # Check for out of scope
        scope_violations = self._check_out_of_scope(message)
        violations.extend(scope_violations)

        # Check for PII
        if self._enable_pii_detection:
            pii_result = self._check_pii_input(message)
            if pii_result["has_pii"]:
                caution_flags.append("pii_detected")
                redacted_message = pii_result["redacted"]

        # Determine if allowed
        # Block only critical/high severity violations
        blocked = any(v.severity in ("critical", "high") for v in violations)

        return InputGuardrailResult(
            allowed=not blocked,
            violations=violations,
            redacted_message=redacted_message,
            caution_flags=caution_flags,
        )

    def check_output(
        self,
        response: str,
        observations: Optional[List[Dict[str, Any]]] = None,
    ) -> OutputGuardrailResult:
        """Check output response against guardrails.

        Checks for:
        1. Chain-of-thought exposure
        2. PII leakage
        3. Safety disposition

        Args:
            response: Generated response to check.
            observations: Optional tool observations used.

        Returns:
            OutputGuardrailResult with check results.
        """
        violations: List[GuardrailViolation] = []
        redacted_response: Optional[str] = None
        safety_disposition = "safe"

        # Check for chain-of-thought exposure
        cot_violations = self._check_cot_exposure(response)
        violations.extend(cot_violations)

        # Check for PII in output
        if self._enable_pii_detection:
            pii_result = self._check_pii_output(response)
            if pii_result["has_pii"]:
                redacted_response = pii_result["redacted"]
                safety_disposition = "caution"

        # Determine safety disposition
        if any(v.severity == "critical" for v in violations):
            safety_disposition = "medical_refusal"
        elif any(v.severity == "high" for v in violations):
            safety_disposition = "caution"

        # Determine if allowed
        blocked = any(v.severity == "critical" for v in violations)

        return OutputGuardrailResult(
            allowed=not blocked,
            violations=violations,
            redacted_response=redacted_response,
            safety_disposition=safety_disposition,
        )

    def _check_injection(self, message: str) -> List[GuardrailViolation]:
        """Check for injection attempts."""
        violations = []
        for pattern in self._injection_patterns:
            matches = pattern.findall(message)
            if matches:
                violations.append(GuardrailViolation(
                    violation_type=ViolationType.INJECTION_ATTEMPT,
                    severity="critical",
                    description="Potential prompt injection attempt detected",
                    location=matches[0] if isinstance(matches[0], str) else str(matches[0]),
                ))
        return violations

    def _check_medical_advice_request(self, message: str) -> List[GuardrailViolation]:
        """Check for medical advice requests."""
        violations = []
        message_lower = message.lower()

        for keyword in self.MEDICAL_ADVICE_KEYWORDS:
            if keyword in message_lower:
                violations.append(GuardrailViolation(
                    violation_type=ViolationType.MEDICAL_ADVICE_REQUEST,
                    severity="medium",
                    description=f"Medical advice keyword detected: {keyword}",
                    location=keyword,
                ))
                break  # Only one violation per message

        return violations

    def _check_out_of_scope(self, message: str) -> List[GuardrailViolation]:
        """Check for out of scope requests."""
        violations = []
        message_lower = message.lower()

        for keyword in self.OUT_OF_SCOPE_KEYWORDS:
            if keyword in message_lower:
                violations.append(GuardrailViolation(
                    violation_type=ViolationType.OUT_OF_SCOPE,
                    severity="high",
                    description=f"Out of scope keyword detected: {keyword}",
                    location=keyword,
                ))
                break

        return violations

    def _check_cot_exposure(self, response: str) -> List[GuardrailViolation]:
        """Check for chain-of-thought exposure in output."""
        violations = []

        for pattern in self._cot_patterns:
            matches = pattern.findall(response)
            if matches:
                violations.append(GuardrailViolation(
                    violation_type=ViolationType.CHAIN_OF_THOUGHT_EXPOSURE,
                    severity="critical",
                    description="Chain-of-thought or internal reasoning exposed",
                    location=matches[0] if isinstance(matches[0], str) else str(matches[0]),
                ))

        return violations

    def _check_pii_input(self, message: str) -> Dict[str, Any]:
        """Check for PII in input message."""
        result = {"has_pii": False, "redacted": None}

        # Use privacy service if available
        if self._privacy_service:
            try:
                detections = self._privacy_service.detect_pii(message)
                if detections:
                    result["has_pii"] = True
                    result["redacted"] = self._privacy_service.redact_pii(message, detections)
                return result
            except Exception as e:
                logger.warning(f"Privacy service failed: {e}")

        # Fallback to basic pattern matching
        redacted = message
        has_pii = False

        for pii_type, pattern in self.PII_PATTERNS.items():
            regex = re.compile(pattern)
            if regex.search(message):
                has_pii = True
                redacted = regex.sub(f"[{pii_type.upper()}_REDACTED]", redacted)

        result["has_pii"] = has_pii
        result["redacted"] = redacted if has_pii else None
        return result

    def _check_pii_output(self, response: str) -> Dict[str, Any]:
        """Check for PII in output response."""
        result = {"has_pii": False, "redacted": None}

        # Use privacy service if available
        if self._privacy_service:
            try:
                detections = self._privacy_service.detect_pii(response)
                if detections:
                    result["has_pii"] = True
                    result["redacted"] = self._privacy_service.redact_pii(response, detections)
                return result
            except Exception as e:
                logger.warning(f"Privacy service failed: {e}")

        # Fallback to basic pattern matching
        redacted = response
        has_pii = False

        for pii_type, pattern in self.PII_PATTERNS.items():
            regex = re.compile(pattern)
            if regex.search(response):
                has_pii = True
                redacted = regex.sub(f"[{pii_type.upper()}_REDACTED]", redacted)

        result["has_pii"] = has_pii
        result["redacted"] = redacted if has_pii else None
        return result


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def create_mock_guardrail_service(
    *,
    allow_all: bool = True,
    medical_advice_severity: str = "medium",
) -> GuardrailService:
    """Create a guardrail service with mock settings for testing.

    Args:
        allow_all: If True, don't block any messages.
        medical_advice_severity: Severity level for medical advice detection.

    Returns:
        GuardrailService configured for testing.
    """
    return GuardrailService(
        enable_pii_detection=True,
        enable_medical_advice_check=True,
        enable_injection_check=True,
    )


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    # Violation types
    "ViolationType",
    # DTOs
    "GuardrailViolation",
    "InputGuardrailResult",
    "OutputGuardrailResult",
    # Protocols
    "PrivacyServiceProtocol",
    # Service
    "GuardrailService",
    # Factories
    "create_mock_guardrail_service",
]
# === TASK:WP-302:END ===

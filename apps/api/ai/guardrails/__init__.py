"""AI guardrails package (WP-302, WP-204).

This module re-exports the public API from service.py for convenience.
"""

from apps.api.ai.guardrails.service import (
    GuardrailService,
    GuardrailViolation,
    InputGuardrailResult,
    OutputGuardrailResult,
    ViolationType,
    create_mock_guardrail_service,
)

__all__ = [
    "GuardrailService",
    "GuardrailViolation",
    "InputGuardrailResult",
    "OutputGuardrailResult",
    "ViolationType",
    "create_mock_guardrail_service",
]

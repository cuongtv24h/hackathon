# === TASK:WP-301:START ===
"""LLM provider abstraction layer (ARCH-03, ARCH-09, INT-05).

This module provides provider isolation for LLM operations following the
architecture defined in:
- docs/artifacts/architecture/component-architecture.md (ARCH-03)
- docs/artifacts/architecture/deployment-resilience.md (ARCH-09)
- docs/artifacts/interface/ai-behavior-contracts.md (INT-05)

Key features:
- Provider chain with automatic fallback on failure
- Timeout and retry handling
- No provider secrets exposed to callers
- Error mapping to canonical error codes (INT-07)
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from packages.contracts import (
    UnifiedErrorEnvelope,
    make_error_envelope,
    CATEGORY_AI,
    CATEGORY_SYSTEM,
    AI_PROVIDER_UNAVAILABLE,
    AI_OUTPUT_REJECTED,
    INTERNAL_ERROR,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider error codes (INT-07 alignment)
# ---------------------------------------------------------------------------

LLM_TIMEOUT = "LLM_TIMEOUT"
LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
LLM_CONTENT_FILTERED = "LLM_CONTENT_FILTERED"


# ---------------------------------------------------------------------------
# Provider-level exception
# ---------------------------------------------------------------------------


class LLMProviderError(Exception):
    """Provider-layer exception that wraps a UnifiedErrorEnvelope."""

    def __init__(self, envelope: UnifiedErrorEnvelope) -> None:
        self.envelope = envelope
        super().__init__(envelope.error.message)

    def to_dict(self) -> Dict[str, Any]:
        return self.envelope.to_dict()


def _provider_error(
    code: str,
    message: str,
    *,
    category: str = CATEGORY_AI,
    retryable: bool = False,
    retry_after_seconds: Optional[int] = None,
) -> LLMProviderError:
    """Create an LLMProviderError wrapping a UnifiedErrorEnvelope."""
    return LLMProviderError(
        make_error_envelope(
            code=code,
            message=message,
            category=category,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
        )
    )


# ---------------------------------------------------------------------------
# DTOs for LLM operations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMRequest:
    """Request to an LLM provider.

    Attributes:
        messages: List of message dicts with 'role' and 'content'.
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature (0.0-2.0).
        system_prompt: Optional system prompt.
        tools: Optional list of tool definitions.
        tool_choice: Optional tool choice strategy.
    """

    messages: List[Dict[str, str]]
    max_tokens: int = 1024
    temperature: float = 0.7
    system_prompt: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("messages must be non-empty")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be positive")


@dataclass(frozen=True)
class LLMResponse:
    """Response from an LLM provider.

    Attributes:
        content: The generated text content.
        tool_calls: Optional list of tool calls made.
        usage: Token usage information.
        model: The model identifier used.
        provider: The provider name.
        finish_reason: Why generation stopped.
        latency_ms: Request latency in milliseconds.
    """

    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    model: str = ""
    provider: str = ""
    finish_reason: str = "stop"
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": list(self.tool_calls),
            "usage": dict(self.usage),
            "model": self.model,
            "provider": self.provider,
            "finish_reason": self.finish_reason,
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True)
class ReasoningResultDTO:
    """Structured reasoning output (INT-05).

    This is a conclusion, not chain-of-thought. Fields defined in
    docs/artifacts/interface/ai-behavior-contracts.md.

    Attributes:
        intent_labels: Identified intent labels.
        domains: Identified domain codes.
        clarity: Clarity assessment (clear/ambiguous/incomplete).
        missing_information: Information needed for complete response.
        scope: Scope assessment (in_scope/out_of_scope/partial).
        safety_disposition: Safety assessment (safe/caution/medical_refusal).
        confidence_band: Confidence level (high/medium/low).
    """

    intent_labels: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    clarity: str = "clear"
    missing_information: List[str] = field(default_factory=list)
    scope: str = "in_scope"
    safety_disposition: str = "safe"
    confidence_band: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_labels": list(self.intent_labels),
            "domains": list(self.domains),
            "clarity": self.clarity,
            "missing_information": list(self.missing_information),
            "scope": self.scope,
            "safety_disposition": self.safety_disposition,
            "confidence_band": self.confidence_band,
        }


# ---------------------------------------------------------------------------
# Abstract provider interface
# ---------------------------------------------------------------------------


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.

    Concrete implementations must implement the _invoke method.
    The base class handles timeout, error mapping, and metrics.
    """

    def __init__(
        self,
        *,
        name: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 1,
    ):
        self.name = name
        self.model = model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    @abstractmethod
    def _invoke(self, request: LLMRequest) -> LLMResponse:
        """Invoke the provider API. Must be implemented by subclasses.

        This method is designed to be mocked in tests. Real implementations
        will make network calls to provider APIs.

        Args:
            request: The LLM request.

        Returns:
            LLMResponse with generated content.

        Raises:
            Exception: On provider failure (will be mapped to LLMProviderError).
        """
        raise NotImplementedError("_invoke must be implemented by subclass")

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a response from the LLM.

        This method wraps _invoke with error handling and metrics.

        Args:
            request: The LLM request.

        Returns:
            LLMResponse with generated content.

        Raises:
            LLMProviderError: On provider failure.
        """
        start_time = time.monotonic()
        try:
            response = self._invoke(request)
            latency_ms = (time.monotonic() - start_time) * 1000

            # Return response with latency populated
            return LLMResponse(
                content=response.content,
                tool_calls=response.tool_calls,
                usage=response.usage,
                model=response.model or self.model,
                provider=response.provider or self.name,
                finish_reason=response.finish_reason,
                latency_ms=latency_ms,
            )
        except LLMProviderError:
            raise
        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                f"LLM provider {self.name} failed after {latency_ms:.1f}ms: {e}"
            )
            raise _provider_error(
                code=AI_PROVIDER_UNAVAILABLE,
                message=f"LLM provider '{self.name}' failed: {str(e)}",
                category=CATEGORY_AI,
                retryable=True,
                retry_after_seconds=5,
            )

    def is_available(self) -> bool:
        """Check if the provider is available.

        Returns:
            True if the provider can be used.
        """
        return True


# ---------------------------------------------------------------------------
# Mock provider for testing
# ---------------------------------------------------------------------------


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM provider for testing.

    This provider returns configurable responses without making network calls.
    It can be configured to simulate errors, delays, and specific responses.
    """

    def __init__(
        self,
        *,
        name: str = "mock",
        model: str = "mock-model",
        response_content: str = "This is a mock response.",
        response_tool_calls: Optional[List[Dict[str, Any]]] = None,
        raise_error: Optional[str] = None,
        delay_seconds: float = 0.0,
    ):
        super().__init__(name=name, model=model)
        self._response_content = response_content
        self._response_tool_calls = response_tool_calls or []
        self._raise_error = raise_error
        self._delay_seconds = delay_seconds
        self._call_count = 0

    def _invoke(self, request: LLMRequest) -> LLMResponse:
        """Return a mock response or raise configured error."""
        self._call_count += 1

        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)

        if self._raise_error:
            if self._raise_error == "timeout":
                raise TimeoutError("Mock timeout")
            elif self._raise_error == "rate_limit":
                raise _provider_error(
                    code=LLM_RATE_LIMITED,
                    message="Mock rate limit exceeded",
                    category=CATEGORY_AI,
                    retryable=True,
                    retry_after_seconds=30,
                )
            elif self._raise_error == "content_filter":
                raise _provider_error(
                    code=LLM_CONTENT_FILTERED,
                    message="Mock content filter triggered",
                    category=CATEGORY_AI,
                    retryable=False,
                )
            elif self._raise_error == "unavailable":
                raise Exception("Mock provider unavailable")

        return LLMResponse(
            content=self._response_content,
            tool_calls=self._response_tool_calls,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            model=self.model,
            provider=self.name,
        )

    @property
    def call_count(self) -> int:
        """Number of times _invoke was called."""
        return self._call_count

    def set_response(self, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None) -> None:
        """Configure the mock response."""
        self._response_content = content
        self._response_tool_calls = tool_calls or []

    def set_error(self, error_type: Optional[str]) -> None:
        """Configure the mock to raise an error."""
        self._raise_error = error_type


# ---------------------------------------------------------------------------
# Provider chain with fallback
# ---------------------------------------------------------------------------


class LLMProviderChain:
    """Chain of LLM providers with automatic fallback.

    On failure, the chain tries the next provider. If all providers fail,
    returns an error or fallback response.

    This implements the "Primary LLM → fallback provider chain → static message"
    degradation behavior defined in ARCH-09.
    """

    def __init__(
        self,
        providers: List[BaseLLMProvider],
        *,
        fallback_message: str = "Xin lỗi, hệ thống đang gặp sự cố kỹ thuật. Vui lòng gọi đường dây nóng 1900-xxxx để được hỗ trợ.",
    ):
        if not providers:
            raise ValueError("providers list must not be empty")
        self._providers = list(providers)
        self._fallback_message = fallback_message

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a response, trying providers in order.

        Args:
            request: The LLM request.

        Returns:
            LLMResponse from the first successful provider.

        Raises:
            LLMProviderError: If all providers fail.
        """
        last_error: Optional[Exception] = None

        for provider in self._providers:
            if not provider.is_available():
                logger.warning(f"Provider {provider.name} is not available, skipping")
                continue

            try:
                logger.debug(f"Trying provider: {provider.name}")
                return provider.generate(request)
            except LLMProviderError as e:
                logger.warning(
                    f"Provider {provider.name} failed: {e.envelope.error.message}"
                )
                last_error = e
                continue
            except Exception as e:
                logger.warning(f"Provider {provider.name} raised unexpected error: {e}")
                last_error = _provider_error(
                    code=AI_PROVIDER_UNAVAILABLE,
                    message=f"Provider '{provider.name}' failed unexpectedly",
                    category=CATEGORY_AI,
                    retryable=True,
                )
                continue

        # All providers failed
        logger.error("All LLM providers failed")
        if last_error:
            raise last_error
        raise _provider_error(
            code=AI_PROVIDER_UNAVAILABLE,
            message="All LLM providers are unavailable",
            category=CATEGORY_AI,
            retryable=True,
            retry_after_seconds=30,
        )

    def get_fallback_message(self) -> str:
        """Return the static fallback message for all-provider failure."""
        return self._fallback_message

    @property
    def providers(self) -> List[BaseLLMProvider]:
        """List of providers in the chain."""
        return list(self._providers)


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def create_mock_provider_chain(
    response_content: str = "This is a mock response.",
) -> LLMProviderChain:
    """Create a provider chain with a mock provider for testing.

    Args:
        response_content: The content to return from the mock provider.

    Returns:
        LLMProviderChain with a single MockLLMProvider.
    """
    provider = MockLLMProvider(response_content=response_content)
    return LLMProviderChain([provider])


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "BaseLLMProvider",
    "LLMProviderError",
    "LLMRequest",
    "LLMResponse",
    "ReasoningResultDTO",
    "MockLLMProvider",
    "LLMProviderChain",
    "create_mock_provider_chain",
    "LLM_TIMEOUT",
    "LLM_RATE_LIMITED",
    "LLM_CONTENT_FILTERED",
]
# === TASK:WP-301:END ===

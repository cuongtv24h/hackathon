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
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import httpx

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
# OpenAI-compatible runtime provider
# ---------------------------------------------------------------------------


class OpenAICompatibleLLMProvider(BaseLLMProvider):
    """Call a real OpenAI-compatible chat-completions API over HTTPS.

    Gemini's OpenAI-compatible endpoint and OpenRouter both use this shape.
    Credentials are supplied at runtime only and are never included in errors
    or logs. Transport and transient provider errors are retried locally before
    the provider chain moves to the next configured provider.
    """

    def __init__(
        self,
        *,
        name: str,
        model: str,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 1,
        extra_headers: Optional[Dict[str, str]] = None,
        client_factory: Callable[..., Any] = httpx.Client,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must be non-empty")
        if not api_key.strip():
            raise ValueError("api_key must be non-empty")
        super().__init__(
            name=name,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._extra_headers = dict(extra_headers or {})
        self._client_factory = client_factory

    def _invoke(self, request: LLMRequest) -> LLMResponse:
        messages = list(request.messages)
        if request.system_prompt:
            messages.insert(0, {"role": "system", "content": request.system_prompt})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.tools:
            payload["tools"] = request.tools
        if request.tool_choice:
            payload["tool_choice"] = request.tool_choice

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self._extra_headers)

        for attempt in range(self._max_retries + 1):
            try:
                client = self._client_factory(timeout=self._timeout_seconds)
                try:
                    response = client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                finally:
                    close = getattr(client, "close", None)
                    if callable(close):
                        close()

                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    retry_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 5
                    raise _provider_error(
                        code=LLM_RATE_LIMITED,
                        message=f"LLM provider '{self.name}' rate limited the request",
                        retryable=True,
                        retry_after_seconds=retry_seconds,
                    )
                if response.status_code in (408, 504):
                    raise _provider_error(
                        code=LLM_TIMEOUT,
                        message=f"LLM provider '{self.name}' timed out",
                        retryable=True,
                        retry_after_seconds=2,
                    )
                if response.status_code >= 500:
                    raise _provider_error(
                        code=AI_PROVIDER_UNAVAILABLE,
                        message=f"LLM provider '{self.name}' is temporarily unavailable",
                        retryable=True,
                        retry_after_seconds=5,
                    )
                if response.status_code >= 400:
                    body = response.text.lower()
                    if "content_filter" in body or "safety" in body:
                        raise _provider_error(
                            code=LLM_CONTENT_FILTERED,
                            message="LLM provider rejected the content by policy",
                            retryable=False,
                        )
                    raise _provider_error(
                        code=AI_PROVIDER_UNAVAILABLE,
                        message=f"LLM provider '{self.name}' rejected the request",
                        retryable=False,
                    )

                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    raise ValueError("provider response contains no choices")
                message = choices[0].get("message") or {}
                content = message.get("content") or ""
                return LLMResponse(
                    content=content,
                    tool_calls=message.get("tool_calls") or [],
                    usage=data.get("usage") or {},
                    model=data.get("model") or self.model,
                    provider=self.name,
                    finish_reason=choices[0].get("finish_reason") or "stop",
                )
            except LLMProviderError:
                raise
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self._max_retries:
                    raise _provider_error(
                        code=LLM_TIMEOUT if isinstance(exc, httpx.TimeoutException) else AI_PROVIDER_UNAVAILABLE,
                        message=f"LLM provider '{self.name}' could not be reached",
                        retryable=True,
                        retry_after_seconds=5,
                    ) from exc
                time.sleep(min(0.5 * (attempt + 1), 1.0))
            except (ValueError, KeyError, TypeError) as exc:
                raise _provider_error(
                    code=AI_PROVIDER_UNAVAILABLE,
                    message=f"LLM provider '{self.name}' returned an invalid response",
                    retryable=True,
                    retry_after_seconds=5,
                ) from exc

        raise _provider_error(
            code=AI_PROVIDER_UNAVAILABLE,
            message=f"LLM provider '{self.name}' failed",
            retryable=True,
        )


class RuntimeLLMAdapter:
    """Adapt the provider chain to the orchestrator's dictionary contract."""

    def __init__(self, provider_chain: "LLMProviderChain") -> None:
        self._provider_chain = provider_chain

    def generate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        messages = list(request.get("messages") or [])
        context = str(request.get("context") or "").strip()
        if context:
            messages.insert(1 if messages and messages[0].get("role") == "system" else 0, {
                "role": "system",
                "content": "Nguồn đã được phê duyệt để trả lời:\n" + context,
            })
        response = self._provider_chain.generate(LLMRequest(
            messages=messages,
            max_tokens=int(request.get("max_tokens", 1024)),
            temperature=float(request.get("temperature", 0.2)),
        ))
        return response.to_dict()


def create_runtime_provider_chain(
    environment: Optional[Dict[str, str]] = None,
) -> LLMProviderChain:
    """Create a real provider chain in the configured, editable order.

    ``LLM_PROVIDER_ORDER`` is a comma-separated list of ``gemini``,
    ``openrouter`` and ``groq``. Changing the list changes primary/fallback
    order without code changes. Legacy PRIMARY/FALLBACK variable names remain
    supported so existing Pilot environments continue to work.
    """
    env = environment if environment is not None else os.environ
    provider_defaults = {
        "gemini": {"name": "gemini", "model": "gemini-2.5-flash", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"},
        "openrouter": {"name": "openrouter", "model": "google/gemini-2.5-flash", "base_url": "https://openrouter.ai/api/v1"},
        "groq": {"name": "groq", "model": "llama-3.3-70b-versatile", "base_url": "https://api.groq.com/openai/v1"},
    }
    order_value = env.get("LLM_PROVIDER_ORDER", "").strip()
    if order_value:
        provider_order = [item.strip().lower() for item in order_value.split(",") if item.strip()]
    else:
        # Backward-compatible inference for environments that predate the
        # explicit order variable: only configured providers are included.
        provider_order = []
        if env.get("LLM_GEMINI_API_KEY") or env.get("LLM_PRIMARY_API_KEY") or env.get("GEMINI_API_KEY"):
            provider_order.append("gemini")
        if env.get("LLM_OPENROUTER_API_KEY") or env.get("LLM_FALLBACK_API_KEY") or env.get("OPENROUTER_API_KEY"):
            provider_order.append("openrouter")
        if env.get("LLM_GROQ_API_KEY") or env.get("LLM_GROK_API_KEY") or env.get("GROQ_API_KEY"):
            provider_order.append("groq")
    # ``grok`` was used in an early configuration draft for Groq. Accept it
    # as a migration alias, but normalize the resolved runtime identity.
    provider_order = ["groq" if name == "grok" else name for name in provider_order]
    if not provider_order:
        raise ValueError("No real LLM provider is configured")
    if len(provider_order) != len(set(provider_order)):
        raise ValueError("LLM_PROVIDER_ORDER must contain unique provider names")
    unknown = [name for name in provider_order if name not in provider_defaults]
    if unknown:
        raise ValueError("Unsupported LLM provider in LLM_PROVIDER_ORDER: " + ", ".join(unknown))

    legacy_keys = {
        "gemini": ("LLM_PRIMARY_API_KEY", "GEMINI_API_KEY"),
        "openrouter": ("LLM_FALLBACK_API_KEY", "OPENROUTER_API_KEY"),
        "groq": ("LLM_GROK_API_KEY", "GROQ_API_KEY"),
    }
    legacy_prefixes = {"gemini": "PRIMARY", "openrouter": "FALLBACK", "groq": "GROK"}
    providers: List[BaseLLMProvider] = []
    for provider_id in provider_order:
        defaults = provider_defaults[provider_id]
        key = env.get("LLM_%s_API_KEY" % provider_id.upper())
        if not key:
            for legacy_key in legacy_keys[provider_id]:
                key = env.get(legacy_key)
                if key:
                    break
        if not key:
            raise ValueError("LLM provider '%s' is ordered but has no API key" % provider_id)

        prefix = "LLM_%s" % provider_id.upper()
        legacy_prefix = legacy_prefixes.get(provider_id)

        def configured_value(field: str, default: str) -> str:
            legacy_value = (
                env.get("LLM_" + legacy_prefix + "_" + field)
                if legacy_prefix and not (provider_id == "groq" and field == "NAME")
                else None
            )
            return (
                env.get(prefix + "_" + field)
                or legacy_value
                or default
            )

        providers.append(OpenAICompatibleLLMProvider(
            name=configured_value("NAME", defaults["name"]),
            model=configured_value("MODEL", defaults["model"]),
            base_url=configured_value("BASE_URL", defaults["base_url"]),
            api_key=key,
            timeout_seconds=float(configured_value("TIMEOUT_SECONDS", "30")),
            max_retries=int(configured_value("MAX_RETRIES", "1")),
        ))

    if not providers:
        raise ValueError("No real LLM provider is configured")
    return LLMProviderChain(providers)


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
                if e.envelope.error.code in {LLM_CONTENT_FILTERED, AI_OUTPUT_REJECTED}:
                    # Safety/policy refusal is terminal; another provider must
                    # not turn resilience fallback into policy bypass.
                    raise
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
    "OpenAICompatibleLLMProvider",
    "RuntimeLLMAdapter",
    "LLMProviderChain",
    "create_mock_provider_chain",
    "create_runtime_provider_chain",
    "LLM_TIMEOUT",
    "LLM_RATE_LIMITED",
    "LLM_CONTENT_FILTERED",
]
# === TASK:WP-301:END ===

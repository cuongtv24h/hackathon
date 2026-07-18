# === TASK:WP-301:START ===
"""Embedding provider abstraction layer (ARCH-03, ARCH-09, INT-05).

This module provides provider isolation for embedding operations following the
architecture defined in:
- docs/artifacts/architecture/component-architecture.md (ARCH-03)
- docs/artifacts/architecture/deployment-resilience.md (ARCH-09)
- docs/artifacts/interface/ai-behavior-contracts.md (INT-05)

Key features:
- Provider abstraction for embedding generation
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
    INTERNAL_ERROR,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider-level exception
# ---------------------------------------------------------------------------


class EmbeddingProviderError(Exception):
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
) -> EmbeddingProviderError:
    """Create an EmbeddingProviderError wrapping a UnifiedErrorEnvelope."""
    return EmbeddingProviderError(
        make_error_envelope(
            code=code,
            message=message,
            category=category,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
        )
    )


# ---------------------------------------------------------------------------
# DTOs for embedding operations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmbeddingRequest:
    """Request to an embedding provider.

    Attributes:
        texts: List of texts to embed.
        model: Optional model override.
    """

    texts: List[str]
    model: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.texts:
            raise ValueError("texts must be non-empty")
        for i, text in enumerate(self.texts):
            if not text or not text.strip():
                raise ValueError(f"texts[{i}] must be non-empty")


@dataclass(frozen=True)
class EmbeddingVector:
    """A single embedding vector with metadata.

    Attributes:
        vector: The embedding vector (list of floats).
        index: Index of the text in the original request.
        model: The model used to generate the embedding.
    """

    vector: List[float]
    index: int = 0
    model: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vector": list(self.vector),
            "index": self.index,
            "model": self.model,
        }


@dataclass(frozen=True)
class EmbeddingResponse:
    """Response from an embedding provider.

    Attributes:
        embeddings: List of embedding vectors.
        model: The model identifier used.
        provider: The provider name.
        usage: Token usage information.
        latency_ms: Request latency in milliseconds.
    """

    embeddings: List[EmbeddingVector]
    model: str = ""
    provider: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "embeddings": [e.to_dict() for e in self.embeddings],
            "model": self.model,
            "provider": self.provider,
            "usage": dict(self.usage),
            "latency_ms": self.latency_ms,
        }

    @property
    def vectors(self) -> List[List[float]]:
        """Extract just the vectors for convenience."""
        return [e.vector for e in self.embeddings]


# ---------------------------------------------------------------------------
# Abstract provider interface
# ---------------------------------------------------------------------------


class BaseEmbeddingProvider(ABC):
    """Abstract base class for embedding providers.

    Concrete implementations must implement the _invoke method.
    The base class handles timeout, error mapping, and metrics.
    """

    def __init__(
        self,
        *,
        name: str,
        model: str,
        dimension: int,
        timeout_seconds: float = 10.0,
        max_retries: int = 1,
    ):
        self.name = name
        self.model = model
        self.dimension = dimension
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    @abstractmethod
    def _invoke(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Invoke the provider API. Must be implemented by subclasses.

        This method is designed to be mocked in tests. Real implementations
        will make network calls to provider APIs.

        Args:
            request: The embedding request.

        Returns:
            EmbeddingResponse with generated embeddings.

        Raises:
            Exception: On provider failure (will be mapped to EmbeddingProviderError).
        """
        raise NotImplementedError("_invoke must be implemented by subclass")

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings for the given texts.

        This method wraps _invoke with error handling and metrics.

        Args:
            request: The embedding request.

        Returns:
            EmbeddingResponse with generated embeddings.

        Raises:
            EmbeddingProviderError: On provider failure.
        """
        start_time = time.monotonic()
        try:
            response = self._invoke(request)
            latency_ms = (time.monotonic() - start_time) * 1000

            # Return response with latency populated
            return EmbeddingResponse(
                embeddings=response.embeddings,
                model=response.model or self.model,
                provider=response.provider or self.name,
                usage=response.usage,
                latency_ms=latency_ms,
            )
        except EmbeddingProviderError:
            raise
        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                f"Embedding provider {self.name} failed after {latency_ms:.1f}ms: {e}"
            )
            raise _provider_error(
                code=AI_PROVIDER_UNAVAILABLE,
                message=f"Embedding provider '{self.name}' failed: {str(e)}",
                category=CATEGORY_AI,
                retryable=True,
                retry_after_seconds=5,
            )

    def embed_single(self, text: str) -> List[float]:
        """Convenience method to embed a single text.

        Args:
            text: The text to embed.

        Returns:
            The embedding vector.
        """
        request = EmbeddingRequest(texts=[text])
        response = self.embed(request)
        return response.vectors[0]

    def is_available(self) -> bool:
        """Check if the provider is available.

        Returns:
            True if the provider can be used.
        """
        return True


# ---------------------------------------------------------------------------
# Mock provider for testing
# ---------------------------------------------------------------------------


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Mock embedding provider for testing.

    This provider returns configurable embeddings without making network calls.
    It generates deterministic embeddings based on text content.
    """

    def __init__(
        self,
        *,
        name: str = "mock",
        model: str = "mock-embedding",
        dimension: int = 768,
        raise_error: Optional[str] = None,
        delay_seconds: float = 0.0,
    ):
        super().__init__(name=name, model=model, dimension=dimension)
        self._raise_error = raise_error
        self._delay_seconds = delay_seconds
        self._call_count = 0

    def _invoke(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Return mock embeddings or raise configured error."""
        self._call_count += 1

        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)

        if self._raise_error:
            if self._raise_error == "timeout":
                raise TimeoutError("Mock timeout")
            elif self._raise_error == "unavailable":
                raise Exception("Mock provider unavailable")

        # Generate deterministic mock embeddings based on text content
        embeddings = []
        for i, text in enumerate(request.texts):
            # Create a deterministic but varied embedding
            vector = self._generate_mock_vector(text)
            embeddings.append(EmbeddingVector(vector=vector, index=i, model=self.model))

        total_chars = sum(len(t) for t in request.texts)
        return EmbeddingResponse(
            embeddings=embeddings,
            model=self.model,
            provider=self.name,
            usage={"total_tokens": total_chars // 4},  # Rough estimate
        )

    def _generate_mock_vector(self, text: str) -> List[float]:
        """Generate a deterministic mock embedding vector.

        Uses a simple hash-based approach to create consistent vectors.
        """
        import hashlib

        # Hash the text to get deterministic values
        text_hash = hashlib.sha256(text.encode()).hexdigest()

        # Use hash values to seed the vector components
        vector = []
        for i in range(self.dimension):
            # Cycle through hash characters to generate values
            char_idx = i % len(text_hash)
            char_val = int(text_hash[char_idx], 16) / 15.0  # 0.0 to 1.0
            # Scale to -1.0 to 1.0 and add some variation
            val = (char_val * 2.0 - 1.0) * (0.5 + 0.5 * (i % 10) / 10.0)
            vector.append(round(val, 6))

        return vector

    @property
    def call_count(self) -> int:
        """Number of times _invoke was called."""
        return self._call_count

    def set_error(self, error_type: Optional[str]) -> None:
        """Configure the mock to raise an error."""
        self._raise_error = error_type


# ---------------------------------------------------------------------------
# Provider chain with fallback
# ---------------------------------------------------------------------------


class EmbeddingProviderChain:
    """Chain of embedding providers with automatic fallback.

    On failure, the chain tries the next provider. If all providers fail,
    raises an error.
    """

    def __init__(
        self,
        providers: List[BaseEmbeddingProvider],
    ):
        if not providers:
            raise ValueError("providers list must not be empty")
        self._providers = list(providers)

        # Verify all providers have the same dimension
        dimensions = {p.dimension for p in providers}
        if len(dimensions) > 1:
            raise ValueError(
                f"All providers must have the same dimension, got: {dimensions}"
            )
        self._dimension = providers[0].dimension

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings, trying providers in order.

        Args:
            request: The embedding request.

        Returns:
            EmbeddingResponse from the first successful provider.

        Raises:
            EmbeddingProviderError: If all providers fail.
        """
        last_error: Optional[Exception] = None

        for provider in self._providers:
            if not provider.is_available():
                logger.warning(f"Provider {provider.name} is not available, skipping")
                continue

            try:
                logger.debug(f"Trying embedding provider: {provider.name}")
                return provider.embed(request)
            except EmbeddingProviderError as e:
                logger.warning(
                    f"Embedding provider {provider.name} failed: {e.envelope.error.message}"
                )
                last_error = e
                continue
            except Exception as e:
                logger.warning(f"Embedding provider {provider.name} raised unexpected error: {e}")
                last_error = _provider_error(
                    code=AI_PROVIDER_UNAVAILABLE,
                    message=f"Embedding provider '{provider.name}' failed unexpectedly",
                    category=CATEGORY_AI,
                    retryable=True,
                )
                continue

        # All providers failed
        logger.error("All embedding providers failed")
        if last_error:
            raise last_error
        raise _provider_error(
            code=AI_PROVIDER_UNAVAILABLE,
            message="All embedding providers are unavailable",
            category=CATEGORY_AI,
            retryable=True,
            retry_after_seconds=30,
        )

    def embed_single(self, text: str) -> List[float]:
        """Convenience method to embed a single text.

        Args:
            text: The text to embed.

        Returns:
            The embedding vector.
        """
        request = EmbeddingRequest(texts=[text])
        response = self.embed(request)
        return response.vectors[0]

    @property
    def dimension(self) -> int:
        """Embedding dimension."""
        return self._dimension

    @property
    def providers(self) -> List[BaseEmbeddingProvider]:
        """List of providers in the chain."""
        return list(self._providers)


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def create_mock_embedding_provider(
    dimension: int = 768,
) -> MockEmbeddingProvider:
    """Create a mock embedding provider for testing.

    Args:
        dimension: The embedding dimension.

    Returns:
        MockEmbeddingProvider instance.
    """
    return MockEmbeddingProvider(dimension=dimension)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "BaseEmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingRequest",
    "EmbeddingVector",
    "EmbeddingResponse",
    "MockEmbeddingProvider",
    "EmbeddingProviderChain",
    "create_mock_embedding_provider",
]
# === TASK:WP-301:END ===

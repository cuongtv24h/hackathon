# === TASK:WP-301:START ===
"""Unit tests for WP-301 AI Provider Abstraction.

These tests verify the LLM and embedding provider implementations defined in:
- apps/api/ai/providers/llm_provider.py
- apps/api/ai/providers/embedding_provider.py

The tests use mocks/fakes for provider calls as required by
docs/spec-registry/runtime-test-policy.yaml.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from apps.api.ai.providers.llm_provider import (
    BaseLLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    ReasoningResultDTO,
    MockLLMProvider,
    OpenAICompatibleLLMProvider,
    RuntimeLLMAdapter,
    LLMProviderChain,
    create_mock_provider_chain,
    create_runtime_provider_chain,
    LLM_TIMEOUT,
    LLM_RATE_LIMITED,
    LLM_CONTENT_FILTERED,
)

from apps.api.ai.providers.embedding_provider import (
    BaseEmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingRequest,
    EmbeddingVector,
    EmbeddingResponse,
    MockEmbeddingProvider,
    EmbeddingProviderChain,
    create_mock_embedding_provider,
)

from packages.contracts import (
    AI_PROVIDER_UNAVAILABLE,
    CATEGORY_AI,
)


# ---------------------------------------------------------------------------
# LLM Provider Tests
# ---------------------------------------------------------------------------


class TestLLMRequest:
    """Tests for LLMRequest DTO."""

    def test_creates_with_required_fields(self) -> None:
        """Test creating request with minimal fields."""
        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])
        assert len(request.messages) == 1
        assert request.max_tokens == 1024
        assert request.temperature == 0.7

    def test_validates_messages_required(self) -> None:
        """Test that messages must be provided."""
        with pytest.raises(ValueError, match="messages must be non-empty"):
            LLMRequest(messages=[])

    def test_validates_temperature_range(self) -> None:
        """Test that temperature must be in valid range."""
        with pytest.raises(ValueError, match="temperature"):
            LLMRequest(
                messages=[{"role": "user", "content": "Test"}],
                temperature=3.0,
            )

    def test_validates_max_tokens_positive(self) -> None:
        """Test that max_tokens must be positive."""
        with pytest.raises(ValueError, match="max_tokens"):
            LLMRequest(
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=0,
            )


class TestLLMResponse:
    """Tests for LLMResponse DTO."""

    def test_creates_with_content(self) -> None:
        """Test creating response with content."""
        response = LLMResponse(content="Hello, world!")
        assert response.content == "Hello, world!"
        assert response.finish_reason == "stop"

    def test_to_dict_returns_valid_dict(self) -> None:
        """Test that to_dict returns a valid dictionary."""
        response = LLMResponse(
            content="Test",
            tool_calls=[{"name": "test_tool"}],
            usage={"total_tokens": 100},
            model="gpt-4",
            provider="openai",
        )
        result = response.to_dict()

        assert result["content"] == "Test"
        assert len(result["tool_calls"]) == 1
        assert result["usage"]["total_tokens"] == 100

    def test_latency_is_populated(self) -> None:
        """Test that latency can be set."""
        response = LLMResponse(content="Test", latency_ms=123.45)
        assert response.latency_ms == 123.45


class TestReasoningResultDTO:
    """Tests for ReasoningResultDTO (INT-05)."""

    def test_creates_with_defaults(self) -> None:
        """Test creating with default values."""
        result = ReasoningResultDTO()
        assert result.intent_labels == []
        assert result.domains == []
        assert result.clarity == "clear"
        assert result.scope == "in_scope"
        assert result.safety_disposition == "safe"

    def test_creates_with_values(self) -> None:
        """Test creating with custom values."""
        result = ReasoningResultDTO(
            intent_labels=["information_query"],
            domains=["BHYT", "appointment"],
            clarity="clear",
            missing_information=["patient_id"],
            scope="in_scope",
            safety_disposition="safe",
            confidence_band="high",
        )
        assert len(result.intent_labels) == 1
        assert len(result.domains) == 2
        assert result.confidence_band == "high"

    def test_to_dict_returns_valid_dict(self) -> None:
        """Test that to_dict returns valid structure."""
        result = ReasoningResultDTO(
            intent_labels=["test"],
            domains=["test_domain"],
        )
        d = result.to_dict()

        assert "intent_labels" in d
        assert "domains" in d
        assert "clarity" in d
        assert "safety_disposition" in d


class TestMockLLMProvider:
    """Tests for MockLLMProvider."""

    def test_returns_configured_response(self) -> None:
        """Test that provider returns configured response."""
        provider = MockLLMProvider(
            name="test",
            model="test-model",
            response_content="This is a test response.",
        )
        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])
        response = provider.generate(request)

        assert response.content == "This is a test response."
        assert response.provider == "test"
        assert response.model == "test-model"

    def test_returns_tool_calls(self) -> None:
        """Test that provider can return tool calls."""
        tool_calls = [{"name": "search_knowledge_base", "arguments": {"query": "test"}}]
        provider = MockLLMProvider(
            response_content="",
            response_tool_calls=tool_calls,
        )
        request = LLMRequest(messages=[{"role": "user", "content": "Search"}])
        response = provider.generate(request)

        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["name"] == "search_knowledge_base"

    def test_raises_timeout_error(self) -> None:
        """Test that provider can simulate timeout."""
        provider = MockLLMProvider(raise_error="timeout")
        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate(request)

        assert exc_info.value.envelope.error.code == AI_PROVIDER_UNAVAILABLE

    def test_raises_rate_limit_error(self) -> None:
        """Test that provider can simulate rate limit."""
        provider = MockLLMProvider(raise_error="rate_limit")
        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate(request)

        assert exc_info.value.envelope.error.code == LLM_RATE_LIMITED

    def test_raises_content_filter_error(self) -> None:
        """Test that provider can simulate content filter."""
        provider = MockLLMProvider(raise_error="content_filter")
        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate(request)

        assert exc_info.value.envelope.error.code == LLM_CONTENT_FILTERED

    def test_can_set_response_dynamically(self) -> None:
        """Test that response can be changed dynamically."""
        provider = MockLLMProvider(response_content="Initial")
        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])

        response1 = provider.generate(request)
        assert response1.content == "Initial"

        provider.set_response("Updated")
        response2 = provider.generate(request)
        assert response2.content == "Updated"

    def test_tracks_call_count(self) -> None:
        """Test that provider tracks number of calls."""
        provider = MockLLMProvider()
        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])

        assert provider.call_count == 0
        provider.generate(request)
        assert provider.call_count == 1
        provider.generate(request)
        assert provider.call_count == 2


class TestRuntimeLLMProvider:
    """Tests for the real-provider adapter without network access."""

    def test_posts_openai_compatible_payload_and_maps_response(self) -> None:
        calls = []

        class FakeResponse:
            status_code = 200
            headers = {}

            def json(self):
                return {
                    "model": "provider-model",
                    "choices": [{"message": {"content": "Grounded answer"}, "finish_reason": "stop"}],
                    "usage": {"total_tokens": 12},
                }

        class FakeClient:
            def __init__(self, **kwargs):
                calls.append({"timeout": kwargs["timeout"]})

            def post(self, url, headers, json):
                calls.append({"url": url, "headers": headers, "json": json})
                return FakeResponse()

            def close(self):
                return None

        provider = OpenAICompatibleLLMProvider(
            name="primary",
            model="configured-model",
            base_url="https://provider.example/v1",
            api_key="test-key",
            client_factory=FakeClient,
        )
        response = provider.generate(LLMRequest(messages=[{"role": "user", "content": "Hello"}]))

        assert response.content == "Grounded answer"
        assert response.provider == "primary"
        assert calls[1]["url"] == "https://provider.example/v1/chat/completions"
        assert calls[1]["json"]["model"] == "configured-model"
        assert calls[1]["headers"]["Authorization"] == "Bearer test-key"

    def test_runtime_adapter_preserves_grounded_context(self) -> None:
        provider = MockLLMProvider(response_content="Grounded answer")
        adapter = RuntimeLLMAdapter(LLMProviderChain([provider]))

        response = adapter.generate({
            "messages": [{"role": "user", "content": "What is the price?"}],
            "context": "[price] Approved service price",
        })

        assert response["content"] == "Grounded answer"
        assert provider.call_count == 1

    def test_runtime_factory_uses_primary_then_diverse_fallback(self) -> None:
        chain = create_runtime_provider_chain({
            "GEMINI_API_KEY": "primary-key",
            "OPENROUTER_API_KEY": "fallback-key",
        })

        assert [provider.name for provider in chain.providers] == ["gemini", "openrouter"]

    def test_runtime_factory_rejects_mock_only_configuration(self) -> None:
        with pytest.raises(ValueError, match="No real LLM provider"):
            create_runtime_provider_chain({})

    def test_runtime_factory_honors_configured_provider_order(self) -> None:
        chain = create_runtime_provider_chain({
            "LLM_PROVIDER_ORDER": "groq,gemini,openrouter",
            "LLM_GROQ_API_KEY": "groq-key",
            "LLM_GEMINI_API_KEY": "gemini-key",
            "LLM_OPENROUTER_API_KEY": "openrouter-key",
        })

        assert [provider.name for provider in chain.providers] == [
            "groq", "gemini", "openrouter"
        ]
        assert chain.providers[0].model == "llama-3.3-70b-versatile"

    def test_runtime_factory_rejects_ordered_provider_without_key(self) -> None:
        with pytest.raises(ValueError, match="groq.*no API key"):
            create_runtime_provider_chain({
                "LLM_PROVIDER_ORDER": "gemini,groq",
                "LLM_GEMINI_API_KEY": "gemini-key",
            })

    def test_runtime_factory_accepts_legacy_grok_alias_for_groq(self) -> None:
        chain = create_runtime_provider_chain({
            "LLM_PROVIDER_ORDER": "grok",
            "LLM_GROK_API_KEY": "legacy-groq-key",
            "LLM_GROK_BASE_URL": "https://api.groq.com/openai/v1",
        })

        assert [provider.name for provider in chain.providers] == ["groq"]


class TestLLMProviderChain:
    """Tests for LLMProviderChain."""

    def test_uses_first_available_provider(self) -> None:
        """Test that chain uses first provider when available."""
        provider1 = MockLLMProvider(name="first", response_content="Response 1")
        provider2 = MockLLMProvider(name="second", response_content="Response 2")
        chain = LLMProviderChain([provider1, provider2])

        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])
        response = chain.generate(request)

        assert response.content == "Response 1"
        assert provider1.call_count == 1
        assert provider2.call_count == 0

    def test_falls_back_on_failure(self) -> None:
        """Test that chain falls back to next provider on failure."""
        provider1 = MockLLMProvider(name="first", raise_error="unavailable")
        provider2 = MockLLMProvider(name="second", response_content="Response 2")
        chain = LLMProviderChain([provider1, provider2])

        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])
        response = chain.generate(request)

        assert response.content == "Response 2"
        assert provider1.call_count == 1
        assert provider2.call_count == 1

    def test_raises_error_when_all_fail(self) -> None:
        """Test that chain raises error when all providers fail."""
        provider1 = MockLLMProvider(name="first", raise_error="unavailable")
        provider2 = MockLLMProvider(name="second", raise_error="unavailable")
        chain = LLMProviderChain([provider1, provider2])

        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])

        with pytest.raises(LLMProviderError) as exc_info:
            chain.generate(request)

        assert exc_info.value.envelope.error.code == AI_PROVIDER_UNAVAILABLE

    def test_requires_at_least_one_provider(self) -> None:
        """Test that chain requires at least one provider."""
        with pytest.raises(ValueError, match="providers list must not be empty"):
            LLMProviderChain([])

    def test_returns_fallback_message(self) -> None:
        """Test that chain can return static fallback message."""
        provider = MockLLMProvider()
        chain = LLMProviderChain([provider], fallback_message="Fallback message")

        assert chain.get_fallback_message() == "Fallback message"

    def test_exposes_providers_list(self) -> None:
        """Test that chain exposes providers list."""
        provider = MockLLMProvider()
        chain = LLMProviderChain([provider])

        assert len(chain.providers) == 1

    def test_does_not_fallback_after_content_filter(self) -> None:
        filtered = MockLLMProvider(name="filtered", raise_error="content_filter")
        fallback = MockLLMProvider(name="fallback", response_content="must not be used")
        chain = LLMProviderChain([filtered, fallback])
        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])

        with pytest.raises(LLMProviderError) as exc_info:
            chain.generate(request)

        assert exc_info.value.envelope.error.code == LLM_CONTENT_FILTERED
        assert fallback.call_count == 0


class TestCreateMockProviderChain:
    """Tests for create_mock_provider_chain factory."""

    def test_creates_functional_chain(self) -> None:
        """Test that factory creates a working chain."""
        chain = create_mock_provider_chain("Test response")
        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])
        response = chain.generate(request)

        assert response.content == "Test response"


# ---------------------------------------------------------------------------
# Embedding Provider Tests
# ---------------------------------------------------------------------------


class TestEmbeddingRequest:
    """Tests for EmbeddingRequest DTO."""

    def test_creates_with_texts(self) -> None:
        """Test creating request with texts."""
        request = EmbeddingRequest(texts=["Hello", "World"])
        assert len(request.texts) == 2

    def test_validates_texts_required(self) -> None:
        """Test that texts must be provided."""
        with pytest.raises(ValueError, match="texts must be non-empty"):
            EmbeddingRequest(texts=[])

    def test_validates_texts_not_empty(self) -> None:
        """Test that texts cannot contain empty strings."""
        with pytest.raises(ValueError, match="must be non-empty"):
            EmbeddingRequest(texts=["Hello", ""])


class TestEmbeddingResponse:
    """Tests for EmbeddingResponse DTO."""

    def test_creates_with_embeddings(self) -> None:
        """Test creating response with embeddings."""
        embeddings = [EmbeddingVector(vector=[0.1, 0.2], index=0)]
        response = EmbeddingResponse(embeddings=embeddings)

        assert len(response.embeddings) == 1
        assert response.vectors[0] == [0.1, 0.2]

    def test_to_dict_returns_valid_dict(self) -> None:
        """Test that to_dict returns valid structure."""
        embeddings = [EmbeddingVector(vector=[0.1, 0.2], index=0, model="test")]
        response = EmbeddingResponse(
            embeddings=embeddings,
            model="test",
            provider="mock",
        )
        d = response.to_dict()

        assert "embeddings" in d
        assert len(d["embeddings"]) == 1


class TestMockEmbeddingProvider:
    """Tests for MockEmbeddingProvider."""

    def test_returns_embeddings(self) -> None:
        """Test that provider returns embeddings."""
        provider = MockEmbeddingProvider(dimension=128)
        request = EmbeddingRequest(texts=["Hello", "World"])
        response = provider.embed(request)

        assert len(response.embeddings) == 2
        assert len(response.embeddings[0].vector) == 128
        assert len(response.embeddings[1].vector) == 128

    def test_returns_deterministic_embeddings(self) -> None:
        """Test that same text produces same embedding."""
        provider = MockEmbeddingProvider(dimension=64)
        request1 = EmbeddingRequest(texts=["Hello"])
        request2 = EmbeddingRequest(texts=["Hello"])

        response1 = provider.embed(request1)
        response2 = provider.embed(request2)

        assert response1.vectors[0] == response2.vectors[0]

    def test_different_texts_produce_different_embeddings(self) -> None:
        """Test that different texts produce different embeddings."""
        provider = MockEmbeddingProvider(dimension=64)
        request = EmbeddingRequest(texts=["Hello", "Goodbye"])
        response = provider.embed(request)

        assert response.vectors[0] != response.vectors[1]

    def test_embed_single_convenience_method(self) -> None:
        """Test embed_single convenience method."""
        provider = MockEmbeddingProvider(dimension=32)
        vector = provider.embed_single("Hello")

        assert len(vector) == 32

    def test_raises_timeout_error(self) -> None:
        """Test that provider can simulate timeout."""
        provider = MockEmbeddingProvider(raise_error="timeout")
        request = EmbeddingRequest(texts=["Hello"])

        with pytest.raises(EmbeddingProviderError) as exc_info:
            provider.embed(request)

        assert exc_info.value.envelope.error.code == AI_PROVIDER_UNAVAILABLE

    def test_tracks_call_count(self) -> None:
        """Test that provider tracks calls."""
        provider = MockEmbeddingProvider()
        request = EmbeddingRequest(texts=["Hello"])

        assert provider.call_count == 0
        provider.embed(request)
        assert provider.call_count == 1


class TestEmbeddingProviderChain:
    """Tests for EmbeddingProviderChain."""

    def test_uses_first_available_provider(self) -> None:
        """Test that chain uses first provider."""
        provider1 = MockEmbeddingProvider(name="first", dimension=64)
        provider2 = MockEmbeddingProvider(name="second", dimension=64)
        chain = EmbeddingProviderChain([provider1, provider2])

        request = EmbeddingRequest(texts=["Hello"])
        response = chain.embed(request)

        assert provider1.call_count == 1
        assert provider2.call_count == 0

    def test_falls_back_on_failure(self) -> None:
        """Test that chain falls back on failure."""
        provider1 = MockEmbeddingProvider(name="first", dimension=64, raise_error="unavailable")
        provider2 = MockEmbeddingProvider(name="second", dimension=64)
        chain = EmbeddingProviderChain([provider1, provider2])

        request = EmbeddingRequest(texts=["Hello"])
        response = chain.embed(request)

        assert provider1.call_count == 1
        assert provider2.call_count == 1

    def test_raises_error_when_all_fail(self) -> None:
        """Test that chain raises error when all fail."""
        provider1 = MockEmbeddingProvider(name="first", raise_error="unavailable")
        provider2 = MockEmbeddingProvider(name="second", raise_error="unavailable")
        chain = EmbeddingProviderChain([provider1, provider2])

        request = EmbeddingRequest(texts=["Hello"])

        with pytest.raises(EmbeddingProviderError):
            chain.embed(request)

    def test_requires_same_dimension(self) -> None:
        """Test that all providers must have same dimension."""
        provider1 = MockEmbeddingProvider(dimension=64)
        provider2 = MockEmbeddingProvider(dimension=128)

        with pytest.raises(ValueError, match="same dimension"):
            EmbeddingProviderChain([provider1, provider2])

    def test_exposes_dimension(self) -> None:
        """Test that chain exposes dimension."""
        provider = MockEmbeddingProvider(dimension=256)
        chain = EmbeddingProviderChain([provider])

        assert chain.dimension == 256


class TestCreateMockEmbeddingProvider:
    """Tests for create_mock_embedding_provider factory."""

    def test_creates_provider_with_dimension(self) -> None:
        """Test that factory creates provider with specified dimension."""
        provider = create_mock_embedding_provider(dimension=512)
        request = EmbeddingRequest(texts=["Test"])
        response = provider.embed(request)

        assert len(response.vectors[0]) == 512


# ---------------------------------------------------------------------------
# Contract shape tests (INT-05, ARCH-03)
# ---------------------------------------------------------------------------


class TestContractShape:
    """Tests verifying contract shapes match specification."""

    def test_llm_request_has_required_fields(self) -> None:
        """Verify LLMRequest has required fields per contract."""
        request = LLMRequest(messages=[{"role": "user", "content": "Test"}])

        assert hasattr(request, "messages")
        assert hasattr(request, "max_tokens")
        assert hasattr(request, "temperature")

    def test_llm_response_has_required_fields(self) -> None:
        """Verify LLMResponse has required fields per contract."""
        response = LLMResponse(content="Test")

        assert hasattr(response, "content")
        assert hasattr(response, "model")
        assert hasattr(response, "provider")
        assert hasattr(response, "finish_reason")

    def test_reasoning_result_has_required_fields(self) -> None:
        """Verify ReasoningResultDTO has required fields (INT-05)."""
        result = ReasoningResultDTO()

        assert hasattr(result, "intent_labels")
        assert hasattr(result, "domains")
        assert hasattr(result, "clarity")
        assert hasattr(result, "scope")
        assert hasattr(result, "safety_disposition")
        assert hasattr(result, "confidence_band")

    def test_embedding_request_has_required_fields(self) -> None:
        """Verify EmbeddingRequest has required fields."""
        request = EmbeddingRequest(texts=["Test"])

        assert hasattr(request, "texts")

    def test_embedding_response_has_required_fields(self) -> None:
        """Verify EmbeddingResponse has required fields."""
        response = EmbeddingResponse(
            embeddings=[EmbeddingVector(vector=[0.1], index=0)]
        )

        assert hasattr(response, "embeddings")
        assert hasattr(response, "model")
        assert hasattr(response, "provider")


# ---------------------------------------------------------------------------
# Error contract tests (INT-07)
# ---------------------------------------------------------------------------


class TestErrorContract:
    """Tests verifying error envelopes comply with INT-07."""

    def test_llm_error_has_required_fields(self) -> None:
        """Test that LLM errors contain all required envelope fields."""
        provider = MockLLMProvider(raise_error="unavailable")
        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate(request)

        envelope = exc_info.value.envelope
        assert hasattr(envelope, "trace_id")
        assert hasattr(envelope, "error")
        assert hasattr(envelope.error, "code")
        assert hasattr(envelope.error, "message")
        assert hasattr(envelope.error, "category")

    def test_embedding_error_has_required_fields(self) -> None:
        """Test that embedding errors contain all required envelope fields."""
        provider = MockEmbeddingProvider(raise_error="unavailable")
        request = EmbeddingRequest(texts=["Hello"])

        with pytest.raises(EmbeddingProviderError) as exc_info:
            provider.embed(request)

        envelope = exc_info.value.envelope
        assert hasattr(envelope, "trace_id")
        assert hasattr(envelope, "error")
        assert hasattr(envelope.error, "code")

    def test_error_to_dict_returns_valid_dict(self) -> None:
        """Test that error to_dict returns valid dictionary."""
        provider = MockLLMProvider(raise_error="unavailable")
        request = LLMRequest(messages=[{"role": "user", "content": "Hello"}])

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate(request)

        error_dict = exc_info.value.to_dict()
        assert isinstance(error_dict, dict)
        assert "trace_id" in error_dict
        assert "error" in error_dict


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "TestLLMRequest",
    "TestLLMResponse",
    "TestReasoningResultDTO",
    "TestMockLLMProvider",
    "TestLLMProviderChain",
    "TestCreateMockProviderChain",
    "TestEmbeddingRequest",
    "TestEmbeddingResponse",
    "TestMockEmbeddingProvider",
    "TestEmbeddingProviderChain",
    "TestCreateMockEmbeddingProvider",
    "TestContractShape",
    "TestErrorContract",
]
# === TASK:WP-301:END ===

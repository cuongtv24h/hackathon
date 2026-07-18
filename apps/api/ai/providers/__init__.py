"""AI provider abstraction package.

This package provides provider isolation for LLM and embedding operations.
"""

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
from apps.api.ai.providers.openai import OpenAIProvider, SafetyEvaluationOutput

__all__ = [
    # LLM
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
    # Embedding
    "BaseEmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingRequest",
    "EmbeddingVector",
    "EmbeddingResponse",
    "MockEmbeddingProvider",
    "EmbeddingProviderChain",
    "create_mock_embedding_provider",
    "OpenAIProvider",
    "SafetyEvaluationOutput",
]

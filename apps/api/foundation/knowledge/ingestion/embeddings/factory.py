# === TASK:WP-008:START ===
from .base import EmbeddingProvider
from .openai import OpenAIEmbeddingProvider
from .gemini import GeminiEmbeddingProvider
from .jina import JinaEmbeddingProvider
from ..settings import EMBEDDING_PROVIDER, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, JINA_BASE_URL
from ..errors import ConfigurationError

def get_embedding_provider(
    provider_name: str = None,
    model: str = None,
    dimensions: int = None
) -> EmbeddingProvider:
    if provider_name is None:
        provider_name = EMBEDDING_PROVIDER
    if model is None:
        model = EMBEDDING_MODEL
    if dimensions is None:
        dimensions = EMBEDDING_DIMENSIONS
        
    p_name = provider_name.lower()
    if p_name == "jina":
        return JinaEmbeddingProvider(
            model=model,
            dimensions=dimensions,
            base_url=JINA_BASE_URL,
        )
    elif p_name == "openai":
        return OpenAIEmbeddingProvider(model=model, dimensions=dimensions)
    elif p_name in ("gemini", "google"):
        return GeminiEmbeddingProvider(model=model)
    else:
        raise ConfigurationError(f"Unsupported embedding provider: {provider_name}")
# === TASK:WP-008:END ===

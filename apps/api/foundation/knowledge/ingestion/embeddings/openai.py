# === TASK:WP-008:START ===
import os
from typing import List
from .base import EmbeddingProvider
from ..errors import ConfigurationError

class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Adapter for OpenAI Embedding API."""

    def __init__(self, model: str = "text-embedding-3-small", dimensions: int = 1536):
        self.model = model
        self.dimensions = dimensions
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is not configured in the environment."
            )
        self._client = None

    def _get_client(self):
        """Create the SDK client once and reuse its connection pool."""
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ConfigurationError(
                "The 'openai' Python package is not installed."
            ) from exc
        self._client = OpenAI(api_key=self.api_key)
        return self._client

    def embed(self, content: str) -> List[float]:
        if not self.api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is not configured in the environment."
            )
        kwargs = {"model": self.model, "input": content}
        if self.dimensions and self.model in ("text-embedding-3-small", "text-embedding-3-large"):
            kwargs["dimensions"] = self.dimensions

        response = self._get_client().embeddings.create(**kwargs)
        return response.data[0].embedding
# === TASK:WP-008:END ===

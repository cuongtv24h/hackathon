# === TASK:WP-008:START ===
import os
from typing import List
from .base import EmbeddingProvider
from ..errors import ConfigurationError

class GeminiEmbeddingProvider(EmbeddingProvider):
    """Adapter for Google Gemini Embedding API."""

    def __init__(self, model: str = "text-embedding-004"):
        self.model = model
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ConfigurationError(
                "GEMINI_API_KEY is not configured in the environment."
            )

    def embed(self, content: str) -> List[float]:
        if not self.api_key:
            raise ConfigurationError(
                "GEMINI_API_KEY is not configured in the environment."
            )
        try:
            from google import genai
        except ImportError:
            raise ConfigurationError(
                "The 'google-genai' package is not installed."
            )

        client = genai.Client(api_key=self.api_key)
        response = client.models.embed_content(
            model=self.model,
            contents=content,
        )
        return response.embeddings[0].values
# === TASK:WP-008:END ===

# === TASK:WP-008:START ===
"""Jina embedding adapter using its OpenAI-compatible API surface."""

import os
import time
from typing import List
from urllib.parse import urlparse

from .base import EmbeddingProvider
from ..errors import ConfigurationError, IngestionError
from ..settings import EMBEDDING_MAX_RETRIES, EMBEDDING_RETRY_BASE_SECONDS


class JinaEmbeddingProvider(EmbeddingProvider):
    """Generate document embeddings with Jina's retrieval-passage task."""

    def __init__(
        self,
        model: str = "jina-embeddings-v5-text-small",
        dimensions: int = 1024,
        base_url: str = "https://api.jina.ai/v1",
    ):
        self.model = model
        self.dimensions = dimensions
        self.base_url = base_url.rstrip("/")
        self.api_key = os.environ.get("JINA_API_KEY")
        self._client = None

        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigurationError("JINA_BASE_URL must be a valid HTTPS URL.")
        if not self.api_key:
            raise ConfigurationError("JINA_API_KEY is not configured in the environment.")

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ConfigurationError("The 'openai' Python package is not installed.") from exc
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def embed(self, content: str) -> List[float]:
        return self.embed_batch([content])[0]

    def embed_batch(self, contents: List[str]) -> List[List[float]]:
        if not contents:
            return []
        last_error = None
        for attempt in range(EMBEDDING_MAX_RETRIES):
            try:
                response = self._get_client().embeddings.create(
                    model=self.model,
                    input=contents,
                    dimensions=self.dimensions,
                    extra_body={"task": "retrieval.passage"},
                )
                rows = list(response.data or [])
                if len(rows) != len(contents):
                    raise IngestionError(
                        f"Jina returned {len(rows)} embeddings for {len(contents)} inputs."
                    )
                if all(getattr(row, "index", None) is not None for row in rows):
                    rows.sort(key=lambda row: row.index)
                embeddings = [row.embedding for row in rows]
                if any(not embedding for embedding in embeddings):
                    raise IngestionError("Jina returned an empty embedding.")
                return embeddings
            except ConfigurationError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt + 1 < EMBEDDING_MAX_RETRIES:
                    time.sleep(EMBEDDING_RETRY_BASE_SECONDS * (2 ** attempt))
        if isinstance(last_error, IngestionError):
            raise last_error
        raise IngestionError(
            f"Jina embedding request failed after {EMBEDDING_MAX_RETRIES} attempts: "
            f"{type(last_error).__name__}"
        ) from last_error
# === TASK:WP-008:END ===

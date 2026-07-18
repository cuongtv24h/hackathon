# === TASK:WP-008:START ===
from typing import List

class EmbeddingProvider:
    """Abstract port for embedding providers."""
    
    def embed(self, content: str) -> List[float]:
        raise NotImplementedError("EmbeddingProvider subclass must implement embed")

    def embed_batch(self, contents: List[str]) -> List[List[float]]:
        """Compatibility fallback for providers without native batching."""
        return [self.embed(content) for content in contents]
# === TASK:WP-008:END ===

# === TASK:WP-008:START ===
import os

# Embedding profile configuration
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "jina").lower()
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "jina-embeddings-v5-text-small")
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))
JINA_BASE_URL = os.environ.get("JINA_BASE_URL", "https://api.jina.ai/v1")
EMBEDDING_BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "64"))
EMBEDDING_MAX_RETRIES = int(os.environ.get("EMBEDDING_MAX_RETRIES", "3"))
EMBEDDING_RETRY_BASE_SECONDS = float(os.environ.get("EMBEDDING_RETRY_BASE_SECONDS", "1"))

# Token Policy Constraints
TARGET_MIN_TOKENS = 300
TARGET_MAX_TOKENS = 600
HARD_MAX_TOKENS = 800
PROSE_OVERLAP_TOKENS = 50
CHAR_CEILING = 4000
# === TASK:WP-008:END ===

# === TASK:WP-008:START ===
class IngestionError(Exception):
    """Base exception for all ingestion-related errors."""
    pass


class ValidationError(ValueError, IngestionError):
    """Raised when source, chunk or embedding validation fails."""
    pass


class ConfigurationError(ValueError, IngestionError):
    """Raised when settings or environment configuration is invalid."""
    pass
# === TASK:WP-008:END ===

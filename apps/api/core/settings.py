# === TASK:WP-010:START ===
"""Application settings loaded from environment via pydantic-settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration for the Hospital Assistant API.

    All values are loaded from environment variables.
    No secrets, database URLs, or provider credentials are stored here.
    """

    app_name: str = "HospitalAssistant"
    debug: bool = False
    api_prefix: str = "/api/v1"

    model_config = {"env_prefix": "HA_", "case_sensitive": False}
# === TASK:WP-010:END ===

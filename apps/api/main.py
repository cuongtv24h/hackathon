# === TASK:WP-010:START ===
"""FastAPI application entry point for the Hospital Assistant API.

This module creates the ASGI application instance. Feature routers,
provider calls and database connections are added by later work packages.
"""

from fastapi import FastAPI

from apps.api.core.settings import Settings

settings = Settings()

app = FastAPI(
    title=settings.app_name,
    docs_url=f"{settings.api_prefix}/docs",
    openapi_url=f"{settings.api_prefix}/openapi.json",
)
# === TASK:WP-010:END ===

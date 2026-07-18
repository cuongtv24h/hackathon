# === TASK:WP-010:START ===
"""FastAPI application entry point for the Hospital Assistant API.

This module creates the ASGI application instance. Feature routers,
provider calls and database connections are added by later work packages.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from apps.api.core.settings import Settings
from apps.api.core.runtime_dependencies import (
    RuntimeDependencyError,
)
from apps.api.ai.orchestrator.core.web_adapter import (
    build_agent_information_assistance_adapter,
)
from apps.api.core.runtime_persistence import build_operational_runtime
from apps.api.gateway.capabilities.information_assistance.router import (
    router as information_assistance_router,
    set_information_assistance_pipeline,
)
from apps.api.gateway.capabilities.emergency_safety.router import (
    router as emergency_safety_router,
    set_emergency_safety_pipeline,
)
from apps.api.gateway.capabilities.appointment_booking.router import (
    router as appointment_booking_router,
    set_appointment_booking_pipeline,
)
from apps.api.gateway.capabilities.appointment_status.router import (
    router as appointment_status_router,
    set_appointment_status_pipeline,
)
from apps.api.ai.orchestrator.emergency_safety.pipeline import EmergencySafetyPipeline
from apps.api.ai.orchestrator.appointment_booking.pipeline import AppointmentBookingPipeline
from apps.api.ai.orchestrator.appointment_status.pipeline import AppointmentStatusPipeline
from apps.api.foundation.appointments.tools.service import create_appointment_tools
from apps.api.gateway.admin.router import router as admin_router
from apps.api.gateway.foundation.appointments_router import router as foundation_appointments_router

logger = logging.getLogger(__name__)

# Local development only; deployment environments keep using their injected
# environment variables. Existing environment values are never overwritten.
load_dotenv(override=False)

settings = Settings()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHAT_WEB_DIST = PROJECT_ROOT / "apps" / "chat-web" / "dist"
ADMIN_WEB_DIST = PROJECT_ROOT / "apps" / "admin-web" / "dist"


def cors_allow_origins():
    """Return the explicit browser origins permitted to call the API."""
    configured = os.environ.get(
        "CORS_ALLOW_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174",
    )
    return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]


def _static_file_or_none(directory: Path, relative_path: str) -> Path | None:
    """Resolve a static asset without allowing paths outside its build directory."""
    candidate = (directory / relative_path).resolve()
    try:
        candidate.relative_to(directory.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _spa_response(directory: Path, relative_path: str) -> FileResponse:
    """Serve a built asset or the SPA entry point for a client-side route."""
    if not directory.is_dir():
        raise HTTPException(
            status_code=503,
            detail="Frontend build is unavailable. Build the web application before serving it.",
        )

    asset = _static_file_or_none(directory, relative_path)
    if asset:
        headers = {"Cache-Control": "public, max-age=31536000, immutable"} if "/assets/" in asset.as_posix() else {}
        return FileResponse(asset, headers=headers)

    entry_point = directory / "index.html"
    if not entry_point.is_file():
        raise HTTPException(status_code=503, detail="Frontend entry point is unavailable.")
    return FileResponse(entry_point, headers={"Cache-Control": "no-cache"})

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Wire capability dependencies at process start without exposing secrets."""
    try:
        app_instance.state.operational_runtime = build_operational_runtime()
        logger.info("Configured shared operational persistence runtime")
    except Exception:
        app_instance.state.operational_runtime = None
        logger.error("Operational persistence dependency is unavailable", exc_info=False)

    try:
        set_information_assistance_pipeline(build_agent_information_assistance_adapter())
        logger.info("Configured PC-01 with the LangGraph hospital agent")
    except (RuntimeDependencyError, ValueError):
        logger.warning("PC-01 runtime dependencies are unavailable; requests use safe grounded fallback")

    # PC-02 is intentionally local-config based and does not depend on the
    # internet, LLM availability or Supabase for its critical path.
    set_emergency_safety_pipeline(EmergencySafetyPipeline())

    his_base_url = os.environ.get("MOCK_HIS_BASE_URL", "")
    parsed_his_url = urlparse(his_base_url)
    if parsed_his_url.scheme in {"http", "https"} and parsed_his_url.netloc:
        appointment_tools = create_appointment_tools(his_base_url=his_base_url)
        set_appointment_booking_pipeline(
            AppointmentBookingPipeline(appointment_tools=appointment_tools)
        )
        set_appointment_status_pipeline(
            AppointmentStatusPipeline(appointment_tools=appointment_tools)
        )
        logger.info("Configured PC-03 and PC-04 with Mock HIS adapter")
    else:
        logger.warning("PC-03 and PC-04 are exposed but not configured: MOCK_HIS_BASE_URL must be an http(s) URL")
    yield


app = FastAPI(
    title=settings.app_name,
    docs_url=f"{settings.api_prefix}/docs",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-Trace-Id"],
    expose_headers=["X-Trace-Id"],
)

app.include_router(information_assistance_router)
app.include_router(emergency_safety_router)
app.include_router(appointment_booking_router)
app.include_router(appointment_status_router)
app.include_router(admin_router)
app.include_router(foundation_appointments_router)


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
async def serve_admin_home():
    """Serve the Admin React application from its production build."""
    return _spa_response(ADMIN_WEB_DIST, "")


@app.get("/admin/{asset_path:path}", include_in_schema=False)
async def serve_admin_static(asset_path: str):
    """Serve Admin assets and client-side routes below ``/admin``."""
    return _spa_response(ADMIN_WEB_DIST, asset_path)


@app.get("/", include_in_schema=False)
async def serve_chat_home():
    """Serve the Chat React application from its production build."""
    return _spa_response(CHAT_WEB_DIST, "")


@app.get("/{asset_path:path}", include_in_schema=False)
async def serve_chat_static(asset_path: str):
    """Serve Chat assets and SPA routes without masking API routing mistakes."""
    reserved_prefixes = ("v1", "docs", "openapi.json", "redoc", "admin")
    if asset_path == "v1" or asset_path.startswith("v1/") or asset_path in reserved_prefixes:
        raise HTTPException(status_code=404, detail="Not Found")
    return _spa_response(CHAT_WEB_DIST, asset_path)
# === TASK:WP-010:END ===

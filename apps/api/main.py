# === TASK:WP-010:START ===
"""FastAPI application entry point for the Hospital Assistant API.

This module creates the ASGI application instance. Feature routers,
provider calls and database connections are added by later work packages.
"""

import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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


def cors_allow_origins():
    """Return the explicit browser origins permitted to call the API."""
    configured = os.environ.get(
        "CORS_ALLOW_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174",
    )
    return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]

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
# === TASK:WP-010:END ===

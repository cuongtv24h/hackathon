# === TASK:WP-404:START ===
"""FastAPI router for the PC-04 Appointment Status capability.

The module exposes the canonical public endpoint
``POST /v1/capabilities/appointment-status:execute`` and adapts request JSON
to the WP-306 appointment-status pipeline without changing the pipeline's
public contracts or requesting additional patient data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from apps.api.core.runtime_persistence import (
    append_assistant_turn,
    append_user_turn,
    get_operational_runtime,
    write_audit,
)
from apps.api.ai.orchestrator.appointment_status.pipeline import (
    AppointmentStatusPipeline,
    AppointmentStatusRequest,
)

CAPABILITY_NAME = "appointment_status"
CAPABILITY_ROUTE = "/v1/capabilities/appointment-status:execute"
VALID_RESPONSE_MODES = {"sync", "stream"}

router = APIRouter()
_default_pipeline: AppointmentStatusPipeline | None = None


class AppointmentStatusExecuteRequest(BaseModel):
    """Gateway request DTO for PC-04.

    Only the minimal approved appointment reference is accepted and passed to
    the canonical ``AppointmentStatusRequest`` consumed by the orchestrator.
    """

    request_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    appointment_reference: Dict[str, str] = Field(...)
    response_mode: str = "sync"

    @field_validator("appointment_reference")
    @classmethod
    def validate_appointment_reference(cls, value: Dict[str, str]) -> Dict[str, str]:
        if set(value.keys()) != {"appointment_id"}:
            raise ValueError("appointment_reference must contain only appointment_id")
        appointment_id = value.get("appointment_id")
        if not isinstance(appointment_id, str) or not appointment_id.strip():
            raise ValueError("appointment_reference.appointment_id must be non-empty")
        return value

    @field_validator("response_mode")
    @classmethod
    def validate_response_mode(cls, value: str) -> str:
        if value not in VALID_RESPONSE_MODES:
            raise ValueError("response_mode must be sync or stream")
        return value

    def to_pipeline_request(self) -> AppointmentStatusRequest:
        """Convert the gateway DTO to the WP-306 pipeline DTO."""
        return AppointmentStatusRequest(
            request_id=self.request_id,
            session_id=self.session_id,
            appointment_reference=self.appointment_reference,
        )


def set_appointment_status_pipeline(pipeline: AppointmentStatusPipeline) -> None:
    """Replace the module-level pipeline; intended for tests/application wiring."""
    global _default_pipeline
    _default_pipeline = pipeline


def build_capability_response_envelope(
    *,
    pipeline_response: Any,
    request_id: str,
    trace_id: str,
) -> Dict[str, Any]:
    """Build the canonical capability response envelope for PC-04."""
    result = pipeline_response.to_dict()
    warnings = result.get("warnings", [])
    return {
        "trace_id": trace_id,
        "request_id": request_id,
        "capability": CAPABILITY_NAME,
        "outcome": result.get("outcome"),
        "result": result,
        "explainability": {
            "summary": "Appointment status lookup uses only the supplied appointment_id.",
            "reference_fields_used": ["appointment_id"],
        },
        "warnings": warnings,
        "errors": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_sse_stream(envelope: Dict[str, Any]) -> str:
    """Render a deterministic SSE stream with the same semantic envelope."""
    import json

    ack = {"trace_id": envelope["trace_id"], "capability": CAPABILITY_NAME}
    completed = envelope
    return (
        f"event: ack\ndata: {json.dumps(ack, ensure_ascii=False)}\n\n"
        f"event: completed\ndata: {json.dumps(completed, ensure_ascii=False)}\n\n"
    )


@router.post(CAPABILITY_ROUTE, response_model=None)
async def execute_appointment_status(
    payload: AppointmentStatusExecuteRequest,
    request: Request,
):
    """Execute the PC-04 Appointment Status capability."""
    trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())

    if _default_pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="appointment status pipeline is not configured",
        )

    runtime = get_operational_runtime(request)
    append_user_turn(runtime, payload.session_id, "appointment status lookup", intent=CAPABILITY_NAME)

    try:
        pipeline_response = _default_pipeline.execute(payload.to_pipeline_request())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    envelope = build_capability_response_envelope(
        pipeline_response=pipeline_response,
        request_id=payload.request_id,
        trace_id=trace_id,
    )
    append_assistant_turn(runtime, payload.session_id, CAPABILITY_NAME, envelope, tools=[{"name": "appointment_status_lookup"}])

    if payload.response_mode == "stream":
        return StreamingResponse(
            iter([build_sse_stream(envelope)]),
            media_type="text/event-stream",
            headers={"x-trace-id": trace_id},
        )

    return JSONResponse(content=envelope, headers={"x-trace-id": trace_id})


__all__ = [
    "CAPABILITY_NAME",
    "CAPABILITY_ROUTE",
    "AppointmentStatusExecuteRequest",
    "build_capability_response_envelope",
    "build_sse_stream",
    "execute_appointment_status",
    "router",
    "set_appointment_status_pipeline",
]
# === TASK:WP-404:END ===

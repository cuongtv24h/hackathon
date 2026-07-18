# === TASK:WP-402:START ===
"""FastAPI router for the PC-02 Emergency Safety capability.

The module exposes the canonical public endpoint
``POST /v1/capabilities/emergency-safety:execute`` and adapts request
JSON to the WP-304 emergency-safety pipeline without changing the
pipeline's public contracts.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from apps.api.core.runtime_persistence import (
    append_assistant_turn,
    append_user_turn,
    get_operational_runtime,
    write_audit,
)
from apps.api.ai.orchestrator.emergency_safety.pipeline import (
    EmergencySafetyPipeline,
    EmergencySafetyRequest,
    OUTCOME_EMERGENCY_TRIGGERED,
    OUTCOME_CLARIFICATION_REQUIRED,
    OUTCOME_NOT_TRIGGERED,
)

CAPABILITY_NAME = "emergency_safety"
CAPABILITY_ROUTE = "/v1/capabilities/emergency-safety:execute"
VALID_RESPONSE_MODES = {"sync", "stream"}
MAX_MESSAGE_LENGTH = 4000
MAX_HISTORY_TURNS = 20

router = APIRouter()
_default_pipeline = EmergencySafetyPipeline()


class EmergencySafetyExecuteRequest(BaseModel):
    """Gateway request DTO for PC-02.

    JSON fields stay snake_case and are mapped directly to the canonical
    ``EmergencySafetyRequest`` consumed by the orchestrator.
    """

    request_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    response_mode: str = "sync"
    client_context: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must be non-empty")
        return value

    @field_validator("conversation_history")
    @classmethod
    def validate_conversation_history(
        cls, value: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        if len(value) > MAX_HISTORY_TURNS:
            raise ValueError("conversation_history cannot exceed 20 turns")
        return value

    @field_validator("response_mode")
    @classmethod
    def validate_response_mode(cls, value: str) -> str:
        if value not in VALID_RESPONSE_MODES:
            raise ValueError("response_mode must be sync or stream")
        return value

    def to_pipeline_request(self) -> EmergencySafetyRequest:
        """Convert the gateway DTO to the WP-304 pipeline DTO."""
        return EmergencySafetyRequest(
            request_id=self.request_id,
            session_id=self.session_id,
            message=self.message,
            conversation_history=self.conversation_history,
            client_context=self.client_context,
        )


def set_emergency_safety_pipeline(pipeline: EmergencySafetyPipeline) -> None:
    """Replace the module-level pipeline; intended for tests/application wiring."""
    global _default_pipeline
    _default_pipeline = pipeline


def build_capability_response_envelope(
    *,
    pipeline_response: Any,
    request_id: str,
    trace_id: str,
) -> Dict[str, Any]:
    """Build the canonical capability response envelope for PC-02."""
    result = pipeline_response.to_dict()
    for nullable_key in ("level", "protocol", "address", "banner", "event_id", "error"):
        result.setdefault(nullable_key, None)

    error_payload = result.get("error")
    if error_payload and isinstance(error_payload, dict) and "error" in error_payload:
        errors = [error_payload["error"]]
    elif error_payload:
        errors = [error_payload]
    else:
        errors = []

    return {
        "trace_id": trace_id,
        "request_id": request_id,
        "capability": CAPABILITY_NAME,
        "outcome": result.get("outcome"),
        "result": result,
        "explainability": result.get("explainability"),
        "warnings": result.get("disclaimers", []),
        "errors": errors,
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
async def execute_emergency_safety(
    payload: EmergencySafetyExecuteRequest,
    request: Request,
):
    """Execute the PC-02 Emergency Safety capability."""
    trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())

    runtime = get_operational_runtime(request)
    append_user_turn(runtime, payload.session_id, payload.message, client_context=payload.client_context, intent=CAPABILITY_NAME, critical=False)

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
    emergency_triggered = envelope.get("outcome") == OUTCOME_EMERGENCY_TRIGGERED
    if emergency_triggered:
        try:
            write_audit(runtime, "emergency", payload.session_id, "emergency_trigger", "conversation_session", details={"capability": CAPABILITY_NAME, "triggered": True}, critical=True)
        except Exception:
            envelope["result"]["message"] = "Yêu cầu khẩn cấp đã được nhận. Vui lòng gọi 115 hoặc đến cơ sở cấp cứu gần nhất ngay lập tức."
    append_assistant_turn(runtime, payload.session_id, CAPABILITY_NAME, envelope, tools=[{"name": "emergency_prefilter"}], emergency=emergency_triggered)

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
    "EmergencySafetyExecuteRequest",
    "build_capability_response_envelope",
    "build_sse_stream",
    "execute_emergency_safety",
    "router",
    "set_emergency_safety_pipeline",
]
# === TASK:WP-402:END ===
# === TASK:WP-401:START ===
"""FastAPI router for the PC-01 Information Assistance capability.

The module exposes the canonical public endpoint
``POST /v1/capabilities/information-assistance:execute`` and adapts request
JSON to the WP-303 information-assistance pipeline without changing the
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
from apps.api.ai.orchestrator.information_assistance.pipeline import (
    InformationAssistancePipeline,
    InformationAssistanceRequest,
)

CAPABILITY_NAME = "information_assistance"
CAPABILITY_ROUTE = "/v1/capabilities/information-assistance:execute"
VALID_RESPONSE_MODES = {"sync", "stream"}
MAX_MESSAGE_LENGTH = 4000
MAX_HISTORY_TURNS = 20

router = APIRouter()
_default_pipeline = InformationAssistancePipeline()


class InformationAssistanceExecuteRequest(BaseModel):
    """Gateway request DTO for PC-01.

    JSON fields stay snake_case and are mapped directly to the canonical
    ``InformationAssistanceRequest`` consumed by the orchestrator.
    """

    request_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    response_mode: str = "sync"
    client_context: Dict[str, Any] = Field(default_factory=dict)
    button_context: Optional[Dict[str, Any]] = None

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

    def to_pipeline_request(self) -> InformationAssistanceRequest:
        """Convert the gateway DTO to the WP-303 pipeline DTO."""
        return InformationAssistanceRequest(
            request_id=self.request_id,
            session_id=self.session_id,
            message=self.message,
            conversation_history=self.conversation_history,
            response_mode=self.response_mode,
            client_context=self.client_context,
            button_context=self.button_context,
        )


def set_information_assistance_pipeline(pipeline: InformationAssistancePipeline) -> None:
    """Replace the module-level pipeline; intended for tests/application wiring."""
    global _default_pipeline
    _default_pipeline = pipeline


def build_capability_response_envelope(
    *,
    pipeline_response: Any,
    request_id: str,
    trace_id: str,
) -> Dict[str, Any]:
    """Build the canonical capability response envelope for PC-01."""
    result = pipeline_response.to_dict()
    return {
        "trace_id": trace_id,
        "request_id": request_id,
        "capability": CAPABILITY_NAME,
        "outcome": result.get("outcome"),
        "result": result,
        "explainability": result.get("explainability"),
        "warnings": result.get("disclaimers", []),
        "errors": [result["error"]] if result.get("error") else [],
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
async def execute_information_assistance(
    payload: InformationAssistanceExecuteRequest,
    request: Request,
):
    """Execute the PC-01 Information Assistance capability."""
    trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())

    runtime = get_operational_runtime(request)
    append_user_turn(runtime, payload.session_id, payload.message, client_context=payload.client_context, intent=CAPABILITY_NAME)

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
    append_assistant_turn(runtime, payload.session_id, CAPABILITY_NAME, envelope, tools=[{"name": "knowledge_search"}])

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
    "InformationAssistanceExecuteRequest",
    "build_capability_response_envelope",
    "build_sse_stream",
    "execute_information_assistance",
    "router",
    "set_information_assistance_pipeline",
]
# === TASK:WP-401:END ===

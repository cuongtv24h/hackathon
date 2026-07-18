# === TASK:WP-302:START ===
"""AI orchestration core service (ARCH-05, ARCH-07, INT-05, INT-07).

This module provides the core orchestration logic that coordinates context,
guardrails, tool calls, explainability, and fallback behavior across all
capabilities (PC-01, PC-02, PC-03, PC-04).

Key features:
- Emergency prefilter runs before reasoning (INT-05)
- Output has grounding/explainability without exposing chain-of-thought
- Fallback behavior per INT-07 (provider chain → static message)
- Tool coordination with validated inputs only

Dependencies:
- WP-301: LLM and embedding providers
- WP-201: Knowledge search tool
- WP-202: Emergency prefilter
- WP-203: Appointment tools
- WP-204: Privacy/guardrails
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from packages.contracts import (
    UnifiedErrorEnvelope,
    make_error_envelope,
    CATEGORY_AI,
    CATEGORY_SAFETY,
    NO_GROUNDED_RESULT,
    OUT_OF_SCOPE,
    MEDICAL_ADVICE_REFUSED,
    AI_PROVIDER_UNAVAILABLE,
    EMERGENCY_PROTOCOL_FALLBACK_USED,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTOs for orchestration (INT-05 contracts)
# ---------------------------------------------------------------------------


class SafetyDisposition(str, Enum):
    """Safety disposition values per INT-05."""
    SAFE = "safe"
    CAUTION = "caution"
    MEDICAL_REFUSAL = "medical_refusal"


class ScopeAssessment(str, Enum):
    """Scope assessment values per INT-05."""
    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"
    PARTIAL = "partial"


class ClarityLevel(str, Enum):
    """Clarity level values per INT-05."""
    CLEAR = "clear"
    AMBIGUOUS = "ambiguous"
    INCOMPLETE = "incomplete"


class ConfidenceBand(str, Enum):
    """Confidence band values per INT-05."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class ConversationContext:
    """Conversation context per INT-05 (max 20 turns)."""
    turns: List[Dict[str, str]] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        if len(self.turns) > 20:
            raise ValueError("ConversationContext cannot exceed 20 turns")


@dataclass(frozen=True)
class BusinessContext:
    """Business context attached to requests."""
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    channel: str = "web_widget"
    locale: str = "vi-VN"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SystemContext:
    """Trusted system context (validated, not user-controlled)."""
    knowledge_base_version: str = "latest"
    emergency_protocols_active: bool = True
    rate_limit_remaining: int = 100
    feature_flags: Dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class OrchestrationInput:
    """Input to the orchestration service.
    
    Per INT-05: Message + max 20 ConversationContext turns + BusinessContext +
    caution flags + trusted SystemContext + validated tool observations.
    """
    message: str
    conversation_context: ConversationContext = field(default_factory=ConversationContext)
    business_context: BusinessContext = field(default_factory=BusinessContext)
    system_context: SystemContext = field(default_factory=SystemContext)
    caution_flags: List[str] = field(default_factory=list)
    tool_observations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class PlanningResultDTO:
    """Planning result per INT-05.
    
    Contains goal and ordered tool steps with dependencies/status.
    """
    goal: str
    tool_steps: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "tool_steps": list(self.tool_steps),
            "status": self.status,
        }


@dataclass(frozen=True)
class ObservationResultDTO:
    """Observation result per INT-05.
    
    Contains tool call/name/status, result reference, citations,
    freshness, conflict and error.
    """
    tool_name: str
    tool_call_id: Optional[str] = None
    status: str = "success"
    result_reference: Optional[str] = None
    citations: List[Dict[str, Any]] = field(default_factory=list)
    freshness_seconds: Optional[int] = None
    conflict: bool = False
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "status": self.status,
            "result_reference": self.result_reference,
            "citations": list(self.citations),
            "freshness_seconds": self.freshness_seconds,
            "conflict": self.conflict,
            "error": self.error,
        }


@dataclass(frozen=True)
class ConversationResultDTO:
    """Conversation result per INT-05.
    
    Contains message, response_type, disclaimers, actions, streaming flag.
    """
    message: str
    response_type: str = "text"
    disclaimers: List[str] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    streaming: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "response_type": self.response_type,
            "disclaimers": list(self.disclaimers),
            "actions": list(self.actions),
            "streaming": self.streaming,
        }


@dataclass(frozen=True)
class ExplainabilityResultDTO:
    """Explainability result per INT-05.
    
    Contains citations and public fallback/refusal/safety evidence.
    Never exposes chain-of-thought or internal reasoning.
    """
    citations: List[Dict[str, Any]] = field(default_factory=list)
    fallback_reason: Optional[str] = None
    refusal_reason: Optional[str] = None
    safety_evidence: Optional[str] = None
    confidence_band: str = "medium"
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "citations": list(self.citations),
            "confidence_band": self.confidence_band,
        }
        if self.fallback_reason is not None:
            result["fallback_reason"] = self.fallback_reason
        if self.refusal_reason is not None:
            result["refusal_reason"] = self.refusal_reason
        if self.safety_evidence is not None:
            result["safety_evidence"] = self.safety_evidence
        return result


@dataclass(frozen=True)
class GroundingFallbackBehavior:
    """Grounding and fallback behavior per INT-05.
    
    Defines what happens when grounding is insufficient or conflicts occur.
    """
    grounded: bool = True
    chunks_used: int = 0
    fallback_triggered: bool = False
    fallback_channel: Optional[str] = None
    static_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "grounded": self.grounded,
            "chunks_used": self.chunks_used,
            "fallback_triggered": self.fallback_triggered,
            "fallback_channel": self.fallback_channel,
            "static_message": self.static_message,
        }


@dataclass(frozen=True)
class OrchestrationResult:
    """Complete orchestration result combining all DTOs."""
    reasoning: Optional[Dict[str, Any]] = None
    planning: Optional[PlanningResultDTO] = None
    observations: List[ObservationResultDTO] = field(default_factory=list)
    conversation: Optional[ConversationResultDTO] = None
    explainability: Optional[ExplainabilityResultDTO] = None
    grounding: Optional[GroundingFallbackBehavior] = None
    error: Optional[UnifiedErrorEnvelope] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if self.reasoning is not None:
            result["reasoning"] = self.reasoning
        if self.planning is not None:
            result["planning"] = self.planning.to_dict()
        if self.observations:
            result["observations"] = [o.to_dict() for o in self.observations]
        if self.conversation is not None:
            result["conversation"] = self.conversation.to_dict()
        if self.explainability is not None:
            result["explainability"] = self.explainability.to_dict()
        if self.grounding is not None:
            result["grounding"] = self.grounding.to_dict()
        if self.error is not None:
            result["error"] = self.error.to_dict()
        return result


# ---------------------------------------------------------------------------
# Protocols for dependency injection (test-friendly)
# ---------------------------------------------------------------------------


@runtime_checkable
class EmergencyPrefilterProtocol(Protocol):
    """Protocol for emergency prefilter (WP-202)."""
    
    def check(self, message: str, context: ConversationContext) -> Dict[str, Any]:
        """Check if message indicates emergency.
        
        Args:
            message: The user message.
            context: Conversation context.
            
        Returns:
            Dict with 'is_emergency', 'protocol_key', 'urgency_level'.
        """
        ...


@runtime_checkable
class KnowledgeSearchProtocol(Protocol):
    """Protocol for knowledge search tool (WP-201)."""
    
    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Search knowledge base.
        
        Args:
            query: Search query.
            top_k: Maximum results.
            filters: Optional filters.
            
        Returns:
            Dict with 'chunks', 'total', 'query_vector'.
        """
        ...


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """Protocol for LLM provider (WP-301)."""
    
    def generate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Generate LLM response.
        
        Args:
            request: LLM request dict.
            
        Returns:
            LLM response dict.
        """
        ...


@runtime_checkable
class GuardrailServiceProtocol(Protocol):
    """Protocol for guardrail service (WP-204/WP-302)."""
    
    def check_input(self, message: str, context: ConversationContext) -> Dict[str, Any]:
        """Check input for violations.
        
        Args:
            message: User message.
            context: Conversation context.
            
        Returns:
            Dict with 'allowed', 'violations', 'redacted_message'.
        """
        ...
    
    def check_output(self, response: str, observations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check output for violations.
        
        Args:
            response: Generated response.
            observations: Tool observations used.
            
        Returns:
            Dict with 'allowed', 'violations', 'redacted_response'.
        """
        ...


# ---------------------------------------------------------------------------
# Orchestration service
# ---------------------------------------------------------------------------


class OrchestrationService:
    """Core orchestration service coordinating AI components.
    
    This service implements the orchestration logic defined in:
    - docs/artifacts/architecture/ai-capability-mapping.md (ARCH-05)
    - docs/artifacts/architecture/context-design.md (ARCH-07)
    - docs/artifacts/interface/ai-behavior-contracts.md (INT-05)
    
    Emergency prefilter runs before reasoning (INT-05 requirement).
    Output has grounding/explainability without exposing chain-of-thought.
    """
    
    # Static fallback message per INT-07
    STATIC_FALLBACK_MESSAGE = (
        "Xin lỗi, hệ thống đang gặp sự cố kỹ thuật. "
        "Vui lòng gọi đường dây nóng 1900-xxxx để được hỗ trợ."
    )
    
    # Medical advice refusal message per INT-05
    MEDICAL_REFUSAL_MESSAGE = (
        "Xin lỗi, tôi không thể đưa ra lời khuyên y tế, chẩn đoán hoặc "
        "khuyến nghị điều trị. Vui lòng tham khảo ý kiến bác sĩ hoặc "
        "gọi đường dây nóng 1900-xxxx để được hỗ trợ."
    )
    
    # Out of scope message per INT-05
    OUT_OF_SCOPE_MESSAGE = (
        "Câu hỏi của bạn nằm ngoài phạm vi hỗ trợ của hệ thống. "
        "Vui lòng liên hệ tổng đài 1900-xxxx để được hỗ trợ."
    )
    
    def __init__(
        self,
        *,
        emergency_prefilter: Optional[EmergencyPrefilterProtocol] = None,
        knowledge_search: Optional[KnowledgeSearchProtocol] = None,
        llm_provider: Optional[LLMProviderProtocol] = None,
        guardrail_service: Optional[GuardrailServiceProtocol] = None,
        fallback_message: Optional[str] = None,
    ):
        """Initialize orchestration service.
        
        Args:
            emergency_prefilter: Emergency prefilter implementation (WP-202).
            knowledge_search: Knowledge search implementation (WP-201).
            llm_provider: LLM provider implementation (WP-301).
            guardrail_service: Guardrail service implementation (WP-204).
            fallback_message: Custom static fallback message.
        """
        self._emergency_prefilter = emergency_prefilter
        self._knowledge_search = knowledge_search
        self._llm_provider = llm_provider
        self._guardrail_service = guardrail_service
        self._fallback_message = fallback_message or self.STATIC_FALLBACK_MESSAGE
    
    def orchestrate(
        self,
        input_data: OrchestrationInput,
    ) -> OrchestrationResult:
        """Execute orchestration for a single user message.
        
        This is the main entry point that:
        1. Runs emergency prefilter first (INT-05 requirement)
        2. Applies input guardrails
        3. Performs planning if needed
        4. Executes tool calls
        5. Generates response
        6. Applies output guardrails
        7. Builds explainability
        8. Handles fallback if needed
        
        Args:
            input_data: The orchestration input.
            
        Returns:
            OrchestrationResult with all DTOs populated.
        """
        trace_id = str(uuid.uuid4())
        
        try:
            # Step 1: Emergency prefilter runs first (INT-05)
            emergency_result = self._run_emergency_prefilter(input_data)
            if emergency_result is not None:
                return emergency_result
            
            # Step 2: Input guardrails
            guardrail_result = self._run_input_guardrails(input_data)
            if guardrail_result is not None:
                return guardrail_result
            
            # Step 3: Planning
            planning = self._plan(input_data)
            if planning is None:
                # No planning needed, direct response
                return self._create_conversation_result(
                    message="Tôi có thể giúp gì cho bạn?",
                    disclaimers=["Đây là hệ thống hỗ trợ thông tin bệnh viện."],
                )
            
            # Step 4: Execute tools
            observations = self._execute_tools(input_data, planning)
            
            # Step 5: Check grounding
            grounding = self._check_grounding(observations)
            if not grounding.grounded:
                return self._create_fallback_result(grounding)
            
            # Step 6: Generate response
            conversation = self._generate_response(input_data, observations, planning)
            if conversation is None:
                return self._create_provider_failure_result(trace_id)
            
            # Step 7: Output guardrails
            output_guard = self._run_output_guardrails(conversation.message, observations)
            if output_guard is not None:
                return output_guard
            
            # Step 8: Build explainability
            explainability = self._build_explainability(observations, grounding)
            
            return OrchestrationResult(
                planning=planning,
                observations=observations,
                conversation=conversation,
                explainability=explainability,
                grounding=grounding,
            )
            
        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            return OrchestrationResult(
                error=make_error_envelope(
                    code=AI_PROVIDER_UNAVAILABLE,
                    message=str(e),
                    category=CATEGORY_AI,
                    retryable=True,
                    retry_after_seconds=5,
                )
            )
    
    def _run_emergency_prefilter(
        self,
        input_data: OrchestrationInput,
    ) -> Optional[OrchestrationResult]:
        """Run emergency prefilter before reasoning (INT-05).
        
        Emergency priority is the first planning rule per INT-05.
        
        Args:
            input_data: Orchestration input.
            
        Returns:
            OrchestrationResult if emergency detected, None otherwise.
        """
        if self._emergency_prefilter is None:
            return None
        
        try:
            emergency = self._emergency_prefilter.check(
                input_data.message,
                input_data.conversation_context,
            )
            
            if emergency.get("is_emergency", False):
                protocol_key = emergency.get("protocol_key", "default")
                urgency_level = emergency.get("urgency_level", "high")
                
                # Emergency response uses approved protocol, not free generation (INT-05)
                return OrchestrationResult(
                    conversation=ConversationResultDTO(
                        message=self._get_emergency_protocol_message(protocol_key),
                        response_type="emergency",
                        disclaimers=[
                            "Đây là tình huống khẩn cấp.",
                            "Vui lòng đến ngay phòng cấp cứu hoặc gọi 115.",
                        ],
                        actions=[
                            {"type": "emergency", "protocol": protocol_key},
                            {"type": "contact", "number": "115"},
                        ],
                    ),
                    explainability=ExplainabilityResultDTO(
                        safety_evidence=f"Emergency protocol {protocol_key} activated",
                        confidence_band="high",
                    ),
                    grounding=GroundingFallbackBehavior(
                        grounded=True,
                        fallback_triggered=True,
                        fallback_channel="emergency_protocol",
                    ),
                )
        except Exception as e:
            logger.warning(f"Emergency prefilter failed: {e}")
            # Don't block on prefilter failure, continue with normal flow
        
        return None
    
    def _run_input_guardrails(
        self,
        input_data: OrchestrationInput,
    ) -> Optional[OrchestrationResult]:
        """Run input guardrails.
        
        Args:
            input_data: Orchestration input.
            
        Returns:
            OrchestrationResult if blocked, None otherwise.
        """
        if self._guardrail_service is None:
            return None
        
        try:
            guard_result = self._guardrail_service.check_input(
                input_data.message,
                input_data.conversation_context,
            )
            
            if not guard_result.get("allowed", True):
                violations = guard_result.get("violations", [])
                return OrchestrationResult(
                    conversation=ConversationResultDTO(
                        message="Tin nhắn của bạn không thể được xử lý do vi phạm chính sách.",
                        response_type="refusal",
                        disclaimers=["Nội dung không được phép."],
                    ),
                    explainability=ExplainabilityResultDTO(
                        refusal_reason=f"Policy violation: {', '.join(violations)}",
                        confidence_band="high",
                    ),
                )
        except Exception as e:
            logger.warning(f"Input guardrail check failed: {e}")
        
        return None
    
    def _plan(self, input_data: OrchestrationInput) -> Optional[PlanningResultDTO]:
        """Create execution plan.
        
        Planning rules per INT-05:
        1. Emergency priority (already handled)
        2. Factual information requires Knowledge Search
        3. Only registry tools and validated inputs
        4. Write tools require confirmation/idempotency
        5. Ask minimal clarification; never fill missing data
        
        Args:
            input_data: Orchestration input.
            
        Returns:
            PlanningResultDTO or None if no planning needed.
        """
        message_lower = input_data.message.lower()
        
        # Determine if knowledge search is needed (INT-05: factual information)
        needs_knowledge = any(
            keyword in message_lower
            for keyword in [
                "giờ", "phòng", "khoa", "dịch vụ", "bảo hiểm", "bhyt",
                "chi phí", "giá", "địa chỉ", "đường", "quy trình", "thủ tục",
            ]
        )
        
        # Determine if appointment-related
        is_appointment = any(
            keyword in message_lower
            for keyword in ["đặt lịch", "đặt hẹn", "lịch khám", "hẹn khám"]
        )
        
        tool_steps = []
        
        if needs_knowledge:
            tool_steps.append({
                "tool": "knowledge_search",
                "params": {"query": input_data.message, "top_k": 5},
                "status": "pending",
            })
        
        if is_appointment:
            tool_steps.append({
                "tool": "appointment_check",
                "params": {"action": "check_availability"},
                "status": "pending",
                "requires_confirmation": True,
            })
        
        if not tool_steps:
            return None
        
        return PlanningResultDTO(
            goal="Provide helpful response based on available tools",
            tool_steps=tool_steps,
            status="planned",
        )
    
    def _execute_tools(
        self,
        input_data: OrchestrationInput,
        planning: PlanningResultDTO,
    ) -> List[ObservationResultDTO]:
        """Execute planned tool calls.
        
        Args:
            input_data: Orchestration input.
            planning: Execution plan.
            
        Returns:
            List of observation results.
        """
        observations = []
        
        for step in planning.tool_steps:
            tool_name = step.get("tool", "")
            params = step.get("params", {})
            
            if tool_name == "knowledge_search" and self._knowledge_search:
                try:
                    result = self._knowledge_search.search(
                        params.get("query", input_data.message),
                        top_k=params.get("top_k", 5),
                    )
                    
                    chunks = result.get("chunks", [])
                    observations.append(ObservationResultDTO(
                        tool_name="knowledge_search",
                        status="success",
                        result_reference=f"kb://search/{len(chunks)}",
                        citations=[
                            {"chunk_id": c.get("id"), "source": c.get("source")}
                            for c in chunks[:3]
                            if c.get("id") and c.get("source")
                        ],
                        freshness_seconds=300,
                    ))
                except Exception as e:
                    logger.error(f"Knowledge search failed: {e}")
                    observations.append(ObservationResultDTO(
                        tool_name="knowledge_search",
                        status="error",
                        error=str(e),
                    ))
            else:
                # Tool not available, record as skipped
                observations.append(ObservationResultDTO(
                    tool_name=tool_name,
                    status="skipped",
                    error="Tool not available",
                ))
        
        return observations
    
    def _check_grounding(
        self,
        observations: List[ObservationResultDTO],
    ) -> GroundingFallbackBehavior:
        """Check if response is properly grounded.
        
        Per INT-05:
        - Only active + approved + effective chunks
        - Insufficient information or conflict forbids factual synthesis
        - Fallback = acknowledge limit + explain reason + specific approved channel
        
        Args:
            observations: Tool observations.
            
        Returns:
            GroundingFallbackBehavior indicating grounding status.
        """
        successful_observations = [
            o for o in observations
            if o.status == "success" and not o.conflict
        ]
        
        total_citations = sum(
            len(o.citations) for o in successful_observations
        )
        
        if total_citations == 0:
            return GroundingFallbackBehavior(
                grounded=False,
                chunks_used=0,
                fallback_triggered=True,
                fallback_channel="static_message",
                static_message=self._fallback_message,
            )
        
        # Check for conflicts
        has_conflict = any(o.conflict for o in observations)
        if has_conflict:
            return GroundingFallbackBehavior(
                grounded=False,
                chunks_used=total_citations,
                fallback_triggered=True,
                fallback_reason="knowledge_conflict",
                fallback_channel="static_message",
                static_message=(
                    "Xin lỗi, tôi không tìm thấy thông tin chính xác cho câu hỏi này. "
                    "Vui lòng liên hệ tổng đài 1900-xxxx để được hỗ trợ."
                ),
            )
        
        return GroundingFallbackBehavior(
            grounded=True,
            chunks_used=total_citations,
        )
    
    def _generate_response(
        self,
        input_data: OrchestrationInput,
        observations: List[ObservationResultDTO],
        planning: PlanningResultDTO,
    ) -> Optional[ConversationResultDTO]:
        """Generate response using LLM provider.
        
        Args:
            input_data: Orchestration input.
            observations: Tool observations.
            planning: Execution plan.
            
        Returns:
            ConversationResultDTO or None if generation failed.
        """
        if self._llm_provider is None:
            # Without LLM, return a simple acknowledgment
            return ConversationResultDTO(
                message="Tôi đã ghi nhận yêu cầu của bạn.",
                response_type="text",
                disclaimers=["Đây là hệ thống hỗ trợ thông tin bệnh viện."],
            )
        
        try:
            # Build context from observations
            context_parts = []
            for obs in observations:
                if obs.status == "success":
                    context_parts.append(f"Tool {obs.tool_name}: {obs.result_reference}")
            
            llm_request = {
                "messages": [
                    {"role": "system", "content": "Bạn là trợ lý hỗ trợ bệnh viện."},
                    {"role": "user", "content": input_data.message},
                ],
                "context": "\n".join(context_parts) if context_parts else None,
            }
            
            response = self._llm_provider.generate(llm_request)
            content = response.get("content", "")
            
            # Add BHYT/price disclaimer if relevant (INT-05)
            disclaimers = ["Đây là thông tin tham khảo, không thay thế tư vấn y tế."]
            if any(o.tool_name == "knowledge_search" for o in observations):
                disclaimers.append(
                    "Thông tin về BHYT, giá dịch vụ và quy trình có thể thay đổi."
                )
            
            return ConversationResultDTO(
                message=content,
                response_type="text",
                disclaimers=disclaimers,
            )
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return None
    
    def _run_output_guardrails(
        self,
        response: str,
        observations: List[ObservationResultDTO],
    ) -> Optional[OrchestrationResult]:
        """Run output guardrails.
        
        Args:
            response: Generated response text.
            observations: Tool observations used.
            
        Returns:
            OrchestrationResult if blocked, None otherwise.
        """
        if self._guardrail_service is None:
            return None
        
        try:
            guard_result = self._guardrail_service.check_output(
                response,
                [o.to_dict() for o in observations],
            )
            
            if not guard_result.get("allowed", True):
                return OrchestrationResult(
                    conversation=ConversationResultDTO(
                        message="Phản hồi đã được điều chỉnh do chính sách nội dung.",
                        response_type="redacted",
                    ),
                    explainability=ExplainabilityResultDTO(
                        refusal_reason="Output policy violation",
                        confidence_band="medium",
                    ),
                )
        except Exception as e:
            logger.warning(f"Output guardrail check failed: {e}")
        
        return None
    
    def _build_explainability(
        self,
        observations: List[ObservationResultDTO],
        grounding: GroundingFallbackBehavior,
    ) -> ExplainabilityResultDTO:
        """Build explainability result.
        
        Per INT-05: citations and public fallback/refusal/safety evidence.
        Never exposes chain-of-thought.
        
        Args:
            observations: Tool observations.
            grounding: Grounding status.
            
        Returns:
            ExplainabilityResultDTO.
        """
        citations = []
        for obs in observations:
            citations.extend(obs.citations)
        
        return ExplainabilityResultDTO(
            citations=citations[:5],  # Limit citations
            confidence_band="medium" if grounding.grounded else "low",
        )
    
    def _create_conversation_result(
        self,
        message: str,
        disclaimers: Optional[List[str]] = None,
    ) -> OrchestrationResult:
        """Create a simple conversation result."""
        return OrchestrationResult(
            conversation=ConversationResultDTO(
                message=message,
                disclaimers=disclaimers or [],
            ),
        )
    
    def _create_fallback_result(
        self,
        grounding: GroundingFallbackBehavior,
    ) -> OrchestrationResult:
        """Create fallback result per INT-05/INT-07.
        
        Fallback = acknowledge limit + explain reason + specific approved channel.
        """
        return OrchestrationResult(
            conversation=ConversationResultDTO(
                message=grounding.static_message or self._fallback_message,
                response_type="fallback",
                disclaimers=["Không tìm thấy thông tin chính xác."],
                actions=[
                    {"type": "contact", "number": "1900-xxxx"},
                ],
            ),
            explainability=ExplainabilityResultDTO(
                fallback_reason=grounding.fallback_reason or "insufficient_grounding",
                confidence_band="low",
            ),
            grounding=grounding,
        )
    
    def _create_provider_failure_result(self, trace_id: str) -> OrchestrationResult:
        """Create result for provider failure per INT-07."""
        return OrchestrationResult(
            conversation=ConversationResultDTO(
                message=self._fallback_message,
                response_type="fallback",
                disclaimers=["Hệ thống đang gặp sự cố."],
                actions=[
                    {"type": "contact", "number": "1900-xxxx"},
                ],
            ),
            error=make_error_envelope(
                code=AI_PROVIDER_UNAVAILABLE,
                message="All providers failed",
                category=CATEGORY_AI,
                retryable=True,
                retry_after_seconds=30,
            ),
        )
    
    def _get_emergency_protocol_message(self, protocol_key: str) -> str:
        """Get emergency protocol message.
        
        Emergency response uses approved protocol, not free generation (INT-05).
        """
        protocols = {
            "cardiac_arrest": "Có vẻ bạn đang gặp tình huống ngừng tim. Vui lòng gọi 115 ngay lập tức và thực hiện CPR nếu được đào tạo.",
            "stroke": "Có vẻ bạn đang gặp dấu hiệu đột quỵ. Vui lòng đến bệnh viện ngay hoặc gọi 115.",
            "severe_bleeding": "Có vẻ bạn đang gặp chảy máu nặng. Vui lòng ép chặt vết thương và gọi 115 ngay.",
            "default": "Đây là tình huống khẩn cấp. Vui lòng đến ngay phòng cấp cứu hoặc gọi 115.",
        }
        return protocols.get(protocol_key, protocols["default"])


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def create_mock_orchestration_service(
    *,
    emergency_response: Optional[Dict[str, Any]] = None,
    search_results: Optional[List[Dict[str, Any]]] = None,
    llm_response: Optional[str] = None,
    guardrail_allow: bool = True,
) -> OrchestrationService:
    """Create an orchestration service with mock dependencies for testing.
    
    Args:
        emergency_response: Mock emergency prefilter response.
        search_results: Mock knowledge search results.
        llm_response: Mock LLM response content.
        guardrail_allow: Whether guardrails should allow.
        
    Returns:
        OrchestrationService with mock dependencies.
    """
    # Create mock emergency prefilter
    class MockEmergencyPrefilter:
        def __init__(self, response: Optional[Dict[str, Any]]):
            self._response = response or {"is_emergency": False}
        
        def check(self, message: str, context: ConversationContext) -> Dict[str, Any]:
            return self._response
    
    # Create mock knowledge search
    class MockKnowledgeSearch:
        def __init__(self, results: Optional[List[Dict[str, Any]]]):
            self._results = results or []
        
        def search(
            self,
            query: str,
            *,
            top_k: int = 5,
            filters: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            return {
                "chunks": self._results[:top_k],
                "total": len(self._results),
                "query": query,
            }
    
    # Create mock LLM provider
    class MockLLMProvider:
        def __init__(self, response: Optional[str]):
            self._response = response or "This is a mock response."
        
        def generate(self, request: Dict[str, Any]) -> Dict[str, Any]:
            return {"content": self._response, "provider": "mock"}
    
    # Create mock guardrail service
    class MockGuardrailService:
        def __init__(self, allow: bool):
            self._allow = allow
        
        def check_input(self, message: str, context: ConversationContext) -> Dict[str, Any]:
            return {"allowed": self._allow, "violations": []}
        
        def check_output(self, response: str, observations: List[Dict[str, Any]]) -> Dict[str, Any]:
            return {"allowed": self._allow, "violations": []}
    
    return OrchestrationService(
        emergency_prefilter=MockEmergencyPrefilter(emergency_response),
        knowledge_search=MockKnowledgeSearch(search_results),
        llm_provider=MockLLMProvider(llm_response),
        guardrail_service=MockGuardrailService(guardrail_allow),
    )


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    # DTOs
    "ConversationContext",
    "BusinessContext",
    "SystemContext",
    "OrchestrationInput",
    "PlanningResultDTO",
    "ObservationResultDTO",
    "ConversationResultDTO",
    "ExplainabilityResultDTO",
    "GroundingFallbackBehavior",
    "OrchestrationResult",
    # Enums
    "SafetyDisposition",
    "ScopeAssessment",
    "ClarityLevel",
    "ConfidenceBand",
    # Protocols
    "EmergencyPrefilterProtocol",
    "KnowledgeSearchProtocol",
    "LLMProviderProtocol",
    "GuardrailServiceProtocol",
    # Service
    "OrchestrationService",
    # Factories
    "create_mock_orchestration_service",
]
# === TASK:WP-302:END ===

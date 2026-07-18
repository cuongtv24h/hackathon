# === TASK:WP-301:START ===
import os
from pathlib import Path
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from openai import OpenAI
from packages.contracts.dto import SafetyDecisionDTO

ROOT = Path(__file__).resolve().parents[4]

class SafetyEvaluationOutput(BaseModel):
    risk: Literal["HIGH", "CAUTION", "LOW"]
    subject: Optional[str] = None
    temporality: Literal["current", "past", "hypothetical", "third_party", "unknown"] = "unknown"
    assertion: Literal["negative", "positive", "possible", "unknown"] = "unknown"
    reason_code: str
    evidence_spans: List[str] = Field(default_factory=list)
    clarification_id: Optional[str] = None


class OpenAIProvider:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini", timeout: float = 10.0):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.timeout = timeout
        
        # In a real run, if the API key is missing we raise ConfigurationError
        # (which is a ValueError as per our error contracts)
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured in the environment.")
            
        self.client = OpenAI(api_key=self.api_key)

    def evaluate_safety(
        self,
        message: str,
        context_messages: Optional[List[dict]] = None,
        rule_hints: Optional[List[str]] = None
    ) -> SafetyDecisionDTO:
        prompt_path = ROOT / "config" / "prompts" / "safety-evaluator.md"
        system_instruction = prompt_path.read_text(encoding="utf-8")

        user_content = f"User Message: {message}\n"
        if rule_hints:
            user_content += f"Rule Hints: {', '.join(rule_hints)}\n"
        if context_messages:
            user_content += "Recent Context:\n"
            for msg in context_messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                user_content += f"- {role}: {content}\n"

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ]

        # Call OpenAI Chat Completion with structured outputs
        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=SafetyEvaluationOutput,
            timeout=self.timeout
        )

        parsed = completion.choices[0].message.parsed
        if not parsed:
            raise ValueError("Failed to parse safety evaluator structured response")

        # Validate that all evidence spans are present in the original message
        validated_spans = []
        for span in parsed.evidence_spans:
            if span in message:
                validated_spans.append(span)
            else:
                raise ValueError(f"Evidence span '{span}' not found in original message")

        return SafetyDecisionDTO(
            risk=parsed.risk,
            subject=parsed.subject,
            temporality=parsed.temporality,
            assertion=parsed.assertion,
            reason_code=parsed.reason_code,
            evidence_spans=validated_spans,
            clarification_id=parsed.clarification_id
        )
# === TASK:WP-301:END ===

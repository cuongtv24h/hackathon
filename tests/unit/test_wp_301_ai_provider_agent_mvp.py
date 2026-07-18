# === TASK:WP-301:START ===
import pytest
import sys
from unittest.mock import MagicMock
from apps.api.ai.providers import OpenAIProvider
from packages.contracts.dto import SafetyDecisionDTO

def test_missing_api_key_raises_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIProvider(api_key=None)

def test_successful_safety_evaluation(monkeypatch):
    # Mock OpenAI client
    mock_client = MagicMock()
    mock_completion = MagicMock()

    class FakeParsed:
        risk = "CAUTION"
        subject = "sốt nhẹ"
        temporality = "current"
        assertion = "possible"
        reason_code = "FEVER_MENTION"
        evidence_spans = ["sốt"]
        clarification_id = "CLAR-EMERGENCY-001"

    mock_choice = MagicMock()
    mock_choice.message.parsed = FakeParsed()
    mock_completion.choices = [mock_choice]
    mock_client.beta.chat.completions.parse.return_value = mock_completion

    # Instantiate provider with fake API key and patch internal OpenAI client
    provider = OpenAIProvider(api_key="fake-key")
    provider.client = mock_client

    result = provider.evaluate_safety("Tôi đang bị sốt nhẹ")
    assert isinstance(result, SafetyDecisionDTO)
    assert result.risk == "CAUTION"
    assert result.subject == "sốt nhẹ"
    assert result.evidence_spans == ["sốt"]
    assert result.clarification_id == "CLAR-EMERGENCY-001"

def test_invalid_evidence_span_rejection(monkeypatch):
    mock_client = MagicMock()
    mock_completion = MagicMock()

    class FakeParsed:
        risk = "HIGH"
        subject = "crisis"
        temporality = "current"
        assertion = "positive"
        reason_code = "CRISIS"
        evidence_spans = ["nguy kịch"]  # Not present in user message
        clarification_id = None

    mock_choice = MagicMock()
    mock_choice.message.parsed = FakeParsed()
    mock_completion.choices = [mock_choice]
    mock_client.beta.chat.completions.parse.return_value = mock_completion

    provider = OpenAIProvider(api_key="fake-key")
    provider.client = mock_client

    # The message is "Tôi đau đầu", so "nguy kịch" is not present in the message
    with pytest.raises(ValueError, match="not found in original message"):
        provider.evaluate_safety("Tôi đau đầu")
# === TASK:WP-301:END ===

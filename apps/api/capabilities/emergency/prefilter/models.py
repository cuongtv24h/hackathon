# === TASK:WP-202:START ===
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field

class RuleConfig(BaseModel):
    rule_id: str
    keywords: List[str]
    description: str

class RulesRoot(BaseModel):
    rules: List[RuleConfig]
    prohibited_content: List[str]
    safety_signals: List[str] = Field(default_factory=list)
    clear_non_risk_markers: List[str] = Field(default_factory=list)
    current_risk_assertion_markers: List[str] = Field(default_factory=list)
    version: str
    effective_date: str
    approval_status: str

class ProtocolConfig(BaseModel):
    protocol_id: str
    message: str
    channels: List[str] = Field(default_factory=list)
    approval_status: str

class ProtocolsRoot(BaseModel):
    protocols: Dict[str, ProtocolConfig]
    version: str
    effective_date: str
    approval_status: str

class ClarificationTemplate(BaseModel):
    clarification_id: str
    question: str
    approval_status: str

class ClarificationsRoot(BaseModel):
    templates: List[ClarificationTemplate]
    version: str
    effective_date: str
    approval_status: str
# === TASK:WP-202:END ===

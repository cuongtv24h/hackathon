# === TASK:WP-202:START ===
import json
import os
from pathlib import Path
from typing import Optional, Tuple
from .models import RulesRoot, ProtocolsRoot, ClarificationsRoot, ProtocolConfig
from .normalizer import normalize_text
from packages.contracts.dto import RuleEvidenceDTO

ROOT = Path(__file__).resolve().parents[5]

def load_emergency_configs() -> Tuple[RulesRoot, ProtocolsRoot, ClarificationsRoot]:
    rules_path = ROOT / "config" / "emergency" / "rules.example.json"
    protocols_path = ROOT / "config" / "emergency" / "protocols.example.json"
    clarifications_path = ROOT / "config" / "emergency" / "clarification-templates.example.json"

    with open(rules_path, encoding="utf-8") as f:
        rules = RulesRoot.model_validate(json.load(f))
    with open(protocols_path, encoding="utf-8") as f:
        protocols = ProtocolsRoot.model_validate(json.load(f))
    with open(clarifications_path, encoding="utf-8") as f:
        clarifications = ClarificationsRoot.model_validate(json.load(f))

    return rules, protocols, clarifications


def validate_configs(
    rules: RulesRoot,
    protocols: ProtocolsRoot,
    clarifications: ClarificationsRoot,
    app_env: str
) -> None:
    # 1. Reject missing protocol references
    if "HIGH" not in protocols.protocols:
        raise ValueError("Missing HIGH protocol configuration")
    if "CAUTION_FALLBACK" not in protocols.protocols:
        raise ValueError("Missing CAUTION_FALLBACK protocol configuration")

    # 2. Check mock indications in production mode
    if app_env == "production":
        if rules.approval_status == "mock":
            raise ValueError("Production mode cannot use mock rules")
        if protocols.approval_status == "mock":
            raise ValueError("Production mode cannot use mock protocols")
        if clarifications.approval_status == "mock":
            raise ValueError("Production mode cannot use mock clarifications")

        for k, p in protocols.protocols.items():
            if p.approval_status == "mock":
                raise ValueError(f"Production mode cannot use mock protocol {k}")
            if "mock" in p.message.lower() or "placeholder" in p.message.lower():
                raise ValueError(f"Production mode cannot contain placeholders in protocol {k}")

        for r in rules.rules:
            if "mock" in r.description.lower():
                raise ValueError(f"Production mode cannot contain mock description in rule {r.rule_id}")

        for t in clarifications.templates:
            if t.approval_status == "mock":
                raise ValueError(f"Production mode cannot use mock clarification {t.clarification_id}")


def match_rules(text: str, rules_config: RulesRoot) -> Optional[RuleEvidenceDTO]:
    """Determine if a user message contains direct HIGH keywords or prohibited content."""
    if not text:
        return None
    norm = normalize_text(text)

    # 1. Match prohibited content (suicide/death crisis)
    for pc in rules_config.prohibited_content:
        norm_pc = normalize_text(pc)
        if norm_pc.normalized_nfc in norm.normalized_nfc:
            idx = norm.normalized_nfc.find(norm_pc.normalized_nfc)
            original_span = text[idx:idx + len(pc)]
            return RuleEvidenceDTO(
                rule_id="RULE-PROHIBITED",
                evidence_span=original_span,
                matched_text=pc
            )
        elif norm_pc.diacritic_free in norm.diacritic_free:
            idx = norm.diacritic_free.find(norm_pc.diacritic_free)
            original_span = text[idx:idx + len(pc)]
            return RuleEvidenceDTO(
                rule_id="RULE-PROHIBITED",
                evidence_span=original_span,
                matched_text=pc
            )

    # 2. Match standard rules
    for r in rules_config.rules:
        for kw in r.keywords:
            norm_kw = normalize_text(kw)
            if norm_kw.normalized_nfc in norm.normalized_nfc:
                idx = norm.normalized_nfc.find(norm_kw.normalized_nfc)
                original_span = text[idx:idx + len(kw)]
                return RuleEvidenceDTO(
                    rule_id=r.rule_id,
                    evidence_span=original_span,
                    matched_text=kw
                )
            elif norm_kw.diacritic_free in norm.diacritic_free:
                idx = norm.diacritic_free.find(norm_kw.diacritic_free)
                original_span = text[idx:idx + len(kw)]
                return RuleEvidenceDTO(
                    rule_id=r.rule_id,
                    evidence_span=original_span,
                    matched_text=kw
                )

    return None
# === TASK:WP-202:END ===

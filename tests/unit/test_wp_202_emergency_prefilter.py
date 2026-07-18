# === TASK:WP-202:START ===
import pytest
from apps.api.capabilities.emergency.prefilter import (
    normalize_text,
    remove_vietnamese_diacritics,
    load_emergency_configs,
    validate_configs,
    match_rules,
    RulesRoot,
    ProtocolsRoot,
    ClarificationsRoot
)

def test_unicode_normalization():
    # Test decomposed vs composed forms
    composed = "cấp cứu"
    decomposed = "cấp cứu"  # with separate diacritic combining marks
    
    norm1 = normalize_text(composed)
    norm2 = normalize_text(decomposed)
    
    assert norm1.normalized_nfc == norm2.normalized_nfc
    assert norm1.diacritic_free == "cap cuu"
    assert norm2.diacritic_free == "cap cuu"

def test_config_loading_and_development_mode():
    rules, protocols, clarifications = load_emergency_configs()
    assert len(rules.rules) > 0
    assert "HIGH" in protocols.protocols
    assert "CAUTION_FALLBACK" in protocols.protocols
    assert len(clarifications.templates) > 0
    
    # Should validate successfully in development mode
    validate_configs(rules, protocols, clarifications, "development")

def test_production_mode_validation_rejects_mock():
    rules, protocols, clarifications = load_emergency_configs()
    
    # In production, mock values should raise ValueError
    with pytest.raises(ValueError, match="cannot use mock"):
        validate_configs(rules, protocols, clarifications, "production")

def test_direct_rules_matching():
    rules, _, _ = load_emergency_configs()
    
    # Composed Vietnamese keyword
    msg1 = "Tôi đang trong tình trạng cấp cứu"
    evidence1 = match_rules(msg1, rules)
    assert evidence1 is not None
    assert evidence1.rule_id == "RULE-EMERGENCY-001"
    assert evidence1.matched_text == "cấp cứu"
    
    # No diacritic keyword matching
    msg2 = "nguy kich lam roi"
    evidence2 = match_rules(msg2, rules)
    assert evidence2 is not None
    assert evidence2.rule_id == "RULE-EMERGENCY-001"
    assert evidence2.matched_text == "nguy kịch"

def test_prohibited_content_matching():
    rules, _, _ = load_emergency_configs()
    
    msg = "Tôi muốn tự tử"
    evidence = match_rules(msg, rules)
    assert evidence is not None
    assert evidence.rule_id == "RULE-PROHIBITED"
    assert evidence.matched_text == "tự tử"

def test_no_match():
    rules, _, _ = load_emergency_configs()
    
    msg = "Tôi muốn đặt lịch khám bệnh ngày mai"
    assert match_rules(msg, rules) is None
# === TASK:WP-202:END ===

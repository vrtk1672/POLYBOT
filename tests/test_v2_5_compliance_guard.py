from __future__ import annotations

from app.rules_neuron.compliance_guard import evaluate_compliance
from app.rules_neuron.contracts import ComplianceBlock, ComplianceBlockType, RulesStatus, Severity


def test_missing_rules_blocks_trade_and_block_overrides_all() -> None:
    decision = evaluate_compliance("m1", rules_text_present=False, wording_risk=0.1, dispute_risk=0.1, resolution_clarity=0.9, source_status=RulesStatus.VERIFIED, jurisdiction_status=RulesStatus.CLEAR)
    assert decision.recommendation == "NO_TRADE"
    assert decision.cannot_trade_reason
    override = evaluate_compliance("m2", rules_text_present=True, wording_risk=0.1, dispute_risk=0.1, resolution_clarity=0.9, source_status=RulesStatus.VERIFIED, jurisdiction_status=RulesStatus.CLEAR, jurisdiction_blocks=[ComplianceBlock(market_id="m2", block_type=ComplianceBlockType.MANUAL_BLOCK, severity=Severity.BLOCKING, reason="manual")])
    assert override.recommendation == "NO_TRADE"


def test_ambiguous_wording_penalizes_and_verified_source_allows_clear() -> None:
    penalized = evaluate_compliance("m1", rules_text_present=True, wording_risk=0.7, dispute_risk=0.2, resolution_clarity=0.7, source_status=RulesStatus.VERIFIED, jurisdiction_status=RulesStatus.CLEAR)
    clear = evaluate_compliance("m2", rules_text_present=True, wording_risk=0.1, dispute_risk=0.1, resolution_clarity=0.9, source_status=RulesStatus.VERIFIED, jurisdiction_status=RulesStatus.CLEAR)
    assert penalized.recommendation == "PENALIZE_HEAVILY"
    assert clear.recommendation == "TRADE_ALLOWED"


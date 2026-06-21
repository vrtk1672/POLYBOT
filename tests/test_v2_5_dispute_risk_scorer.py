from __future__ import annotations

from app.rules_neuron.contracts import ParsedRules, ResolutionSourceStatus, RulesStatus, SettlementMethod
from app.rules_neuron.dispute_risk_scorer import compute_dispute_risk


def test_subjective_manual_unclear_source_high_dispute() -> None:
    parsed = ParsedRules(market_id="m1", rules_text_present=True)
    risk = compute_dispute_risk(parsed, ResolutionSourceStatus(market_id="m1", verification_status=RulesStatus.UNVERIFIED), ["manual discretion"], SettlementMethod.SUBJECTIVE)
    assert risk.dispute_risk >= 0.5


def test_clear_official_source_low_dispute() -> None:
    parsed = ParsedRules(market_id="m1", rules_text_present=True)
    risk = compute_dispute_risk(parsed, ResolutionSourceStatus(market_id="m1", verification_status=RulesStatus.VERIFIED), [], SettlementMethod.OBJECTIVE_SOURCE)
    assert risk.dispute_risk < 0.3


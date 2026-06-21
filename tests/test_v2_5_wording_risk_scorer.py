from __future__ import annotations

from app.rules_neuron.ambiguous_terms_detector import detect_ambiguous_terms
from app.rules_neuron.contracts import ParsedRules, ResolutionSourceStatus, RulesStatus, SettlementMethod
from app.rules_neuron.wording_risk_scorer import compute_wording_risk


def test_missing_rules_and_contradiction_high_risk() -> None:
    parsed = ParsedRules(market_id="m1", rules_text_present=False, settlement_method=SettlementMethod.UNKNOWN)
    score = compute_wording_risk(parsed, deadline_result={"risk": 0.5}, edge_cases=[], ambiguous_terms=[], source_status=ResolutionSourceStatus(market_id="m1", verification_status=RulesStatus.UNVERIFIED), contradictions=["x"])
    assert score.total_wording_risk >= 0.85


def test_clear_objective_rules_low_risk_and_ambiguous_high() -> None:
    source = ResolutionSourceStatus(market_id="m1", verification_status=RulesStatus.VERIFIED, reliability_score=0.9)
    clear = ParsedRules(market_id="m1", rules_text_present=True, settlement_method=SettlementMethod.OBJECTIVE_SOURCE)
    low = compute_wording_risk(clear, deadline_result={"risk": 0.0}, edge_cases=[], ambiguous_terms=[], source_status=source)
    ambiguous = compute_wording_risk(clear, deadline_result={"risk": 0.4}, edge_cases=["before/after boundary ambiguity"], ambiguous_terms=detect_ambiguous_terms("reported by end of day before official confirmation"), source_status=source)
    assert low.total_wording_risk < ambiguous.total_wording_risk


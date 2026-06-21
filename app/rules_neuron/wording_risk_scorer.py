from __future__ import annotations

from app.rules_neuron.ambiguous_terms_detector import ambiguity_score
from app.rules_neuron.contracts import ParsedRules, ResolutionSourceStatus, RulesStatus, SettlementMethod, WordingRiskScore, bounded
from app.rules_neuron.settlement_method_parser import compute_settlement_risk


def compute_wording_risk(
    parsed_rules: ParsedRules,
    *,
    deadline_result: dict,
    edge_cases: list[str],
    ambiguous_terms: list[dict],
    source_status: ResolutionSourceStatus,
    contradictions: list[str] | None = None,
) -> WordingRiskScore:
    missing_rules = not parsed_rules.rules_text_present
    ambiguity = 0.85 if missing_rules else ambiguity_score(ambiguous_terms)
    deadline_risk = float(deadline_result.get("risk") or 0)
    source_risk = 0.65 if source_status.verification_status in {RulesStatus.UNKNOWN, RulesStatus.UNVERIFIED, RulesStatus.WARNING} else 0.15
    settlement_risk = compute_settlement_risk(parsed_rules.settlement_method)
    edge_case_risk = min(len(edge_cases) * 0.18, 0.8)
    contradiction_risk = 0.85 if contradictions else 0.0
    scope_risk = 0.45 if any("threshold" in item or "boundary" in item for item in edge_cases) else 0.0
    total = bounded(max(ambiguity, contradiction_risk, 0.0) * 0.3 + deadline_risk * 0.18 + source_risk * 0.16 + settlement_risk * 0.16 + edge_case_risk * 0.14 + scope_risk * 0.06)
    if missing_rules:
        total = max(total, 0.85)
    return WordingRiskScore(
        market_id=parsed_rules.market_id,
        rules_hash=parsed_rules.rules_hash,
        ambiguity_score=ambiguity,
        deadline_risk=deadline_risk,
        source_risk=source_risk,
        scope_risk=scope_risk,
        settlement_risk=settlement_risk,
        edge_case_risk=edge_case_risk,
        contradiction_risk=contradiction_risk,
        total_wording_risk=total,
        risk_terms=ambiguous_terms,
        explanation="missing rules" if missing_rules else "deterministic wording risk score",
    )


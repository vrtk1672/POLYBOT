from __future__ import annotations

from app.rules_neuron.contracts import DisputeRiskScore, ParsedRules, ResolutionSourceStatus, RulesStatus, SettlementMethod, bounded


def compute_dispute_risk(
    parsed_rules: ParsedRules,
    source_status: ResolutionSourceStatus,
    edge_cases: list[str],
    settlement_method: SettlementMethod,
    *,
    category: str | None = None,
) -> DisputeRiskScore:
    factors: list[str] = []
    risk = 0.0
    if not parsed_rules.rules_text_present:
        risk += 0.75
        factors.append("missing rules")
    if source_status.verification_status in {RulesStatus.UNKNOWN, RulesStatus.UNVERIFIED, RulesStatus.WARNING}:
        risk += 0.25
        factors.append("unclear or unverified source")
    if settlement_method in {SettlementMethod.SUBJECTIVE, SettlementMethod.PLATFORM_MANUAL, SettlementMethod.UNKNOWN}:
        risk += 0.25
        factors.append(f"settlement method {settlement_method.value}")
    if edge_cases:
        risk += min(len(edge_cases) * 0.08, 0.3)
        factors.extend(edge_cases[:4])
    if category and category.lower() in {"legal", "court", "politics", "politics-policy"} and source_status.verification_status != RulesStatus.VERIFIED:
        risk += 0.15
        factors.append("sensitive category with unclear source")
    return DisputeRiskScore(market_id=parsed_rules.market_id, dispute_risk=bounded(risk), factors=factors, explanation="; ".join(factors) or "low deterministic dispute risk")


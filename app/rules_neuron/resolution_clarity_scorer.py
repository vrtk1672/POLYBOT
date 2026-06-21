from __future__ import annotations

from app.rules_neuron.contracts import ParsedRules, ResolutionSourceStatus, RulesStatus, SettlementMethod, bounded


def compute_resolution_clarity(parsed_rules: ParsedRules, source_status: ResolutionSourceStatus, deadline_result: dict, settlement_method: SettlementMethod) -> float:
    clarity = 1.0
    if not parsed_rules.rules_text_present:
        clarity -= 0.55
    if source_status.verification_status != RulesStatus.VERIFIED:
        clarity -= 0.2
    if float(deadline_result.get("risk") or 0) > 0.3:
        clarity -= 0.15
    if settlement_method in {SettlementMethod.SUBJECTIVE, SettlementMethod.PLATFORM_MANUAL, SettlementMethod.UNKNOWN}:
        clarity -= 0.15
    if parsed_rules.dangerous_edge_cases:
        clarity -= min(len(parsed_rules.dangerous_edge_cases) * 0.08, 0.2)
    return bounded(clarity)


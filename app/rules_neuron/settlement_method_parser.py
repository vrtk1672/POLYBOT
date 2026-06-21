from __future__ import annotations

from app.rules_neuron.contracts import SettlementMethod, bounded


def parse_settlement_method(rules_text: str | None) -> SettlementMethod:
    lower = (rules_text or "").lower()
    if any(term in lower for term in ("official source", "according to", "resolved based on", "final result from")):
        return SettlementMethod.OBJECTIVE_SOURCE
    if any(term in lower for term in ("polymarket", "platform", "manual", "admin", "moderator")):
        return SettlementMethod.PLATFORM_MANUAL
    if "oracle" in lower:
        return SettlementMethod.ORACLE
    if any(term in lower for term in ("reasonable", "significant", "substantially", "in spirit", "subjective")):
        return SettlementMethod.SUBJECTIVE
    return SettlementMethod.UNKNOWN


def identify_manual_resolution(rules_text: str | None) -> bool:
    return parse_settlement_method(rules_text) == SettlementMethod.PLATFORM_MANUAL


def identify_objective_source_resolution(rules_text: str | None) -> bool:
    return parse_settlement_method(rules_text) == SettlementMethod.OBJECTIVE_SOURCE


def identify_subjective_wording(rules_text: str | None) -> bool:
    return parse_settlement_method(rules_text) == SettlementMethod.SUBJECTIVE


def compute_settlement_risk(method: SettlementMethod) -> float:
    return {
        SettlementMethod.OBJECTIVE_SOURCE: 0.1,
        SettlementMethod.ORACLE: 0.25,
        SettlementMethod.PLATFORM_MANUAL: 0.45,
        SettlementMethod.SUBJECTIVE: 0.75,
        SettlementMethod.UNKNOWN: 0.6,
    }.get(method, 0.6)


from __future__ import annotations

from app.opportunity.contracts import OpportunityRiskFlag


class NoTradeReasonBuilder:
    def build(self, *, score: float, confidence: float, risk_flags: list[OpportunityRiskFlag], weak_trigger: bool = False) -> list[str]:
        reasons: list[str] = []
        for flag in risk_flags:
            mapping = {
                "missing_context_data": "missing_data",
                "missing_capital_data": "missing_data",
                "missing_context_and_capital": "missing_data",
                "capital_not_allowed": "capital_not_allowed",
                "technical_blocked": "bad_liquidity",
                "missing_bid_ask": "missing_bid_ask",
                "missing_orderbook": "missing_bid_ask",
                "missing_exit_liquidity": "poor_exit_quality",
                "poor_exit_quality": "poor_exit_quality",
                "low_depth": "bad_liquidity",
                "wide_spread": "wide_spread",
                "high_wording_risk": "high_wording_risk",
                "already_priced_in": "already_priced_in",
                "high_slippage": "high_slippage",
                "high_friction": "high_slippage",
            }
            if flag.risk_flag in mapping:
                reasons.append(mapping[flag.risk_flag])
        if weak_trigger:
            reasons.append("weak_trigger")
        if confidence < 0.25:
            reasons.append("low_context_confidence")
        if score < 0.2:
            reasons.append("low_score")
        return list(dict.fromkeys(reasons))


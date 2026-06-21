from __future__ import annotations

from app.opportunity.contracts import OpportunityInput, OpportunityRiskFlag, bounded


class CandidateEngineSuggester:
    def suggest(self, payload: OpportunityInput, *, score: float, risk_flags: list[OpportunityRiskFlag]) -> list[str]:
        if any(flag.blocks_opportunity for flag in risk_flags):
            return ["NO_TRADE"]
        context = payload.context_output or {}
        technical = payload.technical_truth or {}
        liquidity = _as_dict(technical.get("liquidity_signal"))
        fee = payload.fee_reward_signal or {}
        memory = payload.market_memory or {}

        engines: list[str] = []
        if score < 0.25 or bounded(context.get("confidence")) < 0.2:
            return ["NO_TRADE"]
        if bounded(context.get("strength")) >= 0.55 and bounded(context.get("urgency_score")) >= 0.4:
            engines.append("STRIKE")
        if _number(memory.get("wording_risk_avg")) < 0.35 and bounded(context.get("confidence")) >= 0.65 and _number(liquidity.get("exit_quality_score")) >= 0.6:
            engines.append("SAFE")
        if _number(fee.get("reward_score")) >= 0.4 and _number(liquidity.get("entry_liquidity_score")) >= 0.5:
            engines.append("MAKER")
        if bounded(context.get("strength")) >= 0.4 and _number(liquidity.get("max_safe_size_usd")) > 0:
            engines.append("CONVEX")
        if bounded(context.get("urgency_score")) >= 0.7 and score >= 0.45:
            engines.append("HUNT")
        if score >= 0.6 and "SAFE" not in engines:
            engines.append("SAFE")
        if not engines:
            engines.append("NO_TRADE" if score < 0.35 else "WATCH")
        return list(dict.fromkeys(engines))


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _number(value, default=0.0) -> float:
    try:
        return float(default if value is None else value)
    except (TypeError, ValueError):
        return default


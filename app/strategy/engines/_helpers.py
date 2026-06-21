from __future__ import annotations

from app.strategy.contracts import StrategyRouteInput, bounded


def component(payload: StrategyRouteInput, name: str, default: float = 0.0) -> float:
    return bounded(payload.opportunity_components.get(name), default)


def capital_allowed(payload: StrategyRouteInput) -> bool:
    return payload.capital_output.get("capital_allowed") is True or bool(payload.opportunity_components.get("capital_allowed"))


def hard_blocks(payload: StrategyRouteInput) -> list[str]:
    reasons = []
    if payload.opportunity_score_band == "BLOCKED":
        reasons.append("opportunity_blocked")
    for flag in payload.opportunity_risk_flags:
        if flag.get("blocks_opportunity") is True or str(flag.get("severity")).upper() == "BLOCKING":
            reasons.append(str(flag.get("risk_flag") or "blocking_risk_flag"))
    for reason in payload.opportunity_no_trade_reasons:
        if reason in {"missing_bid_ask", "bad_liquidity", "poor_exit_quality", "capital_not_allowed", "high_wording_risk"}:
            reasons.append(reason)
    if payload.insufficient_data_reasons:
        reasons.append("insufficient_data")
    return list(dict.fromkeys(reasons))


def has_candidate(payload: StrategyRouteInput, engine: str) -> bool:
    candidates = set(payload.candidate_engines_from_opportunity)
    return not candidates or engine in candidates or "NO_TRADE" in candidates


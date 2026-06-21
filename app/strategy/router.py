from __future__ import annotations

from typing import Any

from app.strategy.contracts import EngineDecision, EngineRejection, StrategyRoute, StrategyRouteInput, reproducibility_hash
from app.strategy.engine_rejection_builder import EngineRejectionBuilder
from app.strategy.engines import ConvexEngine, HuntEngine, MakerEngine, MoonshotBasketEngine, NoTradeEngine, ReinvestEngine, SafeEngine, StrikeEngine


class StrategyRouter:
    def __init__(self) -> None:
        self.engines = [
            SafeEngine(),
            StrikeEngine(),
            ConvexEngine(),
            MakerEngine(),
            HuntEngine(),
            MoonshotBasketEngine(),
            ReinvestEngine(),
            NoTradeEngine(),
        ]
        self.rejections = EngineRejectionBuilder()

    def route(self, payload: StrategyRouteInput) -> StrategyRoute:
        decisions = [engine.evaluate(payload) for engine in self.engines]
        rejections = [self.rejections.build(decision.engine, [decision.rejection_reason or "engine_rejected"], hard=decision.severity == "BLOCKING", severity=decision.severity) for decision in decisions if not decision.eligible and decision.engine != "NO_TRADE"]
        hard_reasons = _hard_block_reasons(payload)
        eligible_trade = [decision for decision in decisions if decision.eligible and decision.engine != "NO_TRADE"]
        selected: EngineDecision
        status = "ROUTED"
        no_trade_reasons = list(payload.opportunity_no_trade_reasons)
        if hard_reasons:
            selected = _no_trade(decisions)
            status = "BLOCKED"
            no_trade_reasons.extend(hard_reasons)
        elif payload.insufficient_data_reasons:
            selected = _no_trade(decisions)
            status = "INSUFFICIENT_DATA"
            no_trade_reasons.extend(payload.insufficient_data_reasons)
        elif not eligible_trade:
            selected = _no_trade(decisions)
            status = "NO_TRADE"
            no_trade_reasons.append("all_engines_rejected")
        else:
            selected = max(eligible_trade, key=lambda item: (item.engine_score, item.confidence))
        for decision in decisions:
            decision.selected = decision.engine == selected.engine
        if selected.engine == "NO_TRADE" and status == "ROUTED":
            status = "NO_TRADE"
        route = StrategyRoute(
            market_id=payload.market_id,
            side=payload.side,
            selected_engine=selected.engine,
            route_status=status,
            opportunity_score=payload.opportunity_score,
            score_band=payload.opportunity_score_band,
            route_confidence=selected.confidence,
            contract=selected.contract,
            engine_decisions=decisions,
            engine_rejections=rejections,
            no_trade_reasons=no_trade_reasons,
            risk_flags=payload.opportunity_risk_flags,
            cooldown_required=len([item for item in rejections if item.hard_block]) >= 3,
            insufficient_data=bool(payload.insufficient_data_reasons),
            insufficient_data_reasons=payload.insufficient_data_reasons,
            route_reason=_route_reason(selected, status),
        )
        route.reproducibility_hash = reproducibility_hash(_hash_payload(payload, route))
        return route


def _no_trade(decisions: list[EngineDecision]) -> EngineDecision:
    return next(decision for decision in decisions if decision.engine == "NO_TRADE")


def _hard_block_reasons(payload: StrategyRouteInput) -> list[str]:
    reasons: list[str] = []
    if payload.opportunity_score_band == "BLOCKED":
        reasons.append("opportunity_blocked")
    for flag in payload.opportunity_risk_flags:
        if flag.get("blocks_opportunity") is True or str(flag.get("severity")).upper() == "BLOCKING":
            reasons.append(str(flag.get("risk_flag") or "blocking_risk_flag"))
    if "capital_not_allowed" in payload.opportunity_no_trade_reasons:
        reasons.append("capital_not_allowed")
    return list(dict.fromkeys(reasons))


def _route_reason(selected: EngineDecision, status: str) -> str:
    if selected.engine == "NO_TRADE":
        return f"NO_TRADE selected because route status is {status}."
    return f"{selected.engine} selected after independent engine validation; this is a contract only, not an order."


def _hash_payload(payload: StrategyRouteInput, route: StrategyRoute) -> dict[str, Any]:
    return {
        "market_id": payload.market_id,
        "side": payload.side,
        "opportunity_run_id": payload.opportunity_run_id,
        "opportunity_score": payload.opportunity_score,
        "score_band": payload.opportunity_score_band,
        "candidate_engines": payload.candidate_engines_from_opportunity,
        "risk_flags": payload.opportunity_risk_flags,
        "no_trade_reasons": payload.opportunity_no_trade_reasons,
        "selected_engine": route.selected_engine,
        "route_status": route.route_status,
        "engine_decisions": [
            {
                "engine": decision.engine,
                "eligible": decision.eligible,
                "engine_score": decision.engine_score,
                "confidence": decision.confidence,
                "rejection_reason": decision.rejection_reason,
            }
            for decision in route.engine_decisions
        ],
    }


from __future__ import annotations

from typing import Any

from app.opportunity.candidate_engine_suggester import CandidateEngineSuggester
from app.opportunity.contracts import OpportunityInput, OpportunityScore, OpportunitySignalInput, bounded, reproducibility_hash
from app.opportunity.no_trade_reason_builder import NoTradeReasonBuilder
from app.opportunity.risk_flag_builder import OpportunityRiskFlagBuilder


POSITIVE_WEIGHTS = {
    "edge": 0.18,
    "confidence": 0.14,
    "trigger_strength": 0.14,
    "repricing_potential": 0.12,
    "time_efficiency": 0.08,
    "liquidity_quality": 0.12,
    "exit_probability": 0.08,
    "capital_recycling_speed": 0.05,
    "convexity": 0.04,
    "balance_fit": 0.03,
    "fee_reward_advantage": 0.02,
}

NEGATIVE_WEIGHTS = {
    "risk_penalty": 0.20,
    "slippage_penalty": 0.14,
    "lockup_penalty": 0.10,
    "correlation_risk": 0.06,
    "trap_risk": 0.14,
    "wording_risk": 0.14,
    "adverse_selection_risk": 0.10,
    "already_priced_in_score": 0.12,
}


class OpportunityScorer:
    def __init__(
        self,
        *,
        risk_builder: OpportunityRiskFlagBuilder | None = None,
        engine_suggester: CandidateEngineSuggester | None = None,
        no_trade_builder: NoTradeReasonBuilder | None = None,
    ) -> None:
        self._risk_builder = risk_builder or OpportunityRiskFlagBuilder()
        self._engine_suggester = engine_suggester or CandidateEngineSuggester()
        self._no_trade_builder = no_trade_builder or NoTradeReasonBuilder()

    def score(self, payload: OpportunityInput) -> tuple[OpportunityScore, list[OpportunitySignalInput]]:
        components = _components(payload)
        positives = sum(components[name] * weight for name, weight in POSITIVE_WEIGHTS.items())
        negatives = sum(components[name] * weight for name, weight in NEGATIVE_WEIGHTS.items())
        risk_flags = self._risk_builder.build(payload)
        flag_penalty = min(1.0, sum(flag.penalty for flag in risk_flags if not flag.blocks_opportunity) * 0.18)
        hard_block = any(flag.blocks_opportunity for flag in risk_flags)
        raw_score = bounded(positives - negatives - flag_penalty)
        confidence = bounded(components["confidence"] * payload.data_completeness_score)
        weak_trigger = components["trigger_strength"] < 0.2
        if payload.insufficient_data_reasons:
            raw_score *= 0.6
            confidence *= 0.65
        if hard_block:
            raw_score = 0.0
        band = _band(raw_score, confidence, hard_block)
        candidate_engines = self._engine_suggester.suggest(payload, score=raw_score, risk_flags=risk_flags)
        no_trade = self._no_trade_builder.build(score=raw_score, confidence=confidence, risk_flags=risk_flags, weak_trigger=weak_trigger)
        if band == "BLOCKED" and not no_trade:
            no_trade.append("blocked")
        if not no_trade and "NO_TRADE" in candidate_engines:
            no_trade.append("low_score")
        signal_inputs = _signal_inputs(components, payload)
        score = OpportunityScore(
            market_id=payload.market_id,
            side=payload.side,
            opportunity_score=raw_score,
            score_band=band,
            edge=components["edge"],
            confidence=confidence,
            trigger_strength=components["trigger_strength"],
            repricing_potential=components["repricing_potential"],
            time_efficiency=components["time_efficiency"],
            liquidity_quality=components["liquidity_quality"],
            exit_probability=components["exit_probability"],
            capital_recycling_speed=components["capital_recycling_speed"],
            convexity=components["convexity"],
            balance_fit=components["balance_fit"],
            fee_reward_advantage=components["fee_reward_advantage"],
            risk_penalty=components["risk_penalty"],
            slippage_penalty=components["slippage_penalty"],
            lockup_penalty=components["lockup_penalty"],
            correlation_risk=components["correlation_risk"],
            trap_risk=components["trap_risk"],
            wording_risk=components["wording_risk"],
            adverse_selection_risk=components["adverse_selection_risk"],
            already_priced_in_score=components["already_priced_in_score"],
            technical_blocked=bool(payload.technical_truth.get("technical_blocked")),
            capital_allowed=bool(payload.capital_output.get("capital_allowed")),
            insufficient_data=bool(payload.insufficient_data_reasons or payload.context_output.get("insufficient_data") or payload.capital_output.get("insufficient_data")),
            insufficient_data_reasons=payload.insufficient_data_reasons,
            risk_flags=risk_flags,
            candidate_engines=candidate_engines,
            no_trade_reasons=no_trade,
            explanation=_explanation(raw_score, band, risk_flags, no_trade),
            reproducibility_hash=reproducibility_hash({"market_id": payload.market_id, "side": payload.side, "components": components, "risk_flags": [flag.model_dump() for flag in risk_flags], "insufficient": payload.insufficient_data_reasons}),
        )
        return score, signal_inputs


def _components(payload: OpportunityInput) -> dict[str, float]:
    context = payload.context_output or {}
    capital = payload.capital_output or {}
    technical = payload.technical_truth or {}
    memory = payload.market_memory or {}
    liquidity = _dict(technical.get("liquidity_signal"))
    time_signal = _dict(technical.get("time_signal"))
    fee = payload.fee_reward_signal or _dict(technical.get("fee_reward_signal"))
    social_use = _social_usefulness(payload.social_signals, memory)
    whale_use = _whale_usefulness(payload.whale_signals, memory)
    context_strength = bounded(context.get("strength"))
    context_confidence = bounded(context.get("confidence"))
    technical_score = bounded(technical.get("technical_score"))
    memory_confidence = bounded(memory.get("memory_confidence") or memory.get("confidence"))
    liquidity_quality = max(bounded(liquidity.get("entry_liquidity_score")), bounded(liquidity.get("exit_liquidity_score")), bounded(liquidity.get("exit_quality_score")))
    exit_probability = bounded(liquidity.get("exit_quality_score"), 0.0)
    slippage_bps = _num(liquidity.get("expected_slippage_bps"))
    spread_bps = _num(_dict(technical.get("orderbook_signal")).get("spread_bps"))
    wording = max(bounded(memory.get("wording_risk_avg")), _max_rows(payload.rules_signals, ("wording_risk", "rules_risk_score", "avg_wording_risk")), bounded(context.get("risk_score")) * 0.8)
    already = bounded(context.get("already_priced_in_score"))
    friction = bounded(fee.get("friction_score"))
    reward = bounded(fee.get("reward_score"))
    net_edge = bounded(fee.get("net_edge_after_costs"), 0.5)
    edge = bounded((context_strength * 0.45) + (technical_score * 0.2) + (whale_use * 0.12) + (social_use * 0.08) + (net_edge * 0.15))
    repricing = bounded(context_strength * (1 - already) + technical_score * 0.25)
    return {
        "edge": edge,
        "confidence": bounded((context_confidence * 0.35) + (bounded(capital.get("allocation_confidence")) * 0.25) + (memory_confidence * 0.2) + (payload.data_completeness_score * 0.2)),
        "trigger_strength": context_strength,
        "repricing_potential": repricing,
        "time_efficiency": bounded(time_signal.get("time_efficiency_score"), bounded(memory.get("avg_time_efficiency"), 0.35)),
        "liquidity_quality": liquidity_quality,
        "exit_probability": exit_probability,
        "capital_recycling_speed": bounded(capital.get("capital_recycling_score")),
        "convexity": bounded(max(0.0, 0.65 - _num(_dict(technical.get("market_signal")).get("price_yes"), 0.5))),
        "balance_fit": 1.0 if capital.get("capital_allowed") is True else 0.0,
        "fee_reward_advantage": bounded(reward * 0.6 + max(0.0, net_edge - 0.5) * 0.8),
        "risk_penalty": bounded(max(bounded(context.get("risk_score")), 1 - context_confidence if context else 0.3)),
        "slippage_penalty": bounded((slippage_bps / 1000.0) + (spread_bps / 2000.0) + friction * 0.5),
        "lockup_penalty": bounded(time_signal.get("lockup_penalty_score"), bounded(memory.get("avg_hold_seconds")) if _num(memory.get("avg_hold_seconds")) > 86400 else 0.0),
        "correlation_risk": bounded(memory.get("false_signal_rate")),
        "trap_risk": bounded(max(_max_rows(payload.whale_signals, ("whale_reversal_risk", "noise_penalty")), _max_rows(payload.social_signals, ("bot_risk", "spam_ratio")))),
        "wording_risk": wording,
        "adverse_selection_risk": bounded(memory.get("maker_adverse_selection_rate")),
        "already_priced_in_score": already,
    }


def _signal_inputs(components: dict[str, float], payload: OpportunityInput) -> list[OpportunitySignalInput]:
    rows: list[OpportunitySignalInput] = []
    for name, weight in POSITIVE_WEIGHTS.items():
        rows.append(OpportunitySignalInput(source_type=_source_for(name), input_name=name, input_value_numeric=components[name], weight=weight, contribution=components[name] * weight))
    for name, weight in NEGATIVE_WEIGHTS.items():
        rows.append(OpportunitySignalInput(source_type=_source_for(name), input_name=name, input_value_numeric=components[name], weight=-weight, contribution=-(components[name] * weight)))
    rows.append(OpportunitySignalInput(source_type="opportunity", input_name="data_completeness_score", input_value_numeric=payload.data_completeness_score, weight=0.0, contribution=0.0))
    return rows


def _source_for(name: str) -> str:
    if name in {"trigger_strength", "repricing_potential", "already_priced_in_score", "risk_penalty"}:
        return "context_brain"
    if name in {"balance_fit", "capital_recycling_speed"}:
        return "capital_brain"
    if name in {"liquidity_quality", "exit_probability", "slippage_penalty"}:
        return "liquidity"
    if name in {"time_efficiency", "lockup_penalty"}:
        return "time"
    if name in {"fee_reward_advantage"}:
        return "fees"
    if name in {"wording_risk"}:
        return "rules"
    return "market_memory"


def _band(score: float, confidence: float, blocked: bool) -> str:
    if blocked:
        return "BLOCKED"
    if score >= 0.72 and confidence >= 0.72:
        return "HIGH_CONVICTION"
    if score >= 0.55 and confidence >= 0.45:
        return "STRONG"
    if score >= 0.30 and confidence >= 0.25:
        return "WATCHLIST"
    return "LOW"


def _explanation(score: float, band: str, flags, no_trade: list[str]) -> str:
    if band == "BLOCKED":
        return "Opportunity blocked by hard risk flags: " + ", ".join(flag.risk_flag for flag in flags if flag.blocks_opportunity)
    if no_trade:
        return "Opportunity score is constrained by: " + ", ".join(no_trade)
    return f"Opportunity scored {score:.3f} with band {band}; candidate engines are suggestions only."


def _social_usefulness(rows: list[dict[str, Any]], memory: dict[str, Any]) -> float:
    memory_ok = bounded(_first(memory, "source_reliability", "usefulness_score"), 0.5)
    values = [bounded(row.get("hype_pressure")) * (1 - max(bounded(row.get("bot_risk")), bounded(row.get("spam_ratio")))) * memory_ok for row in rows]
    return max(values or [0.0])


def _whale_usefulness(rows: list[dict[str, Any]], memory: dict[str, Any]) -> float:
    whale_memory = memory.get("whale_memory") if isinstance(memory.get("whale_memory"), dict) else {}
    support = max(bounded(whale_memory.get("whale_score")), bounded(whale_memory.get("follow_value_avg"))) * bounded(whale_memory.get("confidence"))
    values = [bounded(row.get("follow_value")) * max(support, 0.0) for row in rows]
    return max(values or [0.0])


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(default if value is None else value)
    except (TypeError, ValueError):
        return default


def _max_rows(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> float:
    return max([bounded(row.get(key)) for row in rows for key in keys] or [0.0])


def _first(mapping: dict[str, Any], outer: str, inner: str) -> Any:
    value = mapping.get(outer)
    if isinstance(value, dict):
        return value.get(inner)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0].get(inner)
    return None


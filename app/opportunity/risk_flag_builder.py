from __future__ import annotations

from typing import Any

from app.opportunity.contracts import OpportunityInput, OpportunityRiskFlag, bounded


class OpportunityRiskFlagBuilder:
    def build(self, payload: OpportunityInput) -> list[OpportunityRiskFlag]:
        flags: list[OpportunityRiskFlag] = []
        for reason in payload.insufficient_data_reasons:
            flags.append(_flag(reason, "WARNING", "input_builder", 0.18, reason == "missing_context_and_capital"))

        context = payload.context_output or {}
        capital = payload.capital_output or {}
        technical = payload.technical_truth or {}
        memory = payload.market_memory or {}
        fee = payload.fee_reward_signal or {}

        if context.get("insufficient_data") is True:
            flags.append(_flag("missing_context_data", "WARNING", "context_brain", 0.25))
        if capital.get("insufficient_data") is True:
            flags.append(_flag("missing_capital_data", "BLOCKING", "capital_brain", 1.0, True))
        if capital and capital.get("capital_allowed") is False:
            flags.append(_flag("capital_not_allowed", "BLOCKING", "capital_brain", 1.0, True, str(capital.get("block_reason") or "capital blocked")))

        if technical.get("technical_blocked") is True:
            flags.append(_flag("technical_blocked", "BLOCKING", "market_technical", 1.0, True))
        block_reasons = _list(technical.get("block_reasons_json") or technical.get("block_reasons"))
        for reason in block_reasons:
            normalized = str(reason)
            blocks = normalized in {"missing_bid_ask", "missing_orderbook", "missing_exit_liquidity", "poor_exit_quality", "low_depth"}
            flags.append(_flag(normalized, "BLOCKING" if blocks else "WARNING", "market_technical", 1.0 if blocks else 0.35, blocks))

        orderbook = _dict(technical.get("orderbook_signal"))
        liquidity = _dict(technical.get("liquidity_signal"))
        if orderbook:
            if orderbook.get("has_bid_ask") is False:
                flags.append(_flag("missing_bid_ask", "BLOCKING", "orderbook", 1.0, True))
            if _number(orderbook.get("spread_bps")) >= 800:
                flags.append(_flag("wide_spread", "WARNING", "orderbook", 0.45))
            if _number(orderbook.get("depth_2c")) <= 0 and orderbook:
                flags.append(_flag("low_depth", "BLOCKING", "orderbook", 1.0, True))
        if liquidity:
            if _number(liquidity.get("exit_quality_score")) < 0.25:
                flags.append(_flag("poor_exit_quality", "BLOCKING", "liquidity", 1.0, True))
            if _number(liquidity.get("expected_slippage_bps")) >= 500:
                flags.append(_flag("high_slippage", "WARNING", "liquidity", 0.45))
            if _number(liquidity.get("max_safe_size_usd")) <= 0:
                flags.append(_flag("missing_exit_liquidity", "BLOCKING", "liquidity", 1.0, True))

        wording = max(
            bounded(context.get("risk_score")),
            bounded(memory.get("wording_risk_avg")),
            _max_from_rows(payload.rules_signals, ("rules_risk_score", "avg_wording_risk", "wording_risk")),
        )
        if wording >= 0.6:
            flags.append(_flag("high_wording_risk", "BLOCKING" if wording >= 0.85 else "WARNING", "rules", wording, wording >= 0.85))
        priced = bounded(context.get("already_priced_in_score"))
        if priced >= 0.75:
            flags.append(_flag("already_priced_in", "WARNING", "context_brain", priced))
        if bounded(fee.get("friction_score")) >= 0.7:
            flags.append(_flag("high_friction", "WARNING", "fees", bounded(fee.get("friction_score"))))
        if "ai_cannot_override_risk" in _list(context.get("risks_json") or context.get("risks")):
            flags.append(_flag("ai_cannot_override_risk", "WARNING", "context_brain", 0.2))

        unique: dict[tuple[str, str], OpportunityRiskFlag] = {}
        for flag in flags:
            key = (flag.risk_flag, flag.source_type)
            existing = unique.get(key)
            if existing is None or flag.penalty > existing.penalty or flag.blocks_opportunity:
                unique[key] = flag
        return list(unique.values())


def _flag(name: str, severity: str, source: str, penalty: float, blocks: bool = False, explanation: str | None = None) -> OpportunityRiskFlag:
    return OpportunityRiskFlag(
        risk_flag=name,
        severity=severity,  # type: ignore[arg-type]
        source_type=source,
        penalty=penalty,
        blocks_opportunity=blocks,
        explanation=explanation or name.replace("_", " "),
    )


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(default if value is None else value)
    except (TypeError, ValueError):
        return default


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _max_from_rows(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> float:
    values = []
    for row in rows:
        for key in keys:
            values.append(bounded(row.get(key)))
    return max(values or [0.0])


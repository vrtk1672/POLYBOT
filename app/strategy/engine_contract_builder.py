from __future__ import annotations

from typing import Any

from app.strategy.contracts import EngineContract, StrategyRouteInput, bounded, non_negative


class EngineContractBuilder:
    def build(
        self,
        payload: StrategyRouteInput,
        *,
        engine: str,
        reason: str,
        entry_mode: str,
        exit_mode: str,
        max_hold_minutes: int,
        max_position_size_usd: float | None = None,
        max_loss_fraction: float = 0.12,
        metadata: dict[str, Any] | None = None,
    ) -> EngineContract:
        components = payload.opportunity_components
        capital = payload.capital_output
        max_safe = non_negative(components.get("max_safe_size_usd") or _nested(payload.technical_truth, "liquidity_signal", "max_safe_size_usd"), 0.0)
        capital_max = non_negative(capital.get("max_position_size_usd"), 0.0)
        base_size = non_negative(max_position_size_usd, 0.0) if max_position_size_usd is not None else _min_positive(max_safe, capital_max, 100.0)
        if engine in {"MOONSHOT_BASKET", "CONVEX"}:
            base_size = min(base_size, 50.0 if engine == "MOONSHOT_BASKET" else 100.0)
        max_loss = round(base_size * bounded(max_loss_fraction, 0.12), 6)
        entry_price = _entry_price(payload, engine)
        stop_loss = max(0.01, round(entry_price * (1 - max_loss_fraction), 4))
        target_exit = min(0.99, round(entry_price + max(0.05, (1 - entry_price) * 0.35), 4))
        return EngineContract(
            engine=engine,
            market_id=payload.market_id,
            side=payload.side,
            entry_conditions={
                "opportunity_score_min": payload.opportunity_score,
                "score_band": payload.opportunity_score_band,
                "engine_validation_required": True,
                "not_an_order": True,
            },
            exit_conditions={
                "target_exit": target_exit,
                "stop_loss": stop_loss,
                "max_hold_minutes": max_hold_minutes,
                "future_exit_cortex_required": True,
            },
            risk_limits={
                "max_loss_usd": max_loss,
                "max_position_size_usd": base_size,
                "requires_future_risk_gate": True,
            },
            position_sizing_rules={
                "sizing_mode": "contract_only",
                "capital_allocator_required": True,
                "no_capital_reserved": True,
            },
            allowed_market_families=[payload.market_family] if payload.market_family else [],
            forbidden_conditions=list(payload.opportunity_no_trade_reasons),
            cooldown_triggers=["hard_block_seen", "engine_rejection_cluster", "data_stale"],
            expected_hold_minutes=max_hold_minutes,
            entry_price_max=entry_price,
            target_exit=target_exit,
            partial_take_profit=round((entry_price + target_exit) / 2, 4),
            stop_loss=stop_loss,
            max_position_size_usd=base_size,
            max_loss_usd=max_loss,
            entry_mode=entry_mode,
            exit_mode=exit_mode,
            execution_mode="CONTRACT_ONLY",
            reason=reason,
            metadata=metadata or {},
        )


def _nested(root: dict[str, Any], *keys: str) -> Any:
    value: Any = root
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _min_positive(*values: float) -> float:
    positives = [value for value in values if value > 0]
    return min(positives) if positives else 0.0


def _entry_price(payload: StrategyRouteInput, engine: str) -> float:
    price = payload.opportunity_components.get("price_yes")
    if price is None:
        price = _nested(payload.technical_truth, "market_signal", "price_yes")
    price = bounded(price, 0.5)
    if engine == "MOONSHOT_BASKET":
        return min(price, 0.2)
    return max(0.01, min(0.98, round(price or 0.5, 4)))


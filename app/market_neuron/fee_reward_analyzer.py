from __future__ import annotations

from typing import Any

from app.market_neuron.contracts import FeeRewardSignal, LiquiditySignal, OrderbookSignal, bounded


class FeeRewardAnalyzer:
    def analyze(
        self,
        orderbook: OrderbookSignal,
        liquidity: LiquiditySignal,
        *,
        fee_snapshot: dict[str, Any] | None = None,
        edge_reference: float = 0.0,
    ) -> FeeRewardSignal:
        fee_snapshot = fee_snapshot or {}
        maker = _bps(fee_snapshot.get("maker_fee") or fee_snapshot.get("maker_cost_bps"))
        taker = _bps(fee_snapshot.get("taker_fee") or fee_snapshot.get("taker_cost_bps"))
        spread_cost = _float(fee_snapshot.get("spread_cost") or fee_snapshot.get("spread_cost_bps") or orderbook.spread_bps or 0)
        slippage_cost = _float(fee_snapshot.get("estimated_slippage_cost") or fee_snapshot.get("slippage_cost_bps") or liquidity.expected_slippage_bps)
        reward_pool = _float(fee_snapshot.get("reward_pool") or fee_snapshot.get("reward_pool_usd"))
        valid_microstructure = orderbook.has_bid_ask and not orderbook.block_reason and not liquidity.block_reason
        reward_score = bounded(reward_pool / 10000) if valid_microstructure else 0.0
        total_cost = maker + taker + spread_cost + slippage_cost
        net_edge = edge_reference - (total_cost / 10000) + reward_score * 0.01
        friction = bounded(total_cost / 1000)
        block = "high_friction_costs" if friction >= 0.85 else None
        return FeeRewardSignal(
            market_id=orderbook.market_id,
            token_id=orderbook.token_id,
            side=orderbook.side,
            maker_cost_bps=maker,
            taker_cost_bps=taker,
            spread_cost_bps=spread_cost,
            slippage_cost_bps=slippage_cost,
            reward_pool_usd=reward_pool,
            reward_score=reward_score,
            net_edge_after_costs=net_edge,
            fee_penalty_score=friction,
            friction_score=friction,
            raw_fee_reward=fee_snapshot,
            block_reason=block,
        )


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(default if value is None else value)
    except (TypeError, ValueError):
        return default


def _bps(value: Any) -> float:
    number = _float(value)
    return number * 10000 if 0 < number < 1 else number


from __future__ import annotations

from app.market_neuron.contracts import LiquiditySignal, OrderbookSignal, bounded


class LiquidityAnalyzer:
    def analyze(self, orderbook: OrderbookSignal, *, target_size_usd: float = 100.0) -> LiquiditySignal:
        if not orderbook.has_bid_ask:
            return LiquiditySignal(
                market_id=orderbook.market_id,
                token_id=orderbook.token_id,
                side=orderbook.side,
                block_reason="missing_exit_liquidity",
            )
        depth_quality = bounded(orderbook.depth_2c / max(target_size_usd * 5, 1))
        spread_penalty = bounded((orderbook.spread_bps or 0) / 1000)
        expected_fill = bounded(depth_quality * (1 - spread_penalty))
        expected_slippage_bps = min(5000.0, (orderbook.spread_bps or 0) * 0.5 + (1 - depth_quality) * 250)
        max_safe_size_usd = max(0.0, orderbook.depth_2c * 0.25)
        exit_quality = bounded((orderbook.orderbook_quality_score * 0.6) + (depth_quality * 0.4) - spread_penalty * 0.25)
        block = None
        if orderbook.depth_2c < 50:
            block = "low_exit_depth"
        elif exit_quality < 0.25:
            block = "poor_exit_liquidity"
        elif expected_slippage_bps >= 500:
            block = "high_expected_slippage"
        return LiquiditySignal(
            market_id=orderbook.market_id,
            token_id=orderbook.token_id,
            side=orderbook.side,
            expected_fill_score=expected_fill,
            expected_slippage_bps=expected_slippage_bps,
            expected_slippage_usd=target_size_usd * expected_slippage_bps / 10000,
            exit_quality_score=exit_quality,
            max_safe_size_usd=max_safe_size_usd,
            max_safe_size_contracts=max_safe_size_usd,
            liquidity_decay_score=bounded(1 - depth_quality),
            entry_liquidity_score=expected_fill,
            exit_liquidity_score=exit_quality,
            raw_liquidity={"target_size_usd": target_size_usd},
            block_reason=block,
        )


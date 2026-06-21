from __future__ import annotations

from app.market_neuron.contracts import FeeRewardSignal, LiquiditySignal, MarketTechnicalSignal, OrderbookSignal, TechnicalMarketTruth, TimeSignal, bounded


class TechnicalSignalBuilder:
    def build_truth(
        self,
        market_signal: MarketTechnicalSignal,
        orderbook_signal: OrderbookSignal,
        liquidity_signal: LiquiditySignal,
        time_signal: TimeSignal,
        fee_reward_signal: FeeRewardSignal,
    ) -> TechnicalMarketTruth:
        reasons = [
            market_signal.block_reason,
            orderbook_signal.block_reason,
            liquidity_signal.block_reason,
            time_signal.block_reason,
            fee_reward_signal.block_reason,
        ]
        if orderbook_signal.stale:
            reasons.append("stale_orderbook")
        if not orderbook_signal.has_bid_ask:
            reasons.append("missing_bid_ask")
        if orderbook_signal.depth_2c <= 0:
            reasons.append("missing_depth")
        if liquidity_signal.exit_quality_score <= 0:
            reasons.append("missing_exit_liquidity")
        blocked = any(reasons)
        data_completeness = min(
            market_signal.data_completeness_score,
            1.0 if orderbook_signal.has_bid_ask and orderbook_signal.depth_2c > 0 else 0.0,
            liquidity_signal.exit_quality_score,
        )
        technical_score = bounded(
            market_signal.momentum_score * 0.15
            + market_signal.trend_strength * 0.10
            + orderbook_signal.orderbook_quality_score * 0.25
            + liquidity_signal.exit_quality_score * 0.25
            + time_signal.time_efficiency_score * 0.10
            + (1 - fee_reward_signal.friction_score) * 0.15
        )
        if blocked:
            technical_score = min(technical_score, 0.25)
        return TechnicalMarketTruth(
            market_id=market_signal.market_id,
            market_signal=market_signal,
            orderbook_signal=orderbook_signal,
            liquidity_signal=liquidity_signal,
            time_signal=time_signal,
            fee_reward_signal=fee_reward_signal,
            technical_score=technical_score,
            technical_blocked=blocked,
            block_reasons=[reason for reason in reasons if reason],
            data_completeness_score=data_completeness,
        )


from __future__ import annotations

from typing import Any

from app.whale_neuron.contracts import WhaleActionType, WhaleEvent, WhaleEventClassification, bounded


class WhaleEventClassifier:
    def classify_event(self, event: WhaleEvent, market_context: dict[str, Any] | None = None) -> tuple[WhaleEventClassification, float]:
        market_context = market_context or {}
        price_move = abs(float(market_context.get("recent_price_move") or 0))
        if event.action_type == WhaleActionType.BUY and price_move >= 0.12:
            return WhaleEventClassification.LATE_CHASE, 0.76
        if event.action_type in {WhaleActionType.SELL, WhaleActionType.POSITION_CLOSE}:
            return (WhaleEventClassification.DISTRIBUTION if (event.size_usd or 0) >= 10000 else WhaleEventClassification.EXIT, 0.72)
        if event.action_type in {WhaleActionType.BUY, WhaleActionType.POSITION_OPEN}:
            if (event.size_usd or 0) >= 10000:
                return WhaleEventClassification.MARKET_MOVER, 0.78
            return WhaleEventClassification.ENTRY, 0.68
        if event.action_type in {WhaleActionType.ADD_LIQUIDITY, WhaleActionType.REMOVE_LIQUIDITY}:
            return WhaleEventClassification.HEDGE, 0.55
        return WhaleEventClassification.UNKNOWN, bounded(event.confidence * 0.5)

    def classify_entry_exit(self, event: WhaleEvent) -> WhaleEventClassification:
        return WhaleEventClassification.ENTRY if event.action_type == WhaleActionType.BUY else WhaleEventClassification.EXIT if event.action_type == WhaleActionType.SELL else WhaleEventClassification.UNKNOWN

    def classify_accumulation_distribution(self, events: list[WhaleEvent]) -> WhaleEventClassification:
        buys = sum(1 for event in events if event.action_type == WhaleActionType.BUY)
        sells = sum(1 for event in events if event.action_type == WhaleActionType.SELL)
        return WhaleEventClassification.ACCUMULATION if buys > sells else WhaleEventClassification.DISTRIBUTION if sells > buys else WhaleEventClassification.UNKNOWN

    def classify_reversal(self, event: WhaleEvent, market_context: dict[str, Any] | None = None) -> bool:
        return event.action_type in {WhaleActionType.SELL, WhaleActionType.POSITION_CLOSE} and abs(float((market_context or {}).get("recent_price_move") or 0)) >= 0.1

    def classify_momentum_chase(self, event: WhaleEvent, market_context: dict[str, Any] | None = None) -> bool:
        return event.action_type == WhaleActionType.BUY and abs(float((market_context or {}).get("recent_price_move") or 0)) >= 0.08

    def classify_late_chase(self, event: WhaleEvent, market_context: dict[str, Any] | None = None) -> bool:
        return self.classify_momentum_chase(event, market_context) and float((market_context or {}).get("minutes_after_move") or 999) > 10

    def classify_hedge(self, event: WhaleEvent) -> bool:
        return event.action_type in {WhaleActionType.ADD_LIQUIDITY, WhaleActionType.REMOVE_LIQUIDITY, WhaleActionType.TRANSFER}

    def classify_market_mover(self, event: WhaleEvent) -> bool:
        return (event.size_usd or 0) >= 10000


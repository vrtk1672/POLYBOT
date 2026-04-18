"""
Safe order intent construction for Stage 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP

from app.models.score import ScoredMarket
from app.stage2.claude_analyst import MarketRecommendation
from app.stage2.ws_listener import extract_token_ids
from app.stage4.buckets import recommended_bucket_notional


@dataclass(slots=True)
class LiveOrderIntent:
    market_id: str
    token_id: str
    question: str
    action: str
    side: str
    bucket: str
    price: float
    size: float
    notional_usd: float
    tick_size: str
    neg_risk: bool
    min_order_size: float


@dataclass(slots=True)
class LiveOrderValidationError(ValueError):
    code: str
    detail: str

    def __str__(self) -> str:
        return self.detail


def _quantize_down(value: float, quantum: str) -> float:
    dec_value = Decimal(str(value))
    dec_quantum = Decimal(quantum)
    return float(dec_value.quantize(dec_quantum, rounding=ROUND_DOWN))


def _quantize_up(value: float, quantum: str) -> float:
    dec_value = Decimal(str(value))
    dec_quantum = Decimal(quantum)
    return float(dec_value.quantize(dec_quantum, rounding=ROUND_UP))


def _market_price_for_action(item: ScoredMarket, action: str) -> float | None:
    if action == "BUY_YES":
        return item.market.yes_price
    if action == "BUY_NO":
        if item.market.no_price is not None:
            return item.market.no_price
        if item.market.yes_price is not None:
            return round(1.0 - item.market.yes_price, 4)
    return None


def build_live_order_intent(
    item: ScoredMarket,
    recommendation: MarketRecommendation,
    *,
    bucket: str,
    tick_size: str,
    neg_risk: bool,
    min_order_size: float,
    max_order_usd: float,
    balance_hint: float | None,
) -> LiveOrderIntent:
    token_ids = extract_token_ids(item.market)
    if recommendation.action == "BUY_YES":
        token_index = 0
    elif recommendation.action == "BUY_NO":
        token_index = 1
    else:
        raise ValueError(f"Unsupported live action: {recommendation.action}")

    if len(token_ids) <= token_index:
        raise ValueError("Required token_id is missing for the selected market outcome")

    price = _market_price_for_action(item, recommendation.action)
    if price is None or price <= 0 or price >= 1:
        raise LiveOrderValidationError(
            code="invalid_price",
            detail=f"Invalid market price for action {recommendation.action}: {price}",
        )

    capped_notional = recommended_bucket_notional(
        total_balance=balance_hint or max_order_usd,
        bucket=bucket,
        max_order_usd=max_order_usd,
    )
    size = _quantize_down(capped_notional / price, "0.001")
    minimum_size = _quantize_up(min_order_size, "0.001") if min_order_size > 0 else 0.0
    if minimum_size > 0 and size < minimum_size:
        minimum_notional = round(minimum_size * price, 4)
        if minimum_notional > max_order_usd + 1e-9:
            raise LiveOrderValidationError(
                code="minimum_size_exceeds_cap",
                detail=(
                    f"minimum size {minimum_size:.3f} requires ${minimum_notional:.4f}, "
                    f"which exceeds LIVE_MAX_ORDER_USD ${max_order_usd:.2f}"
                ),
            )
        size = minimum_size
    notional = round(size * price, 4)

    if notional > max_order_usd + 1e-9:
        size = _quantize_down(max_order_usd / price, "0.001")
        notional = round(size * price, 4)
        if minimum_size > 0 and size < minimum_size:
            raise LiveOrderValidationError(
                code="minimum_size_exceeds_cap",
                detail=(
                    f"minimum size {minimum_size:.3f} cannot fit under LIVE_MAX_ORDER_USD "
                    f"${max_order_usd:.2f}"
                ),
            )

    if size <= 0 or notional <= 0:
        raise LiveOrderValidationError(
            code="zero_size",
            detail="Computed size/notional is zero after validation",
        )

    return LiveOrderIntent(
        market_id=item.market.market_id,
        token_id=token_ids[token_index],
        question=item.market.question,
        action=recommendation.action,
        side="BUY",
        bucket=bucket,
        price=_quantize_down(price, tick_size),
        size=size,
        notional_usd=notional,
        tick_size=tick_size,
        neg_risk=neg_risk,
        min_order_size=min_order_size,
    )

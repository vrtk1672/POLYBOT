"""
Adaptive Stage 4 universe filtering.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.market import NormalizedMarket
from app.models.score import ScoredMarket
from app.stage2.claude_analyst import MarketRecommendation
from app.stage2.ws_listener import extract_token_ids
from app.stage4.config import Stage4Settings
from gamma_crawler import edge_cents, liquidity_bucket


@dataclass(slots=True)
class UniverseCandidate:
    item: ScoredMarket
    recommendation: MarketRecommendation
    bucket: str
    token_ids: list[str]
    feasible_price: float
    edge_cents: float | None
    exclusion_reasons: list[str] = field(default_factory=list)

    @property
    def market(self) -> NormalizedMarket:
        return self.item.market


def _price_for_action(item: ScoredMarket, action: str) -> float | None:
    if action == "BUY_YES":
        return item.market.yes_price
    if action == "BUY_NO":
        if item.market.no_price is not None:
            return item.market.no_price
        if item.market.yes_price is not None:
            return round(1.0 - item.market.yes_price, 4)
    return None


def build_allowed_universe(
    scored_markets: list[ScoredMarket],
    recommendations: list[MarketRecommendation],
    settings: Stage4Settings,
) -> tuple[list[UniverseCandidate], list[str]]:
    rec_by_rank = {rec.rank: rec for rec in recommendations}
    allowed: list[UniverseCandidate] = []
    skipped: list[str] = []

    for index, item in enumerate(scored_markets[: settings.live_allowed_universe_top_n], start=1):
        rec = rec_by_rank.get(index)
        if rec is None:
            skipped.append(f"{item.market.market_id}:missing_recommendation")
            continue
        if rec.action not in {"BUY_YES", "BUY_NO"}:
            skipped.append(f"{item.market.market_id}:action_{rec.action.lower()}")
            continue

        market = item.market
        token_ids = extract_token_ids(market)
        if rec.action == "BUY_YES" and len(token_ids) < 1:
            skipped.append(f"{market.market_id}:missing_yes_token")
            continue
        if rec.action == "BUY_NO" and len(token_ids) < 2:
            skipped.append(f"{market.market_id}:missing_no_token")
            continue

        if settings.live_optional_whitelist_mode == "subset" and settings.live_market_whitelist:
            if market.market_id not in settings.live_market_whitelist:
                skipped.append(f"{market.market_id}:outside_whitelist_subset")
                continue

        if settings.live_require_tradable_market and not market.accepting_orders:
            skipped.append(f"{market.market_id}:not_accepting_orders")
            continue

        feasible_price = _price_for_action(item, rec.action)
        if feasible_price is None or feasible_price <= 0 or feasible_price >= 1:
            skipped.append(f"{market.market_id}:invalid_price")
            continue

        if market.yes_price is None and market.no_price is None:
            skipped.append(f"{market.market_id}:missing_prices")
            continue

        allowed.append(
            UniverseCandidate(
                item=item,
                recommendation=rec,
                bucket=liquidity_bucket(market),
                token_ids=token_ids,
                feasible_price=feasible_price,
                edge_cents=edge_cents(market),
            )
        )

    return allowed, skipped

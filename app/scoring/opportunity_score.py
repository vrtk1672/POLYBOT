from datetime import UTC, datetime

from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.utils.safe_math import clamp, log_scale


class OpportunityScorer:
    """Deterministic Stage 1 scoring.

    This score ranks markets for monitoring, not for automatic execution.
    It prefers markets that are:
    - priced in a tradable band instead of extreme near-0 or near-1 values,
    - approaching resolution soon enough to matter,
    - liquid enough to be meaningful,
    - active recently through volume, updates, and engagement.
    """

    def score_market(self, market: NormalizedMarket) -> ScoredMarket:
        computed_at = datetime.now(UTC)

        price_component = round(self._price_component(market) * 35, 2)
        time_component = round(self._time_component(market, computed_at) * 25, 2)
        liquidity_component = round(self._liquidity_component(market) * 20, 2)
        activity_component = round(self._activity_component(market, computed_at) * 20, 2)

        score = round(
            price_component + time_component + liquidity_component + activity_component,
            2,
        )
        breakdown = ScoreBreakdown(
            price_attractiveness=price_component,
            time_to_close=time_component,
            liquidity_volume=liquidity_component,
            market_activity=activity_component,
        )

        reason = self._build_reason(market, breakdown)
        return ScoredMarket(
            market=market,
            score=clamp(score, 0.0, 100.0),
            breakdown=breakdown,
            reason=reason,
            computed_at=computed_at,
        )

    def _price_component(self, market: NormalizedMarket) -> float:
        prices = [value for value in [market.yes_price, market.no_price] if value is not None]
        if not prices:
            return 0.35

        cheap_side = min(prices)
        balance_reference = market.yes_price if market.yes_price is not None else prices[0]
        balance_strength = 1 - min(abs(balance_reference - 0.5) / 0.5, 1.0)
        cheap_side_strength = 1 - min(abs(cheap_side - 0.2) / 0.2, 1.0)
        return clamp((cheap_side_strength * 0.6) + (balance_strength * 0.4), 0.0, 1.0)

    def _time_component(self, market: NormalizedMarket, now: datetime) -> float:
        if market.end_time is None:
            return 0.4

        hours_to_close = (market.end_time - now).total_seconds() / 3600
        if hours_to_close <= 0:
            return 0.0
        if hours_to_close <= 6:
            return 0.25
        if hours_to_close <= 24:
            return 0.55
        if hours_to_close <= 24 * 7:
            return 1.0
        if hours_to_close <= 24 * 30:
            return 0.7
        if hours_to_close <= 24 * 90:
            return 0.45
        return 0.2

    def _liquidity_component(self, market: NormalizedMarket) -> float:
        liquidity_score = log_scale(market.liquidity, floor=1_000, ceiling=250_000)
        volume_score = log_scale(market.volume, floor=5_000, ceiling=2_000_000)
        return clamp((liquidity_score * 0.55) + (volume_score * 0.45), 0.0, 1.0)

    def _activity_component(self, market: NormalizedMarket, now: datetime) -> float:
        recent_volume = log_scale(market.volume_24h, floor=250, ceiling=100_000)
        discussion = log_scale(market.comment_count, floor=5, ceiling=250)
        recency = 0.25
        if market.updated_at is not None:
            age_hours = max((now - market.updated_at).total_seconds() / 3600, 0.0)
            if age_hours <= 1:
                recency = 1.0
            elif age_hours <= 6:
                recency = 0.8
            elif age_hours <= 24:
                recency = 0.6
            elif age_hours <= 72:
                recency = 0.4
            else:
                recency = 0.2

        return clamp((recent_volume * 0.5) + (discussion * 0.2) + (recency * 0.3), 0.0, 1.0)

    @staticmethod
    def _build_reason(market: NormalizedMarket, breakdown: ScoreBreakdown) -> str:
        parts: list[str] = []
        if breakdown.price_attractiveness >= 20:
            parts.append("tradable price band")
        if breakdown.time_to_close >= 18:
            parts.append("nearer resolution window")
        if breakdown.liquidity_volume >= 12:
            parts.append("solid liquidity/volume")
        if breakdown.market_activity >= 12:
            parts.append("active market flow")

        if not parts:
            parts.append("baseline visibility signal")

        if market.yes_price is not None:
            parts.append(f"yes={market.yes_price:.3f}")

        return ", ".join(parts[:3])

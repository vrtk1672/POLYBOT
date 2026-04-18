import asyncio
import json
from datetime import UTC, datetime
from time import perf_counter

from app.config import Settings
from app.logging import get_logger
from app.models.market import NormalizedMarket
from app.models.score import ScoredMarket
from app.scoring.opportunity_score import OpportunityScorer
from app.utils.terminal import render_top_markets_table
from app.utils.time_utils import parse_datetime

logger = get_logger(__name__)


class MarketService:
    def __init__(self, settings: Settings, gamma_client):
        self._settings = settings
        self._gamma_client = gamma_client
        self._scorer = OpportunityScorer()
        self._lock = asyncio.Lock()
        self._raw_events: list[dict] = []
        self._markets: list[NormalizedMarket] = []
        self._scored_markets: list[ScoredMarket] = []
        self._last_refresh_at: datetime | None = None
        self._last_refresh_duration_ms: float | None = None
        self._last_error: str | None = None

    async def refresh(self) -> None:
        started = perf_counter()
        try:
            events = await self._gamma_client.fetch_active_events()
        except Exception as exc:
            duration_ms = round((perf_counter() - started) * 1000, 2)
            async with self._lock:
                self._last_refresh_duration_ms = duration_ms
                self._last_error = str(exc)
            logger.exception("refresh_fetch_failed duration_ms=%s", duration_ms)
            return

        normalized_markets: list[NormalizedMarket] = []
        skipped_markets = 0

        for event in events:
            for market_payload in event.get("markets", []):
                try:
                    market = self._normalize_market(event, market_payload)
                except Exception as exc:
                    skipped_markets += 1
                    logger.warning(
                        "market_normalization_failed event_id=%s market_id=%s error=%s",
                        event.get("id"),
                        market_payload.get("id"),
                        exc,
                    )
                    continue

                if market is not None:
                    normalized_markets.append(market)

        scored_markets = self._rank_markets(normalized_markets)
        last_refresh_at = datetime.now(UTC)
        duration_ms = round((perf_counter() - started) * 1000, 2)

        async with self._lock:
            self._raw_events = events
            self._markets = normalized_markets
            self._scored_markets = scored_markets
            self._last_refresh_at = last_refresh_at
            self._last_refresh_duration_ms = duration_ms
            self._last_error = None

        logger.info(
            "refresh_complete events=%s markets=%s scored=%s skipped=%s duration_ms=%s",
            len(events),
            len(normalized_markets),
            len(scored_markets),
            skipped_markets,
            duration_ms,
        )
        render_top_markets_table(scored_markets[: self._settings.top_n])

    def _rank_markets(self, markets: list[NormalizedMarket]) -> list[ScoredMarket]:
        scored = [self._scorer.score_market(market) for market in markets]
        scored.sort(
            key=lambda item: (
                item.score,
                item.market.volume_24h or 0.0,
                item.market.liquidity or 0.0,
            ),
            reverse=True,
        )
        logger.info("score_pipeline_complete scored=%s top_n=%s", len(scored), self._settings.top_n)
        return scored

    def _normalize_market(self, event: dict, market_payload: dict) -> NormalizedMarket | None:
        is_active = bool(market_payload.get("active", False))
        is_closed = bool(market_payload.get("closed", False))
        accepting_orders = bool(market_payload.get("acceptingOrders", False))

        if not is_active or is_closed or not accepting_orders:
            return None

        outcome_prices = self._parse_json_list(market_payload.get("outcomePrices"))
        yes_price = self._coerce_price(market_payload.get("lastTradePrice"))
        if yes_price is None and outcome_prices:
            yes_price = self._coerce_price(outcome_prices[0])

        no_price = None
        if len(outcome_prices) > 1:
            no_price = self._coerce_price(outcome_prices[1])
        elif yes_price is not None:
            no_price = round(1 - yes_price, 4)

        best_bid = self._coerce_price(market_payload.get("bestBid"))
        best_ask = self._coerce_price(market_payload.get("bestAsk"))
        spread = self._coerce_non_negative(market_payload.get("spread"))
        if spread is None and best_bid is not None and best_ask is not None:
            spread = round(max(best_ask - best_bid, 0.0), 4)

        market = NormalizedMarket(
            market_id=str(market_payload["id"]),
            event_id=str(event["id"]),
            event_title=str(
                event.get("title") or market_payload.get("question") or "Untitled event"
            ),
            question=str(market_payload.get("question") or event.get("title") or "Untitled market"),
            slug=market_payload.get("slug"),
            end_time=parse_datetime(market_payload.get("endDate") or event.get("endDate")),
            yes_price=yes_price,
            no_price=no_price,
            last_trade_price=self._coerce_price(market_payload.get("lastTradePrice")),
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            liquidity=self._coerce_non_negative(
                market_payload.get("liquidityNum")
                or market_payload.get("liquidityClob")
                or market_payload.get("liquidity")
                or event.get("liquidity")
                or event.get("liquidityClob")
            ),
            volume=self._coerce_non_negative(
                market_payload.get("volumeNum") or market_payload.get("volume")
            ),
            volume_24h=self._coerce_non_negative(
                market_payload.get("volume24hr")
                or market_payload.get("volume24hrClob")
                or event.get("volume24hr")
            ),
            open_interest=self._coerce_non_negative(
                market_payload.get("openInterest") or event.get("openInterest")
            ),
            comment_count=self._coerce_int(event.get("commentCount")),
            competitive=self._coerce_non_negative(
                market_payload.get("competitive") or event.get("competitive")
            ),
            accepting_orders=accepting_orders,
            updated_at=parse_datetime(market_payload.get("updatedAt") or event.get("updatedAt")),
            raw_market=market_payload,
        )
        return market

    async def snapshot(self) -> dict:
        async with self._lock:
            top_markets = [
                item.model_dump(mode="json", exclude={"market": {"raw_market": True}})
                for item in self._scored_markets[: self._settings.top_n]
            ]
            return {
                "raw_event_count": len(self._raw_events),
                "market_count": len(self._markets),
                "top_markets": top_markets,
                "last_refresh_at": self._last_refresh_at,
                "last_refresh_duration_ms": self._last_refresh_duration_ms,
                "last_error": self._last_error,
            }

    async def top_markets(self, limit: int | None = None) -> list[ScoredMarket]:
        async with self._lock:
            return list(self._scored_markets[: limit or self._settings.top_n])

    async def raw_counts(self) -> dict:
        async with self._lock:
            return {
                "raw_event_count": len(self._raw_events),
                "normalized_market_count": len(self._markets),
                "scored_market_count": len(self._scored_markets),
            }

    async def last_refresh(self) -> dict:
        async with self._lock:
            return {
                "last_refresh_at": self._last_refresh_at,
                "last_refresh_duration_ms": self._last_refresh_duration_ms,
                "last_error": self._last_error,
            }

    async def health(self) -> dict:
        async with self._lock:
            status = "ok" if self._last_refresh_at and not self._last_error else "degraded"
            return {
                "status": status,
                "last_refresh_at": self._last_refresh_at,
                "market_count": len(self._markets),
                "last_error": self._last_error,
            }

    async def aclose(self) -> None:
        await self._gamma_client.aclose()

    @staticmethod
    def _parse_json_list(value) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                loaded = json.loads(value)
            except json.JSONDecodeError:
                return []
            return loaded if isinstance(loaded, list) else []
        return []

    @staticmethod
    def _coerce_price(value) -> float | None:
        coerced = MarketService._coerce_non_negative(value)
        if coerced is None:
            return None
        return max(0.0, min(coerced, 1.0))

    @staticmethod
    def _coerce_non_negative(value) -> float | None:
        if value in (None, ""):
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return max(numeric, 0.0)

    @staticmethod
    def _coerce_int(value) -> int | None:
        if value in (None, ""):
            return None
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return None

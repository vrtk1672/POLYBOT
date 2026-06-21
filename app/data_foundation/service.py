from __future__ import annotations

from app.data_foundation.fees_rewards_collector import FeesRewardsCollector
from app.data_foundation.liquidity_profiler import LiquidityProfiler
from app.data_foundation.market_registry import MarketRegistry
from app.data_foundation.market_rules_store import MarketRulesStore
from app.data_foundation.market_snapshotter_v2 import MarketSnapshotterV2
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.logging import get_logger
from app.models.market import NormalizedMarket

logger = get_logger(__name__)


class DataFoundationService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._registry = MarketRegistry(connection_factory=self._factory, event_bus=self._event_bus)
        self._rules = MarketRulesStore(connection_factory=self._factory, event_bus=self._event_bus)
        self._snapshotter = MarketSnapshotterV2(connection_factory=self._factory, event_bus=self._event_bus)
        self._liquidity = LiquidityProfiler(connection_factory=self._factory, event_bus=self._event_bus)
        self._fees = FeesRewardsCollector(connection_factory=self._factory, event_bus=self._event_bus)

    def process_markets(
        self,
        markets: list[NormalizedMarket],
        *,
        cycle_id: str | None = None,
        correlation_id: str | None = None,
        limit: int | None = None,
    ) -> dict[str, int]:
        if not self._factory.enabled:
            return {"markets_seen": 0, "markets_created": 0, "snapshots_created": 0, "rules_updated": 0}
        stats = {"markets_seen": 0, "markets_created": 0, "snapshots_created": 0, "rules_updated": 0}
        for market in markets[: limit or len(markets)]:
            try:
                raw = dict(market.raw_market or {})
                raw.setdefault("id", market.market_id)
                raw.setdefault("question", market.question)
                raw.setdefault("slug", market.slug)
                raw.setdefault("endDate", market.end_time.isoformat() if market.end_time else None)
                raw.setdefault("acceptingOrders", market.accepting_orders)
                record = self._registry.normalize_market(raw)
                _row, created = self._registry.upsert_market(record)
                rules = self._rules.extract_rules(raw, market_id=market.market_id)
                _rules_row, changed = self._rules.upsert_rules(rules)
                liquidity_snapshot = self._liquidity.build_liquidity_snapshot(market.market_id, None)
                self._liquidity.persist_liquidity_snapshot(liquidity_snapshot)
                fee_snapshot = self._fees.extract_fees_rewards(raw, market_id=market.market_id, spread=market.spread)
                self._fees.persist_fee_snapshot(fee_snapshot)
                snapshot = self._snapshotter.build_snapshot_from_market(
                    market,
                    cycle_id=cycle_id,
                    correlation_id=correlation_id,
                    rules=rules,
                    liquidity=liquidity_snapshot,
                )
                self._snapshotter.persist_snapshot(snapshot)
                stats["markets_seen"] += 1
                stats["markets_created"] += int(created)
                stats["rules_updated"] += int(changed)
                stats["snapshots_created"] += 1
            except Exception:
                logger.exception("data_foundation_market_process_failed market_id=%s", getattr(market, "market_id", None))
        return stats

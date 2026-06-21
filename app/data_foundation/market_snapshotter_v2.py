from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.data_foundation.contracts import MarketSnapshotV2
from app.data_foundation.data_completeness import DataCompletenessComputer
from app.data_foundation.data_staleness import DataStalenessPolicy
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.models.market import NormalizedMarket
from app.repositories.market_snapshot_v2_repository import MarketSnapshotV2Repository


class MarketSnapshotterV2:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = MarketSnapshotV2Repository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._completeness = DataCompletenessComputer()
        self._staleness = DataStalenessPolicy()

    def build_snapshot_from_market(
        self,
        market: NormalizedMarket | dict[str, Any],
        *,
        cycle_id: str | None = None,
        correlation_id: str | None = None,
        orderbook: Any | None = None,
        rules: Any | None = None,
        liquidity: Any | None = None,
    ) -> MarketSnapshotV2:
        market_id = _get(market, "market_id") or _get(market, "id")
        raw = _get(market, "raw_market") or _get(market, "raw_market_json") or market
        time_to_close = _get(market, "time_to_close_seconds")
        if time_to_close is None:
            close_time = _get(market, "end_time") or _get(market, "close_time")
            if close_time is not None:
                from datetime import UTC, datetime

                if close_time.tzinfo is None:
                    close_time = close_time.replace(tzinfo=UTC)
                time_to_close = round(max((close_time - datetime.now(UTC)).total_seconds(), 0))
        completeness = self._completeness.compute_data_completeness(
            market=market,
            rules=rules,
            latest_snapshot={
                "current_price_yes": _get(market, "yes_price") or _get(market, "current_price_yes"),
                "best_bid": _get(market, "best_bid"),
                "best_ask": _get(market, "best_ask"),
                "time_to_close_seconds": time_to_close,
            },
            orderbook=orderbook,
            liquidity=liquidity,
            require_orderbook=False,
            require_rules=False,
        )
        stale = self._staleness.is_market_snapshot_stale(_get(market, "updated_at")) if _get(market, "updated_at") else False
        return MarketSnapshotV2(
            snapshot_id=f"msv2_{uuid4().hex}",
            market_id=str(market_id),
            cycle_id=cycle_id,
            correlation_id=correlation_id,
            current_price_yes=_get(market, "yes_price") or _get(market, "current_price_yes"),
            current_price_no=_get(market, "no_price") or _get(market, "current_price_no"),
            best_bid=_get(market, "best_bid"),
            best_ask=_get(market, "best_ask"),
            spread=_get(market, "spread"),
            volume_1h=_get(market, "volume_1h"),
            volume_24h=_get(market, "volume_24h"),
            liquidity=_get(market, "liquidity"),
            time_to_close_seconds=time_to_close,
            accepting_orders=_get(market, "accepting_orders"),
            closed=_get(market, "closed") or False,
            data_completeness_score=completeness.score,
            stale=stale,
            raw_snapshot_json=raw,
            metadata_json={"candidate_allowed": completeness.candidate_allowed, "missing_fields": completeness.missing_fields},
        )

    def persist_snapshot(self, snapshot: MarketSnapshotV2) -> None:
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.append_snapshot(conn, snapshot)
        self._publish(snapshot)

    def get_latest_snapshot(self, market_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._repository.get_latest_snapshot(conn, market_id)

    def list_recent_snapshots(self, market_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return self._repository.list_recent_snapshots(conn, market_id, limit)

    def _publish(self, snapshot: MarketSnapshotV2) -> None:
        try:
            self._event_bus.publish(
                EventType.MARKET_SNAPSHOT_CREATED.value,
                {"market_id": snapshot.market_id, "snapshot_id": snapshot.snapshot_id, "data_completeness_score": snapshot.data_completeness_score, "stale": snapshot.stale},
                source_service="data_foundation",
                aggregate_type="market",
                aggregate_id=snapshot.market_id,
                correlation_id=snapshot.correlation_id,
                cycle_id=snapshot.cycle_id,
                metadata={"non_trading_event": True},
            )
            self._event_bus.publish(
                EventType.DATA_COMPLETENESS_UPDATED.value,
                {"market_id": snapshot.market_id, "data_completeness_score": snapshot.data_completeness_score, "candidate_allowed": snapshot.metadata_json.get("candidate_allowed")},
                source_service="data_foundation",
                aggregate_type="market",
                aggregate_id=snapshot.market_id,
                correlation_id=snapshot.correlation_id,
                cycle_id=snapshot.cycle_id,
                metadata={"non_trading_event": True},
            )
        except Exception:
            return


def _get(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)

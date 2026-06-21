from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.data_foundation.contracts import LiquiditySnapshot, OrderbookSnapshot
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.liquidity_snapshot_repository import LiquiditySnapshotRepository


class LiquidityProfiler:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = LiquiditySnapshotRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def compute_liquidity_score(self, orderbook_snapshot: OrderbookSnapshot | dict[str, Any] | None, market_snapshot: Any | None = None) -> float:
        if orderbook_snapshot is None:
            return 0.0
        spread = _get(orderbook_snapshot, "spread")
        depth_2c = float(_get(orderbook_snapshot, "depth_2c") or 0)
        spread_score = 1.0 if spread is None else max(0.0, min(1.0, 1.0 - (float(spread) / 0.1)))
        depth_score = max(0.0, min(1.0, depth_2c / 1000.0))
        return round((spread_score * 45) + (depth_score * 55), 2)

    def compute_exit_quality(self, orderbook_snapshot: OrderbookSnapshot | dict[str, Any] | None) -> float:
        if orderbook_snapshot is None:
            return 0.0
        imbalance = _get(orderbook_snapshot, "imbalance")
        balance_score = 1.0 if imbalance is None else max(0.0, 1.0 - abs(float(imbalance)))
        depth_1c = min(float(_get(orderbook_snapshot, "depth_1c") or 0) / 500.0, 1.0)
        return round((balance_score * 50) + (depth_1c * 50), 2)

    def estimate_slippage(self, size: float, orderbook_snapshot: OrderbookSnapshot | dict[str, Any] | None) -> float | None:
        if orderbook_snapshot is None:
            return None
        depth = float(_get(orderbook_snapshot, "depth_2c") or 0)
        spread = float(_get(orderbook_snapshot, "spread") or 0)
        if depth <= 0:
            return None
        pressure = min(size / depth, 5.0)
        return round(spread + (pressure * 0.01), 6)

    def estimate_max_safe_size(self, orderbook_snapshot: OrderbookSnapshot | dict[str, Any] | None) -> float:
        if orderbook_snapshot is None:
            return 0.0
        return round(float(_get(orderbook_snapshot, "depth_2c") or 0) * 0.25, 6)

    def estimate_fill_probability(self, orderbook_snapshot: OrderbookSnapshot | dict[str, Any] | None) -> float:
        if orderbook_snapshot is None:
            return 0.0
        spread = float(_get(orderbook_snapshot, "spread") or 1)
        depth = float(_get(orderbook_snapshot, "depth_1c") or 0)
        return round(max(0.0, min(1.0, (1 - spread / 0.1) * min(depth / 500, 1))), 4)

    def build_liquidity_snapshot(self, market_id: str, orderbook_snapshot: OrderbookSnapshot | dict[str, Any] | None) -> LiquiditySnapshot:
        score = self.compute_liquidity_score(orderbook_snapshot)
        return LiquiditySnapshot(
            liquidity_snapshot_id=f"liq_{uuid4().hex}",
            market_id=market_id,
            orderbook_snapshot_id=_get(orderbook_snapshot, "orderbook_snapshot_id"),
            liquidity_score=score,
            exit_quality=self.compute_exit_quality(orderbook_snapshot),
            expected_slippage_small=self.estimate_slippage(10, orderbook_snapshot),
            expected_slippage_medium=self.estimate_slippage(100, orderbook_snapshot),
            expected_slippage_large=self.estimate_slippage(1000, orderbook_snapshot),
            max_safe_size=self.estimate_max_safe_size(orderbook_snapshot),
            fill_probability=self.estimate_fill_probability(orderbook_snapshot),
            liquidity_usd=float(_get(orderbook_snapshot, "depth_5c") or 0),
            depth_1c=_get(orderbook_snapshot, "depth_1c"),
            depth_2c=_get(orderbook_snapshot, "depth_2c"),
            depth_5c=_get(orderbook_snapshot, "depth_5c"),
            metadata_json={"missing_orderbook": orderbook_snapshot is None},
        )

    def persist_liquidity_snapshot(self, snapshot: LiquiditySnapshot) -> None:
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.append_snapshot(conn, snapshot)
        self._publish(snapshot)

    def _publish(self, snapshot: LiquiditySnapshot) -> None:
        try:
            self._event_bus.publish(
                EventType.LIQUIDITY_SNAPSHOT_CREATED.value,
                {"market_id": snapshot.market_id, "liquidity_snapshot_id": snapshot.liquidity_snapshot_id, "liquidity_score": snapshot.liquidity_score},
                source_service="data_foundation",
                aggregate_type="market",
                aggregate_id=snapshot.market_id,
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

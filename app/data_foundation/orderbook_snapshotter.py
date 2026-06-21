from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.data_foundation.contracts import OrderbookSnapshot
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository


class OrderbookSnapshotter:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = OrderbookSnapshotRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def normalize_orderbook(
        self,
        raw_orderbook: dict[str, Any],
        *,
        market_id: str,
        token_id: str | None = None,
        side: str | None = None,
        source: str = "unknown",
        correlation_id: str | None = None,
        raw_payload_ref: str | None = None,
        collected_at: datetime | None = None,
        freshness_window_seconds: int = 120,
        metadata_json: dict[str, Any] | None = None,
    ) -> OrderbookSnapshot:
        collected = collected_at or datetime.now(UTC)
        bids = _levels(raw_orderbook.get("bids") or raw_orderbook.get("buy") or [])
        asks = _levels(raw_orderbook.get("asks") or raw_orderbook.get("sell") or [])
        best_bid = max((level["price"] for level in bids), default=None)
        best_ask = min((level["price"] for level in asks), default=None)
        spread = round(best_ask - best_bid, 6) if best_bid is not None and best_ask is not None else None
        mid = round((best_bid + best_ask) / 2, 6) if best_bid is not None and best_ask is not None else None
        depth_1c = _depth_near(bids, asks, mid, 0.01)
        depth_2c = _depth_near(bids, asks, mid, 0.02)
        depth_5c = _depth_near(bids, asks, mid, 0.05)
        depth_bid_1c = _bid_depth_near(bids, best_bid, 0.01)
        depth_ask_1c = _ask_depth_near(asks, best_ask, 0.01)
        depth_bid_2c = _bid_depth_near(bids, best_bid, 0.02)
        depth_ask_2c = _ask_depth_near(asks, best_ask, 0.02)
        depth_bid_5c = _bid_depth_near(bids, best_bid, 0.05)
        depth_ask_5c = _ask_depth_near(asks, best_ask, 0.05)
        bid_depth = sum(level["size"] for level in bids)
        ask_depth = sum(level["size"] for level in asks)
        imbalance = round((bid_depth - ask_depth) / (bid_depth + ask_depth), 6) if bid_depth + ask_depth > 0 else None
        status, stale_reason = _snapshot_status(
            bids=bids,
            asks=asks,
            best_bid=best_bid,
            best_ask=best_ask,
            raw_orderbook=raw_orderbook,
            collected_at=collected,
            freshness_window_seconds=freshness_window_seconds,
        )
        liquidity_score = _liquidity_score(
            spread=spread,
            depth_bid_2c=depth_bid_2c,
            depth_ask_2c=depth_ask_2c,
            total_bid_depth=bid_depth,
            total_ask_depth=ask_depth,
        )
        return OrderbookSnapshot(
            orderbook_snapshot_id=f"ob_{uuid4().hex}",
            market_id=market_id,
            token_id=token_id or raw_orderbook.get("token_id") or raw_orderbook.get("asset_id"),
            side=side,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            mid_price=mid,
            depth_1c=depth_1c,
            depth_2c=depth_2c,
            depth_5c=depth_5c,
            depth_bid_1c=depth_bid_1c,
            depth_ask_1c=depth_ask_1c,
            depth_bid_2c=depth_bid_2c,
            depth_ask_2c=depth_ask_2c,
            depth_bid_5c=depth_bid_5c,
            depth_ask_5c=depth_ask_5c,
            total_bid_depth=round(bid_depth, 6),
            total_ask_depth=round(ask_depth, 6),
            liquidity_score=liquidity_score,
            source=source,
            snapshot_status=status,
            is_stale=status in {"STALE", "EMPTY", "PARTIAL", "ERROR"},
            stale_reason=stale_reason,
            raw_payload_ref=raw_payload_ref,
            correlation_id=correlation_id,
            collected_at=collected,
            bid_depth_json=bids,
            ask_depth_json=asks,
            imbalance=imbalance,
            raw_orderbook_json=raw_orderbook,
            metadata_json={
                "freshness_window_seconds": freshness_window_seconds,
                "bids_count": len(bids),
                "asks_count": len(asks),
                **(metadata_json or {}),
            },
        )

    def compute_best_bid_ask(self, raw_orderbook: dict[str, Any]) -> tuple[float | None, float | None]:
        snapshot = self.normalize_orderbook(raw_orderbook, market_id="preview")
        return snapshot.best_bid, snapshot.best_ask

    def compute_spread(self, raw_orderbook: dict[str, Any]) -> float | None:
        return self.normalize_orderbook(raw_orderbook, market_id="preview").spread

    def compute_depth_within_price_band(self, raw_orderbook: dict[str, Any], band: float = 0.02) -> float:
        snapshot = self.normalize_orderbook(raw_orderbook, market_id="preview")
        if band <= 0.01:
            return float(snapshot.depth_1c or 0)
        if band <= 0.02:
            return float(snapshot.depth_2c or 0)
        return float(snapshot.depth_5c or 0)

    def compute_imbalance(self, raw_orderbook: dict[str, Any]) -> float | None:
        return self.normalize_orderbook(raw_orderbook, market_id="preview").imbalance

    def persist_orderbook_snapshot(self, snapshot: OrderbookSnapshot) -> None:
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.append_snapshot(conn, snapshot)
        self._publish(snapshot)

    def _publish(self, snapshot: OrderbookSnapshot) -> None:
        try:
            self._event_bus.publish(
                EventType.ORDERBOOK_SNAPSHOT_CREATED.value,
                {"market_id": snapshot.market_id, "orderbook_snapshot_id": snapshot.orderbook_snapshot_id, "spread": snapshot.spread},
                source_service="data_foundation",
                aggregate_type="market",
                aggregate_id=snapshot.market_id,
                metadata={"non_trading_event": True},
            )
        except Exception:
            return


def _levels(value: Any) -> list[dict[str, float]]:
    output: list[dict[str, float]] = []
    if not isinstance(value, list):
        return output
    for item in value:
        try:
            price = float(item.get("price") if isinstance(item, dict) else item[0])
            size = float(item.get("size") if isinstance(item, dict) else item[1])
        except (TypeError, ValueError, IndexError, AttributeError):
            continue
        if price > 0 and size > 0:
            output.append({"price": price, "size": size})
    return output


def _depth_near(bids: list[dict[str, float]], asks: list[dict[str, float]], mid: float | None, band: float) -> float:
    if mid is None:
        return 0.0
    epsilon = 1e-9
    return round(
        sum(level["size"] for level in bids if mid - level["price"] <= band + epsilon)
        + sum(level["size"] for level in asks if level["price"] - mid <= band + epsilon),
        6,
    )


def _bid_depth_near(bids: list[dict[str, float]], best_bid: float | None, band: float) -> float:
    if best_bid is None:
        return 0.0
    epsilon = 1e-9
    return round(sum(level["size"] for level in bids if best_bid - level["price"] <= band + epsilon), 6)


def _ask_depth_near(asks: list[dict[str, float]], best_ask: float | None, band: float) -> float:
    if best_ask is None:
        return 0.0
    epsilon = 1e-9
    return round(sum(level["size"] for level in asks if level["price"] - best_ask <= band + epsilon), 6)


def _snapshot_status(
    *,
    bids: list[dict[str, float]],
    asks: list[dict[str, float]],
    best_bid: float | None,
    best_ask: float | None,
    raw_orderbook: dict[str, Any],
    collected_at: datetime,
    freshness_window_seconds: int,
) -> tuple[str, str | None]:
    if not raw_orderbook:
        return "EMPTY", "raw_orderbook_missing"
    if not bids and not asks:
        return "EMPTY", "empty_orderbook"
    if best_bid is None or best_ask is None:
        return "PARTIAL", "missing_bid_or_ask"
    now = datetime.now(UTC)
    collected = collected_at if collected_at.tzinfo else collected_at.replace(tzinfo=UTC)
    if now - collected > timedelta(seconds=freshness_window_seconds):
        return "STALE", "collected_at_outside_freshness_window"
    return "OK", None


def _liquidity_score(
    *,
    spread: float | None,
    depth_bid_2c: float,
    depth_ask_2c: float,
    total_bid_depth: float,
    total_ask_depth: float,
) -> float:
    if spread is None:
        return 0.0
    spread_score = max(0.0, min(1.0, 1 - (spread / 0.10)))
    near_depth = min(depth_bid_2c, depth_ask_2c)
    total_depth = min(total_bid_depth, total_ask_depth)
    near_score = max(0.0, min(1.0, near_depth / 500.0))
    total_score = max(0.0, min(1.0, total_depth / 2000.0))
    return round((spread_score * 0.45) + (near_score * 0.35) + (total_score * 0.20), 6)

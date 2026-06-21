from __future__ import annotations

from typing import Any

from app.market_neuron.contracts import OrderbookSignal, TechnicalSide, bounded


class OrderbookAnalyzer:
    def analyze(
        self,
        market_id: str,
        *,
        token_id: str | None = None,
        side: str | None = None,
        snapshot: dict[str, Any] | None = None,
        raw_orderbook: dict[str, Any] | None = None,
    ) -> OrderbookSignal:
        raw = raw_orderbook or dict(snapshot or {})
        bids, asks = _levels(raw)
        best_bid = _float(snapshot.get("best_bid")) if snapshot and snapshot.get("best_bid") is not None else (max((p for p, _ in bids), default=None))
        best_ask = _float(snapshot.get("best_ask")) if snapshot and snapshot.get("best_ask") is not None else (min((p for p, _ in asks), default=None))
        has_bid_ask = best_bid is not None and best_ask is not None and best_ask > 0
        if not has_bid_ask:
            return OrderbookSignal(
                market_id=market_id,
                token_id=token_id or (snapshot or {}).get("token_id"),
                side=_side(side or (snapshot or {}).get("side")),
                has_bid_ask=False,
                stale=True,
                raw_orderbook=raw,
                block_reason="missing_bid_ask",
            )
        spread = max(0.0, best_ask - best_bid)
        mid = (best_bid + best_ask) / 2
        spread_bps = (spread / mid * 10000) if mid > 0 else 10000
        depth_1c = _depth_near(bids, asks, best_bid, best_ask, 0.01, snapshot, "depth_1c")
        depth_2c = _depth_near(bids, asks, best_bid, best_ask, 0.02, snapshot, "depth_2c")
        depth_5c = _depth_near(bids, asks, best_bid, best_ask, 0.05, snapshot, "depth_5c")
        bid_total = sum(size for _, size in bids) or _float((snapshot or {}).get("bid_depth_total"))
        ask_total = sum(size for _, size in asks) or _float((snapshot or {}).get("ask_depth_total"))
        imbalance = 0.5 if bid_total + ask_total == 0 else bid_total / (bid_total + ask_total)
        spread_quality = bounded(1 - spread_bps / 1000)
        depth_quality = bounded(depth_2c / 1000)
        queue_quality = bounded((depth_1c / 250) * spread_quality)
        quality = bounded((spread_quality * 0.45) + (depth_quality * 0.35) + (queue_quality * 0.2))
        block = None
        if spread_bps >= 750 or spread >= 0.08:
            block = "wide_spread"
        elif depth_2c < 50:
            block = "low_depth"
        return OrderbookSignal(
            market_id=market_id,
            token_id=token_id or (snapshot or {}).get("token_id"),
            side=_side(side or (snapshot or {}).get("side")),
            best_bid=best_bid,
            best_ask=best_ask,
            mid_price=mid,
            spread=spread,
            spread_bps=spread_bps,
            depth_1c=depth_1c,
            depth_2c=depth_2c,
            depth_5c=depth_5c,
            bid_depth_total=bid_total,
            ask_depth_total=ask_total,
            imbalance_score=imbalance,
            queue_quality_score=queue_quality,
            cancel_burst_score=0.0,
            microstructure_score=quality,
            orderbook_quality_score=quality,
            has_bid_ask=True,
            stale=bool((snapshot or {}).get("stale", False)),
            raw_orderbook=raw,
            block_reason=block,
        )


def _side(value: Any) -> TechnicalSide:
    try:
        return TechnicalSide(str(value or "UNKNOWN").upper())
    except ValueError:
        return TechnicalSide.UNKNOWN


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(default if value is None else value)
    except (TypeError, ValueError):
        return default


def _levels(raw: dict[str, Any]) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    return _parse_levels(raw.get("bids") or raw.get("bid_depth_json") or raw.get("bid_depth") or []), _parse_levels(raw.get("asks") or raw.get("ask_depth_json") or raw.get("ask_depth") or [])


def _parse_levels(value: Any) -> list[tuple[float, float]]:
    levels: list[tuple[float, float]] = []
    if isinstance(value, dict):
        value = [{"price": price, "size": size} for price, size in value.items()]
    for item in value or []:
        if isinstance(item, dict):
            price = _float(item.get("price") or item.get("p"))
            size = _float(item.get("size") or item.get("quantity") or item.get("q"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            price = _float(item[0])
            size = _float(item[1])
        else:
            continue
        if price > 0 and size > 0:
            levels.append((price, size))
    return levels


def _depth_near(bids: list[tuple[float, float]], asks: list[tuple[float, float]], best_bid: float, best_ask: float, width: float, snapshot: dict[str, Any] | None, key: str) -> float:
    if snapshot and snapshot.get(key) is not None:
        return _float(snapshot.get(key))
    bid_depth = sum(size for price, size in bids if best_bid - width <= price <= best_bid)
    ask_depth = sum(size for price, size in asks if best_ask <= price <= best_ask + width)
    return bid_depth + ask_depth


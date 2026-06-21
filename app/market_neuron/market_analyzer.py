from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import pstdev
from typing import Any

from app.market_neuron.contracts import MarketRegime, MarketTechnicalSignal, TrendDirection, bounded


class MarketAnalyzer:
    def analyze(self, market_id: str, snapshots: list[dict[str, Any]] | None) -> MarketTechnicalSignal:
        rows = sorted(snapshots or [], key=lambda row: _ts(row) or datetime.min.replace(tzinfo=UTC))
        if not rows:
            return MarketTechnicalSignal(
                market_id=market_id,
                market_regime=MarketRegime.UNKNOWN,
                stale=True,
                block_reason="missing_market_snapshot",
            )
        latest = rows[-1]
        latest_ts = _ts(latest)
        price = _price(latest)
        changes = {
            "price_change_1m": _change_from_window(rows, latest_ts, timedelta(minutes=1), price),
            "price_change_5m": _change_from_window(rows, latest_ts, timedelta(minutes=5), price),
            "price_change_15m": _change_from_window(rows, latest_ts, timedelta(minutes=15), price),
            "price_change_1h": _change_from_window(rows, latest_ts, timedelta(hours=1), price),
        }
        prices = [_price(row) for row in rows if _price(row) is not None]
        diffs = [prices[idx] - prices[idx - 1] for idx in range(1, len(prices))] if len(prices) > 1 else []
        volatility = bounded((pstdev(diffs) if len(diffs) > 1 else abs(changes["price_change_5m"])) * 10)
        momentum = bounded(abs(changes["price_change_5m"]) * 8 + abs(changes["price_change_15m"]) * 3)
        trend = _trend_direction(changes["price_change_15m"], changes["price_change_5m"])
        trend_strength = bounded(abs(changes["price_change_15m"]) * 8 + abs(changes["price_change_1h"]) * 2)
        stale = bool(latest.get("stale")) or (latest_ts is not None and latest_ts < datetime.now(UTC) - timedelta(minutes=20))
        time_to_close = _float(latest.get("time_to_close_seconds"))
        liquidity = _float(latest.get("liquidity"))
        completeness = bounded(latest.get("data_completeness_score"), 0.0)
        regime = _regime(stale=stale, volatility=volatility, trend_strength=trend_strength, liquidity=liquidity, time_to_close=time_to_close)
        block = "stale_market_snapshot" if stale else None
        return MarketTechnicalSignal(
            market_id=market_id,
            price_yes=price,
            price_no=_float(latest.get("current_price_no") or latest.get("price_no")),
            volume_1h=_float(latest.get("volume_1h")),
            volume_24h=_float(latest.get("volume_24h")),
            volatility_score=volatility,
            momentum_score=momentum,
            trend_direction=trend,
            trend_strength=trend_strength,
            candle_summary={"samples": len(prices), "latest_price": price, "min_price": min(prices) if prices else None, "max_price": max(prices) if prices else None},
            market_regime=regime,
            data_completeness_score=completeness,
            stale=stale,
            raw_snapshot=dict(latest),
            block_reason=block,
            **changes,
        )


def _price(row: dict[str, Any]) -> float | None:
    return _float(row.get("current_price_yes") or row.get("price_yes") or row.get("last_price"))


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ts(row: dict[str, Any]) -> datetime | None:
    value = row.get("snapshot_at") or row.get("ts") or row.get("created_at")
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _change_from_window(rows: list[dict[str, Any]], latest_ts: datetime | None, window: timedelta, latest_price: float | None) -> float:
    if latest_price is None:
        return 0.0
    if latest_ts is None:
        baseline = _price(rows[0])
        return 0.0 if baseline is None else latest_price - baseline
    candidates = [row for row in rows if (_ts(row) or latest_ts) <= latest_ts - window]
    baseline = _price(candidates[-1]) if candidates else _price(rows[0])
    return 0.0 if baseline is None else latest_price - baseline


def _trend_direction(change_15m: float, change_5m: float) -> TrendDirection:
    combined = change_15m + change_5m
    if combined > 0.01:
        return TrendDirection.UP
    if combined < -0.01:
        return TrendDirection.DOWN
    return TrendDirection.FLAT


def _regime(*, stale: bool, volatility: float, trend_strength: float, liquidity: float, time_to_close: float) -> MarketRegime:
    if stale:
        return MarketRegime.STALE
    if time_to_close and time_to_close < 900:
        return MarketRegime.CLOSING_SOON
    if liquidity and liquidity < 50:
        return MarketRegime.ILLIQUID
    if volatility > 0.75:
        return MarketRegime.CHAOTIC
    if volatility > 0.45:
        return MarketRegime.VOLATILE
    if trend_strength > 0.35:
        return MarketRegime.TRENDING
    return MarketRegime.QUIET


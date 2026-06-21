from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory


class AlreadyPricedInDetector:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def detect_already_priced_in(
        self,
        news_event: dict[str, Any],
        market_id: str,
        *,
        snapshots: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        rows = snapshots if snapshots is not None else self._load_snapshots(market_id)
        if len(rows) < 2:
            return {"score": 0.5, "risk_flags": ["missing_price_history"], "reason": "insufficient snapshots"}
        event_time = news_event.get("event_time") or news_event.get("published_at") or news_event.get("collected_at")
        before = [row for row in rows if _dt(row.get("snapshot_at")) and event_time and _dt(row.get("snapshot_at")) <= event_time]
        after = [row for row in rows if _dt(row.get("snapshot_at")) and event_time and _dt(row.get("snapshot_at")) > event_time]
        before_move = _price_move(before[-2:]) if len(before) >= 2 else 0.0
        after_move = _price_move(after[:2]) if len(after) >= 2 else 0.0
        if before_move >= 0.08:
            return {"score": 0.85, "risk_flags": ["price_moved_before_news_seen"], "reason": "pre-news move detected"}
        if after_move >= 0.08:
            return {"score": 0.7, "risk_flags": ["price_moved_after_news_before_processing"], "reason": "post-news move detected"}
        return {"score": 0.1, "risk_flags": [], "reason": "no meaningful price movement detected"}

    def _load_snapshots(self, market_id: str) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM market_snapshots_v2
                WHERE market_id = %s
                ORDER BY snapshot_at ASC
                LIMIT 50
                """,
                (market_id,),
            ).fetchall()


def _price(row: dict[str, Any]) -> float | None:
    value = row.get("current_price_yes") or row.get("best_ask") or row.get("best_bid")
    return float(value) if value is not None else None


def _price_move(rows: list[dict[str, Any]]) -> float:
    if len(rows) < 2:
        return 0.0
    first = _price(rows[0])
    second = _price(rows[-1])
    if first is None or second is None:
        return 0.0
    return abs(second - first)


def _dt(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


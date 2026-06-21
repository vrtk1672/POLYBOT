from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.social_neuron.contracts import LeadLagStatus


class PriceLeadLagDetector:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def detect_social_price_lead_lag(self, market_id: str, *, social_window: int = 900, price_window: int = 1800) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"lead_lag_status": LeadLagStatus.INSUFFICIENT_DATA.value, "confidence": 0.0, "explanation": "database unavailable"}
        since = datetime.now(UTC) - timedelta(seconds=max(social_window, price_window) * 2)
        with self._factory.connect() as conn:
            social = conn.execute(
                """
                SELECT min(e.collected_at) AS first_social
                FROM social_market_links l
                JOIN social_normalized_events e ON e.social_event_id = l.social_event_id
                WHERE l.market_id = %s AND e.collected_at >= %s
                """,
                (market_id, since),
            ).fetchone()
            snapshots = conn.execute(
                """
                SELECT snapshot_at, current_price_yes, best_bid, best_ask
                FROM market_snapshots_v2
                WHERE market_id = %s AND snapshot_at >= %s
                ORDER BY snapshot_at ASC
                """,
                (market_id, since),
            ).fetchall()
        first_social = social["first_social"] if social else None
        if not first_social or len(snapshots) < 2:
            return {"lead_lag_status": LeadLagStatus.INSUFFICIENT_DATA.value, "confidence": 0.0, "explanation": "missing social or market snapshot history"}
        first_price_time = self._first_price_move_time(snapshots)
        if not first_price_time:
            return {"lead_lag_status": LeadLagStatus.INSUFFICIENT_DATA.value, "confidence": 0.2, "explanation": "no meaningful price move"}
        delta = (first_price_time - first_social).total_seconds()
        if delta > 60:
            return {"lead_lag_status": LeadLagStatus.SOCIAL_LEADS_PRICE.value, "confidence": 0.55, "explanation": "social activity preceded price movement"}
        if delta < -60:
            return {"lead_lag_status": LeadLagStatus.SOCIAL_LAGS_PRICE.value, "confidence": 0.55, "explanation": "price movement preceded social activity"}
        return {"lead_lag_status": LeadLagStatus.SIMULTANEOUS.value, "confidence": 0.45, "explanation": "social and price movement were close together"}

    def _first_price_move_time(self, snapshots: list[dict[str, Any]]) -> datetime | None:
        def price(row: dict[str, Any]) -> float | None:
            if row.get("current_price_yes") is not None:
                return float(row["current_price_yes"])
            bid, ask = row.get("best_bid"), row.get("best_ask")
            if bid is not None and ask is not None:
                return (float(bid) + float(ask)) / 2
            return None

        base = price(snapshots[0])
        if base is None:
            return None
        for row in snapshots[1:]:
            current = price(row)
            if current is not None and abs(current - base) >= 0.02:
                return row["snapshot_at"]
        return None

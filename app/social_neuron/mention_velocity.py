from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.social_neuron.contracts import bounded


class MentionVelocityTracker:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def compute_mentions_velocity(self, market_id: str, window_seconds: int = 900) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mention_count": 0, "unique_author_count": 0, "mentions_velocity": 0.0, "spam_ratio": 0.0, "velocity_zscore": 0.0}
        since = datetime.now(UTC) - timedelta(seconds=window_seconds)
        with self._factory.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.author_handle, e.spam_score, e.bot_risk
                FROM social_market_links l
                JOIN social_normalized_events e ON e.social_event_id = l.social_event_id
                WHERE l.market_id = %s AND e.collected_at >= %s
                """,
                (market_id, since),
            ).fetchall()
        mention_count = len(rows)
        unique_author_count = len({row["author_handle"] for row in rows if row.get("author_handle")}) or mention_count
        spam_count = sum(1 for row in rows if float(row.get("spam_score") or 0) >= 0.5 or float(row.get("bot_risk") or 0) >= 0.5)
        velocity = mention_count / max(1.0, window_seconds / 60)
        baseline = self.compute_baseline(market_id, window_seconds * 4)
        zscore = self.compute_velocity_zscore(velocity, baseline)
        return {
            "mention_count": mention_count,
            "unique_author_count": unique_author_count,
            "mentions_velocity": velocity,
            "spam_ratio": bounded(spam_count / mention_count if mention_count else 0),
            "velocity_zscore": zscore,
        }

    def compute_baseline(self, market_id: str, lookback_window: int = 3600) -> float:
        if not self._factory.enabled:
            return 0.0
        since = datetime.now(UTC) - timedelta(seconds=lookback_window)
        with self._factory.connect() as conn:
            count = conn.execute(
                """
                SELECT count(*) AS count
                FROM social_market_links l
                JOIN social_normalized_events e ON e.social_event_id = l.social_event_id
                WHERE l.market_id = %s AND e.collected_at >= %s
                """,
                (market_id, since),
            ).fetchone()["count"]
        return float(count) / max(1.0, lookback_window / 60)

    def compute_velocity_zscore(self, velocity: float, baseline: float) -> float:
        if baseline <= 0:
            return 3.0 if velocity > 0 else 0.0
        return round((velocity - baseline) / max(0.1, baseline), 4)

    def detect_social_burst(self, market_id: str, window_seconds: int = 900) -> bool:
        stats = self.compute_mentions_velocity(market_id, window_seconds)
        return stats["mention_count"] >= 3 and stats["velocity_zscore"] >= 1.0

    def count_unique_authors(self, market_id: str, window_seconds: int = 900) -> int:
        return int(self.compute_mentions_velocity(market_id, window_seconds)["unique_author_count"])

    def compute_spam_ratio(self, market_id: str, window_seconds: int = 900) -> float:
        return float(self.compute_mentions_velocity(market_id, window_seconds)["spam_ratio"])

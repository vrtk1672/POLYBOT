from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.learning.contracts import WhaleLearning
from app.repositories.learning_repository_helpers import recent, row_dict, rows


class WhaleLearningRepository:
    def insert(self, conn: Connection, item: WhaleLearning) -> dict[str, Any]:
        return row_dict(conn.execute(
            """
            INSERT INTO whale_learning (
                whale_learning_id, whale_id, market_family, market_id, observation_type,
                result, prior_follow_value, new_follow_value, prior_noise_score,
                new_noise_score, hit_rate_delta, timing_quality_delta, confidence,
                learning_signal, explanation
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                item.whale_learning_id, item.whale_id, item.market_family, item.market_id,
                item.observation_type, item.result, item.prior_follow_value,
                item.new_follow_value, item.prior_noise_score, item.new_noise_score,
                item.hit_rate_delta, item.timing_quality_delta, item.confidence,
                item.learning_signal, item.explanation,
            ),
        ).fetchone())

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return recent(conn, "whale_learning", limit)

    def summary(self, conn: Connection) -> list[dict[str, Any]]:
        return rows(conn.execute("SELECT whale_id, learning_signal, COUNT(*) AS count, AVG(confidence) AS avg_confidence FROM whale_learning GROUP BY whale_id, learning_signal ORDER BY count DESC").fetchall())


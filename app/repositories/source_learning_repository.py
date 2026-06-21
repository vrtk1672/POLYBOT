from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.learning.contracts import SourceLearning
from app.repositories.learning_repository_helpers import recent, row_dict, rows


class SourceLearningRepository:
    def insert(self, conn: Connection, item: SourceLearning) -> dict[str, Any]:
        return row_dict(conn.execute(
            """
            INSERT INTO source_learning (
                source_learning_id, source_type, source_name, source_id, market_family,
                observation_type, result, prior_reliability, new_reliability,
                usefulness_delta, latency_delta, confidence, learning_signal, explanation
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                item.source_learning_id, item.source_type, item.source_name, item.source_id,
                item.market_family, item.observation_type, item.result, item.prior_reliability,
                item.new_reliability, item.usefulness_delta, item.latency_delta,
                item.confidence, item.learning_signal, item.explanation,
            ),
        ).fetchone())

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return recent(conn, "source_learning", limit)

    def summary(self, conn: Connection) -> list[dict[str, Any]]:
        return rows(conn.execute("SELECT source_type, learning_signal, COUNT(*) AS count, AVG(confidence) AS avg_confidence FROM source_learning GROUP BY source_type, learning_signal ORDER BY count DESC").fetchall())


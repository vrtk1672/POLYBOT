from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.learning.contracts import NoTradeLearning
from app.repositories.learning_repository_helpers import recent, row_dict, rows


class NoTradeLearningRepository:
    def insert(self, conn: Connection, item: NoTradeLearning) -> dict[str, Any]:
        return row_dict(conn.execute(
            """
            INSERT INTO no_trade_learning (
                no_trade_learning_id, no_trade_id, market_id, market_family, candidate_engine,
                regret_band, regret_score, learning_signal, suggested_filter_change,
                confidence, explanation
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                item.no_trade_learning_id, item.no_trade_id, item.market_id,
                item.market_family, item.candidate_engine, item.regret_band,
                item.regret_score, item.learning_signal, item.suggested_filter_change,
                item.confidence, item.explanation,
            ),
        ).fetchone())

    def by_no_trade_id(self, conn: Connection, no_trade_id: str) -> dict[str, Any] | None:
        return row_dict(conn.execute("SELECT * FROM no_trade_learning WHERE no_trade_id=%s ORDER BY created_at DESC LIMIT 1", (no_trade_id,)).fetchone())

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return recent(conn, "no_trade_learning", limit)

    def summary(self, conn: Connection) -> list[dict[str, Any]]:
        return rows(conn.execute("SELECT regret_band, learning_signal, COUNT(*) AS count, AVG(confidence) AS avg_confidence FROM no_trade_learning GROUP BY regret_band, learning_signal ORDER BY count DESC").fetchall())


from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.learning.contracts import EngineLearning
from app.repositories.learning_repository_helpers import recent, row_dict, rows


class EngineLearningRepository:
    def insert(self, conn: Connection, item: EngineLearning) -> dict[str, Any]:
        return row_dict(conn.execute(
            """
            INSERT INTO engine_learning (
                engine_learning_id, engine, market_family, market_id, review_id, no_trade_id,
                observation_type, result, prior_engine_score, new_engine_score, win_rate_delta,
                roi_delta, slippage_penalty_delta, adverse_selection_delta, confidence,
                learning_signal, explanation
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                item.engine_learning_id, item.engine, item.market_family, item.market_id,
                item.review_id, item.no_trade_id, item.observation_type, item.result,
                item.prior_engine_score, item.new_engine_score, item.win_rate_delta,
                item.roi_delta, item.slippage_penalty_delta, item.adverse_selection_delta,
                item.confidence, item.learning_signal, item.explanation,
            ),
        ).fetchone())

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return recent(conn, "engine_learning", limit)

    def summary(self, conn: Connection) -> list[dict[str, Any]]:
        return rows(conn.execute("SELECT engine, learning_signal, COUNT(*) AS count, AVG(confidence) AS avg_confidence FROM engine_learning GROUP BY engine, learning_signal ORDER BY count DESC").fetchall())


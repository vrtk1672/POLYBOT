from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.no_trade.contracts import NoTradeRegretScore


class NoTradeRegretScoreRepository:
    def insert(self, conn: Connection, regret: NoTradeRegretScore) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO no_trade_regret_score (
                regret_id, no_trade_id, market_id, regret_score, regret_band,
                missed_upside_score, avoided_loss_score, avoided_risk_score,
                liquidity_regret_score, confidence, learning_signal, update_memory,
                explanation
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                regret.regret_id,
                regret.no_trade_id,
                regret.market_id,
                regret.regret_score,
                regret.regret_band,
                regret.missed_upside_score,
                regret.avoided_loss_score,
                regret.avoided_risk_score,
                regret.liquidity_regret_score,
                regret.confidence,
                regret.learning_signal,
                regret.update_memory,
                regret.explanation,
            ),
        ).fetchone()

    def by_no_trade_id(self, conn: Connection, no_trade_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM no_trade_regret_score WHERE no_trade_id=%s ORDER BY created_at DESC, id DESC", (no_trade_id,)).fetchall()

    def summary(self, conn: Connection) -> dict[str, Any]:
        return conn.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE regret_band='HIGH_REGRET') AS high_regret_count,
              COUNT(*) FILTER (WHERE regret_band='GOOD_NO_TRADE') AS good_no_trade_count,
              COUNT(*) FILTER (WHERE regret_band='INSUFFICIENT_DATA') AS insufficient_data_count,
              AVG(regret_score) AS avg_regret_score
            FROM no_trade_regret_score
            """
        ).fetchone()

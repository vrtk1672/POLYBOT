from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.no_trade.contracts import NoTradeReason


class NoTradeReasonRepository:
    def insert_many(self, conn: Connection, no_trade_id: str, reasons: list[NoTradeReason]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for reason in reasons:
            rows.append(
                conn.execute(
                    """
                    INSERT INTO no_trade_reasons (
                        no_trade_id, reason, severity, source_layer, source_field,
                        penalty, hard_block, explanation
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (no_trade_id, reason.reason, reason.severity, reason.source_layer, reason.source_field, reason.penalty, reason.hard_block, reason.explanation),
                ).fetchone()
            )
        return rows

    def by_no_trade_id(self, conn: Connection, no_trade_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM no_trade_reasons WHERE no_trade_id=%s ORDER BY id", (no_trade_id,)).fetchall()

    def top(self, conn: Connection, limit: int = 20) -> list[dict[str, Any]]:
        return conn.execute("SELECT reason, severity, COUNT(*) AS count FROM no_trade_reasons GROUP BY reason, severity ORDER BY count DESC, reason LIMIT %s", (limit,)).fetchall()


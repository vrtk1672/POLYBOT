from __future__ import annotations

from typing import Any

from psycopg import Connection


class ProfitPocketRepository:
    def upsert(self, conn: Connection, *, pocket_id: str, totals: dict[str, float], source_type: str, confidence: float = 0.85) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO profit_pocket (
                pocket_id, total_realized_profit_usd, available_profit_usd, reserved_profit_usd,
                withdrawn_profit_usd, reinvested_profit_usd, source_type, confidence
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (pocket_id) DO UPDATE SET
                total_realized_profit_usd=EXCLUDED.total_realized_profit_usd,
                available_profit_usd=EXCLUDED.available_profit_usd,
                reserved_profit_usd=EXCLUDED.reserved_profit_usd,
                withdrawn_profit_usd=EXCLUDED.withdrawn_profit_usd,
                reinvested_profit_usd=EXCLUDED.reinvested_profit_usd,
                source_type=EXCLUDED.source_type,
                confidence=EXCLUDED.confidence,
                updated_at=now()
            RETURNING *
            """,
            (
                pocket_id,
                totals.get("total_realized_profit_usd", 0.0),
                totals.get("available_profit_usd", 0.0),
                totals.get("reserved_profit_usd", 0.0),
                totals.get("withdrawn_profit_usd", 0.0),
                totals.get("reinvested_profit_usd", 0.0),
                source_type,
                confidence,
            ),
        ).fetchone()

    def latest(self, conn: Connection) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM profit_pocket ORDER BY updated_at DESC, id DESC LIMIT 1").fetchone()



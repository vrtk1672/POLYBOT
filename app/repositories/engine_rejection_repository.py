from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.strategy.contracts import EngineRejection


class EngineRejectionRepository:
    def insert_many(self, conn: Connection, run_id: str, market_id: str, rejections: list[EngineRejection]) -> None:
        for rejection in rejections:
            conn.execute(
                """
                INSERT INTO engine_rejections (
                    run_id, market_id, engine, rejection_reason, severity, source_type,
                    source_id, hard_block, explanation
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    run_id,
                    market_id,
                    rejection.engine,
                    rejection.rejection_reason,
                    rejection.severity,
                    rejection.source_type,
                    rejection.source_id,
                    rejection.hard_block,
                    rejection.explanation,
                ),
            )

    def by_run(self, conn: Connection, run_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM engine_rejections WHERE run_id=%s ORDER BY id ASC", (run_id,)).fetchall()

    def recent(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM engine_rejections ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()


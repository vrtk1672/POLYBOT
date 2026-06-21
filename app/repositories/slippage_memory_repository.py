from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_memory.contracts import SlippageMemory
from app.repositories.market_memory_repository import _jsonable


class SlippageMemoryRepository:
    def insert(self, conn: Connection, memory: SlippageMemory) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO slippage_memory (
                market_id, market_family, token_id, side, observations_count,
                avg_expected_slippage_bps, avg_realized_slippage_bps, slippage_error_bps,
                failed_fill_rate, slippage_risk_score, confidence, summary_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                memory.market_id, memory.market_family, memory.token_id, memory.side,
                memory.observations_count, memory.avg_expected_slippage_bps,
                memory.avg_realized_slippage_bps, memory.slippage_error_bps,
                memory.failed_fill_rate, memory.slippage_risk_score, memory.confidence,
                Jsonb(_jsonable(memory.summary)),
            ),
        ).fetchone()

    def list(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM slippage_memory ORDER BY slippage_risk_score DESC, updated_at DESC LIMIT %s", (limit,)).fetchall()


from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class WhalePerformanceRepository:
    def insert_record(self, conn: Connection, record: dict[str, Any]) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO whale_performance_history (
                whale_performance_id, whale_id, market_id, whale_event_id, observed_outcome,
                pnl_proxy, timing_quality, entry_quality, exit_quality, was_early, was_late,
                was_noisy, follow_result, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (record["whale_performance_id"], record["whale_id"], record.get("market_id"), record.get("whale_event_id"), record.get("observed_outcome"), record.get("pnl_proxy"), record.get("timing_quality"), record.get("entry_quality"), record.get("exit_quality"), record.get("was_early"), record.get("was_late"), record.get("was_noisy"), record.get("follow_result", "INSUFFICIENT_DATA"), Jsonb(record.get("metadata", {}))),
        ).fetchone()

    def list_for_whale(self, conn: Connection, whale_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM whale_performance_history WHERE whale_id = %s ORDER BY evaluated_at DESC LIMIT %s", (whale_id, limit)).fetchall()

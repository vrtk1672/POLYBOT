from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class ContextBrainRunRepository:
    def insert_started(self, conn: Connection, *, run_id: str, market_id: str, market_family: str | None, runtime_mode: str | None, input_sources: list[str], input_completeness_score: float, memory_confidence: float, ai_used: bool = False, ai_request_id: str | None = None) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO context_brain_runs (
                run_id, market_id, market_family, runtime_mode, input_sources_json,
                input_completeness_score, memory_confidence, ai_used, ai_request_id, status
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'STARTED')
            RETURNING *
            """,
            (run_id, market_id, market_family, runtime_mode, Jsonb(input_sources), input_completeness_score, memory_confidence, ai_used, ai_request_id),
        ).fetchone()

    def finish(self, conn: Connection, run_id: str, *, status: str = "COMPLETED", error: str | None = None) -> None:
        conn.execute("UPDATE context_brain_runs SET finished_at = now(), status = %s, error = %s WHERE run_id = %s", (status, error, run_id))

    def health(self, conn: Connection) -> dict[str, Any]:
        return conn.execute("SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS runs_today, MAX(created_at) AS latest_run_ts FROM context_brain_runs").fetchone()

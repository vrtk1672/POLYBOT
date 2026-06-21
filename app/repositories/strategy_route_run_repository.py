from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class StrategyRouteRunRepository:
    def insert_started(self, conn: Connection, *, run_id: str, market_id: str, market_family: str | None, side: str, opportunity_run_id: str | None, opportunity_score_id: int | None, runtime_mode: str | None, input_sources: list[str], input_completeness_score: float) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO strategy_route_runs (
                run_id, market_id, market_family, side, opportunity_run_id, opportunity_score_id,
                runtime_mode, input_sources_json, input_completeness_score, status
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'STARTED')
            RETURNING *
            """,
            (run_id, market_id, market_family, side, opportunity_run_id, opportunity_score_id, runtime_mode, Jsonb(input_sources), input_completeness_score),
        ).fetchone()

    def finish(self, conn: Connection, run_id: str, *, status: str = "COMPLETED", error: str | None = None) -> None:
        conn.execute("UPDATE strategy_route_runs SET finished_at = now(), status = %s, error = %s WHERE run_id = %s", (status, error, run_id))

    def health(self, conn: Connection) -> dict[str, Any]:
        return conn.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) AS runs_today,
              COUNT(*) FILTER (WHERE status = 'ERROR' AND created_at::date = CURRENT_DATE) AS errors_today,
              MAX(created_at) AS latest_run_ts
            FROM strategy_route_runs
            """
        ).fetchone()


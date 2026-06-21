from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class RiskGateRunRepository:
    def insert_started(self, conn: Connection, **row: Any) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO risk_gate_runs (
                run_id, market_id, market_family, side, engine, strategy_route_id, allocation_id,
                runtime_mode, input_sources_json, input_completeness_score
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                row["run_id"],
                row["market_id"],
                row.get("market_family"),
                row.get("side", "UNKNOWN"),
                row.get("engine", "NO_TRADE"),
                row.get("strategy_route_id"),
                row.get("allocation_id"),
                row.get("runtime_mode"),
                Jsonb(row.get("input_sources", [])),
                row.get("input_completeness_score", 0),
            ),
        ).fetchone()

    def finish(self, conn: Connection, run_id: str, status: str = "FINISHED", error: str | None = None) -> None:
        conn.execute("UPDATE risk_gate_runs SET finished_at=now(), status=%s, error=%s WHERE run_id=%s", (status, error, run_id))

    def health(self, conn: Connection) -> dict[str, Any]:
        return conn.execute(
            """
            SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS gate_runs_today,
                   COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND status='ERROR') AS errors_today,
                   MAX(created_at) AS latest_gate_ts
            FROM risk_gate_runs
            """
        ).fetchone()



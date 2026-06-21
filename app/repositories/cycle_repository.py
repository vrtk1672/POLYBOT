from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.cycle import CycleCloseContract, CycleOpenContract


class CycleRepository:
    def open_cycle(self, conn: Connection, cycle: CycleOpenContract) -> None:
        conn.execute(
            """
            INSERT INTO cycles (
                id, started_at, status, mode, trigger_source, session_id,
                top_n, pages_requested, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET started_at = EXCLUDED.started_at,
                status = EXCLUDED.status,
                mode = EXCLUDED.mode,
                trigger_source = EXCLUDED.trigger_source,
                session_id = EXCLUDED.session_id,
                top_n = EXCLUDED.top_n,
                pages_requested = EXCLUDED.pages_requested,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            """,
            (
                cycle.id,
                cycle.started_at,
                cycle.status,
                cycle.mode,
                cycle.trigger_source,
                cycle.session_id,
                cycle.top_n,
                cycle.pages_requested,
                Jsonb(cycle.metadata),
            ),
        )

    def close_cycle(self, conn: Connection, cycle: CycleCloseContract) -> None:
        conn.execute(
            """
            UPDATE cycles
            SET completed_at = %s,
                status = %s,
                markets_fetched_count = %s,
                markets_scored_count = %s,
                markets_ranked_count = %s,
                decisions_count = %s,
                selected_market_id = %s,
                runtime_ms = %s,
                last_error = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (
                cycle.completed_at,
                cycle.status,
                cycle.markets_fetched_count,
                cycle.markets_scored_count,
                cycle.markets_ranked_count,
                cycle.decisions_count,
                cycle.selected_market_id,
                cycle.runtime_ms,
                cycle.last_error,
                cycle.id,
            ),
        )

    def get_cycle(self, conn: Connection, cycle_id: str) -> dict[str, object] | None:
        return conn.execute(
            "SELECT * FROM cycles WHERE id = %s",
            (cycle_id,),
        ).fetchone()

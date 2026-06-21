from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.shadow_run import ShadowRunCloseContract, ShadowRunOpenContract


class ShadowRunsRepository:
    def open_run(self, conn: Connection, shadow_run: ShadowRunOpenContract) -> None:
        conn.execute(
            """
            INSERT INTO shadow_runs (
                id, cycle_id, mode, started_at, status, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET cycle_id = EXCLUDED.cycle_id,
                mode = EXCLUDED.mode,
                started_at = EXCLUDED.started_at,
                status = EXCLUDED.status,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = now()
            """,
            (
                shadow_run.id,
                shadow_run.cycle_id,
                shadow_run.mode,
                shadow_run.started_at,
                shadow_run.status,
                Jsonb(shadow_run.metadata_json),
            ),
        )

    def close_run(self, conn: Connection, shadow_run: ShadowRunCloseContract) -> None:
        conn.execute(
            """
            UPDATE shadow_runs
            SET ended_at = %s,
                status = %s,
                markets_seen_count = %s,
                markets_ranked_count = %s,
                candidates_selected_count = %s,
                shadow_orders_count = %s,
                metadata_json = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (
                shadow_run.ended_at,
                shadow_run.status,
                shadow_run.markets_seen_count,
                shadow_run.markets_ranked_count,
                shadow_run.candidates_selected_count,
                shadow_run.shadow_orders_count,
                Jsonb(shadow_run.metadata_json),
                shadow_run.id,
            ),
        )

    def get_by_id(self, conn: Connection, shadow_run_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM shadow_runs
            WHERE id = %s
            LIMIT 1
            """,
            (shadow_run_id,),
        ).fetchone()

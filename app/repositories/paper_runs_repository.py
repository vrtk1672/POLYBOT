from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.paper_run import PaperRunCloseContract, PaperRunOpenContract


class PaperRunsRepository:
    def open_run(self, conn: Connection, paper_run: PaperRunOpenContract) -> None:
        conn.execute(
            """
            INSERT INTO paper_runs (
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
                paper_run.id,
                paper_run.cycle_id,
                paper_run.mode,
                paper_run.started_at,
                paper_run.status,
                Jsonb(paper_run.metadata_json),
            ),
        )

    def close_run(self, conn: Connection, paper_run: PaperRunCloseContract) -> None:
        conn.execute(
            """
            UPDATE paper_runs
            SET ended_at = %s,
                status = %s,
                markets_seen_count = %s,
                markets_ranked_count = %s,
                candidates_selected_count = %s,
                signals_emitted_count = %s,
                metadata_json = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (
                paper_run.ended_at,
                paper_run.status,
                paper_run.markets_seen_count,
                paper_run.markets_ranked_count,
                paper_run.candidates_selected_count,
                paper_run.signals_emitted_count,
                Jsonb(paper_run.metadata_json),
                paper_run.id,
            ),
        )

    def get_by_id(self, conn: Connection, paper_run_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM paper_runs
            WHERE id = %s
            LIMIT 1
            """,
            (paper_run_id,),
        ).fetchone()

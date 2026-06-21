from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.cognition_summary_run import (
    CognitionSummaryRunCloseContract,
    CognitionSummaryRunOpenContract,
)


class CognitionSummaryRunsRepository:
    def open_run(self, conn: Connection, run: CognitionSummaryRunOpenContract) -> None:
        conn.execute(
            """
            INSERT INTO cognition_summary_runs (
                id, source_type, source_ref, status,
                narrator_version, prompt_version, model_name,
                started_at, input_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run.id,
                run.source_type,
                run.source_ref,
                run.status,
                run.narrator_version,
                run.prompt_version,
                run.model_name,
                run.started_at,
                run.input_count,
                Jsonb(run.metadata_json),
            ),
        )

    def close_run(self, conn: Connection, run: CognitionSummaryRunCloseContract) -> None:
        conn.execute(
            """
            UPDATE cognition_summary_runs
            SET status = %s,
                ended_at = %s,
                success_count = %s,
                failure_count = %s,
                metadata_json = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (
                run.status,
                run.ended_at,
                run.success_count,
                run.failure_count,
                Jsonb(run.metadata_json),
                run.id,
            ),
        )

    def get_by_id(self, conn: Connection, run_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM cognition_summary_runs
            WHERE id = %s
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()

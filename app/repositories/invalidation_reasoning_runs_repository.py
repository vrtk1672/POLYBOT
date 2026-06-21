from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.invalidation_reasoning_run import (
    InvalidationReasoningRunCloseContract,
    InvalidationReasoningRunOpenContract,
)


class InvalidationReasoningRunsRepository:
    def open_run(self, conn: Connection, run: InvalidationReasoningRunOpenContract) -> None:
        conn.execute(
            """
            INSERT INTO invalidation_reasoning_runs (
                id, resolution_analysis_run_id, source_type, source_ref, status,
                reasoner_version, prompt_version, model_name,
                started_at, input_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run.id,
                run.resolution_analysis_run_id,
                run.source_type,
                run.source_ref,
                run.status,
                run.reasoner_version,
                run.prompt_version,
                run.model_name,
                run.started_at,
                run.input_count,
                Jsonb(run.metadata_json),
            ),
        )

    def close_run(self, conn: Connection, run: InvalidationReasoningRunCloseContract) -> None:
        conn.execute(
            """
            UPDATE invalidation_reasoning_runs
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
            FROM invalidation_reasoning_runs
            WHERE id = %s
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()

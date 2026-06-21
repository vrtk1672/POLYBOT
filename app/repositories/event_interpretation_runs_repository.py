from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.event_interpretation_run import (
    EventInterpretationRunCloseContract,
    EventInterpretationRunOpenContract,
)


class EventInterpretationRunsRepository:
    def open_run(self, conn: Connection, run: EventInterpretationRunOpenContract) -> None:
        conn.execute(
            """
            INSERT INTO event_interpretation_runs (
                id, source_type, source_ref, status, prompt_version, model_name,
                started_at, input_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET source_type = EXCLUDED.source_type,
                source_ref = EXCLUDED.source_ref,
                status = EXCLUDED.status,
                prompt_version = EXCLUDED.prompt_version,
                model_name = EXCLUDED.model_name,
                started_at = EXCLUDED.started_at,
                input_count = EXCLUDED.input_count,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = now()
            """,
            (
                run.id,
                run.source_type,
                run.source_ref,
                run.status,
                run.prompt_version,
                run.model_name,
                run.started_at,
                run.input_count,
                Jsonb(run.metadata_json),
            ),
        )

    def close_run(self, conn: Connection, run: EventInterpretationRunCloseContract) -> None:
        conn.execute(
            """
            UPDATE event_interpretation_runs
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
            FROM event_interpretation_runs
            WHERE id = %s
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()

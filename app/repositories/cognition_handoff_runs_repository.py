from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.cognition_handoff_run import (
    CognitionHandoffRunCloseContract,
    CognitionHandoffRunOpenContract,
)


class CognitionHandoffRunsRepository:
    def open_run(self, conn: Connection, run: CognitionHandoffRunOpenContract) -> None:
        conn.execute(
            """
            INSERT INTO cognition_handoff_runs (
                id, external_event_enrichment_run_id, source_type, source_ref, status,
                handoff_version, started_at, input_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run.id,
                run.external_event_enrichment_run_id,
                run.source_type,
                run.source_ref,
                run.status,
                run.handoff_version,
                run.started_at,
                run.input_count,
                Jsonb(run.metadata_json),
            ),
        )

    def close_run(self, conn: Connection, run: CognitionHandoffRunCloseContract) -> None:
        conn.execute(
            """
            UPDATE cognition_handoff_runs
            SET status = %s,
                ended_at = %s,
                sent_count = %s,
                held_count = %s,
                skipped_count = %s,
                failure_count = %s,
                metadata_json = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (
                run.status,
                run.ended_at,
                run.sent_count,
                run.held_count,
                run.skipped_count,
                run.failure_count,
                Jsonb(run.metadata_json),
                run.id,
            ),
        )

    def get_by_id(self, conn: Connection, run_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM cognition_handoff_runs
            WHERE id = %s
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()

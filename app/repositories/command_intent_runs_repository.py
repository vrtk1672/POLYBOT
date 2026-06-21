from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.command_intent_run import (
    CommandIntentRunCloseContract,
    CommandIntentRunOpenContract,
)


class CommandIntentRunsRepository:
    def open_run(self, conn: Connection, run: CommandIntentRunOpenContract) -> None:
        conn.execute(
            """
            INSERT INTO command_intent_runs (
                id, source_type, source_ref, status, command_intent_version,
                started_at, input_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run.id,
                run.source_type,
                run.source_ref,
                run.status,
                run.command_intent_version,
                run.started_at,
                run.input_count,
                Jsonb(run.metadata_json),
            ),
        )

    def close_run(self, conn: Connection, run: CommandIntentRunCloseContract) -> None:
        conn.execute(
            """
            UPDATE command_intent_runs
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
            FROM command_intent_runs
            WHERE id = %s
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()

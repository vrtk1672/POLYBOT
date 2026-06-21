from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.intelligence_ingestion_run import (
    IntelligenceIngestionRunCloseContract,
    IntelligenceIngestionRunOpenContract,
)


class IntelligenceIngestionRunsRepository:
    def open_run(self, conn: Connection, run: IntelligenceIngestionRunOpenContract) -> None:
        conn.execute(
            """
            INSERT INTO intelligence_ingestion_runs (
                id, intelligence_source_id, run_type, status, started_at, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                run.id,
                run.intelligence_source_id,
                run.run_type,
                run.status,
                run.started_at,
                Jsonb(run.metadata_json),
            ),
        )

    def close_run(self, conn: Connection, run: IntelligenceIngestionRunCloseContract) -> None:
        conn.execute(
            """
            UPDATE intelligence_ingestion_runs
            SET status = %s,
                ended_at = %s,
                fetched_count = %s,
                normalized_count = %s,
                deduped_count = %s,
                failed_count = %s,
                metadata_json = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (
                run.status,
                run.ended_at,
                run.fetched_count,
                run.normalized_count,
                run.deduped_count,
                run.failed_count,
                Jsonb(run.metadata_json),
                run.id,
            ),
        )

    def get_by_id(self, conn: Connection, run_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM intelligence_ingestion_runs
            WHERE id = %s
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()

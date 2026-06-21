from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.artifact import RunArtifactContract


class RunArtifactsRepository:
    def upsert(self, conn: Connection, artifact: RunArtifactContract) -> None:
        conn.execute(
            """
            INSERT INTO run_artifacts (
                id, cycle_id, artifact_type, artifact_scope, path, checksum, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (path) DO UPDATE
            SET cycle_id = EXCLUDED.cycle_id,
                artifact_type = EXCLUDED.artifact_type,
                artifact_scope = EXCLUDED.artifact_scope,
                checksum = EXCLUDED.checksum,
                metadata_json = EXCLUDED.metadata_json
            """,
            (
                artifact.id,
                artifact.cycle_id,
                artifact.artifact_type,
                artifact.artifact_scope,
                artifact.path,
                artifact.checksum,
                Jsonb(artifact.metadata_json),
            ),
        )

    def list_for_cycle(self, conn: Connection, cycle_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM run_artifacts
            WHERE cycle_id = %s
            ORDER BY created_at ASC, path ASC
            """,
            (cycle_id,),
        ).fetchall()

    def list_for_cycle_market(
        self,
        conn: Connection,
        *,
        cycle_id: str,
        market_id: str,
    ) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM run_artifacts
            WHERE cycle_id = %s
              AND (
                    metadata_json->>'market_id' = %s
                    OR artifact_scope = 'cycle'
                  )
            ORDER BY created_at ASC, path ASC
            """,
            (cycle_id, market_id),
        ).fetchall()

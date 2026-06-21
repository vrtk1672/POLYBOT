from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.ranking_policy_run import RankingPolicyRunCloseContract, RankingPolicyRunOpenContract


class RankingPolicyRunsRepository:
    def open_run(self, conn: Connection, run: RankingPolicyRunOpenContract) -> None:
        conn.execute(
            """
            INSERT INTO ranking_policy_runs (
                id, ranking_v2_run_id, source_type, source_ref, status, policy_version,
                started_at, input_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run.id,
                run.ranking_v2_run_id,
                run.source_type,
                run.source_ref,
                run.status,
                run.policy_version,
                run.started_at,
                run.input_count,
                Jsonb(run.metadata_json),
            ),
        )

    def close_run(self, conn: Connection, run: RankingPolicyRunCloseContract) -> None:
        conn.execute(
            """
            UPDATE ranking_policy_runs
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
            FROM ranking_policy_runs
            WHERE id = %s
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()

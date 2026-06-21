from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.invalidation_policy_record import InvalidationPolicyRecordContract


class InvalidationPolicyRecordsRepository:
    def insert(self, conn: Connection, record: InvalidationPolicyRecordContract) -> None:
        conn.execute(
            """
            INSERT INTO invalidation_policy_records (
                id, invalidation_policy_run_id, market_id, cycle_id,
                ranking_policy_candidate_id, cognition_summary_id, invalidation_reasoning_id,
                trade_classification_id, bucket_allocation_id, invalidation_state_class,
                exit_policy_class, invalidation_severity_score, exit_urgency_score,
                deployment_gate_effect, policy_reason_codes_json, policy_reason_text,
                explanation_json, policy_version
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
            """,
            (
                record.id,
                record.invalidation_policy_run_id,
                record.market_id,
                record.cycle_id,
                record.ranking_policy_candidate_id,
                record.cognition_summary_id,
                record.invalidation_reasoning_id,
                record.trade_classification_id,
                record.bucket_allocation_id,
                record.invalidation_state_class,
                record.exit_policy_class,
                record.invalidation_severity_score,
                record.exit_urgency_score,
                record.deployment_gate_effect,
                Jsonb(record.policy_reason_codes_json),
                record.policy_reason_text,
                Jsonb(record.explanation_json),
                record.policy_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM invalidation_policy_records
            WHERE invalidation_policy_run_id = %s
            ORDER BY exit_urgency_score DESC, invalidation_severity_score DESC, created_at DESC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, invalidation_policy_record_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM invalidation_policy_records
            WHERE id = %s
            LIMIT 1
            """,
            (invalidation_policy_record_id,),
        ).fetchone()

    def get_latest_by_market(self, conn: Connection, market_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM invalidation_policy_records
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()

    def list_exit_recommended(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM invalidation_policy_records
            WHERE exit_policy_class = 'EXIT_RECOMMENDED'
            ORDER BY exit_urgency_score DESC, invalidation_severity_score DESC, created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

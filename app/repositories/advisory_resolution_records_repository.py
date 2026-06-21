from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.advisory_resolution_record import AdvisoryResolutionRecordContract


class AdvisoryResolutionRecordsRepository:
    def insert(self, conn: Connection, record: AdvisoryResolutionRecordContract) -> None:
        conn.execute(
            """
            INSERT INTO advisory_resolution_records (
                id, advisory_resolution_run_id, market_id, cycle_id,
                invalidation_policy_record_id, exit_advisory_run_id,
                primary_advisory_action_class, primary_priority_class,
                action_readiness_class, conflict_status_class,
                exposure_count, critical_exposure_count,
                advisory_reason_codes_json, advisory_reason_text,
                explanation_json, advisory_resolution_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.id,
                record.advisory_resolution_run_id,
                record.market_id,
                record.cycle_id,
                record.invalidation_policy_record_id,
                record.exit_advisory_run_id,
                record.primary_advisory_action_class,
                record.primary_priority_class,
                record.action_readiness_class,
                record.conflict_status_class,
                record.exposure_count,
                record.critical_exposure_count,
                Jsonb(record.advisory_reason_codes_json),
                record.advisory_reason_text,
                Jsonb(record.explanation_json),
                record.advisory_resolution_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM advisory_resolution_records
            WHERE advisory_resolution_run_id = %s
            ORDER BY
                CASE primary_priority_class
                    WHEN 'CRITICAL' THEN 1
                    WHEN 'HIGH' THEN 2
                    WHEN 'MEDIUM' THEN 3
                    ELSE 4
                END ASC,
                created_at DESC,
                id DESC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, advisory_resolution_record_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM advisory_resolution_records
            WHERE id = %s
            LIMIT 1
            """,
            (advisory_resolution_record_id,),
        ).fetchone()

    def get_latest_by_market(self, conn: Connection, market_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM advisory_resolution_records
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()

    def list_for_market(self, conn: Connection, market_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM advisory_resolution_records
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (market_id,),
        ).fetchall()

    def list_action_ready(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM advisory_resolution_records
            WHERE action_readiness_class IN ('READY_FOR_REVIEW', 'READY_FOR_CONTROLLED_ORCHESTRATION')
            ORDER BY
                CASE action_readiness_class
                    WHEN 'READY_FOR_CONTROLLED_ORCHESTRATION' THEN 1
                    ELSE 2
                END ASC,
                CASE primary_priority_class
                    WHEN 'CRITICAL' THEN 1
                    WHEN 'HIGH' THEN 2
                    WHEN 'MEDIUM' THEN 3
                    ELSE 4
                END ASC,
                created_at DESC,
                id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

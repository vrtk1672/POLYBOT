from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.exit_advisory_record import ExitAdvisoryRecordContract


class ExitAdvisoryRecordsRepository:
    def insert(self, conn: Connection, record: ExitAdvisoryRecordContract) -> None:
        conn.execute(
            """
            INSERT INTO exit_advisory_records (
                id, exit_advisory_run_id, market_id, invalidation_policy_record_id,
                exposure_type, exposure_ref_id, advisory_action_class, advisory_priority_class,
                advisory_reason_codes_json, advisory_reason_text, explanation_json, advisory_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.id,
                record.exit_advisory_run_id,
                record.market_id,
                record.invalidation_policy_record_id,
                record.exposure_type,
                record.exposure_ref_id,
                record.advisory_action_class,
                record.advisory_priority_class,
                Jsonb(record.advisory_reason_codes_json),
                record.advisory_reason_text,
                Jsonb(record.explanation_json),
                record.advisory_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM exit_advisory_records
            WHERE exit_advisory_run_id = %s
            ORDER BY
                CASE advisory_priority_class
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

    def get_by_id(self, conn: Connection, exit_advisory_record_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM exit_advisory_records
            WHERE id = %s
            LIMIT 1
            """,
            (exit_advisory_record_id,),
        ).fetchone()

    def get_latest_by_market(self, conn: Connection, market_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM exit_advisory_records
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()

    def get_latest_for_exposure(
        self,
        conn: Connection,
        *,
        exposure_type: str,
        exposure_ref_id: str,
    ) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM exit_advisory_records
            WHERE exposure_type = %s
              AND exposure_ref_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (exposure_type, exposure_ref_id),
        ).fetchone()

    def list_for_market(self, conn: Connection, market_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM exit_advisory_records
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (market_id,),
        ).fetchall()

    def list_for_policy_record(self, conn: Connection, invalidation_policy_record_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM exit_advisory_records
            WHERE invalidation_policy_record_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (invalidation_policy_record_id,),
        ).fetchall()

    def list_critical(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM exit_advisory_records
            WHERE advisory_priority_class = 'CRITICAL'
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

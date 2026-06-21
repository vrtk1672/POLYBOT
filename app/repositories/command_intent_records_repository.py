from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.command_intent_record import CommandIntentRecordContract


class CommandIntentRecordsRepository:
    def insert(self, conn: Connection, record: CommandIntentRecordContract) -> None:
        conn.execute(
            """
            INSERT INTO command_intent_records (
                id, command_intent_run_id, market_id, advisory_resolution_record_id,
                exit_advisory_record_id, exposure_type, exposure_ref_id,
                command_intent_class, command_priority_class, command_status_class,
                orchestration_eligibility_class, command_reason_codes_json,
                command_reason_text, explanation_json, advisory_resolution_version,
                command_intent_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.id,
                record.command_intent_run_id,
                record.market_id,
                record.advisory_resolution_record_id,
                record.exit_advisory_record_id,
                record.exposure_type,
                record.exposure_ref_id,
                record.command_intent_class,
                record.command_priority_class,
                record.command_status_class,
                record.orchestration_eligibility_class,
                Jsonb(record.command_reason_codes_json),
                record.command_reason_text,
                Jsonb(record.explanation_json),
                record.advisory_resolution_version,
                record.command_intent_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM command_intent_records
            WHERE command_intent_run_id = %s
            ORDER BY
                CASE command_priority_class
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

    def get_by_id(self, conn: Connection, command_intent_record_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM command_intent_records
            WHERE id = %s
            LIMIT 1
            """,
            (command_intent_record_id,),
        ).fetchone()

    def get_latest_by_market(self, conn: Connection, market_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM command_intent_records
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
            FROM command_intent_records
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
            FROM command_intent_records
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (market_id,),
        ).fetchall()

    def list_for_resolution_record(self, conn: Connection, advisory_resolution_record_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM command_intent_records
            WHERE advisory_resolution_record_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (advisory_resolution_record_id,),
        ).fetchall()

    def list_orchestration_eligible(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM command_intent_records
            WHERE orchestration_eligibility_class = 'ELIGIBLE_FOR_CONTROLLED_ORCHESTRATION'
            ORDER BY
                CASE command_priority_class
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

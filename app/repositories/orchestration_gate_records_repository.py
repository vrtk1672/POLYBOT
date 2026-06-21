from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.orchestration_gate_record import OrchestrationGateRecordContract


class OrchestrationGateRecordsRepository:
    def insert(self, conn: Connection, record: OrchestrationGateRecordContract) -> None:
        conn.execute(
            """
            INSERT INTO orchestration_gate_records (
                id, orchestration_gate_run_id, market_id, command_intent_record_id,
                orchestration_decision_class, orchestration_reason_codes_json,
                orchestration_reason_text, gate_explanation_json, packet_candidate_id,
                orchestration_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.id,
                record.orchestration_gate_run_id,
                record.market_id,
                record.command_intent_record_id,
                record.orchestration_decision_class,
                Jsonb(record.orchestration_reason_codes_json),
                record.orchestration_reason_text,
                Jsonb(record.gate_explanation_json),
                record.packet_candidate_id,
                record.orchestration_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM orchestration_gate_records
            WHERE orchestration_gate_run_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, orchestration_gate_record_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM orchestration_gate_records
            WHERE id = %s
            LIMIT 1
            """,
            (orchestration_gate_record_id,),
        ).fetchone()

    def get_latest_by_market(self, conn: Connection, market_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM orchestration_gate_records
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
            FROM orchestration_gate_records
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (market_id,),
        ).fetchall()

    def has_recent_allowed_for_exposure_command(
        self,
        conn: Connection,
        *,
        exposure_type: str,
        exposure_ref_id: str,
        command_intent_class: str,
        since: datetime,
    ) -> bool:
        row = conn.execute(
            """
            SELECT 1
            FROM orchestration_gate_records ogr
            JOIN command_intent_records cir
              ON cir.id = ogr.command_intent_record_id
            WHERE ogr.orchestration_decision_class = 'ALLOW_DRY_RUN'
              AND cir.exposure_type = %s
              AND cir.exposure_ref_id = %s
              AND cir.command_intent_class = %s
              AND ogr.created_at >= %s
            LIMIT 1
            """,
            (exposure_type, exposure_ref_id, command_intent_class, since),
        ).fetchone()
        return row is not None

from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.orchestration_packet import OrchestrationPacketContract


class OrchestrationPacketsRepository:
    def insert(self, conn: Connection, packet: OrchestrationPacketContract) -> None:
        conn.execute(
            """
            INSERT INTO orchestration_packets (
                id, orchestration_gate_run_id, packet_status_class, packet_priority_class,
                packet_action_count, markets_covered_count, included_command_intent_ids_json,
                packet_reason_codes_json, packet_reason_text, explanation_json,
                orchestration_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                packet.id,
                packet.orchestration_gate_run_id,
                packet.packet_status_class,
                packet.packet_priority_class,
                packet.packet_action_count,
                packet.markets_covered_count,
                Jsonb(packet.included_command_intent_ids_json),
                Jsonb(packet.packet_reason_codes_json),
                packet.packet_reason_text,
                Jsonb(packet.explanation_json),
                packet.orchestration_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM orchestration_packets
            WHERE orchestration_gate_run_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, orchestration_packet_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM orchestration_packets
            WHERE id = %s
            LIMIT 1
            """,
            (orchestration_packet_id,),
        ).fetchone()

    def list_dry_run_ready(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM orchestration_packets
            WHERE packet_status_class = 'DRY_RUN_READY'
            ORDER BY
                CASE packet_priority_class
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

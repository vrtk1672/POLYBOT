from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.cognition_handoff_candidate import CognitionHandoffCandidateContract


class CognitionHandoffCandidatesRepository:
    def insert(self, conn: Connection, candidate: CognitionHandoffCandidateContract) -> None:
        conn.execute(
            """
            INSERT INTO cognition_handoff_candidates (
                id, cognition_handoff_run_id, external_event_id, external_event_enrichment_id,
                intelligence_source_id, handoff_decision_class, handoff_priority_class,
                handoff_reason_code, handoff_reason_text, topic_class, usability_hint_class,
                novelty_hint_class, contradiction_hint_class, trust_weight_snapshot,
                handoff_payload_json, linked_interpretation_run_id, linked_interpretation_id,
                status, error_text, handoff_version
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            """,
            (
                candidate.id,
                candidate.cognition_handoff_run_id,
                candidate.external_event_id,
                candidate.external_event_enrichment_id,
                candidate.intelligence_source_id,
                candidate.handoff_decision_class,
                candidate.handoff_priority_class,
                candidate.handoff_reason_code,
                candidate.handoff_reason_text,
                candidate.topic_class,
                candidate.usability_hint_class,
                candidate.novelty_hint_class,
                candidate.contradiction_hint_class,
                candidate.trust_weight_snapshot,
                Jsonb(candidate.handoff_payload_json),
                candidate.linked_interpretation_run_id,
                candidate.linked_interpretation_id,
                candidate.status,
                candidate.error_text,
                candidate.handoff_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM cognition_handoff_candidates
            WHERE cognition_handoff_run_id = %s
            ORDER BY created_at ASC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, candidate_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM cognition_handoff_candidates
            WHERE id = %s
            LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()

    def list_for_external_event(self, conn: Connection, external_event_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM cognition_handoff_candidates
            WHERE external_event_id = %s
            ORDER BY created_at DESC
            """,
            (external_event_id,),
        ).fetchall()

    def list_pending(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM cognition_handoff_candidates
            WHERE handoff_decision_class IN ('SEND_TO_INTERPRETER', 'HOLD_FOR_REVIEW')
              AND status = 'SUCCESS'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

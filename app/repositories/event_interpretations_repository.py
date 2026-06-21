from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.event_interpretation import EventInterpretationContract


class EventInterpretationsRepository:
    def insert(self, conn: Connection, interpretation: EventInterpretationContract) -> None:
        conn.execute(
            """
            INSERT INTO event_interpretations (
                id, interpretation_run_id, source_type, source_ref, status, error_text,
                raw_event_text, raw_event_payload_json, normalized_event_title, event_type,
                event_summary, certainty_score, ambiguity_score, novelty_score,
                directness_class, directness_score, contradiction_risk,
                affected_market_candidates_json, affected_outcomes_json,
                recommended_action_class, explanation_json, prompt_version, model_name
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                interpretation.id,
                interpretation.interpretation_run_id,
                interpretation.source_type,
                interpretation.source_ref,
                interpretation.status,
                interpretation.error_text,
                interpretation.raw_event_text,
                Jsonb(interpretation.raw_event_payload_json),
                interpretation.normalized_event_title,
                interpretation.event_type,
                interpretation.event_summary,
                interpretation.certainty_score,
                interpretation.ambiguity_score,
                interpretation.novelty_score,
                interpretation.directness_class,
                interpretation.directness_score,
                interpretation.contradiction_risk,
                Jsonb(interpretation.affected_market_candidates_json),
                Jsonb(interpretation.affected_outcomes_json),
                interpretation.recommended_action_class,
                Jsonb(interpretation.explanation_json),
                interpretation.prompt_version,
                interpretation.model_name,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM event_interpretations
            WHERE interpretation_run_id = %s
            ORDER BY created_at ASC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, interpretation_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM event_interpretations
            WHERE id = %s
            LIMIT 1
            """,
            (interpretation_id,),
        ).fetchone()

    def list_recent(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM event_interpretations
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

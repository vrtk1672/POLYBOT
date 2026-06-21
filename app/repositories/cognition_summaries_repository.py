from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.cognition_summary import CognitionSummaryContract


class CognitionSummariesRepository:
    def insert(self, conn: Connection, summary: CognitionSummaryContract) -> None:
        conn.execute(
            """
            INSERT INTO cognition_summaries (
                id, cognition_summary_run_id, interpretation_id, market_link_candidate_id,
                resolution_analysis_id, invalidation_reasoning_id, market_id, market_question,
                event_summary_snapshot, raw_context_json, narration_summary, concise_narration_text,
                cognition_conclusion_class, overall_confidence_score, caution_score,
                usability_class, recommended_operator_focus, evidence_json, status,
                error_text, narrator_version, prompt_version, model_name
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                summary.id,
                summary.cognition_summary_run_id,
                summary.interpretation_id,
                summary.market_link_candidate_id,
                summary.resolution_analysis_id,
                summary.invalidation_reasoning_id,
                summary.market_id,
                summary.market_question,
                summary.event_summary_snapshot,
                Jsonb(summary.raw_context_json),
                summary.narration_summary,
                summary.concise_narration_text,
                summary.cognition_conclusion_class,
                summary.overall_confidence_score,
                summary.caution_score,
                summary.usability_class,
                summary.recommended_operator_focus,
                Jsonb(summary.evidence_json),
                summary.status,
                summary.error_text,
                summary.narrator_version,
                summary.prompt_version,
                summary.model_name,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM cognition_summaries
            WHERE cognition_summary_run_id = %s
            ORDER BY created_at ASC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, summary_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM cognition_summaries
            WHERE id = %s
            LIMIT 1
            """,
            (summary_id,),
        ).fetchone()

    def list_for_market(self, conn: Connection, market_id: str, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM cognition_summaries
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (market_id, limit),
        ).fetchall()

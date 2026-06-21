from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.invalidation_reasoning import InvalidationReasoningContract


class InvalidationReasoningsRepository:
    def insert(self, conn: Connection, reasoning: InvalidationReasoningContract) -> None:
        conn.execute(
            """
            INSERT INTO invalidation_reasonings (
                id, invalidation_reasoning_run_id, interpretation_id, market_link_candidate_id,
                resolution_analysis_id, market_id, market_question, raw_context_json,
                reasoning_summary, thesis_effect_class, invalidation_risk_score,
                confidence_degradation_score, contradiction_strength_score,
                recommended_monitoring_class, advisory_action_class,
                explanation_json, status, error_text, reasoner_version, prompt_version, model_name
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                reasoning.id,
                reasoning.invalidation_reasoning_run_id,
                reasoning.interpretation_id,
                reasoning.market_link_candidate_id,
                reasoning.resolution_analysis_id,
                reasoning.market_id,
                reasoning.market_question,
                Jsonb(reasoning.raw_context_json),
                reasoning.reasoning_summary,
                reasoning.thesis_effect_class,
                reasoning.invalidation_risk_score,
                reasoning.confidence_degradation_score,
                reasoning.contradiction_strength_score,
                reasoning.recommended_monitoring_class,
                reasoning.advisory_action_class,
                Jsonb(reasoning.explanation_json),
                reasoning.status,
                reasoning.error_text,
                reasoning.reasoner_version,
                reasoning.prompt_version,
                reasoning.model_name,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM invalidation_reasonings
            WHERE invalidation_reasoning_run_id = %s
            ORDER BY created_at ASC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, reasoning_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM invalidation_reasonings
            WHERE id = %s
            LIMIT 1
            """,
            (reasoning_id,),
        ).fetchone()

    def list_for_market(self, conn: Connection, market_id: str, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM invalidation_reasonings
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (market_id, limit),
        ).fetchall()

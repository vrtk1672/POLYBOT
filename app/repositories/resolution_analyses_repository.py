from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.resolution_analysis import ResolutionAnalysisContract


class ResolutionAnalysesRepository:
    def insert(self, conn: Connection, analysis: ResolutionAnalysisContract) -> None:
        conn.execute(
            """
            INSERT INTO resolution_analyses (
                id, resolution_analysis_run_id, interpretation_id, market_link_candidate_id,
                market_id, market_question, raw_context_json, resolution_summary,
                wording_clarity_score, ambiguity_risk_score, resolution_mismatch_risk,
                resolution_confidence_score, direct_fit_class, usable_now_class,
                explanation_json, status, error_text, analyzer_version, prompt_version, model_name
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                analysis.id,
                analysis.resolution_analysis_run_id,
                analysis.interpretation_id,
                analysis.market_link_candidate_id,
                analysis.market_id,
                analysis.market_question,
                Jsonb(analysis.raw_context_json),
                analysis.resolution_summary,
                analysis.wording_clarity_score,
                analysis.ambiguity_risk_score,
                analysis.resolution_mismatch_risk,
                analysis.resolution_confidence_score,
                analysis.direct_fit_class,
                analysis.usable_now_class,
                Jsonb(analysis.explanation_json),
                analysis.status,
                analysis.error_text,
                analysis.analyzer_version,
                analysis.prompt_version,
                analysis.model_name,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM resolution_analyses
            WHERE resolution_analysis_run_id = %s
            ORDER BY created_at ASC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, analysis_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM resolution_analyses
            WHERE id = %s
            LIMIT 1
            """,
            (analysis_id,),
        ).fetchone()

    def list_for_market(self, conn: Connection, market_id: str, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM resolution_analyses
            WHERE market_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (market_id, limit),
        ).fetchall()

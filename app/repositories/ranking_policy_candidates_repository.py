from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.ranking_policy_candidate import RankingPolicyCandidateContract


class RankingPolicyCandidatesRepository:
    def insert(self, conn: Connection, candidate: RankingPolicyCandidateContract) -> None:
        conn.execute(
            """
            INSERT INTO ranking_policy_candidates (
                id, ranking_policy_run_id, market_id, ranking_v2_candidate_id,
                total_rank_score, rank_position, rank_tier_class,
                gate_decision_class, gate_priority_class, max_selected_within_run,
                selection_reason_codes_json, selection_reason_text,
                policy_explanation_json, policy_version
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s
            )
            """,
            (
                candidate.id,
                candidate.ranking_policy_run_id,
                candidate.market_id,
                candidate.ranking_v2_candidate_id,
                candidate.total_rank_score,
                candidate.rank_position,
                candidate.rank_tier_class,
                candidate.gate_decision_class,
                candidate.gate_priority_class,
                candidate.max_selected_within_run,
                Jsonb(candidate.selection_reason_codes_json),
                candidate.selection_reason_text,
                Jsonb(candidate.policy_explanation_json),
                candidate.policy_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM ranking_policy_candidates
            WHERE ranking_policy_run_id = %s
            ORDER BY rank_position ASC, total_rank_score DESC, created_at DESC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, ranking_policy_candidate_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM ranking_policy_candidates
            WHERE id = %s
            LIMIT 1
            """,
            (ranking_policy_candidate_id,),
        ).fetchone()

    def get_latest_by_market(self, conn: Connection, market_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM ranking_policy_candidates
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()

    def list_selectable(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM ranking_policy_candidates
            WHERE gate_decision_class = 'SELECTABLE'
            ORDER BY
                CASE gate_priority_class
                    WHEN 'PRIMARY' THEN 1
                    WHEN 'SECONDARY' THEN 2
                    ELSE 3
                END ASC,
                total_rank_score DESC,
                created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

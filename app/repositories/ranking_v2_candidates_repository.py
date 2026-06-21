from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.ranking_v2_candidate import RankingV2CandidateContract


class RankingV2CandidatesRepository:
    def insert(self, conn: Connection, candidate: RankingV2CandidateContract) -> None:
        conn.execute(
            """
            INSERT INTO ranking_v2_candidates (
                id, ranking_v2_run_id, market_id, cycle_id, market_snapshot_id,
                decision_id, cognition_summary_id, whale_market_score_id,
                trade_classification_id, bucket_allocation_id, total_rank_score,
                factor_scores_json, rank_position, rank_tier_class,
                rank_reason_codes_json, rank_reason_text, explanation_json,
                ranking_version
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s
            )
            """,
            (
                candidate.id,
                candidate.ranking_v2_run_id,
                candidate.market_id,
                candidate.cycle_id,
                candidate.market_snapshot_id,
                candidate.decision_id,
                candidate.cognition_summary_id,
                candidate.whale_market_score_id,
                candidate.trade_classification_id,
                candidate.bucket_allocation_id,
                candidate.total_rank_score,
                Jsonb(candidate.factor_scores_json),
                candidate.rank_position,
                candidate.rank_tier_class,
                Jsonb(candidate.rank_reason_codes_json),
                candidate.rank_reason_text,
                Jsonb(candidate.explanation_json),
                candidate.ranking_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM ranking_v2_candidates
            WHERE ranking_v2_run_id = %s
            ORDER BY rank_position ASC, total_rank_score DESC, created_at DESC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, ranking_v2_candidate_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM ranking_v2_candidates
            WHERE id = %s
            LIMIT 1
            """,
            (ranking_v2_candidate_id,),
        ).fetchone()

    def get_latest_by_market(self, conn: Connection, market_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM ranking_v2_candidates
            WHERE market_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()

    def list_top_candidates(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM ranking_v2_candidates
            ORDER BY total_rank_score DESC, created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

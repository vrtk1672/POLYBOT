from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.ranking_snapshot import RankingSnapshotContract


class RankingSnapshotsRepository:
    def upsert_many(
        self,
        conn: Connection,
        rankings: list[RankingSnapshotContract],
    ) -> dict[str, int]:
        ids: dict[str, int] = {}
        for ranking in rankings:
            row = conn.execute(
                """
                INSERT INTO ranking_snapshots (
                    cycle_id, market_snapshot_id, market_id, rank_position,
                    base_score, adaptive_rank,
                    selected_flag, eligible_flag, reject_reason, ranking_breakdown,
                    recommendation_action, recommendation_confidence, recommendation_reason
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (cycle_id, market_id) DO UPDATE
                SET market_snapshot_id = EXCLUDED.market_snapshot_id,
                    rank_position = EXCLUDED.rank_position,
                    base_score = EXCLUDED.base_score,
                    adaptive_rank = EXCLUDED.adaptive_rank,
                    selected_flag = EXCLUDED.selected_flag,
                    eligible_flag = EXCLUDED.eligible_flag,
                    reject_reason = EXCLUDED.reject_reason,
                    ranking_breakdown = EXCLUDED.ranking_breakdown,
                    recommendation_action = EXCLUDED.recommendation_action,
                    recommendation_confidence = EXCLUDED.recommendation_confidence,
                    recommendation_reason = EXCLUDED.recommendation_reason
                RETURNING id, market_id
                """,
                (
                    ranking.cycle_id,
                    ranking.market_snapshot_id,
                    ranking.market_id,
                    ranking.rank_position,
                    ranking.base_score,
                    ranking.adaptive_rank,
                    ranking.selected_flag,
                    ranking.eligible_flag,
                    ranking.reject_reason,
                    Jsonb(ranking.ranking_breakdown),
                    ranking.recommendation_action,
                    ranking.recommendation_confidence,
                    ranking.recommendation_reason,
                ),
            ).fetchone()
            ids[str(row["market_id"])] = int(row["id"])
        return ids

    def list_for_cycle(self, conn: Connection, cycle_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM ranking_snapshots
            WHERE cycle_id = %s
            ORDER BY rank_position ASC NULLS LAST, market_id ASC
            """,
            (cycle_id,),
        ).fetchall()

    def get_for_cycle_market(
        self,
        conn: Connection,
        *,
        cycle_id: str,
        market_id: str,
    ) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM ranking_snapshots
            WHERE cycle_id = %s
              AND market_id = %s
            LIMIT 1
            """,
            (cycle_id, market_id),
        ).fetchone()

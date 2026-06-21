from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.whale_market_score import WhaleMarketScoreContract


class WhaleMarketScoresRepository:
    def insert(self, conn: Connection, score: WhaleMarketScoreContract) -> None:
        conn.execute(
            """
            INSERT INTO whale_market_scores (
                id, whale_scoring_run_id, market_id, scoring_window_start, scoring_window_end,
                whale_presence_score, whale_conviction_score, smart_whale_alignment_score,
                whale_reversal_risk, supporting_wallet_count, top_supporting_wallets_json,
                category_mix_json, scoring_reason_codes_json, scoring_reason_text,
                explanation_json, scorer_version
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
            """,
            (
                score.id,
                score.whale_scoring_run_id,
                score.market_id,
                score.scoring_window_start,
                score.scoring_window_end,
                score.whale_presence_score,
                score.whale_conviction_score,
                score.smart_whale_alignment_score,
                score.whale_reversal_risk,
                score.supporting_wallet_count,
                Jsonb(score.top_supporting_wallets_json),
                Jsonb(score.category_mix_json),
                Jsonb(score.scoring_reason_codes_json),
                score.scoring_reason_text,
                Jsonb(score.explanation_json),
                score.scorer_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM whale_market_scores
            WHERE whale_scoring_run_id = %s
            ORDER BY whale_presence_score DESC, whale_conviction_score DESC, created_at DESC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, whale_market_score_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM whale_market_scores
            WHERE id = %s
            LIMIT 1
            """,
            (whale_market_score_id,),
        ).fetchone()

    def get_latest_by_market(self, conn: Connection, market_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM whale_market_scores
            WHERE market_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()

    def list_top_scores(self, conn: Connection, limit: int, order_by: str) -> list[dict[str, object]]:
        allowed = {
            "whale_presence_score",
            "whale_conviction_score",
            "smart_whale_alignment_score",
            "whale_reversal_risk",
        }
        order_column = order_by if order_by in allowed else "whale_presence_score"
        query = f"""
            SELECT *
            FROM whale_market_scores
            ORDER BY {order_column} DESC, created_at DESC
            LIMIT %s
        """
        return conn.execute(query, (limit,)).fetchall()

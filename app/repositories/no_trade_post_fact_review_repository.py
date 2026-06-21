from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.no_trade.contracts import PostFactReview


class NoTradePostFactReviewRepository:
    def insert(self, conn: Connection, review: PostFactReview) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO no_trade_post_fact_review (
                review_id, no_trade_id, market_id, review_time, review_horizon_seconds,
                observed_price_at_decision, observed_price_after,
                observed_max_favorable_move, observed_max_adverse_move,
                would_have_roi, would_have_drawdown, would_have_exit_possible,
                liquidity_after_score, decision_correct, review_status, evidence_json,
                explanation
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                review.review_id,
                review.no_trade_id,
                review.market_id,
                review.review_time,
                review.review_horizon_seconds,
                review.observed_price_at_decision,
                review.observed_price_after,
                review.observed_max_favorable_move,
                review.observed_max_adverse_move,
                review.would_have_roi,
                review.would_have_drawdown,
                review.would_have_exit_possible,
                review.liquidity_after_score,
                review.decision_correct,
                review.review_status,
                Jsonb(review.evidence),
                review.explanation,
            ),
        ).fetchone()

    def by_no_trade_id(self, conn: Connection, no_trade_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM no_trade_post_fact_review WHERE no_trade_id=%s ORDER BY created_at DESC, id DESC", (no_trade_id,)).fetchall()

    def pending(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM no_trade_post_fact_review WHERE review_status='PENDING' ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()


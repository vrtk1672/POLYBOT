from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.learning.contracts import TradeReview
from app.repositories.learning_repository_helpers import recent, row_dict


class TradeReviewRepository:
    def insert(self, conn: Connection, review: TradeReview) -> dict[str, Any]:
        return row_dict(conn.execute(
            """
            INSERT INTO trade_reviews (
                review_id, trade_id, order_id, exit_plan_id, exit_intent_id, market_id,
                market_family, side, engine, strategy_route_id, opportunity_run_id,
                capital_allocation_id, risk_gate_run_id, entry_price, exit_price,
                entry_time, exit_time, hold_seconds, realized_pnl_usd, realized_roi,
                roi_per_hour, max_favorable_excursion, max_adverse_excursion,
                entry_quality_score, exit_quality_score, slippage_accuracy_score,
                signal_accuracy_score, engine_result, review_status, insufficient_data,
                insufficient_data_reasons_json, evidence_json, explanation
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                review.review_id, review.trade_id, review.order_id, review.exit_plan_id,
                review.exit_intent_id, review.market_id, review.market_family, review.side,
                review.engine, review.strategy_route_id, review.opportunity_run_id,
                review.capital_allocation_id, review.risk_gate_run_id, review.entry_price,
                review.exit_price, review.entry_time, review.exit_time, review.hold_seconds,
                review.realized_pnl_usd, review.realized_roi, review.roi_per_hour,
                review.max_favorable_excursion, review.max_adverse_excursion,
                review.entry_quality_score, review.exit_quality_score,
                review.slippage_accuracy_score, review.signal_accuracy_score,
                review.engine_result, review.review_status, review.insufficient_data,
                Jsonb(review.insufficient_data_reasons), Jsonb(review.evidence), review.explanation,
            ),
        ).fetchone())

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return recent(conn, "trade_reviews", limit)

    def by_order_id(self, conn: Connection, order_id: str) -> dict[str, Any] | None:
        return row_dict(conn.execute("SELECT * FROM trade_reviews WHERE order_id=%s ORDER BY created_at DESC LIMIT 1", (order_id,)).fetchone())


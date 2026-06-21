from __future__ import annotations

from typing import Any

from app.no_trade.contracts import NoTradeDecision, PostFactReview


class NoTradePostFactReviewer:
    def review(self, *, decision: NoTradeDecision, evidence: dict[str, Any] | None = None, review_horizon_seconds: int = 0) -> PostFactReview:
        evidence = evidence or {}
        before = evidence.get("observed_price_at_decision", decision.would_have_entry_price)
        after = evidence.get("observed_price_after")
        exit_possible = evidence.get("would_have_exit_possible")
        liquidity = evidence.get("liquidity_after_score")
        if before is None or after is None or exit_possible is None:
            return PostFactReview(
                no_trade_id=decision.no_trade_id,
                market_id=decision.market_id,
                review_horizon_seconds=review_horizon_seconds,
                observed_price_at_decision=before,
                observed_price_after=after,
                would_have_exit_possible=exit_possible,
                liquidity_after_score=liquidity,
                review_status="INSUFFICIENT_DATA",
                evidence=evidence,
                explanation="Post-fact review has insufficient later price/liquidity evidence; regret is not guessed.",
            )
        before_f = float(before)
        after_f = float(after)
        roi = (after_f - before_f) / before_f if before_f > 0 else None
        favorable = evidence.get("observed_max_favorable_move")
        adverse = evidence.get("observed_max_adverse_move")
        drawdown = None if adverse is None or before_f <= 0 else (float(adverse) - before_f) / before_f
        decision_correct = roi is not None and (roi <= 0 or not bool(exit_possible) or float(liquidity or 0) < 0.25)
        return PostFactReview(
            no_trade_id=decision.no_trade_id,
            market_id=decision.market_id,
            review_horizon_seconds=review_horizon_seconds,
            observed_price_at_decision=before_f,
            observed_price_after=after_f,
            observed_max_favorable_move=favorable,
            observed_max_adverse_move=adverse,
            would_have_roi=roi,
            would_have_drawdown=drawdown,
            would_have_exit_possible=bool(exit_possible),
            liquidity_after_score=liquidity,
            decision_correct=decision_correct,
            review_status="REVIEWED",
            evidence=evidence,
            explanation="Post-fact review computed from supplied later market evidence.",
        )

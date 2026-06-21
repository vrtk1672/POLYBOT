from __future__ import annotations

from app.learning.contracts import EngineLearning, TradeReview


class EngineLearningBuilder:
    def build_from_review(self, review: TradeReview) -> EngineLearning:
        engine = review.engine or "UNKNOWN"
        if review.review_status != "REVIEWED":
            signal = "insufficient_data"
            confidence = 0.35
            result = "UNKNOWN"
            delta = 0.0
        elif review.engine_result == "WIN":
            signal = "reward_engine"
            confidence = 0.82
            result = "WIN"
            delta = 0.04
        elif review.engine_result == "LOSS":
            signal = "penalize_engine"
            confidence = 0.9 if engine in {"SAFE", "HUNT"} else 0.78
            result = "LOSS"
            delta = -0.08 if engine in {"SAFE", "HUNT"} else -0.05
        else:
            signal = "keep_engine"
            confidence = 0.62
            result = review.engine_result
            delta = 0.0
        return EngineLearning(
            engine=engine,
            market_family=review.market_family,
            market_id=review.market_id,
            review_id=review.review_id,
            observation_type="trade_review",
            result=result,
            prior_engine_score=None,
            new_engine_score=None,
            win_rate_delta=delta if signal == "reward_engine" else None,
            roi_delta=review.realized_roi,
            slippage_penalty_delta=-0.03 if (review.slippage_accuracy_score is not None and review.slippage_accuracy_score < 0.5) else None,
            adverse_selection_delta=-0.03 if review.max_adverse_excursion and review.max_adverse_excursion < -0.05 else None,
            confidence=confidence,
            learning_signal=signal,
            explanation=f"Engine {engine} learning derived from {review.review_status} trade review.",
        )

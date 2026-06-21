from __future__ import annotations

from app.no_trade.contracts import NoTradeDecision, NoTradeRegretScore, PostFactReview


class NoTradeRegretScorer:
    def score(self, *, decision: NoTradeDecision, review: PostFactReview) -> NoTradeRegretScore:
        hard_block = any(reason.hard_block for reason in decision.reasons)
        if review.review_status != "REVIEWED" or review.would_have_roi is None or review.would_have_exit_possible is None:
            return NoTradeRegretScore(no_trade_id=decision.no_trade_id, market_id=decision.market_id, regret_band="INSUFFICIENT_DATA", learning_signal="improve_data", explanation="Regret not scored because post-fact evidence is insufficient.")
        roi = float(review.would_have_roi)
        liquidity_ok = bool(review.would_have_exit_possible) and float(review.liquidity_after_score or 0) >= 0.25
        avoided_loss = max(0.0, -roi)
        missed_upside = max(0.0, roi)
        avoided_risk = 0.6 if hard_block else 0.0
        if hard_block and missed_upside > 0:
            band = "NEUTRAL"
            regret = min(0.45, missed_upside * 0.5)
            learning = "keep_filter"
            explanation = "Favorable move occurred, but original no-trade was a hard safety block."
        elif missed_upside > 0.2 and liquidity_ok:
            band = "HIGH_REGRET"
            regret = min(1.0, missed_upside)
            learning = "loosen_filter"
            explanation = "No-trade missed a favorable move with plausible exit liquidity."
        elif missed_upside > 0.05 and liquidity_ok:
            band = "MILD_REGRET"
            regret = min(0.6, missed_upside)
            learning = "loosen_filter"
            explanation = "No-trade missed some upside with plausible exit liquidity."
        elif avoided_loss > 0 or not liquidity_ok:
            band = "GOOD_NO_TRADE"
            regret = 0.0
            learning = "keep_filter" if liquidity_ok else "improve_liquidity_model"
            explanation = "No-trade avoided loss or protected against poor exit liquidity."
        else:
            band = "NEUTRAL"
            regret = 0.1
            learning = "keep_filter"
            explanation = "Post-fact result was neutral."
        confidence = min(1.0, float(decision.data_confidence) * 0.5 + 0.5)
        return NoTradeRegretScore(
            no_trade_id=decision.no_trade_id,
            market_id=decision.market_id,
            regret_score=regret,
            regret_band=band,
            missed_upside_score=min(1.0, missed_upside),
            avoided_loss_score=min(1.0, avoided_loss),
            avoided_risk_score=avoided_risk,
            liquidity_regret_score=0.0 if liquidity_ok else 0.8,
            confidence=confidence,
            learning_signal=learning,
            update_memory=confidence >= 0.6 and band != "INSUFFICIENT_DATA",
            explanation=explanation,
        )

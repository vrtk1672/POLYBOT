from app.no_trade.candidate_tracker import NoTradeCandidateTracker
from app.no_trade.post_fact_reviewer import NoTradePostFactReviewer
from app.no_trade.regret_scorer import NoTradeRegretScorer
from test_v2_17_fixtures import favorable_evidence, no_trade_payload


def test_high_regret_requires_favorable_move_and_liquidity():
    decision = NoTradeCandidateTracker().build_decision(no_trade_payload(primary_reason="low_edge", reasons=["low_edge"]))
    review = NoTradePostFactReviewer().review(decision=decision, evidence=favorable_evidence())
    regret = NoTradeRegretScorer().score(decision=decision, review=review)
    assert regret.regret_band == "HIGH_REGRET"


def test_hard_risk_block_prevents_naive_high_regret():
    decision = NoTradeCandidateTracker().build_decision(no_trade_payload(primary_reason="high_wording_risk", reasons=["high_wording_risk"]))
    review = NoTradePostFactReviewer().review(decision=decision, evidence=favorable_evidence())
    regret = NoTradeRegretScorer().score(decision=decision, review=review)
    assert regret.regret_band != "HIGH_REGRET"


def test_good_no_trade_detected_when_drawdown_avoided():
    decision = NoTradeCandidateTracker().build_decision(no_trade_payload(primary_reason="low_edge", reasons=["low_edge"]))
    review = NoTradePostFactReviewer().review(decision=decision, evidence=favorable_evidence(observed_price_after=0.4, observed_max_adverse_move=0.35))
    regret = NoTradeRegretScorer().score(decision=decision, review=review)
    assert regret.regret_band == "GOOD_NO_TRADE"


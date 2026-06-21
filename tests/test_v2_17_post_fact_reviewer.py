from app.no_trade.candidate_tracker import NoTradeCandidateTracker
from app.no_trade.post_fact_reviewer import NoTradePostFactReviewer
from test_v2_17_fixtures import favorable_evidence, no_trade_payload


def test_post_fact_review_with_no_later_data_is_insufficient():
    decision = NoTradeCandidateTracker().build_decision(no_trade_payload())
    review = NoTradePostFactReviewer().review(decision=decision, evidence={})
    assert review.review_status == "INSUFFICIENT_DATA"
    assert review.decision_correct is None


def test_post_fact_review_computes_roi_when_evidence_exists():
    decision = NoTradeCandidateTracker().build_decision(no_trade_payload())
    review = NoTradePostFactReviewer().review(decision=decision, evidence=favorable_evidence())
    assert review.review_status == "REVIEWED"
    assert review.would_have_roi == 0.5


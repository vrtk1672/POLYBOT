from app.learning.trade_reviewer import TradeReviewer
from test_v2_19_fixtures import completed_trade_payload, incomplete_trade_payload


def test_closed_trade_reviewed():
    review = TradeReviewer().review(completed_trade_payload())
    assert review.review_status == "REVIEWED"
    assert review.engine_result == "WIN"
    assert review.realized_pnl_usd and review.realized_pnl_usd > 0


def test_incomplete_trade_becomes_pending_or_insufficient_data():
    review = TradeReviewer().review(incomplete_trade_payload())
    assert review.review_status in {"PENDING", "INSUFFICIENT_DATA"}
    assert review.insufficient_data is True

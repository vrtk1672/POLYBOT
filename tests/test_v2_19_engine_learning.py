from app.learning.engine_learning_builder import EngineLearningBuilder
from app.learning.trade_reviewer import TradeReviewer
from test_v2_19_fixtures import completed_trade_payload


def test_good_engine_rewarded():
    review = TradeReviewer().review(completed_trade_payload(engine="SAFE"))
    learning = EngineLearningBuilder().build_from_review(review)
    assert learning.learning_signal == "reward_engine"


def test_bad_engine_penalized():
    review = TradeReviewer().review(completed_trade_payload(engine="HUNT", entry_price=0.57, exit_price=0.42))
    learning = EngineLearningBuilder().build_from_review(review)
    assert learning.learning_signal == "penalize_engine"
    assert learning.confidence >= 0.9

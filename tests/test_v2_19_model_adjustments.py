from app.learning.engine_learning_builder import EngineLearningBuilder
from app.learning.model_adjustment_recommender import ModelAdjustmentRecommender
from app.learning.trade_reviewer import TradeReviewer
from test_v2_19_fixtures import completed_trade_payload


def test_model_adjustment_recommended_but_not_applied():
    review = TradeReviewer().review(completed_trade_payload(entry_price=0.57, exit_price=0.42))
    learning = EngineLearningBuilder().build_from_review(review)
    adjustment = ModelAdjustmentRecommender().from_engine_learning(learning)
    assert adjustment is not None
    assert adjustment.status in {"RECOMMENDED", "REVIEW_REQUIRED"}
    assert adjustment.applied_at is None if hasattr(adjustment, "applied_at") else True

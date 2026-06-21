from app.learning.source_learning_builder import SourceLearningBuilder


def test_good_source_rewarded():
    item = SourceLearningBuilder().build({"source_type": "news", "usefulness_score": 0.8, "prior_reliability": 0.5})
    assert item.learning_signal == "reward_source"
    assert item.new_reliability > item.prior_reliability


def test_stale_false_source_penalized():
    item = SourceLearningBuilder().build({"source_type": "social", "stale": True, "prior_reliability": 0.7})
    assert item.learning_signal == "penalize_source"

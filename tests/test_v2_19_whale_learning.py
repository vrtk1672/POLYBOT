from app.learning.whale_learning_builder import WhaleLearningBuilder


def test_whale_reliability_updated_from_evidence():
    item = WhaleLearningBuilder().build({"whale_id": "wallet_1", "hit": True, "prior_follow_value": 0.4, "prior_noise_score": 0.4})
    assert item.learning_signal == "reward_whale"
    assert item.new_follow_value > item.prior_follow_value


def test_noisy_whale_penalized():
    item = WhaleLearningBuilder().build({"whale_id": "wallet_1", "noisy": True, "prior_follow_value": 0.4})
    assert item.learning_signal == "penalize_whale"

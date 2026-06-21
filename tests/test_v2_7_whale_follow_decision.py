from app.whale_neuron.follow_decision import WhaleFollowDecisionLogger
from app.whale_neuron.contracts import WhaleProfile


def test_follow_decision_logger_persists_decision_contract_without_db():
    logger = WhaleFollowDecisionLogger()
    decision = logger.compute_follow_value(WhaleProfile(whale_id="w", sample_size=0, noise_score=0.5))
    row = logger.persist_follow_decision(decision)
    assert row["decision"] == "INSUFFICIENT_DATA"
    assert row["follow_value"] <= 0.45


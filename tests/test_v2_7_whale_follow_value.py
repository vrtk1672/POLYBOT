from app.whale_neuron.contracts import WhaleEvent, WhaleFollowDecisionValue, WhaleProfile
from app.whale_neuron.follow_value import WhaleFollowValueScorer


def test_follow_value_requires_evidence_and_penalizes_noise():
    scorer = WhaleFollowValueScorer()
    good = WhaleProfile(whale_id="good", sample_size=8, timing_quality=0.9, hit_rate=0.8, noise_score=0.1, follow_value=0.8, copy_worthy_score=0.8, confidence=0.8)
    unknown = WhaleProfile(whale_id="unknown", sample_size=1, follow_value=0.9)
    noisy = WhaleProfile(whale_id="bad", sample_size=8, noise_score=0.9, follow_value=0.8)
    assert scorer.compute_follow_value(good).decision == WhaleFollowDecisionValue.FOLLOW
    assert scorer.compute_follow_value(unknown, WhaleEvent(source_id="manual", size_usd=12000)).decision != WhaleFollowDecisionValue.FOLLOW
    assert scorer.compute_follow_value(noisy).decision == WhaleFollowDecisionValue.PENALIZE


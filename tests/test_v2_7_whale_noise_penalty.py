from app.whale_neuron.contracts import WhaleEventClassification, WhaleProfile
from app.whale_neuron.noise_penalty import WhaleNoisePenalty


class E:
    def __init__(self, classification, action="BUY"):
        self.event_classification = classification
        self.action_type = action


def test_noise_penalty_scores_bad_and_specialist_cases():
    scorer = WhaleNoisePenalty()
    noisy = WhaleProfile(whale_id="w", sample_size=10, noise_score=0.8)
    specialist = WhaleProfile(whale_id="w", sample_size=10, market_specialties=["sports"], win_consistency=0.9)
    assert scorer.compute_noise_score(noisy) >= 0.8
    assert scorer.compute_late_chase_penalty([E(WhaleEventClassification.LATE_CHASE), E(WhaleEventClassification.ENTRY)]) == 0.5
    assert scorer.compute_market_family_noise(specialist) < 0.3
    assert 0 <= scorer.apply_noise_penalty_to_score(1.0, 0.9) <= 1


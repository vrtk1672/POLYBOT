from app.whale_neuron.contracts import WhaleActionType, WhaleEvent, WhaleProfile
from app.whale_neuron.market_score import WhaleMarketScorer


def test_market_score_boosts_good_and_penalizes_bad_context():
    scorer = WhaleMarketScorer()
    event = WhaleEvent(source_id="manual", whale_id="w", market_id="m", action_type=WhaleActionType.BUY, size_usd=20000, confidence=0.9)
    profile = WhaleProfile(whale_id="w", sample_size=8, timing_quality=0.9, follow_value=0.8, copy_worthy_score=0.8, noise_score=0.1, confidence=0.8)
    blocked = scorer.score_whale_for_market(event, profile, {"market_known": True, "compliance_blocked": True})
    score = scorer.score_whale_for_market(event, profile, {"market_known": True})
    dump = scorer.score_whale_for_market(WhaleEvent(source_id="manual", whale_id="w", market_id="m", action_type=WhaleActionType.SELL, size_usd=20000), profile, {"market_known": True})
    assert score and score.follow_value > blocked.follow_value
    assert dump and dump.whale_reversal_risk > 0.5
    assert score.signal["node"] == "whale"


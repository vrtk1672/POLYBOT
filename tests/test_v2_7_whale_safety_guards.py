from app.whale_neuron.contracts import WhaleEvent, WhaleProfile
from app.whale_neuron.follow_value import WhaleFollowValueScorer
from app.whale_neuron.market_score import WhaleMarketScorer


def test_whale_safety_guards_no_orders_or_exits():
    event = WhaleEvent(source_id="manual", whale_id="unknown", market_id="m", action_type="SELL", size_usd=50000)
    profile = WhaleProfile(whale_id="unknown", sample_size=1, follow_value=1.0, noise_score=0.2)
    score = WhaleMarketScorer().score_whale_for_market(event, profile, {"market_known": True, "compliance_blocked": True})
    decision = WhaleFollowValueScorer().compute_follow_value(profile, event, score)
    text = str(score.model_dump()) + str(decision.model_dump())
    assert decision.decision != "FOLLOW"
    assert score.confidence < 0.6
    assert "order_intent" not in text and "exit_intent" not in text and "create_order" not in text


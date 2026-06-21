import pytest

from app.whale_neuron.contracts import WhaleEvent, WhaleProfile, WhaleSignal, WhaleSide, WhaleSource, WhaleSourceType


def test_whale_contracts_validate_and_bound_scores():
    source = WhaleSource(source_id="manual", name="Manual", source_type=WhaleSourceType.MANUAL, reliability_score=4)
    event = WhaleEvent(source_id="manual", side=WhaleSide.YES, action_type="BUY", size_usd=12000, confidence=9)
    profile = WhaleProfile(whale_id="w1", timing_quality=2, noise_score=-1, follow_value=5)
    signal = WhaleSignal(market_id="m1", whale_id="w1", side=WhaleSide.YES, size_usd=12000, follow_value=2, noise_score=-1, timing_quality=3)
    assert source.reliability_score == 1
    assert event.size_usd == 12000
    assert profile.follow_value == 1
    assert signal.model_dump()["node"] == "whale"
    assert not {"order_id_to_create", "execute", "order_intent"}.intersection(signal.model_dump())


def test_invalid_side_rejected():
    with pytest.raises(Exception):
        WhaleSignal(market_id="m1", whale_id="w1", side="MAYBE")


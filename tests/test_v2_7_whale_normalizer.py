from app.whale_neuron.contracts import WhaleActionType, WhaleSide
from app.whale_neuron.normalizer import WhaleEventNormalizer


def test_normalizer_handles_raw_and_malformed_events():
    normalizer = WhaleEventNormalizer()
    event = normalizer.normalize_raw_event({"source_id": "manual", "wallet_address": "0xabc", "side": "yes", "action_type": "buy", "size_usd": 12000, "price": 0.42})
    malformed = normalizer.normalize_raw_event({"source_id": "manual", "side": "wat", "action_type": "wat"})
    assert event.whale_id == "0xabc"
    assert event.side == WhaleSide.YES
    assert event.action_type == WhaleActionType.BUY
    assert event.notional == 12000
    assert malformed.side == WhaleSide.UNKNOWN


from app.whale_neuron.contracts import WhaleActionType, WhaleEvent, WhaleEventClassification
from app.whale_neuron.event_classifier import WhaleEventClassifier


def test_event_classifier_core_cases():
    classifier = WhaleEventClassifier()
    large_buy = WhaleEvent(source_id="manual", action_type=WhaleActionType.BUY, size_usd=15000)
    sell = WhaleEvent(source_id="manual", action_type=WhaleActionType.SELL, size_usd=12000)
    late = WhaleEvent(source_id="manual", action_type=WhaleActionType.BUY, size_usd=8000)
    unknown = WhaleEvent(source_id="manual")
    assert classifier.classify_event(large_buy)[0] in {WhaleEventClassification.ENTRY, WhaleEventClassification.MARKET_MOVER}
    assert classifier.classify_event(sell)[0] in {WhaleEventClassification.EXIT, WhaleEventClassification.DISTRIBUTION}
    assert classifier.classify_event(late, {"recent_price_move": 0.2})[0] == WhaleEventClassification.LATE_CHASE
    assert classifier.classify_event(unknown)[0] == WhaleEventClassification.UNKNOWN
    assert 0 <= classifier.classify_event(large_buy)[1] <= 1


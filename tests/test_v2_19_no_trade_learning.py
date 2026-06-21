from app.learning.no_trade_learning_builder import NoTradeLearningBuilder


def test_high_regret_creates_loosen_filter_or_improve_data():
    learning = NoTradeLearningBuilder().build(
        {"no_trade_id": "nt1", "market_id": "m1", "candidate_engine": "STRIKE", "primary_reason": "low_edge"},
        {"no_trade_id": "nt1", "market_id": "m1", "regret_band": "HIGH_REGRET", "regret_score": 0.9, "confidence": 0.8},
    )
    assert learning.learning_signal in {"loosen_filter", "improve_data"}


def test_good_no_trade_creates_keep_filter():
    learning = NoTradeLearningBuilder().build(
        {"no_trade_id": "nt1", "market_id": "m1"},
        {"no_trade_id": "nt1", "market_id": "m1", "regret_band": "GOOD_NO_TRADE", "confidence": 0.8},
    )
    assert learning.learning_signal == "keep_filter"

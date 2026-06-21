from app.learning.signal_performance_analyzer import SignalPerformanceAnalyzer


def test_good_signal_rewarded():
    item = SignalPerformanceAnalyzer().analyze({"source_type": "technical", "signal_type": "momentum", "direction": "UP", "observed_move": 0.1, "predicted_strength": 0.1})
    assert item.accuracy_score > 0.7
    assert item.false_positive is False


def test_bad_signal_false_positive():
    item = SignalPerformanceAnalyzer().analyze({"source_type": "social", "signal_type": "hype", "direction": "UP", "observed_move": -0.1, "predicted_strength": 0.2})
    assert item.false_positive is True
    assert item.accuracy_score < 0.5

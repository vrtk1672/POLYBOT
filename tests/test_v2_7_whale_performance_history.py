from app.whale_neuron.performance_history import WhalePerformanceHistory


def test_performance_history_handles_insufficient_data():
    history = WhalePerformanceHistory()
    assert history.evaluate_whale_market_outcome("w", "m")["follow_result"] == "INSUFFICIENT_DATA"
    record = {"whale_performance_id": "p1", "whale_id": "w", "follow_result": "GOOD_FOLLOW", "timing_quality": 0.8}
    assert history.record_performance(record)["follow_result"] == "GOOD_FOLLOW"


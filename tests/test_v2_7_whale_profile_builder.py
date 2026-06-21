from app.whale_neuron.profile_builder import WhaleProfileBuilder


def test_profile_builder_computes_history_proxies():
    builder = WhaleProfileBuilder()
    perf = [{"follow_result": "GOOD_FOLLOW", "timing_quality": 0.8}, {"follow_result": "BAD_FOLLOW", "timing_quality": 0.2}]
    events = [{"size_usd": 10000, "event_classification": "LATE_CHASE", "metadata_json": {"market_family": "sports"}}]
    assert builder.compute_hit_rate(perf) == 0.5
    assert builder.compute_timing_quality(perf) == 0.5
    assert builder.compute_average_trade_size(events) == 10000
    assert builder.compute_market_specialties(events) == ["sports"]


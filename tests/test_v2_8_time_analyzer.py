from datetime import UTC, datetime, timedelta

from app.market_neuron.time_analyzer import TimeAnalyzer


def test_time_analyzer_computes_time_pressure_and_roi_reference():
    signal = TimeAnalyzer().analyze("m1", market_close_time=datetime.now(UTC) + timedelta(hours=2))
    assert signal.time_to_close_seconds is not None
    assert signal.urgency_score > 0
    assert signal.roi_per_hour_reference is not None


def test_short_ttl_increases_urgency():
    short = TimeAnalyzer().analyze("m1", market_close_time=datetime.now(UTC) + timedelta(minutes=10))
    long = TimeAnalyzer().analyze("m1", market_close_time=datetime.now(UTC) + timedelta(days=7))
    assert short.urgency_score > long.urgency_score
    assert short.ttl_bucket == "short"


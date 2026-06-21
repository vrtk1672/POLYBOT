from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.news_neuron.priced_in_detector import AlreadyPricedInDetector


def test_price_movement_before_news_scores_high() -> None:
    now = datetime.now(UTC)
    score = AlreadyPricedInDetector().detect_already_priced_in(
        {"event_time": now},
        "m1",
        snapshots=[
            {"snapshot_at": now - timedelta(minutes=3), "current_price_yes": 0.4},
            {"snapshot_at": now - timedelta(minutes=1), "current_price_yes": 0.55},
            {"snapshot_at": now + timedelta(minutes=1), "current_price_yes": 0.56},
        ],
    )
    assert score["score"] >= 0.8


def test_missing_snapshots_handled_honestly_and_no_move_low() -> None:
    now = datetime.now(UTC)
    detector = AlreadyPricedInDetector()
    assert detector.detect_already_priced_in({"event_time": now}, "m1", snapshots=[])["risk_flags"] == ["missing_price_history"]
    low = detector.detect_already_priced_in(
        {"event_time": now},
        "m1",
        snapshots=[
            {"snapshot_at": now - timedelta(minutes=2), "current_price_yes": 0.5},
            {"snapshot_at": now - timedelta(minutes=1), "current_price_yes": 0.51},
            {"snapshot_at": now + timedelta(minutes=1), "current_price_yes": 0.51},
        ],
    )
    assert low["score"] <= 0.2


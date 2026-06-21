from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter


def _raw_book() -> dict[str, object]:
    return {
        "bids": [{"price": "0.48", "size": "100"}, {"price": "0.49", "size": "200"}],
        "asks": [{"price": "0.51", "size": "150"}, {"price": "0.53", "size": "300"}],
    }


def test_normalizer_computes_best_bid_ask_spread_and_mid_price() -> None:
    snapshot = OrderbookSnapshotter().normalize_orderbook(_raw_book(), market_id="m1", token_id="t1")

    assert snapshot.best_bid == 0.49
    assert snapshot.best_ask == 0.51
    assert round(snapshot.spread or 0, 2) == 0.02
    assert snapshot.mid_price == 0.5
    assert snapshot.snapshot_status == "OK"


def test_normalizer_computes_directional_depth_bands() -> None:
    snapshot = OrderbookSnapshotter().normalize_orderbook(_raw_book(), market_id="m1")

    assert snapshot.depth_bid_1c == 300
    assert snapshot.depth_ask_1c == 150
    assert snapshot.depth_bid_2c == 300
    assert snapshot.depth_ask_2c == 450
    assert snapshot.depth_bid_5c == 300
    assert snapshot.depth_ask_5c == 450
    assert snapshot.total_bid_depth == 300
    assert snapshot.total_ask_depth == 450


def test_empty_orderbook_becomes_empty_not_ok() -> None:
    snapshot = OrderbookSnapshotter().normalize_orderbook({"bids": [], "asks": []}, market_id="m1")

    assert snapshot.snapshot_status == "EMPTY"
    assert snapshot.is_stale is True
    assert snapshot.best_bid is None
    assert snapshot.best_ask is None


def test_missing_bid_or_ask_becomes_partial() -> None:
    snapshot = OrderbookSnapshotter().normalize_orderbook({"bids": [{"price": "0.49", "size": "10"}], "asks": []}, market_id="m1")

    assert snapshot.snapshot_status == "PARTIAL"
    assert snapshot.is_stale is True
    assert snapshot.stale_reason == "missing_bid_or_ask"


def test_old_snapshot_becomes_stale() -> None:
    snapshot = OrderbookSnapshotter().normalize_orderbook(
        _raw_book(),
        market_id="m1",
        collected_at=datetime.now(UTC) - timedelta(seconds=300),
        freshness_window_seconds=120,
    )

    assert snapshot.snapshot_status == "STALE"
    assert snapshot.is_stale is True


def test_liquidity_score_is_deterministic_and_clamped() -> None:
    first = OrderbookSnapshotter().normalize_orderbook(_raw_book(), market_id="m1").liquidity_score
    second = OrderbookSnapshotter().normalize_orderbook(_raw_book(), market_id="m1").liquidity_score

    assert first == second
    assert 0 <= (first or 0) <= 1

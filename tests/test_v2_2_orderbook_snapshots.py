from __future__ import annotations

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_orderbook_best_bid_ask_spread_and_depth() -> None:
    raw = {
        "bids": [{"price": "0.48", "size": "100"}, {"price": "0.49", "size": "200"}],
        "asks": [{"price": "0.51", "size": "150"}, {"price": "0.53", "size": "300"}],
    }
    snapshot = OrderbookSnapshotter().normalize_orderbook(raw, market_id="m1", token_id="t1")
    assert snapshot.best_bid == 0.49
    assert snapshot.best_ask == 0.51
    assert round(snapshot.spread, 2) == 0.02
    assert snapshot.depth_1c == 350
    assert snapshot.depth_2c == 450
    assert snapshot.depth_5c == 750


def test_empty_orderbook_handled_safely() -> None:
    snapshot = OrderbookSnapshotter().normalize_orderbook({"bids": [], "asks": []}, market_id="m1")
    assert snapshot.best_bid is None
    assert snapshot.best_ask is None
    assert snapshot.depth_2c == 0


def test_malformed_orderbook_does_not_crash() -> None:
    snapshot = OrderbookSnapshotter().normalize_orderbook({"bids": [{"bad": "x"}], "asks": "oops"}, market_id="m1")
    assert snapshot.bid_depth_json == []
    assert snapshot.ask_depth_json == []


def test_orderbook_snapshot_saved(postgres_test_schema) -> None:
    run_migrations()
    snapshotter = OrderbookSnapshotter()
    snapshot = snapshotter.normalize_orderbook({"bids": [[0.49, 100]], "asks": [[0.51, 100]]}, market_id="m1")
    snapshotter.persist_orderbook_snapshot(snapshot)
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM orderbook_snapshots WHERE orderbook_snapshot_id = %s", (snapshot.orderbook_snapshot_id,)).fetchone()
    assert row is not None

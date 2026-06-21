from __future__ import annotations

from app.data_foundation.contracts import OrderbookSnapshot
from app.data_foundation.liquidity_profiler import LiquidityProfiler
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _book(spread: float = 0.01, depth: float = 1000, imbalance: float = 0.0) -> OrderbookSnapshot:
    return OrderbookSnapshot(
        orderbook_snapshot_id="ob1",
        market_id="m1",
        spread=spread,
        depth_1c=depth / 2,
        depth_2c=depth,
        depth_5c=depth * 2,
        imbalance=imbalance,
    )


def test_good_orderbook_gives_high_liquidity_score() -> None:
    assert LiquidityProfiler().compute_liquidity_score(_book()) > 80


def test_wide_spread_lowers_liquidity_score() -> None:
    assert LiquidityProfiler().compute_liquidity_score(_book(spread=0.09, depth=1000)) < 65


def test_one_sided_book_lowers_exit_quality() -> None:
    assert LiquidityProfiler().compute_exit_quality(_book(imbalance=0.95)) < 60


def test_missing_book_low_score() -> None:
    snapshot = LiquidityProfiler().build_liquidity_snapshot("m1", None)
    assert snapshot.liquidity_score == 0
    assert snapshot.max_safe_size == 0


def test_max_safe_size_computed() -> None:
    assert LiquidityProfiler().estimate_max_safe_size(_book(depth=800)) == 200


def test_liquidity_snapshot_saved(postgres_test_schema) -> None:
    run_migrations()
    profiler = LiquidityProfiler()
    snapshot = profiler.build_liquidity_snapshot("m1", _book())
    profiler.persist_liquidity_snapshot(snapshot)
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM liquidity_snapshots WHERE liquidity_snapshot_id = %s", (snapshot.liquidity_snapshot_id,)).fetchone()
    assert row is not None

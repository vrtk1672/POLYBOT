from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data_foundation.market_snapshotter_v2 import MarketSnapshotterV2
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.models.market import NormalizedMarket


def _market(updated_at=None):
    return NormalizedMarket(
        market_id="m1",
        event_id="e1",
        event_title="Event",
        question="Question?",
        yes_price=0.5,
        no_price=0.5,
        best_bid=0.49,
        best_ask=0.51,
        spread=0.02,
        liquidity=100,
        volume_24h=10,
        accepting_orders=True,
        end_time=datetime.now(UTC) + timedelta(hours=1),
        updated_at=updated_at or datetime.now(UTC),
        raw_market={"clobTokenIds": ["yes", "no"]},
    )


def test_snapshot_append_latest_and_event(postgres_test_schema) -> None:
    run_migrations()
    snapshotter = MarketSnapshotterV2()
    snapshot = snapshotter.build_snapshot_from_market(_market(), rules={"rules_text": "x"}, liquidity={"liquidity_score": 1})
    snapshotter.persist_snapshot(snapshot)
    latest = snapshotter.get_latest_snapshot("m1")
    assert latest["snapshot_id"] == snapshot.snapshot_id
    assert latest["data_completeness_score"] > 0
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT event_type FROM event_log WHERE event_type='market.snapshot.created'").fetchone()
    assert row is not None


def test_stale_snapshot_flagged(postgres_test_schema) -> None:
    run_migrations()
    snapshotter = MarketSnapshotterV2()
    snapshot = snapshotter.build_snapshot_from_market(_market(updated_at=datetime.now(UTC) - timedelta(minutes=10)))
    assert snapshot.stale is True

from __future__ import annotations

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository


def test_repository_persists_snapshot_and_recent_query_latest_first(postgres_test_schema) -> None:
    run_migrations()
    repository = OrderbookSnapshotRepository()
    snapshotter = OrderbookSnapshotter()
    first = snapshotter.normalize_orderbook({"bids": [[0.48, 50]], "asks": [[0.52, 50]]}, market_id="m1", token_id="t1", source="test")
    second = snapshotter.normalize_orderbook({"bids": [[0.49, 100]], "asks": [[0.51, 100]]}, market_id="m1", token_id="t1", source="test")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        repository.append_snapshot(conn, first)
        repository.append_snapshot(conn, second)
        rows = repository.list_recent(conn, limit=10, market_id="m1")

    assert len(rows) == 2
    assert rows[0]["orderbook_snapshot_id"] == second.orderbook_snapshot_id
    assert rows[0]["snapshot_status"] == "OK"
    assert float(rows[0]["liquidity_score"]) >= 0

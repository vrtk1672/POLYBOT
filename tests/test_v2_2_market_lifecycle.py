from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data_foundation.market_lifecycle_tracker import MarketLifecycleTracker
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_discovered_closed_stale_reactivated_and_no_duplicate(postgres_test_schema) -> None:
    run_migrations()
    tracker = MarketLifecycleTracker()
    row = tracker.persist_lifecycle_event("m1", "DISCOVERED", new_status="OPEN")
    assert row["event_type"] == "DISCOVERED"
    tracker.persist_lifecycle_event("m1", "CLOSED", previous_status="OPEN", new_status="CLOSED")
    tracker.mark_stale_if_needed({"market_id": "m2", "last_seen_at": datetime.now(UTC) - timedelta(minutes=10), "active": True})
    tracker.persist_lifecycle_event("m2", "REACTIVATED", previous_status="STALE", new_status="OPEN")
    tracker.persist_lifecycle_event("m2", "REACTIVATED", previous_status="STALE", new_status="OPEN")
    with DatabaseConnectionFactory().connect() as conn:
        closed = conn.execute("SELECT 1 FROM market_lifecycle_events WHERE event_type='CLOSED'").fetchone()
        stale = conn.execute("SELECT 1 FROM market_lifecycle_events WHERE event_type='STALE'").fetchone()
        reactivated_count = conn.execute("SELECT COUNT(*) AS count FROM market_lifecycle_events WHERE event_type='REACTIVATED'").fetchone()["count"]
    assert closed is not None
    assert stale is not None
    assert reactivated_count == 1

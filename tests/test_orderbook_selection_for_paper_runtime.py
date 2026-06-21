from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.last_mile_orderbook_refresh import latest_matching_orderbook


def test_fresh_matching_snapshot_preferred_over_stale_snapshot(postgres_test_schema) -> None:
    _prepare()
    now = datetime.now(UTC)
    _insert_book("stale", "market-a", "token-yes", "YES", now - timedelta(minutes=15))
    _insert_book("fresh", "market-a", "token-yes", "YES", now - timedelta(seconds=10))

    with DatabaseConnectionFactory().connect() as conn:
        row = latest_matching_orderbook(conn, market_id="market-a", token_id="token-yes", side="YES")

    assert row is not None
    assert row["orderbook_snapshot_id"] == "fresh"


def test_wrong_token_snapshot_is_rejected(postgres_test_schema) -> None:
    _prepare()
    now = datetime.now(UTC)
    _insert_book("wrong-token", "market-a", "other-token", "YES", now - timedelta(seconds=10))

    with DatabaseConnectionFactory().connect() as conn:
        row = latest_matching_orderbook(conn, market_id="market-a", token_id="token-yes", side="YES")

    assert row is None


def test_wrong_market_snapshot_is_rejected(postgres_test_schema) -> None:
    _prepare()
    now = datetime.now(UTC)
    _insert_book("wrong-market", "other-market", "token-yes", "YES", now - timedelta(seconds=10))

    with DatabaseConnectionFactory().connect() as conn:
        row = latest_matching_orderbook(conn, market_id="market-a", token_id="token-yes", side="YES")

    assert row is None


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        if _table_exists(conn, "orderbook_snapshots"):
            conn.execute("DELETE FROM orderbook_snapshots")


def _insert_book(snapshot_id: str, market_id: str, token_id: str, side: str, ts: datetime) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid,
                best_ask, spread, mid_price, liquidity_score, source,
                snapshot_status, is_stale, snapshot_at, collected_at, created_at
            )
            VALUES (%s,%s,%s,%s,0.48,0.52,0.04,0.50,0.6,'test',
                    'OK',false,%s,%s,%s)
            """,
            (snapshot_id, market_id, token_id, side, ts, ts, ts),
        )


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])

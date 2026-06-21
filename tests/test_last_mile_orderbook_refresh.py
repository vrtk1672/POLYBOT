from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.last_mile_orderbook_refresh import (
    LastMileOrderbookRefreshService,
    latest_matching_orderbook,
)


class _BookHttp:
    def __init__(self, payload=None, exc: Exception | None = None) -> None:
        self.payload = payload
        self.exc = exc
        self.calls = 0

    def get_json(self, url: str, *, params=None):
        self.calls += 1
        if self.exc:
            raise self.exc
        payload = dict(self.payload or {})
        payload.setdefault("asset_id", (params or {}).get("token_id"))
        payload.setdefault("market", "condition-a")
        payload.setdefault("bids", [{"price": "0.49", "size": "120"}])
        payload.setdefault("asks", [{"price": "0.52", "size": "110"}])
        return payload, 12


def test_successful_last_mile_refresh_persists_fresh_exact_snapshot(postgres_test_schema) -> None:
    _prepare()
    _insert_stale_snapshot("market-a", "condition-a", "token-yes", "YES")
    service = LastMileOrderbookRefreshService(http_client=_BookHttp())

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = service.ensure_fresh(
            conn,
            decision_id="decision-a",
            source_review_id="review-a",
            market_id="market-a",
            condition_id="condition-a",
            token_id="token-yes",
            side="YES",
            ttl_seconds=180,
            force=True,
        )

    assert result["refresh_state"] == "REFRESHED_FRESH"
    assert result["stale_cleared"] is True
    with DatabaseConnectionFactory().connect() as conn:
        latest = latest_matching_orderbook(conn, market_id="market-a", token_id="token-yes", side="YES")
    assert latest is not None
    assert latest["token_id"] == "token-yes"
    assert latest["side"] == "YES"


def test_failed_last_mile_refresh_records_exact_connector_reason(postgres_test_schema) -> None:
    _prepare()
    _insert_stale_snapshot("market-a", "condition-a", "token-yes", "YES")
    service = LastMileOrderbookRefreshService(http_client=_BookHttp(exc=RuntimeError("network down")))

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = service.ensure_fresh(
            conn,
            decision_id="decision-a",
            source_review_id="review-a",
            market_id="market-a",
            condition_id="condition-a",
            token_id="token-yes",
            side="YES",
            ttl_seconds=180,
            force=True,
        )

    assert result["refresh_state"] == "FAILED"
    assert result["refresh_error"] == "ORDERBOOK_CONNECTOR_ERROR"
    assert result["stale_cleared"] is False


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in ("last_mile_orderbook_refresh_attempts", "orderbook_snapshots"):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _insert_stale_snapshot(market_id: str, condition_id: str, token_id: str, side: str) -> None:
    old = datetime.now(UTC) - timedelta(minutes=20)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid,
                best_ask, spread, mid_price, liquidity_score, source,
                snapshot_status, is_stale, snapshot_at, collected_at, created_at,
                metadata_json
            )
            VALUES (%s,%s,%s,%s,0.48,0.52,0.04,0.50,0.6,'test',
                    'OK',false,%s,%s,%s,%s)
            """,
            (f"stale-{market_id}-{side}", market_id, token_id, side, old, old, old, {"condition_id": condition_id}),
        )


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])

from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.orderbook_snapshots import OrderbookSnapshotService


def _count(conn, table: str) -> int:
    exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]
    if not exists:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _seed_market() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, question, slug, yes_token_id, no_token_id, outcome_tokens_json,
                accepting_orders, closed, archived, active, raw_market_json, metadata_json
            )
            VALUES (
                'm1', 'Test market?', 'test-market', 'yes-token', 'no-token',
                '{"yes":"yes-token","no":"no-token"}'::jsonb,
                true, false, false, true, '{}'::jsonb, '{}'::jsonb
            )
            """
        )


def _fetcher(token_id: str) -> dict[str, object]:
    return {"asset_id": token_id, "bids": [[0.49, 100]], "asks": [[0.51, 100]]}


def test_orderbook_collection_creates_no_orders_intents_fills_positions_or_live_actions(postgres_test_schema) -> None:
    run_migrations()
    _seed_market()

    result = OrderbookSnapshotService(fetcher=_fetcher).collect_snapshots(limit=1)

    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 0
        assert _count(conn, "shadow_orders") == 0
        assert _count(conn, "live_orders") == 0
        assert _count(conn, "order_intents") == 0
        assert _count(conn, "paper_fills") == 0
        assert _count(conn, "positions") == 0
        exec_allowed = conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed = true").fetchone()["count"]
        assert exec_allowed == 0

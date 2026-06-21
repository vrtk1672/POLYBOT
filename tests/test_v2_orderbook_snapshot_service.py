from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.mesh_blockers import MeshBlockersService
from app.services.orderbook_snapshots import OrderbookSnapshotService


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
            ON CONFLICT (market_id) DO UPDATE SET
                yes_token_id = EXCLUDED.yes_token_id,
                no_token_id = EXCLUDED.no_token_id,
                accepting_orders = true,
                closed = false,
                active = true,
                last_seen_at = now()
            """
        )


def _fetcher(token_id: str) -> dict[str, object]:
    return {
        "asset_id": token_id,
        "bids": [{"price": "0.48", "size": "100"}, {"price": "0.49", "size": "200"}],
        "asks": [{"price": "0.51", "size": "150"}, {"price": "0.53", "size": "300"}],
    }


def test_collect_snapshots_persists_real_source_books_and_dashboard_summary(postgres_test_schema) -> None:
    run_migrations()
    _seed_market()

    result = OrderbookSnapshotService(fetcher=_fetcher).collect_snapshots(limit=1)
    summary = OrderbookSnapshotService(fetcher=_fetcher).get_dashboard_summary()

    assert result["mock_data"] is False
    assert result["markets_checked"] == 1
    assert result["snapshots_created"] == 2
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert summary["mock_data"] is False
    assert summary["total_snapshots"] == 2
    assert summary["fresh_snapshots"] == 2
    assert summary["ok_snapshots"] == 2
    assert summary["avg_spread"] == 0.02
    assert 0 <= summary["avg_liquidity_score"] <= 1


def test_orderbook_missing_resolves_only_when_fresh_snapshots_exist(postgres_test_schema) -> None:
    run_migrations()
    _seed_market()

    before = MeshBlockersService().get_mesh_blockers()
    OrderbookSnapshotService(fetcher=_fetcher).collect_snapshots(limit=1)
    after = MeshBlockersService().get_mesh_blockers()

    assert "ORDERBOOK_SNAPSHOTS_MISSING" in before["blocked_by"]
    assert "ORDERBOOK_SNAPSHOTS_MISSING" not in after["blocked_by"]
    assert after["paper_ready"] is False
    assert "NO_RISK_CORE" in after["blocked_by"]
    assert "NO_EXIT_FOUNDATION" in after["blocked_by"]

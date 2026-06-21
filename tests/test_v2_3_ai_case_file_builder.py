from __future__ import annotations

from app.ai_brain.case_file_builder import AICaseFileBuilder
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _seed_market(*, orderbook: bool = True, rules: bool = True, stale: bool = False, closed: bool = False) -> None:
    with DatabaseConnectionFactory().connect() as conn:
        conn.execute(
            """
            INSERT INTO markets_v2 (market_id, question, yes_token_id, no_token_id, accepting_orders, closed, category)
            VALUES ('m1', 'Will BTC close higher?', 'yes', 'no', true, %s, 'crypto')
            """,
            (closed,),
        )
        if rules:
            conn.execute("INSERT INTO market_rules (market_id, rules_text, resolution_source, rules_hash) VALUES ('m1', 'Resolve from exchange close.', 'exchange', 'rh')")
        conn.execute(
            """
            INSERT INTO market_snapshots_v2 (snapshot_id, market_id, current_price_yes, best_bid, best_ask, spread, time_to_close_seconds, data_completeness_score, stale)
            VALUES ('s1', 'm1', 0.55, 0.54, 0.56, 0.02, 3600, 90, %s)
            """,
            (stale,),
        )
        if orderbook:
            conn.execute("INSERT INTO orderbook_snapshots (orderbook_snapshot_id, market_id, best_bid, best_ask, spread, depth_2c) VALUES ('ob1', 'm1', 0.54, 0.56, 0.02, 100)")
        conn.execute("INSERT INTO liquidity_snapshots (liquidity_snapshot_id, market_id, liquidity_score, exit_quality, max_safe_size) VALUES ('l1', 'm1', 90, 80, 50)")
        conn.execute("INSERT INTO fee_snapshots (fee_snapshot_id, market_id, spread_cost) VALUES ('f1', 'm1', 0.02)")
        conn.execute("INSERT INTO market_family_map (market_id, market_family, confidence) VALUES ('m1', 'crypto-daily', 0.8)")
        conn.commit()


def test_complete_market_builds_compact_case_file(postgres_test_schema) -> None:
    run_migrations()
    _seed_market()
    case_file = AICaseFileBuilder().build_case_file("m1")
    assert case_file.allowed_for_ai is True
    assert case_file.market_family == "crypto-daily"
    assert case_file.orderbook_missing is False
    assert case_file.rules_missing is False


def test_missing_orderbook_and_rules_represented_honestly(postgres_test_schema) -> None:
    run_migrations()
    _seed_market(orderbook=False, rules=False)
    case_file = AICaseFileBuilder().build_case_file("m1")
    assert case_file.orderbook_missing is True
    assert case_file.rules_missing is True
    assert "orderbook" in case_file.missing_fields
    assert case_file.allowed_for_ai is False


def test_stale_and_closed_market_block_cloud_like_analysis(postgres_test_schema) -> None:
    run_migrations()
    _seed_market(stale=True, closed=True)
    case_file = AICaseFileBuilder().build_case_file("m1")
    assert case_file.allowed_for_ai is False
    assert case_file.blocked_reason in {"market_closed", "stale_data"}

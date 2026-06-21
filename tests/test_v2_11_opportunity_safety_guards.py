from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.opportunity.service import OpportunityService


def test_opportunity_service_creates_no_orders_intents_exits_or_balance_mutation(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    manual = {
        "context_output": {"strength": 0.9, "confidence": 0.9},
        "capital_output": {"capital_allowed": True, "allocation_confidence": 0.9},
        "market_signal": {"technical_score": 0.8, "data_completeness_score": 1.0},
        "orderbook_signal": {"has_bid_ask": True, "spread_bps": 80, "depth_2c": 500},
        "liquidity_signal": {"exit_quality_score": 0.8, "max_safe_size_usd": 1000},
        "data_completeness_score": 1.0,
    }
    with factory.connect() as conn:
        baseline = _counts(conn)
    result = OpportunityService(connection_factory=factory).score_market("safe", manual_input=manual)
    with factory.connect() as conn:
        after = _counts(conn)

    assert result["written"] is True
    assert baseline == after
    assert result["result"]["score"]["candidate_engines"]


def test_high_score_cannot_bypass_hard_risk_flags(postgres_test_schema):
    run_migrations()
    manual = {
        "context_output": {"strength": 1.0, "confidence": 1.0},
        "capital_output": {"capital_allowed": True, "allocation_confidence": 1.0},
        "market_signal": {"technical_score": 1.0},
        "orderbook_signal": {"has_bid_ask": False, "depth_2c": 0},
        "liquidity_signal": {"exit_quality_score": 0.0, "max_safe_size_usd": 0},
        "fee_reward_signal": {"reward_score": 1.0},
        "data_completeness_score": 1.0,
    }

    result = OpportunityService(connection_factory=DatabaseConnectionFactory()).score_market("unsafe", dry_run=True, manual_input=manual)

    assert result["result"]["score"]["score_band"] == "BLOCKED"
    assert result["result"]["score"]["opportunity_score"] == 0.0


def _counts(conn):
    out = {}
    for table in ("orders", "order_intents", "exit_intents", "paper_orders", "paper_positions", "live_orders"):
        exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
        if exists:
            out[table] = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
        else:
            out[table] = None
    return out


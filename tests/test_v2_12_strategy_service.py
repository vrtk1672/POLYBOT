from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.strategy.service import StrategyService


def _manual():
    return {
        "market_family": "crypto",
        "side": "YES",
        "opportunity_score": 0.82,
        "opportunity_score_band": "STRONG",
        "candidate_engines_from_opportunity": ["SAFE", "STRIKE", "CONVEX", "HUNT"],
        "opportunity_components": {
            "confidence": 0.86,
            "trigger_strength": 0.8,
            "repricing_potential": 0.76,
            "time_efficiency": 0.72,
            "liquidity_quality": 0.84,
            "exit_probability": 0.86,
            "convexity": 0.72,
            "wording_risk": 0.05,
            "risk_penalty": 0.1,
            "trap_risk": 0.1,
            "already_priced_in_score": 0.12,
            "capital_allowed": True,
            "max_safe_size_usd": 1000,
        },
        "context_output": {"context_shift": True},
        "capital_output": {"capital_allowed": True, "max_position_size_usd": 500},
        "technical_truth": {"orderbook_signal": {"has_bid_ask": True, "depth_2c": 800}, "liquidity_signal": {"max_safe_size_usd": 1000}},
        "data_completeness_score": 1.0,
    }


def test_service_persists_route_decisions_rejections_and_events(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    result = StrategyService(connection_factory=factory).route_market("strat_m1", manual_input=_manual())
    assert result["written"] is True
    run_id = result["result"]["run_id"]
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM strategy_route_runs").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM strategy_routes_v2").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM engine_decisions WHERE run_id=%s", (run_id,)).fetchone()["count"] == 8
        assert conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type='strategy.route.created'").fetchone()["count"] == 1


def test_service_handles_missing_opportunity_honestly(postgres_test_schema):
    run_migrations()
    result = StrategyService(connection_factory=DatabaseConnectionFactory()).route_market("missing", dry_run=True)
    route = result["result"]["route"]
    assert result["written"] is False
    assert route["selected_engine"] == "NO_TRADE"
    assert route["route_status"] == "INSUFFICIENT_DATA"
    assert "missing_opportunity_score" in route["insufficient_data_reasons"]


def test_service_handles_blocked_opportunity_as_no_trade(postgres_test_schema):
    run_migrations()
    manual = _manual()
    manual["opportunity_score_band"] = "BLOCKED"
    manual["opportunity_risk_flags"] = [{"risk_flag": "bad_liquidity", "severity": "BLOCKING", "blocks_opportunity": True}]
    result = StrategyService(connection_factory=DatabaseConnectionFactory()).route_market("blocked", dry_run=True, manual_input=manual)
    assert result["result"]["route"]["selected_engine"] == "NO_TRADE"
    assert result["result"]["route"]["route_status"] == "BLOCKED"


from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.strategy.service import StrategyService


def test_strategy_service_creates_no_orders_order_intents_exits_or_balance_mutation(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        baseline = _counts(conn)
    result = StrategyService(connection_factory=factory).route_market("safe_strategy", manual_input=_manual())
    with factory.connect() as conn:
        after = _counts(conn)
    assert result["written"] is True
    assert baseline == after
    assert result["result"]["route"]["contract"]["execution_mode"] == "CONTRACT_ONLY"


def test_hunt_blocked_without_approval_and_can_route_with_approval_when_valid(postgres_test_schema):
    run_migrations()
    manual = _manual()
    manual["candidate_engines_from_opportunity"] = ["HUNT"]
    manual["opportunity_components"].update({"time_efficiency": 0.9, "trigger_strength": 0.9, "repricing_potential": 0.9, "exit_probability": 0.75})
    service = StrategyService(connection_factory=DatabaseConnectionFactory())
    blocked = service.route_market("hunt_no", dry_run=True, manual_input=manual, hunt_approval=False)
    assert any(d["engine"] == "HUNT" and d["rejection_reason"] == "hunt_requires_governor_approval" for d in blocked["result"]["route"]["engine_decisions"])
    approved = service.route_market("hunt_yes", dry_run=True, manual_input=manual, hunt_approval=True)
    assert approved["result"]["route"]["selected_engine"] == "HUNT"


def test_candidate_engines_are_revalidated_not_blindly_accepted(postgres_test_schema):
    run_migrations()
    manual = _manual()
    manual["candidate_engines_from_opportunity"] = ["MAKER"]
    manual["technical_truth"] = {"orderbook_signal": {"has_bid_ask": False, "depth_2c": 0}}
    result = StrategyService(connection_factory=DatabaseConnectionFactory()).route_market("bad_maker", dry_run=True, manual_input=manual)
    assert result["result"]["route"]["selected_engine"] == "NO_TRADE"
    assert any(d["engine"] == "MAKER" and d["eligible"] is False for d in result["result"]["route"]["engine_decisions"])


def _counts(conn):
    out = {}
    for table in ("orders", "order_intents", "exit_intents", "paper_orders", "paper_positions", "live_orders"):
        exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
        out[table] = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] if exists else None
    return out


def _manual():
    return {
        "side": "YES",
        "opportunity_score": 0.82,
        "opportunity_score_band": "STRONG",
        "candidate_engines_from_opportunity": ["SAFE", "STRIKE", "CONVEX"],
        "opportunity_components": {"confidence": 0.86, "trigger_strength": 0.8, "repricing_potential": 0.76, "time_efficiency": 0.72, "liquidity_quality": 0.84, "exit_probability": 0.86, "convexity": 0.72, "wording_risk": 0.05, "risk_penalty": 0.1, "trap_risk": 0.1, "capital_allowed": True, "max_safe_size_usd": 1000},
        "context_output": {"context_shift": True},
        "capital_output": {"capital_allowed": True, "max_position_size_usd": 500},
        "technical_truth": {"orderbook_signal": {"has_bid_ask": True, "depth_2c": 800}, "liquidity_signal": {"max_safe_size_usd": 1000}},
        "data_completeness_score": 1.0,
    }

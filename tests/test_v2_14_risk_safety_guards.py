from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.risk.service import RiskService


def test_risk_service_creates_no_orders_intents_exits_or_balance_mutations(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    service = RiskService(connection_factory=factory)
    service.rebuild_governor(manual_payload={"daily_loss_usd": 0})
    service.evaluate_gate(
        market_id="risk_safety",
        manual_input={
            "engine": "SAFE",
            "strategy_route": {"market_id": "risk_safety", "selected_engine": "SAFE", "route_status": "ROUTED", "route_confidence": 0.9, "target_exit": 0.8, "stop_loss": 0.3},
            "capital_allocation": {"allocation_id": "a1", "allocation_status": "ALLOCATED", "approved_size_usd": 10, "max_loss_usd": 5, "engine_budget_after_usd": 20},
            "governor_state": {"governor_status": "OK"},
            "data_completeness_score": 1,
        },
    )
    with factory.connect() as conn:
        for table in ("orders", "order_intents", "exit_intents"):
            exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
            if exists:
                assert conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) AS count FROM risk_gate_decisions WHERE approved IS TRUE").fetchone()["count"] == 1


def test_kill_and_missing_exit_plan_cannot_be_overridden():
    service = RiskService(connection_factory=DatabaseConnectionFactory())
    result = service.evaluate_gate(
        market_id="kill_manual",
        dry_run=True,
        manual_input={
            "engine": "SAFE",
            "strategy_route": {"selected_engine": "SAFE", "route_status": "ROUTED", "route_confidence": 0.9},
            "capital_allocation": {"allocation_status": "ALLOCATED", "approved_size_usd": 10, "max_loss_usd": 5},
            "governor_state": {"governor_status": "KILL", "kill_switch_active": True},
            "manual_override": {"override_id": "override_soft"},
        },
    )
    decision = result["decision"]
    assert decision["blocked"] is True
    assert "governor_kill" in decision["block_reasons"]
    assert "missing_exit_plan" in decision["block_reasons"]


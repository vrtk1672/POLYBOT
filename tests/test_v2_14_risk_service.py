from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.risk.service import RiskService


def _manual():
    return {
        "market_family": "sports",
        "side": "YES",
        "engine": "SAFE",
        "strategy_route": {
            "id": 1,
            "market_id": "risk_m1",
            "selected_engine": "SAFE",
            "route_status": "ROUTED",
            "route_confidence": 0.8,
            "target_exit": 0.8,
            "stop_loss": 0.3,
            "engine_contract_json": {"target_exit": 0.8, "stop_loss": 0.3},
        },
        "capital_allocation": {"allocation_id": "a1", "allocation_status": "ALLOCATED", "approved_size_usd": 25, "max_loss_usd": 10, "engine_budget_after_usd": 100},
        "governor_state": {"governor_status": "OK", "data_confidence": 0.9},
        "data_completeness_score": 1,
    }


def test_service_persists_governor_gate_limits_breaches_and_events(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    service = RiskService(connection_factory=factory)
    gov = service.rebuild_governor(manual_payload={"daily_loss_usd": 60, "attack_bank_available": 0})
    assert gov["written"] is True
    result = service.evaluate_gate(market_id="risk_m1", manual_input=_manual())
    assert result["written"] is True
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM risk_governor_state").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM risk_limits").fetchone()["count"] >= 9
        assert conn.execute("SELECT COUNT(*) AS count FROM risk_breaches").fetchone()["count"] >= 1
        assert conn.execute("SELECT COUNT(*) AS count FROM risk_gate_runs").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM risk_gate_decisions").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type='risk.gate.approved'").fetchone()["count"] == 1


def test_service_dry_runs_write_nothing(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    service = RiskService(connection_factory=factory)
    assert service.rebuild_governor(dry_run=True, manual_payload={"daily_loss_usd": 0})["written"] is False
    assert service.evaluate_gate(market_id="risk_dry", dry_run=True, manual_input=_manual())["written"] is False
    assert service.create_override(payload={"actor": "op", "reason": "test", "scope": "ENGINE", "override_type": "SOFT_RISK"}, dry_run=True)["written"] is False
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM risk_gate_decisions").fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) AS count FROM risk_governor_state").fetchone()["count"] == 0


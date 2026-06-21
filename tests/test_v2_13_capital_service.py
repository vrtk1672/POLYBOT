from app.capital.service import CapitalService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _capital():
    return {"total_capital_usd": 1000, "available_capital_usd": 1000, "realized_pnl_usd": 120}


def _route(engine="SAFE", status="ROUTED"):
    return {
        "id": 1,
        "run_id": "strategy_manual",
        "market_id": "capital_service_m1",
        "market_family": "sports",
        "side": "YES",
        "selected_engine": engine,
        "route_status": status,
        "route_confidence": 0.9,
        "max_position_size_usd": 80,
        "max_loss_usd": 20,
        "max_hold_minutes": 45,
        "engine_contract_json": {"max_position_size_usd": 80, "max_loss_usd": 20},
    }


def test_service_persists_capital_state_budgets_allocations_reinvest_and_events(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    service = CapitalService(connection_factory=factory)
    state_result = service.rebuild_state(manual_payload=_capital())
    assert state_result["written"] is True
    allocation = service.allocate(market_id="capital_service_m1", manual_route=_route(), manual_capital=_capital(), requested_size_usd=60)
    assert allocation["written"] is True
    reinvest = service.evaluate_reinvest(realized_profit_usd=100)
    assert reinvest["written"] is True
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM capital_state_v2").fetchone()["count"] >= 1
        assert conn.execute("SELECT COUNT(*) AS count FROM engine_budgets").fetchone()["count"] >= 8
        assert conn.execute("SELECT COUNT(*) AS count FROM capital_allocations_v2").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM reinvest_ledger").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM profit_pocket").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM attack_bank WHERE base_capital_used_usd = 0").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM capital_events").fetchone()["count"] >= 3
        assert conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type='capital.allocation.created'").fetchone()["count"] == 1


def test_service_dry_runs_write_nothing_and_blocks_no_trade(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    service = CapitalService(connection_factory=factory)
    dry_state = service.rebuild_state(dry_run=True, manual_payload=_capital())
    dry_alloc = service.allocate(market_id="dry", dry_run=True, manual_route=_route(), manual_capital=_capital(), requested_size_usd=50)
    dry_reinvest = service.evaluate_reinvest(dry_run=True, realized_profit_usd=100)
    blocked = service.allocate(market_id="blocked", manual_route=_route(engine="NO_TRADE", status="NO_TRADE"), manual_capital=_capital(), requested_size_usd=50)
    assert dry_state["written"] is False
    assert dry_alloc["written"] is False
    assert dry_reinvest["written"] is False
    assert blocked["decision"]["allocation_status"] == "BLOCKED"
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM capital_state_v2").fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) AS count FROM capital_allocations_v2").fetchone()["count"] == 1


from app.capital.service import CapitalService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_capital_api_service_creates_no_orders_intents_exits_or_external_mutations(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    service = CapitalService(connection_factory=factory)
    route = {
        "id": 1,
        "run_id": "safe_route",
        "market_id": "safety_m1",
        "side": "YES",
        "selected_engine": "SAFE",
        "route_status": "ROUTED",
        "route_confidence": 0.9,
        "max_position_size_usd": 50,
        "max_loss_usd": 10,
        "engine_contract_json": {"max_position_size_usd": 50},
    }
    capital = {"total_capital_usd": 1000, "available_capital_usd": 1000, "realized_pnl_usd": 100}
    service.allocate(market_id="safety_m1", manual_route=route, manual_capital=capital)
    with factory.connect() as conn:
        for table in ("orders", "order_intents", "exit_intents"):
            exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
            if exists:
                assert conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) AS count FROM capital_allocations_v2 WHERE approved_size_usd > 0").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM attack_bank WHERE base_capital_used_usd <> 0").fetchone()["count"] == 0


def test_missing_capital_data_is_insufficient_and_attack_bank_uses_no_base():
    result = CapitalService(connection_factory=DatabaseConnectionFactory()).allocate(
        market_id="missing",
        dry_run=True,
        manual_route={"market_id": "missing", "selected_engine": "SAFE", "route_status": "ROUTED", "side": "YES", "max_position_size_usd": 50},
        manual_capital={"total_capital_usd": 0, "available_capital_usd": 0},
    )
    decision = result["decision"]
    assert decision["allocation_status"] == "DRY_RUN"
    assert decision["approved_size_usd"] == 0


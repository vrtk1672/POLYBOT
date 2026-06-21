from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.market_memory.service import MarketMemoryService
from app.market_neuron.service import MarketNeuronService


def _seed_v2_8_market(factory: DatabaseConnectionFactory, market_id: str = "mmem") -> None:
    MarketNeuronService(connection_factory=factory).analyze_market(
        market_id,
        token_id="yes",
        side="YES",
        raw_market_snapshot={"current_price_yes": 0.55, "data_completeness_score": 1.0, "time_to_close_seconds": 7200},
        raw_orderbook={"bids": [[0.54, 1000]], "asks": [[0.56, 1000]]},
    )


def test_service_persists_all_memory_table_types_and_events(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    _seed_v2_8_market(factory)

    result = MarketMemoryService(connection_factory=factory).rebuild(market_id="mmem", dry_run=False)

    assert result["written"] is True
    with factory.connect() as conn:
        for table in (
            "market_memory_v2",
            "market_family_memory",
            "engine_performance_memory",
            "source_reliability_memory",
            "whale_memory",
            "slippage_memory",
            "rules_risk_memory",
            "no_trade_memory",
        ):
            assert conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] >= 1
        assert conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'market.memory.updated'").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'market.memory.insufficient_data'").fetchone()["count"] == 1


def test_service_handles_missing_v2_8_data_without_fake_best_engine(postgres_test_schema):
    run_migrations()
    result = MarketMemoryService(connection_factory=DatabaseConnectionFactory()).rebuild(market_id="missing", dry_run=True)

    snapshot = result["snapshots"][0]
    assert result["written"] is False
    assert "missing_v2_8_technical_signals" in snapshot["insufficient_data"]
    assert snapshot["market_memory"]["best_engine"] == "UNKNOWN"
    assert snapshot["confidence"] == 0


def test_service_dry_run_does_not_write(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    _seed_v2_8_market(factory, "dry")
    with factory.connect() as conn:
        before = conn.execute("SELECT COUNT(*) AS count FROM market_memory_v2").fetchone()["count"]

    result = MarketMemoryService(connection_factory=factory).rebuild(market_id="dry", dry_run=True)

    assert result["dry_run"] is True
    with factory.connect() as conn:
        after = conn.execute("SELECT COUNT(*) AS count FROM market_memory_v2").fetchone()["count"]
    assert after == before

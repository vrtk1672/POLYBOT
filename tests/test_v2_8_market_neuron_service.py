from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.market_neuron.service import MarketNeuronService


def test_service_persists_all_signal_types_and_publishes_events(postgres_test_schema):
    run_migrations()
    service = MarketNeuronService(connection_factory=DatabaseConnectionFactory())
    result = service.analyze_market(
        "mtech",
        token_id="yes",
        side="YES",
        raw_market_snapshot={"current_price_yes": 0.5, "data_completeness_score": 1.0, "time_to_close_seconds": 7200},
        raw_orderbook={"bids": [[0.49, 1000]], "asks": [[0.51, 1000]]},
    )
    assert result["market_id"] == "mtech"
    assert result["technical_blocked"] is False
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM market_technical_signals WHERE market_id = 'mtech'").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM orderbook_signals WHERE market_id = 'mtech'").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM liquidity_signals WHERE market_id = 'mtech'").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM time_signals WHERE market_id = 'mtech'").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM fee_reward_signals WHERE market_id = 'mtech'").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'market.technical_truth.created'").fetchone()["count"] == 1


def test_service_handles_missing_orderbook_honestly(postgres_test_schema):
    run_migrations()
    result = MarketNeuronService(connection_factory=DatabaseConnectionFactory()).analyze_market(
        "missing_ob",
        raw_market_snapshot={"current_price_yes": 0.5, "data_completeness_score": 0.5},
    )
    assert result["technical_blocked"] is True
    assert "missing_bid_ask" in result["block_reasons"]
    assert "missing_exit_liquidity" in result["block_reasons"]


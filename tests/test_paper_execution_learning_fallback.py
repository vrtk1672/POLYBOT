from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_execution import PaperExecutionService

from test_paper_execution_price_fixtures import GovernorAllow, NoRefresh, PowerOn, prepare_execution_price_fixture, seed_intent, seed_orderbook


def test_defense_20_uses_bounded_regular_orderbook_as_labeled_learning_fallback(postgres_test_schema) -> None:
    prepare_execution_price_fixture(defense_level=20)
    stale = seed_orderbook(snapshot_ref="stale-stored", seconds_old=1200)
    seed_orderbook(snapshot_ref="fresh-regular", source="live_orderbook_watcher", seconds_old=5, spread="0.03")
    intent_id = seed_intent(snapshot_id=stale["id"])

    result = PaperExecutionService(
        system_power=PowerOn(),
        governor=GovernorAllow(),
        last_mile_orderbook_refresh=NoRefresh(),
    ).run_execution(correlation_id="fallback-defense20")

    assert result["status"] == "OK"
    assert result["orders_created"] == 1
    assert result["fills_created"] == 1
    assert result["positions_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        fill = conn.execute("SELECT * FROM paper_fills WHERE source_intent_id=%s", (intent_id,)).fetchone()
    assert fill["metadata_json"]["execution_price_source"] == "PAPER_LEARNING_PRICE_FALLBACK"
    assert fill["metadata_json"]["trusted_orderbook_used"] is False
    assert fill["metadata_json"]["fallback_source"] == "REGULAR_ORDERBOOK"
    assert fill["metadata_json"]["fallback_learning_only"] is True


def test_defense_100_does_not_use_regular_orderbook_fallback(postgres_test_schema) -> None:
    prepare_execution_price_fixture(defense_level=100)
    stale = seed_orderbook(snapshot_ref="strict-stale", seconds_old=1200)
    seed_orderbook(snapshot_ref="strict-fresh-regular", source="live_orderbook_watcher", seconds_old=5, spread="0.03")
    seed_intent(snapshot_id=stale["id"])

    result = PaperExecutionService(
        system_power=PowerOn(),
        governor=GovernorAllow(),
        last_mile_orderbook_refresh=NoRefresh(),
    ).run_execution(correlation_id="fallback-defense100")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["orders_created"] == 0
    assert result["block_reasons_json"]["ORDERBOOK_CONNECTOR_ERROR"] == 1
    assert result["block_reasons_json"]["NO_EXECUTABLE_PAPER_PRICE"] == 1

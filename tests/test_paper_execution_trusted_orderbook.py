from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_execution import PaperExecutionService

from test_paper_execution_price_fixtures import GovernorAllow, PowerOn, StubRefresh, prepare_execution_price_fixture, seed_intent, seed_orderbook


def test_trusted_orderbook_snapshot_executes_with_price_source_metadata(postgres_test_schema) -> None:
    prepare_execution_price_fixture(defense_level=100)
    snapshot = seed_orderbook(snapshot_ref="trusted-direct", source="test_trusted_orderbook")
    intent_id = seed_intent(snapshot_id=snapshot["id"])

    result = PaperExecutionService(system_power=PowerOn(), governor=GovernorAllow()).run_execution(correlation_id="trusted-direct")

    assert result["status"] == "OK"
    assert result["orders_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        fill = conn.execute("SELECT * FROM paper_fills WHERE source_intent_id=%s", (intent_id,)).fetchone()
    assert fill["metadata_json"]["execution_price_source"] == "TRUSTED_ORDERBOOK"
    assert fill["metadata_json"]["trusted_orderbook_used"] is True
    assert fill["metadata_json"]["fallback_source"] == "NONE"


def test_last_mile_trusted_snapshot_is_used_when_stored_snapshot_missing(postgres_test_schema) -> None:
    prepare_execution_price_fixture(defense_level=100)
    refreshed = seed_orderbook(snapshot_ref="last-mile-trusted", source="polymarket_clob_last_mile_paper")
    intent_id = seed_intent(snapshot_id=None)

    result = PaperExecutionService(
        system_power=PowerOn(),
        governor=GovernorAllow(),
        last_mile_orderbook_refresh=StubRefresh(refreshed),
    ).run_execution(correlation_id="trusted-last-mile")

    assert result["status"] == "OK"
    assert result["orders_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        fill = conn.execute("SELECT * FROM paper_fills WHERE source_intent_id=%s", (intent_id,)).fetchone()
    assert fill["metadata_json"]["execution_price_source"] == "LAST_MILE_TRUSTED_ORDERBOOK"
    assert fill["metadata_json"]["trusted_orderbook_used"] is True

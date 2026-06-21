from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_execution import PaperExecutionService

from test_paper_execution_price_fixtures import GovernorAllow, NoRefresh, PowerOn, prepare_execution_price_fixture, seed_intent


def test_no_safe_price_expires_intent_with_precise_diagnostic(postgres_test_schema) -> None:
    prepare_execution_price_fixture(defense_level=20)
    intent_id = seed_intent(snapshot_id=None)

    result = PaperExecutionService(
        system_power=PowerOn(),
        governor=GovernorAllow(),
        last_mile_orderbook_refresh=NoRefresh(),
    ).run_execution(correlation_id="no-price")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["fills_created"] == 0
    assert result["block_reasons_json"]["NO_EXECUTABLE_PAPER_PRICE"] == 1
    assert "MISSING_TRUSTED_ORDERBOOK" not in result["block_reasons_json"]
    with DatabaseConnectionFactory().connect() as conn:
        intent = conn.execute("SELECT * FROM paper_intents WHERE paper_intent_id=%s", (intent_id,)).fetchone()
    assert intent["intent_status"] == "EXPIRED_NO_EXECUTION"
    assert "NO_EXECUTABLE_PAPER_PRICE" in intent["execution_block_reason"]

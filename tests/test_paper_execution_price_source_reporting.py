from __future__ import annotations

from app.services.paper_defense import PaperDefenseGovernor
from app.services.paper_execution import PaperExecutionService

from test_paper_execution_price_fixtures import GovernorAllow, NoRefresh, PowerOn, prepare_execution_price_fixture, seed_intent, seed_orderbook


def test_session_learning_report_includes_execution_price_source_fields(postgres_test_schema) -> None:
    prepare_execution_price_fixture(defense_level=20)
    stale = seed_orderbook(snapshot_ref="report-stale", seconds_old=1200)
    seed_orderbook(snapshot_ref="report-fresh-regular", source="live_orderbook_watcher", seconds_old=5, spread="0.03")
    seed_intent(snapshot_id=stale["id"])

    result = PaperExecutionService(
        system_power=PowerOn(),
        governor=GovernorAllow(),
        last_mile_orderbook_refresh=NoRefresh(),
    ).run_execution(correlation_id="report-fallback")

    assert result["status"] == "OK"
    report = PaperDefenseGovernor().learning_report(session_id="paper-execution-price-session", write_files=False)
    trade = report["trade_table"][0]
    assert trade["execution_price_source"] == "PAPER_LEARNING_PRICE_FALLBACK"
    assert trade["trusted_orderbook_used"] is False
    assert trade["fallback_source"] == "REGULAR_ORDERBOOK"
    assert "price_confidence" in trade
    assert "spread" in trade

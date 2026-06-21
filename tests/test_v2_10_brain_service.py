from app.brains.service import BrainService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _context_manual():
    return {
        "news_signals": [{"strength": 0.9, "confidence": 0.9, "direction": "YES", "already_priced_in": 0.1}],
        "technical_signals": [{"technical_score": 0.8, "data_completeness_score": 1.0}],
        "memory_snapshot": {"confidence": 0.8},
        "data_completeness_score": 1.0,
    }


def _capital_manual():
    return {
        "balance": 1000,
        "available_capital": 800,
        "locked_capital": 50,
        "engine_budgets": {"strike": 100},
        "risk_limits": {"min_cash_reserve_pct": 0.2, "max_alloc_pct": 0.1, "max_open_exposure_pct": 0.8},
        "memory_snapshot": {"confidence": 0.8, "slippage_memory": [{"slippage_risk_score": 0.1}]},
        "data_completeness_score": 1.0,
    }


def test_service_persists_context_and_capital_outputs_and_events(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    service = BrainService(connection_factory=factory)

    context = service.analyze_context("brain_m1", manual_input=_context_manual())
    capital = service.analyze_capital(market_id="brain_m1", candidate_engine="strike", manual_input=_capital_manual())

    assert context["written"] is True
    assert capital["written"] is True
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM context_brain_runs").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM context_brain_outputs").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM capital_brain_runs").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM capital_brain_outputs").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'context_brain.output.created'").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'capital_brain.output.created'").fetchone()["count"] == 1


def test_service_handles_missing_memory_and_capital_honestly(postgres_test_schema):
    run_migrations()
    service = BrainService(connection_factory=DatabaseConnectionFactory())

    context = service.analyze_context("missing", dry_run=True)
    capital = service.analyze_capital(market_id="missing", dry_run=True, manual_input={})

    assert context["output"]["insufficient_data"] is True
    assert capital["output"]["insufficient_data"] is True


def test_combined_snapshot_separates_interesting_from_worth_money(postgres_test_schema):
    run_migrations()
    service = BrainService(connection_factory=DatabaseConnectionFactory())
    result = service.analyze_both(
        "brain_m2",
        candidate_engine="strike",
        dry_run=True,
        manual_context=_context_manual(),
        manual_capital={**_capital_manual(), "available_capital": 50},
    )

    snapshot = result["snapshot"]
    assert snapshot["interesting"] is True
    assert snapshot["worth_money"] is False
    assert "interesting_not_worth_money" in snapshot["reasons"]

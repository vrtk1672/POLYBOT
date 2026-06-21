from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_intents import PaperIntentGateService

from paper_intent_fixtures import prepare_paper_intent_schema, seed_blocked_candidate


def test_no_trade_ledger_safety_and_unaccounted_detection(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_blocked_candidate("safety-ledger")

    before = PaperIntentGateService().get_no_trade_dashboard_summary()
    assert before["unaccounted_candidates"] == 1

    result = PaperIntentGateService().build_intents(limit=10)
    after = PaperIntentGateService().get_no_trade_dashboard_summary()

    assert result["paper_ready_after"] is False
    assert after["unaccounted_candidates"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_intents").fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) AS count FROM no_trade_log WHERE source_layer='paper_intent_gate'").fetchone()["count"] == 1

from __future__ import annotations

from app.services.paper_intents import PaperIntentGateService

from paper_intent_fixtures import prepare_paper_intent_schema, seed_blocked_candidate


def test_no_trade_ledger_accounts_blocked_candidate(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_blocked_candidate("ledger", blockers=["EXIT_NOT_READY"], missing=["EXIT_NOT_READY"], risk_approved=True)

    result = PaperIntentGateService().build_intents(limit=10)
    summary = PaperIntentGateService().get_no_trade_dashboard_summary()

    assert result["no_trade_records_created"] == 1
    assert summary["mock_data"] is False
    assert summary["total_no_trade_records"] == 1
    assert summary["unaccounted_candidates"] == 0
    assert summary["counts_by_category"][0]["category"] == "EXIT_BLOCKED"

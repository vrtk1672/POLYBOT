from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_intents import PaperIntentGateService

from paper_intent_fixtures import prepare_paper_intent_schema, seed_blocked_candidate, seed_eligible_candidate


def test_eligible_candidate_creates_paper_intent(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_eligible_candidate("intent-ok")

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_intents_created"] == 1
    assert result["no_trade_records_created"] == 0
    assert result["accounted_candidates"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM paper_intents").fetchone()
    assert row["paper_only"] is True
    assert row["live"] is False
    assert row["execution_allowed"] is False
    assert row["order_intent_created"] is False


def test_blocked_ineligible_incomplete_candidates_create_no_trade(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_blocked_candidate("blocked", status="BLOCKED")
    seed_blocked_candidate("ineligible", status="INELIGIBLE")
    seed_blocked_candidate("incomplete", status="INCOMPLETE", blockers=["MISSING_FRESH_ORDERBOOK"], missing=["MISSING_FRESH_ORDERBOOK"])

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_intents_created"] == 0
    assert result["no_trade_records_created"] == 3
    assert result["accounted_candidates"] == 3
    assert result["unaccounted_candidates"] == 0


def test_missing_hard_requirements_do_not_create_intent(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_blocked_candidate("no-thesis", status="ELIGIBLE", thesis_id=None, blockers=[], missing=[])
    seed_blocked_candidate("no-risk", status="ELIGIBLE", risk_decision_id=None, blockers=[], missing=[])
    seed_blocked_candidate("no-exit", status="ELIGIBLE", exit_plan_id=None, blockers=[], missing=[])
    seed_blocked_candidate("no-market", status="ELIGIBLE", market_id=None, blockers=[], missing=[])
    seed_blocked_candidate("no-side", status="ELIGIBLE", side=None, blockers=[], missing=[])
    seed_blocked_candidate("no-book", status="ELIGIBLE", orderbook_snapshot_id=None, blockers=[], missing=[])

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_intents_created"] == 0
    assert result["no_trade_records_created"] == 6


def test_dry_run_candidate_does_not_create_intent(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_blocked_candidate("dry", status="ELIGIBLE", blockers=[], missing=[], not_dry_run=False, is_dry_run_generated=True)

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["candidates_checked"] == 0
    assert result["paper_intents_created"] == 0

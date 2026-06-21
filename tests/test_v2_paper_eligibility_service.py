from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_eligibility import PaperEligibilityService

from paper_eligibility_fixtures import prepare_paper_eligibility_schema, seed_paper_eligibility_chain


def test_eligibility_evaluates_exit_plans(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    seed_paper_eligibility_chain("blocked", exit_status="BLOCKED", paper_exit_ready=False, risk_approved=False)

    result = PaperEligibilityService().evaluate_candidates(limit=10)

    assert result["mock_data"] is False
    assert result["exit_plans_checked"] == 1
    assert result["candidates_created"] == 1
    assert result["blocked_count"] == 1


def test_blocked_exit_and_unapproved_risk_block_eligibility(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    seed_paper_eligibility_chain("blocked-exit", exit_status="BLOCKED", paper_exit_ready=False, risk_approved=False)

    PaperEligibilityService().evaluate_candidates(limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM paper_eligibility_candidates").fetchone()
    assert row["status"] == "BLOCKED"
    assert "EXIT_NOT_READY" in row["eligibility_blockers"]
    assert "RISK_NOT_APPROVED" in row["eligibility_blockers"]
    assert row["paper_intent_allowed"] is False
    assert row["execution_allowed"] is False


def test_missing_market_side_orderbook_binding_lineage_and_dry_run_block(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    seed_paper_eligibility_chain("missing-market", market_id=None, orderbook=False, binding=False, lineage=False)
    seed_paper_eligibility_chain("missing-side", side=None)
    seed_paper_eligibility_chain("missing-book", orderbook=False)
    seed_paper_eligibility_chain("missing-binding", binding=False)
    seed_paper_eligibility_chain("dry", dry_run=True)

    result = PaperEligibilityService().evaluate_candidates(limit=10)

    assert result["blocked_count"] == 5
    assert result["missing_market_count"] >= 1
    assert result["missing_orderbook_count"] >= 2
    assert result["missing_binding_count"] >= 2
    assert result["missing_lineage_count"] >= 1
    assert result["dry_run_blocked_count"] == 1


def test_fully_evidenced_candidate_can_be_eligible_without_intent_or_execution(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    seed_paper_eligibility_chain("eligible")

    result = PaperEligibilityService().evaluate_candidates(limit=10)

    assert result["eligible_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM paper_eligibility_candidates").fetchone()
    assert row["status"] == "ELIGIBLE"
    assert row["paper_intent_allowed"] is False
    assert row["execution_allowed"] is False

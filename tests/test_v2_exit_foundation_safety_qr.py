from __future__ import annotations

from app.services.exit_foundation import ExitFoundationService

from paper_eligibility_fixtures import prepare_paper_eligibility_schema, seed_paper_eligibility_chain


def test_exit_foundation_still_does_not_create_paper_eligibility_or_execution(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    seed_paper_eligibility_chain("exit-safety", exit_status="BLOCKED", paper_exit_ready=False, risk_approved=False)

    result = ExitFoundationService().build_exit_plans(limit=10)

    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0

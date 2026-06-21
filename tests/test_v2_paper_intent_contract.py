from __future__ import annotations

import pytest

from app.neural_mesh.paper_intents import PaperIntent, PaperIntentRun


def test_paper_intent_contract_enforces_non_execution() -> None:
    intent = PaperIntent(
        paper_intent_id="pi-1",
        eligibility_id="e-1",
        thesis_id="t-1",
        risk_decision_id="r-1",
        exit_plan_id="x-1",
        market_id="m-1",
        side="YES",
    )

    assert intent.paper_only is True
    assert intent.live is False
    assert intent.execution_allowed is False
    assert intent.order_intent_created is False


def test_paper_intent_contract_rejects_execution_flags() -> None:
    with pytest.raises(ValueError):
        PaperIntent(
            paper_intent_id="pi-2",
            eligibility_id="e-2",
            thesis_id="t-2",
            risk_decision_id="r-2",
            exit_plan_id="x-2",
            market_id="m-2",
            side="YES",
            execution_allowed=True,
        )


def test_paper_intent_run_rejects_executable_artifacts() -> None:
    with pytest.raises(ValueError):
        PaperIntentRun(run_id="run-1", status="OK", started_at="2026-01-01T00:00:00Z", order_intents_created=1)


def test_paper_intent_run_allows_paper_order_ledger_activity() -> None:
    run = PaperIntentRun(run_id="run-paper", status="OK", started_at="2026-01-01T00:00:00Z", orders_created=1)

    assert run.orders_created == 1
    assert run.live_actions_created == 0

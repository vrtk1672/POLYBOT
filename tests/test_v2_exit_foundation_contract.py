from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.neural_mesh.exit_foundation import ExitFoundationPlan, ExitFoundationRun


def test_complete_exit_plan_requires_target_stop_and_rules() -> None:
    plan = ExitFoundationPlan(
        exit_plan_id="exit-complete",
        thesis_id="thesis-1",
        risk_decision_id="risk-1",
        market_id="market-1",
        side="YES",
        status="COMPLETE",
        exit_type="BASIC_PROTECTIVE_EXIT",
        target_exit=0.55,
        stop_loss=0.47,
        orderbook_snapshot_id=1,
        invalidation_rules=["orderbook_stale"],
        emergency_exit_rules=["manual_kill"],
        liquidity_exit_check={"max_spread": 0.08},
        paper_exit_ready=True,
    )

    assert plan.generated_by == "runtime"
    assert plan.paper_intent_allowed is False
    assert plan.execution_allowed is False


def test_complete_exit_plan_rejects_missing_exit_rules() -> None:
    with pytest.raises(ValidationError):
        ExitFoundationPlan(
            exit_plan_id="exit-bad",
            market_id="market-1",
            side="YES",
            status="COMPLETE",
            exit_type="BASIC_PROTECTIVE_EXIT",
            target_exit=0.55,
            stop_loss=0.47,
            orderbook_snapshot_id=1,
        )


def test_blocked_exit_plan_cannot_be_paper_ready() -> None:
    with pytest.raises(ValidationError):
        ExitFoundationPlan(
            exit_plan_id="exit-blocked",
            status="BLOCKED",
            exit_type="BLOCKED_NO_ENTRY_EXIT",
            blockers=["RISK_BLOCKED"],
            paper_exit_ready=True,
        )


def test_exit_plan_cannot_allow_paper_intents_or_execution() -> None:
    with pytest.raises(ValidationError):
        ExitFoundationPlan(exit_plan_id="exit-paper", status="BLOCKED", exit_type="BLOCKED_NO_ENTRY_EXIT", paper_intent_allowed=True)
    with pytest.raises(ValidationError):
        ExitFoundationPlan(exit_plan_id="exit-exec", status="BLOCKED", exit_type="BLOCKED_NO_ENTRY_EXIT", execution_allowed=True)


def test_exit_foundation_run_is_non_executing() -> None:
    with pytest.raises(ValidationError):
        ExitFoundationRun(
            run_id="run-bad",
            status="OK",
            orders_created=1,
            started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )

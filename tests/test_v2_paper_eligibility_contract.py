from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.neural_mesh.paper_eligibility import PaperEligibilityCandidate, PaperEligibilityRun


def test_eligible_candidate_requires_all_mandatory_evidence() -> None:
    candidate = PaperEligibilityCandidate(
        eligibility_id="eligibility-ok",
        thesis_id="thesis",
        risk_decision_id="risk",
        exit_plan_id="exit",
        coordinator_decision_id="coord",
        brain_output_ids=["brain"],
        signal_ids=["signal"],
        market_id="market",
        side="YES",
        status="ELIGIBLE",
        orderbook_snapshot_id=1,
        link_confidence=0.95,
        lineage_trusted=True,
        risk_approved=True,
        exit_ready=True,
        not_dry_run=True,
    )
    assert candidate.paper_intent_allowed is False
    assert candidate.execution_allowed is False


def test_eligible_candidate_rejects_missing_exit_plan_or_lineage() -> None:
    with pytest.raises(ValueError):
        PaperEligibilityCandidate(
            eligibility_id="eligibility-bad",
            thesis_id="thesis",
            risk_decision_id="risk",
            status="ELIGIBLE",
            market_id="market",
            side="YES",
            orderbook_snapshot_id=1,
            risk_approved=True,
            exit_ready=True,
            not_dry_run=True,
        )


def test_candidate_cannot_allow_paper_intents_or_execution() -> None:
    with pytest.raises(ValueError):
        PaperEligibilityCandidate(eligibility_id="eligibility-paper", status="BLOCKED", paper_intent_allowed=True)
    with pytest.raises(ValueError):
        PaperEligibilityCandidate(eligibility_id="eligibility-exec", status="BLOCKED", execution_allowed=True)


def test_paper_eligibility_run_is_non_executing() -> None:
    run = PaperEligibilityRun(run_id="run", status="OK", started_at=datetime.now(UTC))
    assert run.mock_data is False
    assert run.paper_ready_after is False
    with pytest.raises(ValueError):
        PaperEligibilityRun(run_id="bad", status="OK", started_at=datetime.now(UTC), orders_created=1)

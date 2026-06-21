from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.neural_mesh.risk_core import RiskCoreRun, RiskDecision


def test_risk_decision_contract_blocks_execution_and_paper() -> None:
    decision = RiskDecision(
        risk_decision_id="risk-thesis-1",
        thesis_id="thesis-1",
        decision="BLOCK",
        risk_status="BLOCKED",
        blockers=["missing_market_id"],
    )

    assert decision.paper_candidate_allowed is False
    assert decision.execution_allowed is False
    assert decision.risk_approved is False
    assert decision.blockers == ["MISSING_MARKET_ID"]


def test_risk_decision_rejects_paper_candidate_allowed() -> None:
    with pytest.raises(ValueError):
        RiskDecision(
            risk_decision_id="risk-thesis-1",
            thesis_id="thesis-1",
            decision="BLOCK",
            risk_status="BLOCKED",
            paper_candidate_allowed=True,
        )


def test_risk_core_run_rejects_executable_artifacts() -> None:
    with pytest.raises(ValueError):
        RiskCoreRun(
            run_id="run-1",
            status="OK",
            orders_created=1,
            started_at=datetime.now(UTC),
        )


def test_risk_core_run_shape_is_non_mock() -> None:
    run = RiskCoreRun(
        run_id="run-1",
        status="OK",
        thesis_profiles_checked=1,
        blocked_count=1,
        started_at=datetime.now(UTC),
    )

    payload = run.to_api_dict()
    assert payload["mock_data"] is False
    assert payload["paper_ready_after"] is False


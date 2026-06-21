from __future__ import annotations

from app.services import exit_foundation


def _candidate_row(**overrides):
    row = {
        "eligibility_id": "candidate-exit-1",
        "market_id": "market-1",
        "side": "YES",
        "condition_id": "condition-1",
        "token_id": "token-yes",
        "risk_decision_id": "risk-1",
        "orderbook_snapshot_pk": 123,
        "orderbook_snapshot_id": "ob-123",
        "orderbook_best_bid": 0.4,
        "orderbook_best_ask": 0.42,
        "orderbook_mid_price": 0.41,
        "orderbook_spread": 0.02,
        "orderbook_liquidity_score": 0.8,
        "orderbook_is_stale": False,
        "orderbook_snapshot_status": "OK",
        "risk_evidence_decision": "RISK_REVIEW",
        "risk_evidence_blocker": "RISK_REVIEW_EDGE_WEAK",
        "risk_evidence_score": 0.74,
        "risk_evidence_id": "risk-evidence-1",
    }
    row.update(overrides)
    return row


def test_candidate_specific_exit_plan_uses_candidate_orderbook_evidence() -> None:
    plan = exit_foundation._plan_from_candidate(
        _candidate_row(),
        event_id="event-1",
        correlation_id="corr-1",
    )

    assert plan.exit_plan_id == "exit_candidate_candidate-exit-1"
    assert plan.market_id == "market-1"
    assert plan.side == "YES"
    assert plan.orderbook_snapshot_id == 123
    assert plan.status == "COMPLETE"
    assert plan.paper_exit_ready is True
    assert plan.execution_allowed is False
    assert plan.paper_intent_allowed is False
    assert plan.liquidity_exit_check["token_id"] == "token-yes"
    assert plan.liquidity_exit_check["correlation_id"] == "corr-1"


def test_candidate_specific_exit_plan_preserves_real_risk_block() -> None:
    plan = exit_foundation._plan_from_candidate(
        _candidate_row(risk_evidence_decision="RISK_BLOCK", risk_evidence_blocker="RISK_BLOCKED_LINEAGE_CRITICAL"),
        event_id="event-1",
        correlation_id="corr-1",
    )

    assert plan.status == "BLOCKED"
    assert "RISK_BLOCKED" in plan.blockers
    assert "RISK_BLOCKED_LINEAGE_CRITICAL" in plan.blockers
    assert plan.paper_exit_ready is False

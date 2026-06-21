from __future__ import annotations

from app.services.trade_opportunity_score import score_actionability_item
from tests_support_strict_actionability import qualified_actionability_item


def _near_miss(**overrides):
    item = qualified_actionability_item(
        edge_score=0.8,
        fresh_sources_used=["source-a", "source-b"],
        directional_sources_found=2,
        risk_gate_state="RISK_REVIEW_LINEAGE_PARTIAL",
        capital_gate_state="CAPITAL_WATCH",
        risk_capital_policy_state="CAPITAL_WATCH",
        dynamic_rpdh=0.05,
        capital_efficiency_after_thesis=0.55,
        strict_paper_qualification={"qualified": False, "state": "NOT_ACTIONABLE_RISK_REVIEW"},
        joined_trade_thesis={
            "thesis_id": "thesis-1",
            "candidate_id": "candidate-1",
            "side": "YES",
            "token_id": "token-yes",
            "source_refresh_cycle_id": "cycle-1",
            "status": "THESIS_SUPPORTED",
            "trade_thesis_type": "MISPRICING_REVERSION",
            "exit_intent": "PRICE_TARGET_EXIT",
            "expected_hold_time_hours": 48.0,
            "thesis_confidence": 0.75,
            "exit_confidence": 0.68,
            "expected_reward": 6.0,
        },
        risk_capital_gate_trace={
            "classification": "CAPITAL_WATCH",
            "risk_capital_policy_state": "CAPITAL_WATCH",
            "capital_efficiency_score": 0.55,
            "dynamic_reward_per_dollar_hour": 0.05,
        },
    )
    item.update(overrides)
    return item


def test_risk_review_can_be_observation_eligible_not_full_paper() -> None:
    score = score_actionability_item(_near_miss())

    assert score["decision_band"] == "PAPER_OBSERVATION"
    assert score["paper_observation_eligible"] is True
    assert score["full_paper_certification_ready"] is False
    assert "risk_review_not_full_paper_ready" in score["soft_blockers"]


def test_capital_watch_can_be_observation_eligible_not_full_paper() -> None:
    score = score_actionability_item(_near_miss(risk_gate_state="RISK_SUPPORT"))

    assert score["decision_band"] == "PAPER_OBSERVATION"
    assert "capital_watch_not_full_paper_ready" in score["soft_blockers"]


def test_paper_observation_does_not_grant_execution_authority() -> None:
    score = score_actionability_item(_near_miss())

    assert score["learning_only"] is True
    assert score["execution_authority"] == "NONE_DATA_ONLY"

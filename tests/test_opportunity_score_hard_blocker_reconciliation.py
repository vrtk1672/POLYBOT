from __future__ import annotations

from app.services.trade_opportunity_score import score_actionability_item
from tests_support_strict_actionability import qualified_actionability_item


def test_hard_blockers_removed_only_when_matching_evidence_is_clean() -> None:
    score = score_actionability_item(
        qualified_actionability_item(
            risk_gate_state="RISK_REVIEW",
            capital_gate_state="CAPITAL_WATCH",
            risk_capital_gate_trace={
                "classification": "CAPITAL_WATCH",
                "risk_capital_policy_state": "CAPITAL_WATCH",
                "dynamic_reward_per_dollar_hour": 0.05,
            },
            candidate_trusted_orderbook_state="TRUSTED_FRESH_FOR_CANDIDATE",
            candidate_price_path_state="CANDIDATE_PRICE_READY",
            edge_score=1.0,
            fresh_sources_used=["payout", "orderbook", "signal_quality"],
            directional_sources_found=2,
            dynamic_rpdh=0.05,
            joined_trade_thesis={
                "candidate_id": "candidate-1",
                "side": "YES",
                "token_id": "token-yes",
                "source_refresh_cycle_id": "cycle-1",
                "status": "THESIS_SUPPORTED",
                "thesis_confidence": 0.9,
                "exit_confidence": 0.8,
                "expected_reward": 3.0,
            },
        )
    )

    assert score["decision_band"] == "PAPER_OBSERVATION"
    assert score["hard_blockers"] == []
    assert "risk_review_not_full_paper_ready" in score["soft_blockers"]
    assert "capital_watch_not_full_paper_ready" in score["soft_blockers"]


def test_soft_blockers_do_not_become_hard_blockers() -> None:
    score = score_actionability_item(
        qualified_actionability_item(
            risk_gate_state="RISK_REVIEW",
            capital_gate_state="CAPITAL_WATCH",
            risk_capital_gate_trace={
                "classification": "CAPITAL_WATCH",
                "risk_capital_policy_state": "CAPITAL_WATCH",
            },
        )
    )

    assert "risk_hard_blocked" not in score["hard_blockers"]
    assert "capital_hard_blocked" not in score["hard_blockers"]
    assert "risk_review_not_full_paper_ready" in score["soft_blockers"]
    assert "capital_watch_not_full_paper_ready" in score["soft_blockers"]


def test_missing_event_link_keeps_candidate_hard_blocked_even_with_high_score_inputs() -> None:
    score = score_actionability_item(
        qualified_actionability_item(
            candidate_event_scope="NOT_ACTIONABLE",
            candidate_event_actionability_scope="NOT_ACTIONABLE",
            candidate_event_link_state="STALE_CANDIDATE_LINK",
            edge_score=1.0,
            fresh_sources_used=["payout", "orderbook", "signal_quality"],
        )
    )

    assert score["decision_band"] == "HARD_BLOCKED"
    assert "candidate_event_scope_not_actionable" in score["hard_blockers"]
    assert "missing_candidate_event_link" in score["hard_blockers"]


def test_no_paper_artifact_authority_is_granted_by_score() -> None:
    score = score_actionability_item(qualified_actionability_item())

    assert score["execution_authority"] == "NONE_DATA_ONLY"

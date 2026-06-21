from __future__ import annotations

from app.services.trade_opportunity_score import attach_opportunity_score, summarize_opportunity_scores
from tests_support_strict_actionability import qualified_actionability_item


def test_paper_actionability_metadata_exposes_score_and_band() -> None:
    item = attach_opportunity_score(
        qualified_actionability_item(
            edge_score=0.8,
            fresh_sources_used=["source-a", "source-b"],
            directional_sources_found=2,
            dynamic_rpdh=0.12,
            capital_efficiency_after_thesis=0.8,
            strict_paper_qualification={"qualified": True},
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
                "thesis_confidence": 0.8,
                "exit_confidence": 0.7,
                "expected_reward": 8.0,
            },
            risk_capital_gate_trace={
                "classification": "PASSED",
                "risk_capital_policy_state": "CAPITAL_SUPPORT",
                "capital_efficiency_score": 0.8,
                "dynamic_reward_per_dollar_hour": 0.12,
            },
        )
    )

    assert item["opportunity_score"]["overall_score"] > 0
    assert item["decision_band"] == item["opportunity_score"]["decision_band"]
    assert "edge_quality_score" in item["opportunity_score_components"]
    assert item["full_paper_certification_ready"] is True


def test_paper_certification_score_counts_separate_observation_from_full() -> None:
    full = attach_opportunity_score(
        qualified_actionability_item(
            edge_score=0.9,
            fresh_sources_used=["source-a", "source-b", "source-c"],
            directional_sources_found=3,
            dynamic_rpdh=0.15,
            capital_efficiency_after_thesis=0.9,
            strict_paper_qualification={"qualified": True},
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
                "thesis_confidence": 0.9,
                "exit_confidence": 0.8,
                "expected_reward": 10.0,
            },
            risk_capital_gate_trace={
                "classification": "PASSED",
                "risk_capital_policy_state": "CAPITAL_SUPPORT",
                "capital_efficiency_score": 0.9,
                "dynamic_reward_per_dollar_hour": 0.15,
            },
        )
    )
    observation = attach_opportunity_score(
        qualified_actionability_item(
            risk_gate_state="RISK_REVIEW",
            capital_gate_state="CAPITAL_WATCH",
            risk_capital_policy_state="CAPITAL_WATCH",
            dynamic_rpdh=0.05,
            capital_efficiency_after_thesis=0.55,
            strict_paper_qualification={"qualified": False},
            joined_trade_thesis={
                "thesis_id": "thesis-2",
                "candidate_id": "candidate-1",
                "side": "YES",
                "token_id": "token-yes",
                "source_refresh_cycle_id": "cycle-1",
                "status": "THESIS_SUPPORTED",
                "trade_thesis_type": "MISPRICING_REVERSION",
                "exit_intent": "PRICE_TARGET_EXIT",
                "expected_hold_time_hours": 48.0,
                "thesis_confidence": 0.75,
                "exit_confidence": 0.7,
                "expected_reward": 6.0,
            },
            risk_capital_gate_trace={
                "classification": "CAPITAL_WATCH",
                "risk_capital_policy_state": "CAPITAL_WATCH",
                "capital_efficiency_score": 0.55,
                "dynamic_reward_per_dollar_hour": 0.05,
            },
        )
    )

    counts = summarize_opportunity_scores([full, observation])

    assert counts["full_paper_certification"] == 1
    assert counts["paper_observation_eligible"] == 1

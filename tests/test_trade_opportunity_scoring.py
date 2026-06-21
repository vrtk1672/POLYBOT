from __future__ import annotations

from app.services.trade_opportunity_score import score_actionability_item
from tests_support_strict_actionability import qualified_actionability_item


def _strong_item(**overrides):
    item = qualified_actionability_item(
        edge_score=0.82,
        fresh_sources_used=["source-a", "source-b", "source-c"],
        directional_sources_found=3,
        dynamic_rpdh=0.12,
        capital_efficiency_after_thesis=0.85,
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
            "capital_efficiency_score": 0.85,
            "dynamic_reward_per_dollar_hour": 0.12,
        },
    )
    item.update(overrides)
    return item


def test_score_object_is_deterministic_and_exposes_components() -> None:
    item = _strong_item()

    first = score_actionability_item(item)
    second = score_actionability_item(item)

    assert first["opportunity_score_id"] == second["opportunity_score_id"]
    assert first["overall_score"] == second["overall_score"]
    assert set(first["components"]) == {
        "profit_potential_score",
        "edge_quality_score",
        "source_confidence_score",
        "trade_thesis_score",
        "capital_efficiency_score",
        "exit_quality_score",
        "risk_penalty_score",
        "timing_score",
        "confidence_score",
    }


def test_hard_blocker_overrides_high_score() -> None:
    score = score_actionability_item(_strong_item(candidate_event_link_state="TOKEN_SIDE_MISMATCH"))

    assert score["decision_band"] == "HARD_BLOCKED"
    assert "token_side_mismatch" in score["hard_blockers"]


def test_missing_event_link_hard_blocks() -> None:
    score = score_actionability_item(_strong_item(candidate_event_link_state="MISSING_CANDIDATE_EVENT_LINK"))

    assert score["decision_band"] == "HARD_BLOCKED"
    assert "missing_candidate_event_link" in score["hard_blockers"]


def test_capital_block_hard_blocks() -> None:
    score = score_actionability_item(
        _strong_item(
            capital_gate_state="CAPITAL_BLOCK",
            risk_capital_policy_state="CAPITAL_BLOCK",
            risk_capital_gate_trace={"classification": "CAPITAL_BLOCK", "risk_capital_policy_state": "CAPITAL_BLOCK"},
        )
    )

    assert score["decision_band"] == "HARD_BLOCKED"
    assert "capital_hard_blocked" in score["hard_blockers"]


def test_exit_not_ready_hard_blocks() -> None:
    score = score_actionability_item(_strong_item(exit_gate_state="EXIT_NOT_READY", exit_readiness_state="EXIT_NOT_READY"))

    assert score["decision_band"] == "HARD_BLOCKED"
    assert "exit_not_ready" in score["hard_blockers"]

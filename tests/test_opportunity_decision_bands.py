from __future__ import annotations

from app.services.trade_opportunity_score import score_actionability_item
from tests_support_strict_actionability import qualified_actionability_item


def _item(**overrides):
    item = qualified_actionability_item(
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
            "thesis_confidence": 0.85,
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
    item.update(overrides)
    return item


def test_valid_full_paper_candidate_gets_full_certification_band() -> None:
    score = score_actionability_item(_item())

    assert score["decision_band"] == "FULL_PAPER_CERTIFICATION"
    assert score["full_paper_certification_ready"] is True


def test_watch_candidate_gets_watch_only_band() -> None:
    score = score_actionability_item(
        _item(
            edge_state="EDGE_WATCH",
            source_backed=False,
            dynamic_rpdh=0.005,
            capital_efficiency_after_thesis=0.4,
            strict_paper_qualification={"qualified": False},
        )
    )

    assert score["decision_band"] == "WATCH_ONLY"


def test_no_trade_candidate_gets_no_trade_band() -> None:
    score = score_actionability_item(
        _item(
            edge_state="NO_CURRENT_DIRECTIONAL_EDGE",
            source_backed=False,
            risk_usable=False,
            risk_gate_state="RISK_REVIEW",
            capital_gate_state="CAPITAL_WATCH",
            risk_capital_policy_state="CAPITAL_WATCH",
            dynamic_rpdh=None,
            capital_efficiency_after_thesis=0.1,
            risk_capital_gate_trace={"classification": "CAPITAL_WATCH", "risk_capital_policy_state": "CAPITAL_WATCH", "capital_efficiency_score": 0.1},
            joined_trade_thesis={
                "thesis_id": "thesis-1",
                "candidate_id": "candidate-1",
                "side": "YES",
                "token_id": "token-yes",
                "source_refresh_cycle_id": "cycle-1",
                "status": "THESIS_WATCH",
                "trade_thesis_type": "MISPRICING_REVERSION",
                "exit_intent": "PRICE_TARGET_EXIT",
                "expected_hold_time_hours": 48.0,
            },
            candidate_event_link_state="LINKED_TO_CANDIDATE",
            strict_paper_qualification={"qualified": False},
        )
    )

    assert score["decision_band"] == "NO_TRADE"

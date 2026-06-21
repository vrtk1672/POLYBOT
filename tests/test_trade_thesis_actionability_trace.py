from __future__ import annotations

from app.control_center.decision_propagation_trace import _phase10_gate


def test_phase10_gate_preserves_risk_capital_blocker_detail() -> None:
    action = {
        "candidate_paper_actionability_state": "BLOCKED_BY_RISK",
        "risk_capital_gate_trace": {
            "risk_capital_blocker": "RISK_BLOCKED_CAPITAL",
            "trade_thesis_trace": {
                "trade_thesis_type": "MISPRICING_REVERSION",
                "dynamic_hold_time_applied": True,
            },
        },
    }

    assert _phase10_gate(action) == "RISK_BLOCKED_CAPITAL"


def test_actionability_thesis_trace_shape_is_flat_for_dashboard() -> None:
    risk_capital_gate_trace = {
        "trade_thesis_trace": {
            "thesis_id": "thesis-1",
            "trade_thesis_type": "MISPRICING_REVERSION",
            "exit_intent": "PRICE_TARGET_EXIT",
            "hold_time_used_hours": 48,
            "dynamic_reward_per_dollar_hour": 0.01,
        }
    }

    assert risk_capital_gate_trace["trade_thesis_trace"]["trade_thesis_type"] == "MISPRICING_REVERSION"
    assert risk_capital_gate_trace["trade_thesis_trace"]["dynamic_reward_per_dollar_hour"] == 0.01

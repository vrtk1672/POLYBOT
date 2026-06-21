from __future__ import annotations


def qualified_actionability_item(**overrides):
    item = {
        "candidate_id": "candidate-1",
        "market_id": "market-1",
        "side": "YES",
        "token_id": "token-yes",
        "candidate_event_scope": "CANDIDATE_SCOPED",
        "candidate_event_actionability_scope": "CANDIDATE_SCOPED",
        "candidate_event_link_state": "LINKED_TO_CANDIDATE",
        "candidate_paper_actionability_state": "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED",
        "paper_actionability_state": "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED",
        "operational_paper_execution_state": "EXECUTION_DISABLED_PAPER_OFF",
        "edge_state": "EDGE_SUPPORTED",
        "source_backed": True,
        "risk_usable": True,
        "risk_gate_state": "RISK_SUPPORT",
        "capital_gate_state": "CAPITAL_OK",
        "exit_gate_state": "EXIT_READY",
        "exit_readiness_state": "EXIT_READY",
        "source_refresh_cycle_id": "cycle-1",
        "thesis_id": "thesis-1",
        "trade_thesis_type": "MISPRICING_REVERSION",
        "exit_intent": "PRICE_TARGET_EXIT",
        "expected_hold_time_hours": 48.0,
        "hold_time_source": "REVERSION_WINDOW",
        "joined_trade_thesis": {
            "candidate_id": "candidate-1",
            "side": "YES",
            "token_id": "token-yes",
            "source_refresh_cycle_id": "cycle-1",
            "status": "THESIS_SUPPORTED",
        },
        "risk_capital_gate_trace": {
            "classification": "PASSED",
            "risk_capital_policy_state": "CAPITAL_SUPPORT",
        },
        "risk_capital_policy_state": "CAPITAL_SUPPORT",
        "lifecycle_gate_trace": {
            "actionability_class": "ACTIONABLE_SMALL_PAPER",
            "allow_paper_intent": True,
            "critical_blockers": [],
        },
        "stale_gate_selected": False,
        "stale_sources_blocking": [],
        "blockers": [],
    }
    item.update(overrides)
    return item

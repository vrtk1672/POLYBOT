from app.services.paper_observation_policy import build_policy_review
from app.services.trade_opportunity_score import score_actionability_item
from test_paper_observation_policy_review import _row


def test_trade_opportunity_score_exposes_observation_policy_fields_without_execution_authority():
    item = {
        "candidate_id": "candidate-1",
        "market_id": "m1",
        "side": "YES",
        "token_id": "yes-token",
        "edge_state": "EDGE_SUPPORTED",
        "source_backed": True,
        "candidate_event_scope": "CANDIDATE_SCOPED",
        "candidate_event_link_state": "LINKED_TO_CANDIDATE",
        "candidate_trusted_orderbook_state": "FRESH",
        "thesis_id": "thesis-1",
        "joined_trade_thesis": {"status": "THESIS_SUPPORTED", "expected_reward": 5},
        "exit_intent": "TIME_STOP",
        "exit_gate_state": "EXIT_READY",
        "risk_gate_state": "RISK_OK",
        "risk_capital_policy_state": "CAPITAL_WATCH",
        "paper_observation_policy_review_id": "policy-1",
        "paper_observation_policy_state": "OBSERVATION_POLICY_ELIGIBLE",
        "observation_allowed_by_policy": True,
        "observation_policy_blockers": [],
    }

    score = score_actionability_item(item)

    assert score["observation_policy_review_id"] == "policy-1"
    assert score["observation_policy_state"] == "OBSERVATION_POLICY_ELIGIBLE"
    assert score["observation_allowed_by_policy"] is True
    assert score["execution_authority"] == "NONE_DATA_ONLY"


def test_review_record_keeps_policy_visibility_flags_false_for_paper_actionability():
    review = build_policy_review(_row())

    assert review["data_only"] is True
    assert review["observation_policy_review_only"] is True
    assert review["paper_allowed"] is False
    assert review["shadow_allowed"] is False
    assert review["live_allowed"] is False
    assert review["metadata_json"]["observation_execution_mode_implemented"] is False

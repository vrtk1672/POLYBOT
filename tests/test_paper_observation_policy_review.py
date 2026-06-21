from app.services.paper_observation_policy import (
    OBSERVATION_POLICY_ELIGIBLE,
    OBSERVATION_POLICY_INCOMPLETE,
    build_policy_review,
)


def _row(**overrides):
    row = {
        "seed_mesh_result_id": "result-1",
        "seed_mesh_inquiry_id": "inq-1",
        "proactive_candidate_seed_id": "seed-1",
        "adapter_payload_id": "payload-1",
        "targeted_revalidation_id": "reval-1",
        "market_memory_id": "memory-1",
        "source_event_id": "event-1",
        "market_id": "m1",
        "condition_id": "c1",
        "side": "YES",
        "token_id": "yes-token",
        "opportunity_decision_band": "PAPER_OBSERVATION",
        "opportunity_score": 66,
        "edge_state": "EDGE_SUPPORTED",
        "trade_thesis_state": "THESIS_SUPPORTED",
        "risk_state": "RISK_OK",
        "capital_state": "CAPITAL_WATCH",
        "exit_state": "EXIT_READY",
        "lifecycle_state": "DATA_ONLY_RESEARCH",
        "orderbook_refresh_state": "FRESH",
        "token_side_resolution_state": "SIDE_DIRECTIONAL_YES",
        "candidate_event_scope_state": "CANDIDATE_SCOPED",
        "market_memory_status": "ACTIVE",
        "market_active": True,
        "hard_blockers_json": [],
        "soft_blockers_json": ["capital_watch_not_full_paper_ready"],
        "seed_execution_allowed": False,
        "seed_paper_allowed": False,
        "seed_shadow_allowed": False,
        "seed_live_allowed": False,
    }
    row.update(overrides)
    return row


def test_clean_paper_observation_becomes_policy_eligible_without_execution_flags():
    review = build_policy_review(_row())

    assert review["observation_policy_state"] == OBSERVATION_POLICY_ELIGIBLE
    assert review["observation_allowed_by_policy"] is True
    assert review["execution_allowed"] is False
    assert review["paper_allowed"] is False
    assert review["shadow_allowed"] is False
    assert review["live_allowed"] is False
    assert review["metadata_json"]["not_full_paper"] is True


def test_missing_lineage_is_incomplete_not_eligible():
    review = build_policy_review(_row(adapter_payload_id=None, targeted_revalidation_id=None))

    assert review["observation_policy_state"] == OBSERVATION_POLICY_INCOMPLETE
    assert "lineage_not_complete" in review["policy_blockers_json"]
    assert review["observation_allowed_by_policy"] is False

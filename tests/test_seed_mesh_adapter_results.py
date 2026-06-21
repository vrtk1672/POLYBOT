from app.services.proactive_seed_mesh_adapter import (
    build_adapter_payload,
    build_adapter_result,
    build_blocked_adapter_result,
    build_failed_adapter_result,
    evaluate_adapter_request,
)


def clean_row(**overrides):
    row = {
        "seed_mesh_inquiry_id": "seed_mesh_inquiry_1",
        "proactive_candidate_seed_id": "seed_yes",
        "source_event_id": "event_1",
        "event_to_market_link_id": "link_1",
        "targeted_revalidation_id": "reval_1",
        "market_memory_id": "memory_1",
        "research_watchlist_id": "watch_1",
        "market_id": "2365093",
        "condition_id": "cond_1",
        "side": "YES",
        "token_id": "token_yes",
        "priority_band": "HIGH",
        "priority_score": 98,
        "request_state": "SKIPPED",
        "inquiry_research_only": True,
        "inquiry_execution_allowed": False,
        "inquiry_paper_allowed": False,
        "inquiry_shadow_allowed": False,
        "inquiry_live_allowed": False,
        "inquiry_blockers_json": ["SAFE_MESH_CONTRACT_MISSING"],
        "seed_state": "GENERATED",
        "research_only": True,
        "execution_allowed": False,
        "paper_allowed": False,
        "shadow_allowed": False,
        "live_allowed": False,
        "link_confidence": 0.92,
        "direction_confidence": 0.8,
        "orderbook_snapshot_id": "ob_1",
        "orderbook_refresh_state": "FRESH",
        "liquidity_state": "MEDIUM",
        "spread_state": "MEDIUM",
        "movement_state": "NO_CLEAR_MOVE",
        "already_priced_in_state": "NO",
        "candidate_event_scope_state": "CANDIDATE_SCOPED",
        "token_side_resolution_state": "TOKEN_SIDE_DIRECT",
        "blockers_json": [],
    }
    row.update(overrides)
    return row


def mesh_session(edge_state="EDGE_WATCH", risk_usable=False):
    return {
        "mesh_session_id": "full_mesh_inquiry_1",
        "inquiry_state": "PARTIAL",
        "edge_thesis_id": "edge_1",
        "edge_state": edge_state,
        "edge_score": 0.62,
        "source_backed": True,
        "risk_usable": risk_usable,
        "inquiry_edge_thesis": {
            "edge_thesis_id": "edge_1",
            "edge_state": edge_state,
            "edge_score": 0.62,
            "source_backed": True,
            "risk_usable": risk_usable,
            "source_records": [{"source_type": "ORDERBOOK", "supports_side": "YES"}],
        },
    }


def test_mesh_path_missing_or_unsafe_is_exact_failed_reason():
    row = clean_row()
    payload = build_adapter_payload(row, adapter_run_id="run_1")
    result = build_failed_adapter_result(row, payload=payload, reason="SAFE_MESH_DATA_ONLY_PATH_UNAVAILABLE")

    assert result["result_state"] == "FAILED"
    assert "ADAPTER_MESH_INVOCATION_FAILED" in result["hard_blockers_json"]
    assert "SAFE_MESH_DATA_ONLY_PATH_UNAVAILABLE" in result["required_to_improve_json"][0]


def test_blocked_result_does_not_fake_mesh_output():
    verdict = evaluate_adapter_request(clean_row(token_side_resolution_state="TOKEN_SIDE_UNKNOWN"))
    result = build_blocked_adapter_result(clean_row(token_side_resolution_state="TOKEN_SIDE_UNKNOWN"), verdict)

    assert result["result_state"] == "BLOCKED"
    assert result["edge_state"] == "UNKNOWN"
    assert result["trade_thesis_state"] == "UNKNOWN"
    assert result["paper_observation_eligible"] is False


def test_edge_thesis_score_are_linked_when_produced():
    row = clean_row()
    payload = build_adapter_payload(row, adapter_run_id="run_1")
    result = build_adapter_result(row, payload=payload, session=mesh_session(edge_state="EDGE_SUPPORTED", risk_usable=True))

    assert result["edge_state"] == "EDGE_SUPPORTED"
    assert result["metadata_json"]["edge_thesis_id"] == "edge_1"
    assert result["metadata_json"]["trade_thesis_id"]
    assert result["metadata_json"]["opportunity_score_id"]
    assert result["opportunity_decision_band"] in {"HARD_BLOCKED", "WATCH_ONLY", "PAPER_OBSERVATION", "NO_TRADE", "FULL_PAPER_CERTIFICATION"}


def test_opportunity_band_does_not_grant_execution():
    row = clean_row()
    payload = build_adapter_payload(row, adapter_run_id="run_1")
    result = build_adapter_result(row, payload=payload, session=mesh_session(edge_state="EDGE_SUPPORTED", risk_usable=True))

    assert result["metadata_json"]["execution_allowed"] is False
    assert result["metadata_json"]["paper_allowed"] is False
    assert result["metadata_json"]["paper_observation_classification_only"] is True

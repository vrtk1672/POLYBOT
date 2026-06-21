from app.services.proactive_seed_mesh_adapter import (
    MESH_DATA_ONLY_COMPLETED,
    build_adapter_payload,
    build_adapter_result,
    build_mesh_bundle_from_payload,
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
        "seed_type": "EVENT_RECALL_REVALIDATED_MARKET",
        "research_only": True,
        "execution_allowed": False,
        "paper_allowed": False,
        "shadow_allowed": False,
        "live_allowed": False,
        "link_type": "DIRECT_LINK",
        "link_confidence": 0.92,
        "direction_for_market": "YES",
        "direction_confidence": 0.8,
        "orderbook_snapshot_id": "ob_1",
        "orderbook_refresh_state": "FRESH",
        "liquidity_state": "MEDIUM",
        "spread_state": "MEDIUM",
        "payout_odds_state": "AVAILABLE",
        "movement_state": "NO_CLEAR_MOVE",
        "already_priced_in_state": "NO",
        "candidate_event_scope_state": "CANDIDATE_SCOPED",
        "token_side_resolution_state": "TOKEN_SIDE_DIRECT",
        "blockers_json": [],
        "soft_warnings_json": [],
        "required_to_pass_json": [],
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


def test_clean_high_yes_seed_request_is_adapter_selected():
    verdict = evaluate_adapter_request(clean_row())

    assert verdict["selected"] is True
    assert verdict["blockers"] == []


def test_clean_medium_no_seed_request_is_adapter_selected():
    verdict = evaluate_adapter_request(clean_row(side="NO", token_id="token_no", priority_band="MEDIUM", direction_for_market="NO"))

    assert verdict["selected"] is True


def test_adapter_payload_is_research_only_namespaced():
    payload = build_adapter_payload(clean_row(), adapter_run_id="run_1")

    assert payload["synthetic_candidate_id"] == "research_seed_candidate_seed_yes"
    assert payload["payload_type"] == "PROACTIVE_SEED_RESEARCH_CANDIDATE"
    assert payload["research_only"] is True
    assert payload["execution_allowed"] is False
    assert payload["paper_allowed"] is False
    assert payload["shadow_allowed"] is False
    assert payload["live_allowed"] is False


def test_mesh_bundle_preserves_data_only_lineage_and_flags():
    payload = build_adapter_payload(clean_row(), adapter_run_id="run_1")
    bundle = build_mesh_bundle_from_payload(payload)

    assert bundle["candidate_id"].startswith("research_seed_candidate_")
    assert bundle["research_only"] is True
    assert bundle["execution_allowed"] is False
    assert bundle["paper_allowed"] is False
    assert bundle["candidate_event_actionability_scope"] == "CANDIDATE_SCOPED"
    assert bundle["lineage"]["source_event_id"] == "event_1"


def test_adapter_result_is_data_only_completed_without_execution_grant():
    row = clean_row()
    payload = build_adapter_payload(row, adapter_run_id="run_1")
    result = build_adapter_result(row, payload=payload, session=mesh_session())

    assert result["result_state"] == MESH_DATA_ONLY_COMPLETED
    assert result["metadata_json"]["research_only"] is True
    assert result["metadata_json"]["execution_allowed"] is False
    assert result["metadata_json"]["paper_allowed"] is False
    assert result["metadata_json"]["paper_observation_classification_only"] is True

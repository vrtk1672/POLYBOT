from app.services.proactive_seed_mesh_inquiry import (
    ProactiveSeedMeshInquiryService,
    build_seed_mesh_inquiry_request,
    build_seed_mesh_result,
    evaluate_seed_mesh_selection,
)


def clean_seed(**overrides):
    seed = {
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
        "seed_state": "GENERATED",
        "research_only": True,
        "execution_allowed": False,
        "paper_allowed": False,
        "shadow_allowed": False,
        "live_allowed": False,
        "orderbook_refresh_state": "FRESH",
        "token_side_resolution_state": "TOKEN_SIDE_DIRECT",
        "priority_band": "HIGH",
        "priority_score": 98,
        "blockers_json": [],
    }
    seed.update(overrides)
    return seed


def test_inquiry_request_carries_full_lineage():
    seed = clean_seed()
    verdict = evaluate_seed_mesh_selection(seed)
    request = build_seed_mesh_inquiry_request(seed, verdict=verdict, run_id="run_1")

    lineage = request["metadata_json"]["lineage"]
    assert lineage["source_event_id"] == "event_1"
    assert lineage["event_to_market_link_id"] == "link_1"
    assert lineage["targeted_revalidation_id"] == "reval_1"
    assert lineage["proactive_candidate_seed_id"] == "seed_yes"
    assert lineage["research_watchlist_id"] == "watch_1"


def test_result_surface_fields_are_read_only_unknown_when_skipped():
    seed = clean_seed()
    verdict = evaluate_seed_mesh_selection(seed)
    request = build_seed_mesh_inquiry_request(seed, verdict=verdict, run_id="run_1")
    result = build_seed_mesh_result(request)

    assert result["edge_state"] == "UNKNOWN"
    assert result["risk_state"] == "UNKNOWN"
    assert result["capital_state"] == "UNKNOWN"
    assert result["exit_state"] == "UNKNOWN"
    assert result["lifecycle_state"] == "UNKNOWN"
    assert result["paper_observation_eligible"] is False
    assert result["full_paper_ready"] is False


def test_empty_seed_fields_are_prefixed_to_avoid_edge_collision():
    fields = ProactiveSeedMeshInquiryService().fields_for_seed(proactive_candidate_seed_id=None)

    assert "seed_mesh_edge_state" in fields
    assert "edge_state" not in fields
    assert fields["mesh_inquiry_request_count"] == 0


def test_empty_market_fields_expose_counts():
    fields = ProactiveSeedMeshInquiryService().fields_for_market(market_id=None)

    assert fields["seed_mesh_inquiry_count"] == 0
    assert fields["mesh_completed_count"] == 0
    assert fields["paper_observation_interest_from_seed_mesh"] == 0

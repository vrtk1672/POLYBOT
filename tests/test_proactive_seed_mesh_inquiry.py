from app.services.proactive_seed_mesh_inquiry import (
    SAFE_MESH_CONTRACT_MISSING,
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


def test_clean_high_priority_yes_seed_gets_data_only_request():
    verdict = evaluate_seed_mesh_selection(clean_seed())
    request = build_seed_mesh_inquiry_request(clean_seed(), verdict=verdict, run_id="run_1")

    assert verdict["selected"] is True
    assert request["request_state"] == "SKIPPED"
    assert request["mesh_handoff_mode"] == "DATA_ONLY"
    assert request["research_only"] is True
    assert request["execution_allowed"] is False
    assert request["paper_allowed"] is False
    assert request["shadow_allowed"] is False
    assert request["live_allowed"] is False
    assert SAFE_MESH_CONTRACT_MISSING in request["blockers_json"]


def test_clean_medium_priority_no_seed_gets_data_only_request():
    seed = clean_seed(proactive_candidate_seed_id="seed_no", side="NO", token_id="token_no", priority_band="MEDIUM", priority_score=64)
    verdict = evaluate_seed_mesh_selection(seed)

    assert verdict["selected"] is True
    assert verdict["request_state"] == "SKIPPED"


def test_result_is_transparent_skipped_not_fake_mesh_approval():
    verdict = evaluate_seed_mesh_selection(clean_seed())
    request = build_seed_mesh_inquiry_request(clean_seed(), verdict=verdict, run_id="run_1")
    result = build_seed_mesh_result(request)

    assert result["result_state"] == "SKIPPED"
    assert result["edge_state"] == "UNKNOWN"
    assert result["trade_thesis_state"] == "UNKNOWN"
    assert result["opportunity_decision_band"] == "UNKNOWN"
    assert result["paper_observation_eligible"] is False
    assert result["full_paper_ready"] is False
    assert result["metadata_json"]["fake_mesh_result"] is False
    assert result["metadata_json"]["paper_intent_created"] is False


def test_low_priority_seed_skipped_before_mesh_contract():
    verdict = evaluate_seed_mesh_selection(clean_seed(priority_band="LOW"))

    assert verdict["selected"] is False
    assert verdict["request_state"] == "BLOCKED"
    assert "PRIORITY_NOT_SELECTED_LOW" in verdict["blockers"]

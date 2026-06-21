from app.services.proactive_seed_mesh_inquiry import build_seed_mesh_inquiry_request, evaluate_seed_mesh_selection


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


def test_execution_allowed_seed_is_rejected():
    verdict = evaluate_seed_mesh_selection(clean_seed(execution_allowed=True))

    assert verdict["selected"] is False
    assert "EXECUTION_ALLOWED_MUST_BE_FALSE" in verdict["blockers"]


def test_paper_allowed_seed_is_rejected():
    verdict = evaluate_seed_mesh_selection(clean_seed(paper_allowed=True))

    assert verdict["selected"] is False
    assert "PAPER_ALLOWED_MUST_BE_FALSE" in verdict["blockers"]


def test_shadow_and_live_allowed_seed_is_rejected():
    verdict = evaluate_seed_mesh_selection(clean_seed(shadow_allowed=True, live_allowed=True))

    assert verdict["selected"] is False
    assert "SHADOW_ALLOWED_MUST_BE_FALSE" in verdict["blockers"]
    assert "LIVE_ALLOWED_MUST_BE_FALSE" in verdict["blockers"]


def test_request_preserves_all_execution_flags_false_even_for_selected_seed():
    seed = clean_seed()
    verdict = evaluate_seed_mesh_selection(seed)
    request = build_seed_mesh_inquiry_request(seed, verdict=verdict, run_id="run_1")

    assert request["research_only"] is True
    assert request["execution_allowed"] is False
    assert request["paper_allowed"] is False
    assert request["shadow_allowed"] is False
    assert request["live_allowed"] is False


def test_mesh_handoff_never_implies_completion_when_contract_missing():
    seed = clean_seed()
    verdict = evaluate_seed_mesh_selection(seed)
    request = build_seed_mesh_inquiry_request(seed, verdict=verdict, run_id="run_1")

    assert request["request_state"] == "SKIPPED"
    assert request["mesh_inquiry_session_id"] is None
    assert request["edge_result_id"] is None
    assert request["trade_thesis_id"] is None
    assert request["opportunity_score_id"] is None

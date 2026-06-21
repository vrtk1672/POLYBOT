from app.services.proactive_seed_mesh_inquiry import evaluate_seed_mesh_selection


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


def test_side_unknown_seed_skipped():
    verdict = evaluate_seed_mesh_selection(clean_seed(side="SIDE_UNKNOWN", token_id=None))

    assert verdict["selected"] is False
    assert "SIDE_NOT_MESH_ELIGIBLE" in verdict["blockers"]
    assert "TOKEN_ID_MISSING" in verdict["blockers"]


def test_watch_only_seed_skipped():
    verdict = evaluate_seed_mesh_selection(clean_seed(seed_state="WATCH_ONLY"))

    assert verdict["selected"] is False
    assert "SEED_STATE_NOT_GENERATED_WATCH_ONLY" in verdict["blockers"]


def test_blocked_seed_skipped():
    verdict = evaluate_seed_mesh_selection(clean_seed(seed_state="BLOCKED", blockers_json=["TOKEN_SIDE_CONFLICT"]))

    assert verdict["selected"] is False
    assert "SEED_STATE_NOT_GENERATED_BLOCKED" in verdict["blockers"]
    assert "TOKEN_SIDE_CONFLICT" in verdict["blockers"]


def test_dormant_seed_skipped():
    verdict = evaluate_seed_mesh_selection(clean_seed(priority_band="DORMANT"))

    assert verdict["selected"] is False
    assert "PRIORITY_NOT_SELECTED_DORMANT" in verdict["blockers"]


def test_stale_orderbook_seed_skipped():
    verdict = evaluate_seed_mesh_selection(clean_seed(orderbook_refresh_state="STALE"))

    assert verdict["selected"] is False
    assert "ORDERBOOK_NOT_FRESH" in verdict["blockers"]


def test_token_side_unknown_seed_skipped():
    verdict = evaluate_seed_mesh_selection(clean_seed(token_side_resolution_state="TOKEN_SIDE_UNKNOWN"))

    assert verdict["selected"] is False
    assert "TOKEN_SIDE_NOT_DIRECT" in verdict["blockers"]

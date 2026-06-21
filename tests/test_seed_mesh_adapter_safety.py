from app.services.proactive_seed_mesh_adapter import evaluate_adapter_request


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
        "orderbook_refresh_state": "FRESH",
        "candidate_event_scope_state": "CANDIDATE_SCOPED",
        "token_side_resolution_state": "TOKEN_SIDE_DIRECT",
        "blockers_json": [],
    }
    row.update(overrides)
    return row


def test_side_unknown_skipped():
    verdict = evaluate_adapter_request(clean_row(side="SIDE_UNKNOWN", token_id=None))

    assert verdict["selected"] is False
    assert "SIDE_NOT_ADAPTER_ELIGIBLE" in verdict["blockers"]


def test_watch_only_seed_skipped():
    verdict = evaluate_adapter_request(clean_row(seed_state="WATCH_ONLY"))

    assert verdict["selected"] is False
    assert "SEED_STATE_NOT_GENERATED" in verdict["blockers"]


def test_blocked_seed_skipped():
    verdict = evaluate_adapter_request(clean_row(seed_state="BLOCKED"))

    assert verdict["selected"] is False
    assert "SEED_STATE_NOT_GENERATED" in verdict["blockers"]


def test_stale_orderbook_skipped():
    verdict = evaluate_adapter_request(clean_row(orderbook_refresh_state="STALE"))

    assert verdict["selected"] is False
    assert "ORDERBOOK_NOT_FRESH" in verdict["blockers"]


def test_token_side_unknown_skipped():
    verdict = evaluate_adapter_request(clean_row(token_side_resolution_state="TOKEN_SIDE_UNKNOWN"))

    assert verdict["selected"] is False
    assert "TOKEN_SIDE_NOT_DIRECT" in verdict["blockers"]


def test_execution_allowed_seed_rejected():
    verdict = evaluate_adapter_request(clean_row(execution_allowed=True))

    assert verdict["selected"] is False
    assert "EXECUTION_ALLOWED_MUST_BE_FALSE" in verdict["blockers"]


def test_paper_allowed_seed_rejected():
    verdict = evaluate_adapter_request(clean_row(paper_allowed=True))

    assert verdict["selected"] is False
    assert "PAPER_ALLOWED_MUST_BE_FALSE" in verdict["blockers"]


def test_candidate_event_scope_must_be_candidate_scoped():
    verdict = evaluate_adapter_request(clean_row(candidate_event_scope_state="MARKET_LEVEL_ONLY"))

    assert verdict["selected"] is False
    assert "CANDIDATE_EVENT_SCOPE_NOT_CANDIDATE_SCOPED" in verdict["blockers"]

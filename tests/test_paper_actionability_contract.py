from __future__ import annotations

from app.control_center.paper_actionability import _map_actionability


def _bundle(
    decision: str = "PRICE_READY",
    *,
    scope: str = "CANDIDATE_SCOPED",
    confidence: str = "HIGH",
    conflicts=None,
    opinions=None,
):
    return {
        "candidate_event_actionability_scope": scope,
        "correlation_confidence": confidence,
        "bundle_state": "COMPLETE",
        "conflicts": conflicts or [],
        "coordinator": {"decision": decision},
        "opinions": opinions
        or {
            "liquidity": {"state": "PRESENT"},
            "risk": {"state": "PRESENT", "blockers": []},
            "exit": {"state": "PRESENT", "blockers": []},
            "capital": {"capital_opinion_state": "CAPITAL_OK", "state": "PRESENT"},
            "lifecycle": {"lifecycle_opinion_state": "LIFECYCLE_ALLOWED", "state": "PRESENT"},
        },
    }


def test_all_five_ready_maps_to_actionable_small_paper() -> None:
    state, operational, confidence, blockers, required, next_state = _map_actionability(
        _bundle(),
        {"candidate_price_path_state": "CANDIDATE_PRICE_READY"},
        paper_simulation_enabled=True,
    )

    assert state == "ACTIONABLE_SMALL_PAPER"
    assert operational == "EXECUTION_READY_IF_ENABLED"
    assert confidence == "HIGH"
    assert blockers == []
    assert next_state == "READY_FOR_PAPER_CERTIFICATION"
    assert any("candidate-scoped mesh gates" in item for item in required)


def test_all_five_ready_with_paper_off_maps_to_actionable_if_enabled() -> None:
    state, operational, confidence, blockers, required, next_state = _map_actionability(
        _bundle(),
        {"candidate_price_path_state": "CANDIDATE_PRICE_READY"},
        paper_simulation_enabled=False,
    )

    assert state == "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED"
    assert operational == "EXECUTION_DISABLED_PAPER_OFF"
    assert confidence == "HIGH"
    assert blockers == ["PAPER_SIMULATION_OFF"]
    assert next_state == "ENABLE_PAPER_SIMULATION_IN_PHASE_10_ONLY"
    assert required


def test_lifecycle_denied_maps_to_blocked_by_lifecycle() -> None:
    state, _operational, _confidence, blockers, _required, _next = _map_actionability(_bundle("LIFECYCLE_BLOCKED"), {"candidate_price_path_state": "CANDIDATE_PRICE_READY"})

    assert state == "BLOCKED_BY_LIFECYCLE"
    assert "BLOCKED_BY_LIFECYCLE" in blockers


def test_lifecycle_stale_maps_to_waiting_for_lifecycle() -> None:
    bundle = _bundle(opinions={"lifecycle": {"lifecycle_opinion_state": "LIFECYCLE_STALE"}, "capital": {"capital_opinion_state": "CAPITAL_OK"}, "risk": {"state": "PRESENT", "blockers": []}, "exit": {"state": "PRESENT", "blockers": []}, "liquidity": {"state": "PRESENT"}})
    state, _operational, _confidence, blockers, _required, _next = _map_actionability(bundle, {"candidate_price_path_state": "CANDIDATE_PRICE_READY"})

    assert state == "WAITING_FOR_LIFECYCLE"
    assert "WAITING_FOR_LIFECYCLE" in blockers


def test_capital_blocked_maps_to_blocked_by_capital() -> None:
    state, _operational, _confidence, blockers, _required, _next = _map_actionability(_bundle("CAPITAL_BLOCKED"), {"candidate_price_path_state": "CANDIDATE_PRICE_READY"})

    assert state == "BLOCKED_BY_CAPITAL"
    assert "BLOCKED_BY_CAPITAL" in blockers


def test_capital_missing_maps_to_waiting_for_capital() -> None:
    bundle = _bundle(opinions={"capital": {"capital_opinion_state": "CAPITAL_MISSING"}, "lifecycle": {"lifecycle_opinion_state": "LIFECYCLE_ALLOWED"}, "risk": {"state": "PRESENT", "blockers": []}, "exit": {"state": "PRESENT", "blockers": []}, "liquidity": {"state": "PRESENT"}})
    state, _operational, _confidence, blockers, _required, _next = _map_actionability(bundle, {"candidate_price_path_state": "CANDIDATE_PRICE_READY"})

    assert state == "WAITING_FOR_CAPITAL"
    assert "WAITING_FOR_CAPITAL" in blockers


def test_risk_blocked_maps_to_blocked_by_risk() -> None:
    bundle = _bundle(opinions={"risk": {"state": "PRESENT", "blockers": ["RISK_BLOCKED"]}, "exit": {"state": "PRESENT", "blockers": []}, "capital": {"capital_opinion_state": "CAPITAL_OK"}, "lifecycle": {"lifecycle_opinion_state": "LIFECYCLE_ALLOWED"}, "liquidity": {"state": "PRESENT"}})
    state, _operational, _confidence, blockers, _required, _next = _map_actionability(bundle, {"candidate_price_path_state": "CANDIDATE_PRICE_READY"})

    assert state == "BLOCKED_BY_RISK"
    assert "BLOCKED_BY_RISK" in blockers


def test_exit_blocked_maps_to_blocked_by_exit() -> None:
    bundle = _bundle(opinions={"exit": {"state": "PRESENT", "blockers": ["EXIT_NOT_READY"]}, "risk": {"state": "PRESENT", "blockers": []}, "capital": {"capital_opinion_state": "CAPITAL_OK"}, "lifecycle": {"lifecycle_opinion_state": "LIFECYCLE_ALLOWED"}, "liquidity": {"state": "PRESENT"}})
    state, _operational, _confidence, blockers, _required, _next = _map_actionability(bundle, {"candidate_price_path_state": "CANDIDATE_PRICE_READY"})

    assert state == "BLOCKED_BY_EXIT"
    assert "BLOCKED_BY_EXIT" in blockers


def test_duplicate_active_intent_maps_to_blocked_by_duplicate() -> None:
    state, operational, _confidence, blockers, _required, _next = _map_actionability(
        _bundle(),
        {"candidate_price_path_state": "CANDIDATE_PRICE_READY"},
        duplicate_active_intent_risk=True,
    )

    assert state == "BLOCKED_BY_DUPLICATE"
    assert operational == "EXECUTION_DISABLED_SAFETY"
    assert "BLOCKED_BY_DUPLICATE" in blockers


def test_open_position_conflict_maps_to_blocked_by_open_position() -> None:
    state, operational, _confidence, blockers, _required, _next = _map_actionability(
        _bundle(),
        {"candidate_price_path_state": "CANDIDATE_PRICE_READY"},
        open_paper_position_conflict=True,
    )

    assert state == "BLOCKED_BY_OPEN_POSITION"
    assert operational == "EXECUTION_DISABLED_SAFETY"
    assert "BLOCKED_BY_OPEN_POSITION" in blockers


def test_stale_orderbook_maps_to_waiting_for_price_refresh() -> None:
    state, _operational, _confidence, blockers, _required, _next = _map_actionability(_bundle(), {"candidate_price_path_state": "CANDIDATE_STALE_ORDERBOOK"})

    assert state == "WAITING_FOR_PRICE_REFRESH"
    assert "WAITING_FOR_PRICE_REFRESH" in blockers


def test_market_level_event_maps_to_blocked_by_data() -> None:
    state, _operational, confidence, blockers, _required, _next = _map_actionability(
        _bundle(scope="MARKET_SCOPED_ONLY", confidence="LOW"),
        {"candidate_price_path_state": "CANDIDATE_PRICE_READY"},
    )

    assert state == "BLOCKED_BY_DATA"
    assert confidence == "LOW"
    assert "MARKET_LEVEL_EVENT_NOT_CANDIDATE_ACTIONABLE" in blockers


def test_conflicted_lifecycle_uses_specific_blocker_not_generic_no_trade() -> None:
    state, _operational, _confidence, blockers, _required, _next = _map_actionability(
        _bundle("LIFECYCLE_BLOCKED", conflicts=[{"type": "LIFECYCLE_DENIED_COORDINATOR_PRICE_READY"}]),
        {"candidate_price_path_state": "CANDIDATE_PRICE_READY"},
    )

    assert state == "BLOCKED_BY_LIFECYCLE"
    assert "BLOCKED_BY_LIFECYCLE" in blockers
    assert "NO_TRADE" not in blockers

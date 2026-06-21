from __future__ import annotations

from app.services.multi_trigger_candidate_generation import _seed_id, _trigger, build_seed_from_trigger, evaluate_trigger


def row(**overrides):
    data = {
        "market_memory_id": "memory_dupe",
        "market_id": "market_dupe",
        "condition_id": "condition_dupe",
        "status": "ACTIVE",
        "market_status": "ACTIVE",
        "yes_token_id": "yes_token",
        "no_token_id": "no_token",
        "token_verification_state": "TOKENS_VERIFIED",
        "priority_band": "HIGH",
        "priority_score": 85,
    }
    data.update(overrides)
    return data


def test_trigger_id_is_deterministic_by_type_market_side_source() -> None:
    first = _trigger(row(id=1), "MARKET_MOVEMENT", "YES", 0.8, 0.8, "market_movement_id", "movement_1", ["RECENT_MARKET_MOVEMENT"])
    second = _trigger(row(id=1), "MARKET_MOVEMENT", "YES", 0.8, 0.8, "market_movement_id", "movement_1", ["RECENT_MARKET_MOVEMENT"])

    assert first["multi_trigger_id"] == second["multi_trigger_id"]


def test_seed_id_is_deterministic_for_trigger_and_side() -> None:
    assert _seed_id("trigger_1", "YES") == _seed_id("trigger_1", "YES")
    assert _seed_id("trigger_1", "YES") != _seed_id("trigger_1", "NO")


def test_duplicate_trigger_builds_same_seed_not_new_seed() -> None:
    first = _trigger(row(id=1), "ORDERBOOK_PRESSURE", "YES", 0.8, 0.8, "orderbook_signal_id", "orderbook_1", ["ORDERBOOK_PRESSURE"])
    second = _trigger(row(id=1), "ORDERBOOK_PRESSURE", "YES", 0.8, 0.8, "orderbook_signal_id", "orderbook_1", ["ORDERBOOK_PRESSURE"])
    first.update(evaluate_trigger(first))
    second.update(evaluate_trigger(second))

    assert build_seed_from_trigger(first)["proactive_candidate_seed_id"] == build_seed_from_trigger(second)["proactive_candidate_seed_id"]


def test_different_trigger_source_creates_different_lineage() -> None:
    first = _trigger(row(id=1), "ORDERBOOK_PRESSURE", "YES", 0.8, 0.8, "orderbook_signal_id", "orderbook_1", ["ORDERBOOK_PRESSURE"])
    second = _trigger(row(id=2), "ORDERBOOK_PRESSURE", "YES", 0.8, 0.8, "orderbook_signal_id", "orderbook_2", ["ORDERBOOK_PRESSURE"])

    assert first["multi_trigger_id"] != second["multi_trigger_id"]

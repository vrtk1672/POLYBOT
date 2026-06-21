from __future__ import annotations

from app.services.multi_trigger_candidate_generation import build_seed_from_trigger, evaluate_trigger


def trigger(**overrides):
    row = {
        "multi_trigger_id": "multi_trigger_market_move_yes",
        "trigger_run_id": "run_1",
        "trigger_type": "MARKET_MOVEMENT",
        "market_memory_id": "memory_1",
        "market_id": "market_1",
        "condition_id": "condition_1",
        "side_hint": "YES",
        "side_confidence": 0.82,
        "trigger_strength": 0.82,
        "trigger_confidence": 0.78,
        "trigger_score": 82.0,
        "evidence_summary": "market movement trigger",
        "trigger_reasons_json": ["RECENT_MARKET_MOVEMENT"],
        "research_priority_band": "HIGH",
        "research_priority_score": 90,
        "market_status": "ACTIVE",
        "token_verification_state": "TOKENS_VERIFIED",
        "yes_token_id": "yes_token",
        "no_token_id": "no_token",
        "orderbook_snapshot_id": "orderbook_1",
        "market_movement_id": "movement_1",
    }
    row.update(overrides)
    return row


def test_market_movement_trigger_can_create_research_yes_seed() -> None:
    item = trigger()
    item.update(evaluate_trigger(item))

    seed = build_seed_from_trigger(item)

    assert seed["seed_state"] == "GENERATED"
    assert seed["seed_type"] == "MARKET_MOVEMENT_TRIGGER"
    assert seed["side"] == "YES"
    assert seed["token_id"] == "yes_token"
    assert seed["research_only"] is True
    assert seed["execution_allowed"] is False
    assert seed["paper_allowed"] is False
    assert seed["shadow_allowed"] is False
    assert seed["live_allowed"] is False


def test_payout_discrepancy_trigger_can_create_no_seed_when_side_clear() -> None:
    item = trigger(
        multi_trigger_id="multi_trigger_payout_no",
        trigger_type="PAYOUT_DISCREPANCY",
        side_hint="NO",
        payout_odds_evaluation_id="payout_eval_1",
    )
    item.update(evaluate_trigger(item))

    seed = build_seed_from_trigger(item)

    assert seed["seed_state"] == "GENERATED"
    assert seed["seed_type"] == "PAYOUT_DISCREPANCY_TRIGGER"
    assert seed["side"] == "NO"
    assert seed["token_id"] == "no_token"
    assert seed["payout_odds_state"] == "AVAILABLE"


def test_orderbook_pressure_trigger_uses_verified_token_side() -> None:
    item = trigger(
        multi_trigger_id="multi_trigger_orderbook_yes",
        trigger_type="ORDERBOOK_PRESSURE",
        side_hint="YES",
        orderbook_signal_id="orderbook_signal_1",
    )
    item.update(evaluate_trigger(item))

    seed = build_seed_from_trigger(item)

    assert seed["seed_state"] == "GENERATED"
    assert seed["seed_type"] == "ORDERBOOK_PRESSURE_TRIGGER"
    assert seed["token_id"] == "yes_token"
    assert seed["movement_state"] == "ACTIVE"


def test_whale_market_level_trigger_is_watch_only_without_side() -> None:
    item = trigger(
        multi_trigger_id="multi_trigger_whale_watch",
        trigger_type="WHALE",
        side_hint="SIDE_UNKNOWN",
        whale_event_id="whale_score_1",
        trigger_score=72,
    )
    item.update(evaluate_trigger(item))

    seed = build_seed_from_trigger(item)

    assert item["seed_generation_state"] == "WATCH_ONLY"
    assert seed["seed_state"] == "WATCH_ONLY"
    assert seed["side"] == "SIDE_UNKNOWN"
    assert seed["token_id"] is None
    assert "SIDE_UNKNOWN_NOT_ACTIONABLE" in seed["soft_warnings_json"]

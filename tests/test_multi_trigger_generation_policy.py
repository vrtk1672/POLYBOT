from __future__ import annotations

from app.services.multi_trigger_candidate_generation import build_seed_from_trigger, evaluate_trigger
from test_multi_trigger_candidate_generation import trigger


def test_side_unknown_creates_watch_only_not_actionable_seed() -> None:
    item = trigger(side_hint="SIDE_UNKNOWN", trigger_score=70)
    item.update(evaluate_trigger(item))
    seed = build_seed_from_trigger(item)

    assert item["seed_generation_state"] == "WATCH_ONLY"
    assert seed["seed_state"] == "WATCH_ONLY"
    assert seed["side"] == "SIDE_UNKNOWN"
    assert seed["execution_allowed"] is False


def test_low_confidence_blocks_or_watch_only_without_fake_side() -> None:
    item = trigger(trigger_score=25, trigger_strength=0.2, trigger_confidence=0.2)
    item.update(evaluate_trigger(item))

    assert item["seed_generation_state"] == "BLOCKED"
    assert "TRIGGER_CONFIDENCE_TOO_LOW" in item["guardrail_blockers_json"]


def test_unverified_token_blocks_seed_generation() -> None:
    item = trigger(token_verification_state="TOKENS_MISMATCH")
    item.update(evaluate_trigger(item))

    assert item["seed_generation_state"] == "BLOCKED"
    assert "TOKENS_NOT_VERIFIED" in item["guardrail_blockers_json"]


def test_closed_market_blocks_seed_generation() -> None:
    item = trigger(market_status="CLOSED")
    item.update(evaluate_trigger(item))

    assert item["seed_generation_state"] == "BLOCKED"
    assert "MARKET_NOT_ACTIVE" in item["guardrail_blockers_json"]


def test_low_priority_market_is_not_selected_by_default() -> None:
    item = trigger(research_priority_band="LOW")
    item.update(evaluate_trigger(item))

    assert item["seed_generation_state"] == "BLOCKED"
    assert "PRIORITY_NOT_SELECTED" in item["guardrail_blockers_json"]


def test_missing_side_token_blocks_actionable_seed() -> None:
    item = trigger(side_hint="YES", yes_token_id=None)
    item.update(evaluate_trigger(item))

    assert item["seed_generation_state"] == "BLOCKED"
    assert "SIDE_TOKEN_MISSING" in item["guardrail_blockers_json"]

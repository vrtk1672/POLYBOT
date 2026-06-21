from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ai_brain.cache import AICache, is_expired, stable_hash
from app.ai_brain.contracts import AITaskType


def test_identical_request_has_same_cache_key_and_changed_inputs_miss() -> None:
    cache = AICache()
    base = cache.build_cache_key(
        task_type=AITaskType.RULES_SUMMARY,
        market_id="m1",
        input_hash=stable_hash({"rules_hash": "a", "snapshot_hash": "s1"}),
        prompt_version_id="p1",
        model_name="qwen3:14b",
    )
    same = cache.build_cache_key(
        task_type=AITaskType.RULES_SUMMARY,
        market_id="m1",
        input_hash=stable_hash({"rules_hash": "a", "snapshot_hash": "s1"}),
        prompt_version_id="p1",
        model_name="qwen3:14b",
    )
    changed_rules = cache.build_cache_key(
        task_type=AITaskType.RULES_SUMMARY,
        market_id="m1",
        input_hash=stable_hash({"rules_hash": "b", "snapshot_hash": "s1"}),
        prompt_version_id="p1",
        model_name="qwen3:14b",
    )
    changed_snapshot = cache.build_cache_key(
        task_type=AITaskType.RULES_SUMMARY,
        market_id="m1",
        input_hash=stable_hash({"rules_hash": "a", "snapshot_hash": "s2"}),
        prompt_version_id="p1",
        model_name="qwen3:14b",
    )
    assert base == same
    assert base != changed_rules
    assert base != changed_snapshot


def test_expired_cache_ignored_helper() -> None:
    assert is_expired(datetime.now(UTC) - timedelta(seconds=1)) is True
    assert is_expired(datetime.now(UTC) + timedelta(seconds=30)) is False

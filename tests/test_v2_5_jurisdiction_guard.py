from __future__ import annotations

from app.rules_neuron.jurisdiction_guard import evaluate_jurisdiction


def test_jurisdiction_guard_unknown_block_and_clear() -> None:
    unknown, _ = evaluate_jurisdiction("m1")
    blocked, blocks = evaluate_jurisdiction("m2", category="prohibited")
    clear, safe_blocks = evaluate_jurisdiction("m3", category="crypto")
    assert unknown == "UNKNOWN"
    assert blocked == "BLOCKED"
    assert blocks[0].severity == "BLOCKING"
    assert clear == "CLEAR"
    assert not safe_blocks


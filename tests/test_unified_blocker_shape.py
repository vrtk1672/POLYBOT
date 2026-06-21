from __future__ import annotations

from app.control_center.unified_blockers import unified_blocker, unified_blockers


def test_unified_blocker_shape_contains_required_fields() -> None:
    blocker = unified_blocker(
        "MARKET_SCOPED_ONLY_EVENT",
        source="test",
        candidate_id="candidate-1",
        event_id="event-1",
        correlation_id="corr-1",
        market_id="market-1",
        side="YES",
        token_id="token-1",
    )

    assert blocker["blocker_code"] == "MARKET_SCOPED_ONLY_EVENT"
    assert blocker["severity"] == "HARD_BLOCK"
    assert blocker["source"] == "test"
    assert blocker["candidate_id"] == "candidate-1"
    assert blocker["event_id"] == "event-1"
    assert blocker["correlation_id"] == "corr-1"
    assert blocker["required_to_pass"]
    assert blocker["is_operator_action_required"] is True
    assert blocker["created_at"]


def test_unified_blockers_populates_required_to_pass_for_hard_blockers() -> None:
    blockers = unified_blockers(["BLOCKED_BY_LIFECYCLE"], source="test")

    assert blockers[0]["severity"] == "GOVERNANCE_DENIED"
    assert blockers[0]["required_to_pass"]

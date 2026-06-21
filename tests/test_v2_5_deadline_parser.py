from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.rules_neuron.deadline_parser import compute_deadline_risk, parse_deadline_from_rules


def test_clear_deadline_low_risk_and_missing_high_risk() -> None:
    deadline = parse_deadline_from_rules("Resolves at 2026-06-01T12:00:00Z using official source.")
    assert deadline is not None
    assert compute_deadline_risk("Resolves at 2026-06-01T12:00:00Z.", deadline, deadline)["risk"] == 0
    assert compute_deadline_risk("", None, None)["risk"] >= 0.45


def test_timezone_ambiguity_and_close_conflict_raise_risk() -> None:
    close = datetime.now(UTC)
    result = compute_deadline_risk("Resolves by end of day", None, close + timedelta(days=3))
    assert result["risk"] >= 0.6
    weird = compute_deadline_risk("not a date ((( before after", None, close)
    assert weird["risk"] >= 0.45


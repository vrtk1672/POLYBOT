from __future__ import annotations

import pytest

from app.neural_mesh.signal_market_binding import SignalMarketBindingCandidate, SignalMarketBindingRun


def test_binding_candidate_requires_reason_and_signal() -> None:
    candidate = SignalMarketBindingCandidate(
        signal_id="signal-1",
        candidate_market_id="market-1",
        confidence=0.95,
        reason="explicit market_id exists locally",
        action="auto_linked",
    )

    assert candidate.action == "AUTO_LINKED"
    assert candidate.confidence == 0.95


def test_binding_run_enforces_non_executing() -> None:
    with pytest.raises(ValueError):
        SignalMarketBindingRun(
            run_id="run-1",
            status="OK",
            orders_created=1,
            started_at="2026-01-01T00:00:00Z",
        )


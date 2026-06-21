from __future__ import annotations

from app.control_center.runtime_monitoring_report import build_monitoring_snapshot


def test_degraded_reason_is_exposed_in_monitoring_snapshot() -> None:
    snapshot = build_monitoring_snapshot(
        minute=0,
        overview={
            "runtime_state": "PAPER",
            "supervisor_state": "DEGRADED",
            "supervisor": {"errors": ["Paper simulation cycle failed: TypeError"]},
            "sources_events": {},
            "triggers": {},
            "candidates": {},
            "decisions": {},
            "execution": {},
            "pnl": {},
            "runtime_truth": {},
            "errors": [],
        },
        health={},
    )

    assert snapshot["supervisor_state"] == "DEGRADED"
    assert snapshot["degraded_reason"] == "Paper simulation cycle failed: TypeError"

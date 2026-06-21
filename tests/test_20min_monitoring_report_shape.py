from __future__ import annotations

from app.control_center.runtime_monitoring_report import build_monitoring_snapshot, missing_monitoring_snapshot_keys


def test_20min_monitoring_snapshot_contains_required_shape() -> None:
    snapshot = build_monitoring_snapshot(
        minute=5,
        overview={
            "runtime_state": "PAPER",
            "supervisor_state": "RUNNING",
            "supervisor": {},
            "runtime_truth": {"current_active_cycle_id": "cycle-1", "latest_completed_cycle_id": "cycle-0"},
            "sources_events": {"recent_events": 10, "linked_events": 7},
            "triggers": {"total": 3},
            "candidates": {"seeds_generated": 11, "mesh_reviewed": 4},
            "decisions": {
                "paper_ready_decisions": 2,
                "runtime_decisions_total": 1,
                "unique_market_count": 1,
                "unique_side_count": 1,
                "duplicate_suppression_count": 5,
                "top_blockers": ["DUPLICATE_OPEN_PAPER_EXPOSURE: 1"],
            },
            "execution": {
                "paper_intents": 1,
                "paper_orders": 1,
                "paper_fills": 1,
                "paper_positions": 1,
                "open_paper_positions": 0,
                "live_orders": 0,
                "shadow_orders": 0,
                "real_orders": 0,
            },
            "pnl": {"daily": -0.4},
            "errors": [],
        },
        health={"active_cycle_id": "cycle-1"},
    )

    assert missing_monitoring_snapshot_keys(snapshot) == []
    assert snapshot["minute"] == 5
    assert snapshot["live_orders"] == 0

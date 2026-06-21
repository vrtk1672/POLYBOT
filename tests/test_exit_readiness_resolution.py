from __future__ import annotations

from app.services import lifecycle_governance


def test_exit_plan_ready_overrides_stale_exit_hold_insufficient_data(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle_governance, "_table_exists", lambda conn, table: table == "exit_plans")
    monkeypatch.setattr(
        lifecycle_governance,
        "_fetchone",
        lambda conn, query, params=(): {
            "exit_plan_id": params[0],
            "status": "COMPLETE",
            "plan_status": "ACTIVE",
            "paper_exit_ready": True,
            "blockers": [],
            "missing_exit_evidence": [],
            "entry_price": 0.44,
            "target_exit": 0.49,
            "stop_loss": 0.41,
            "liquidity_exit_check": {"current_spread": 0.02, "current_liquidity_score": 0.8},
            "orderbook_snapshot_id": 123,
            "updated_at": None,
        },
    )

    plan = {
        "subject_type": "PAPER_CANDIDATE",
        "subject_id": "candidate-1",
        "source_refs_json": {"exit_plan_id": "exit_candidate_candidate-1"},
    }
    summary = lifecycle_governance._exit_plan_readiness_summary(object(), plan)

    assert summary["status"] == "EXIT_READY"
    assert summary["classification"] == "READY"
    assert lifecycle_governance._status_from_exit_plan(summary) == "EXIT_READY"


def test_exit_block_remains_current_when_plan_has_blockers(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle_governance, "_table_exists", lambda conn, table: table == "exit_plans")
    monkeypatch.setattr(
        lifecycle_governance,
        "_fetchone",
        lambda conn, query, params=(): {
            "exit_plan_id": params[0],
            "status": "BLOCKED",
            "plan_status": "INSUFFICIENT_DATA",
            "paper_exit_ready": False,
            "blockers": ["EXIT_LIQUIDITY_INSUFFICIENT"],
            "missing_exit_evidence": [],
            "liquidity_exit_check": {"current_spread": 0.12, "current_liquidity_score": 0.1},
            "orderbook_snapshot_id": 123,
            "updated_at": None,
        },
    )

    summary = lifecycle_governance._exit_plan_readiness_summary(
        object(),
        {"subject_type": "PAPER_CANDIDATE", "subject_id": "candidate-1", "source_refs_json": {}},
    )

    assert summary["status"] == "EXIT_BLOCKED"
    assert summary["classification"] == "CURRENT_REAL_BLOCKER"
    assert "EXIT_LIQUIDITY_INSUFFICIENT" in summary["blockers"]

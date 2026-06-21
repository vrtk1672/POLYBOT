from __future__ import annotations

from app.services.mesh_blockers import build_mesh_blocker_report


def _blocked_truth() -> dict[str, object]:
    return {
        "runtime": {
            "env_mode": "PAPER",
            "persisted_mode": "DATA_ONLY",
            "mode_mismatch": True,
            "kill_switch_env": True,
            "kill_switch_persisted": False,
            "kill_switch_mismatch": True,
            "live_enabled": False,
            "permissions": {"can_run_paper_engine": False},
        },
        "signal_quality": {"can_feed_paper": 0},
        "signal_processing": {
            "total": 100,
            "unprocessed_count": 39,
            "stale_count": 88,
            "rejected_count": 0,
            "paper_eligible_informational_count": 0,
            "by_state": [],
        },
        "link_coverage": {
            "link_coverage_ratio": 0.1439,
            "linked_signals": 20,
            "unlinked_signals": 119,
        },
        "lineage_coverage": {
            "lineage_coverage_ratio": 0.741,
            "unbound_signals": 36,
            "missing_lineage_fields": [{"field": "raw_payload_ref", "count": 36}],
        },
        "dry_run_provenance": {
            "brain_outputs_total": 48,
            "brain_outputs_runtime": 0,
            "brain_outputs_dry_run": 48,
            "coordinator_decisions_total": 12,
            "coordinator_decisions_runtime": 0,
            "coordinator_decisions_dry_run": 12,
            "blocked_from_paper_count": 160,
        },
        "thesis": {"total_thesis_profiles": 0, "positions_without_thesis": 0},
        "counts": {
            "orderbook_snapshots": 0,
            "paper_orders": 0,
            "shadow_orders": 0,
            "live_orders": 0,
            "order_intents": 0,
            "execution_allowed_true": 0,
            "risk_core_evidence": 0,
            "exit_foundation_evidence": 0,
        },
        "tables": {"orderbook_snapshots_exists": False, "order_intents_exists": False},
    }


def _codes(report: dict[str, object], section: str = "blockers") -> set[str]:
    return {str(item["code"]) for item in report[section]}  # type: ignore[index]


def test_paper_ready_false_when_critical_blockers_exist() -> None:
    payload = build_mesh_blocker_report(_blocked_truth()).to_api_dict()

    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    assert payload["overall_status"] == "BLOCKED"
    assert payload["counts"]["active_blockers"] > 0


def test_expected_readiness_blockers_are_active() -> None:
    payload = build_mesh_blocker_report(_blocked_truth()).to_api_dict()
    codes = _codes(payload)

    for code in (
        "ORDERBOOK_SNAPSHOTS_MISSING",
        "SIGNAL_PROCESSING_INCOMPLETE",
        "SIGNAL_QUALITY_GATE_BLOCKED",
        "SIGNAL_LINKING_TOO_LOW",
        "SIGNALS_STALE_HIGH",
        "SIGNAL_LINEAGE_COVERAGE_LOW",
        "BRAIN_OUTPUTS_DRY_RUN_ONLY",
        "COORDINATOR_DECISIONS_DRY_RUN_ONLY",
        "NO_RUNTIME_BRAIN_OUTPUTS",
        "NO_RUNTIME_COORDINATOR_DECISIONS",
        "DRY_RUN_EVIDENCE_BLOCKED_FROM_PAPER",
        "NO_THESIS_PROFILES",
        "NO_RISK_CORE",
        "NO_EXIT_FOUNDATION",
        "NO_PAPER_ELIGIBLE_SIGNALS",
        "ENV_PERSISTED_MODE_MISMATCH",
        "ENV_PERSISTED_KILL_SWITCH_MISMATCH",
    ):
        assert code in codes
        assert code in payload["blocked_by"]


def test_safety_confirmations_are_info_not_paper_blockers() -> None:
    payload = build_mesh_blocker_report(_blocked_truth()).to_api_dict()
    info_codes = _codes(payload, "info")

    assert "LIVE_DISABLED" in info_codes
    assert "PAPER_ORDERS_ZERO" in info_codes
    assert "ORDER_INTENTS_ABSENT" in info_codes
    assert "LIVE_DISABLED" not in payload["blocked_by"]
    assert "PAPER_ORDERS_ZERO" not in payload["blocked_by"]


def test_response_includes_evidence_and_recommended_next_step() -> None:
    payload = build_mesh_blocker_report(_blocked_truth()).to_api_dict()

    brain_blocker = next(item for item in payload["blockers"] if item["code"] == "BRAIN_OUTPUTS_DRY_RUN_ONLY")
    assert brain_blocker["evidence"]["brain_outputs_runtime"] == 0
    assert brain_blocker["evidence"]["brain_outputs_dry_run"] == 48
    assert brain_blocker["recommended_next_step"]

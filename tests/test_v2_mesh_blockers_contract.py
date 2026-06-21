from __future__ import annotations

from datetime import UTC, datetime

from app.neural_mesh.mesh_blockers import MeshBlocker, MeshBlockerReport


def test_mesh_blocker_contract_requires_explanation_and_evidence() -> None:
    blocker = MeshBlocker(
        code="brain_outputs_dry_run_only",
        active=True,
        severity="critical",
        category="brain",
        reason="Brain Outputs exist only as dry-run outputs.",
        evidence={"brain_outputs_runtime": 0, "brain_outputs_dry_run": 48},
        source="dry_run_provenance",
        recommended_next_step="Implement runtime brain producer adapters.",
        blocks_paper=True,
    )

    payload = blocker.to_api_dict()
    assert payload["code"] == "BRAIN_OUTPUTS_DRY_RUN_ONLY"
    assert payload["severity"] == "CRITICAL"
    assert payload["category"] == "BRAIN"
    assert payload["blocks_paper"] is True
    assert payload["evidence"]["brain_outputs_runtime"] == 0


def test_mesh_blocker_report_keeps_paper_ready_false() -> None:
    blocker = MeshBlocker(
        code="NO_EXIT_FOUNDATION",
        active=True,
        severity="CRITICAL",
        category="EXIT",
        reason="No Exit Foundation certification evidence exists.",
        evidence={},
        source="exit_foundation_evidence",
        recommended_next_step="Build Exit Foundation before Paper.",
    )
    report = MeshBlockerReport(
        mock_data=False,
        paper_ready=False,
        overall_status="blocked",
        blocked_by=[blocker.code],
        blockers=[blocker],
        info=[],
        counts={"critical": 1, "active_blockers": 1},
        last_updated=datetime.now(UTC),
    )

    payload = report.to_api_dict()
    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    assert payload["overall_status"] == "BLOCKED"
    assert payload["blocked_by"] == ["NO_EXIT_FOUNDATION"]

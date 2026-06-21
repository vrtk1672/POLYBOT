from __future__ import annotations

from app.db.migrate import run_migrations
from app.services.side_evidence import DeterministicSideEvidenceService


def test_dashboard_side_evidence_truth_is_real(postgres_test_schema) -> None:
    run_migrations()

    summary = DeterministicSideEvidenceService().get_dashboard_summary(limit=5)

    assert summary["mock_data"] is False
    assert "side_recovery_allowed" in summary
    assert "trusted_links_with_matched_side" in summary
    assert "candidate_trace" in summary
    assert summary["live_orders"] == 0
    assert summary["no_live_execution"] is True

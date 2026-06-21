from __future__ import annotations

from app.services.decision_autopsy import DecisionAutopsyService
from decision_autopsy_helpers import prepare_autopsy_fixture, seed_degraded_service


def test_supervisor_degraded_exposes_reason(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_degraded_service()

    payload = DecisionAutopsyService().supervisor_autopsy()

    assert payload["status"] == "OK"
    assert payload["supervisor_state"] == "DEGRADED"
    assert any("test degraded" in reason for reason in payload["degraded_reasons"])
    assert payload["blocks_paper_entries"] is False

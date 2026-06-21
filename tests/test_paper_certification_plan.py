from __future__ import annotations

from app.control_center.paper_certification_plan import PaperCertificationPlanService


def test_paper_certification_plan_exists_and_defines_criteria() -> None:
    payload = PaperCertificationPlanService().get_plan()

    assert payload["plan_state"] == "DEFINED_NOT_STARTED"
    assert payload["green_criteria"]
    assert payload["yellow_criteria"]
    assert payload["red_criteria"]
    assert "live_orders" in payload["forbidden_artifact_types"]


def test_paper_certification_plan_does_not_activate_paper() -> None:
    payload = PaperCertificationPlanService().get_plan()

    assert "PAPER_SIMULATION_OFF" in payload["blockers"]
    assert any("does not activate" in warning for warning in payload["warnings"])
    assert all("POST paper-on" not in action.lower() for action in payload.get("forbidden_actions", []))

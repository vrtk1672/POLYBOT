from __future__ import annotations

from app.services.query.dashboard_v2_query_service import DashboardV2QueryService


def test_settings_exposes_locked_reason_gated_controls() -> None:
    payload = DashboardV2QueryService().get_page("settings")
    controls = payload["data"]["advanced_controls"]
    assert controls["unlock_required"] is True
    assert controls["reason_required"] is True
    assert controls["confirmation_required"] is True
    assert controls["dangerous_one_click_controls"] is False
    assert controls["available_controls"] == []


def test_dashboard_v2_unknown_page_does_not_execute_action() -> None:
    payload = DashboardV2QueryService().get_page("kill")
    assert payload["status"] == "ERROR"
    assert payload["stale"] is True
    assert payload["data"] == {}
    assert "unknown_dashboard_v2_page:kill" in payload["errors"]


def test_dashboard_v2_source_declares_read_only_truth() -> None:
    payload = DashboardV2QueryService().get_page("no-trade")
    assert payload["data_source"]["mock_data"] is False
    assert payload["data_source"]["type"] == "postgres_runtime_truth"
    assert "OperatorDashboardQueryService" in payload["data_source"]["service"]

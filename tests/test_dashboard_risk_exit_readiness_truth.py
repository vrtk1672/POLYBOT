from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.post_side_risk_exit_readiness import PostSideRiskExitReadinessService
from app.services.system_power import SystemPowerService

from paper_eligibility_fixtures import table_exists


def test_dashboard_risk_exit_readiness_truth(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        if table_exists(conn, "post_side_risk_exit_recovery_runs"):
            conn.execute("DELETE FROM post_side_risk_exit_recovery_runs")
    SystemPowerService().turn_on(actor="test", reason="dashboard_post_side")

    payload = PostSideRiskExitReadinessService().get_dashboard_summary(limit=5)

    assert payload["mock_data"] is False
    assert "recovery_allowed" in payload
    assert "top_risk_blockers" in payload
    assert "top_exit_blockers" in payload
    assert payload["live_orders"] == 0
    assert payload["no_live_execution"] is True

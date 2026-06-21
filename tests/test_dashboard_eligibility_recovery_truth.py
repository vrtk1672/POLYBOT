from __future__ import annotations

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.services.candidate_eligibility_recovery import CandidateEligibilityRecoveryService
from app.services.system_power import SystemPowerService

from paper_eligibility_fixtures import seed_paper_eligibility_chain, table_exists


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "candidate_eligibility_recovery_runs",
            "paper_execution_runs",
            "paper_trade_ledger",
            "paper_fills",
            "paper_position_events",
            "paper_positions",
            "paper_order_events",
            "paper_orders",
            "paper_signals",
            "paper_runs",
            "paper_intent_runs",
            "no_trade_runs",
            "paper_intents",
            "no_trade_log",
            "paper_eligibility_runs",
            "paper_eligibility_candidates",
            "exit_plan_rules",
            "exit_plan_runs",
            "exit_plans",
            "risk_decisions",
            "thesis_profiles",
            "signal_market_links",
            "neuron_signals",
            "coordinator_decision_inputs",
            "coordinator_decisions",
            "brain_output_dependencies",
            "brain_outputs",
            "orderbook_snapshots",
            "markets_v2",
        ):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
    SystemPowerService().turn_on(actor="test", reason="dashboard_eligibility_recovery")


def test_dashboard_eligibility_recovery_truth_is_real(postgres_test_schema) -> None:
    _prepare()
    ids = seed_paper_eligibility_chain("dashboard-recovery", side=None)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            "UPDATE signal_market_links SET link_evidence_json = %s WHERE signal_id = %s",
            (Jsonb({"matched_side": "YES"}), ids["signal_id"]),
        )
    CandidateEligibilityRecoveryService().run_recovery(cycle_id="dashboard-recovery-cycle", limit=10)

    response = TestClient(create_app()).get("/dashboard/api/v2/eligibility-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["recovery_allowed"] is True
    assert payload["latest_recovery_status"] == "OK"
    assert payload["sides_recovered"] == 1
    assert payload["eligible_candidates"] >= 1
    assert payload["paper_intents"] >= 1
    assert payload["paper_orders"] >= 1
    assert payload["paper_fills"] >= 1
    assert payload["paper_positions"] >= 1
    assert payload["real_orders"] == 0
    assert payload["live_orders"] == 0
    assert payload["no_live_execution"] is True
    assert len(payload["candidate_trace"]) >= 1

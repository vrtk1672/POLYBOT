from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.exit_foundation import ExitFoundationPlan
from app.repositories.exit_foundation_repository import ExitFoundationRepository, exit_plan_from_row


def test_exit_foundation_repository_persists_plan(postgres_test_schema) -> None:
    run_migrations()
    repo = ExitFoundationRepository()
    plan = ExitFoundationPlan(
        exit_plan_id="exit-risk-repo",
        thesis_id="thesis-repo",
        risk_decision_id="risk-repo",
        market_id="market-repo",
        side="YES",
        status="BLOCKED",
        exit_type="BLOCKED_NO_ENTRY_EXIT",
        blockers=["RISK_BLOCKED"],
        missing_exit_evidence=["MISSING_RISK_APPROVAL"],
        invalidation_rules=["ORDERBOOK_STALE"],
        emergency_exit_rules=["MANUAL_KILL"],
        liquidity_exit_check={"max_spread": 0.08},
    )

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        row, created = repo.upsert_plan(conn, plan)
        repo.record_rules(conn, plan)

    assert created is True
    loaded = exit_plan_from_row(row)
    assert loaded.exit_plan_id == "exit-risk-repo"
    assert loaded.paper_intent_allowed is False
    assert loaded.execution_allowed is False
    with DatabaseConnectionFactory().connect() as conn:
        rules = conn.execute("SELECT COUNT(*) AS count FROM exit_plan_rules WHERE exit_plan_id = 'exit-risk-repo'").fetchone()["count"]
    assert rules == 4


def test_exit_foundation_repository_recent_returns_latest(postgres_test_schema) -> None:
    run_migrations()
    repo = ExitFoundationRepository()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        repo.upsert_plan(conn, ExitFoundationPlan(exit_plan_id="exit-old", status="BLOCKED", exit_type="BLOCKED_NO_ENTRY_EXIT"))
        repo.upsert_plan(conn, ExitFoundationPlan(exit_plan_id="exit-new", status="INCOMPLETE", exit_type="TIME_ONLY_EXIT"))
        rows = repo.list_plans(conn, limit=5, status="INCOMPLETE")

    assert len(rows) == 1
    assert rows[0]["exit_plan_id"] == "exit-new"

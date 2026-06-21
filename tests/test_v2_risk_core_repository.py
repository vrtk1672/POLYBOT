from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.risk_core import RiskDecision
from app.repositories.risk_core_repository import RiskCoreRepository, risk_decision_from_row


def test_risk_core_repository_persists_decision(postgres_test_schema) -> None:
    run_migrations()
    repo = RiskCoreRepository()
    decision = RiskDecision(
        risk_decision_id="risk-thesis-repo",
        thesis_id="thesis-repo",
        market_id="market-repo",
        decision="BLOCK",
        risk_status="BLOCKED",
        risk_score=1.0,
        blockers=["THESIS_BLOCKED"],
        required_missing_evidence=["MISSING_MARKET_ID"],
    )

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        row, created = repo.upsert_decision(conn, decision)

    assert created is True
    loaded = risk_decision_from_row(row)
    assert loaded.risk_decision_id == "risk-thesis-repo"
    assert loaded.execution_allowed is False
    assert loaded.paper_candidate_allowed is False


def test_risk_core_repository_recent_returns_latest(postgres_test_schema) -> None:
    run_migrations()
    repo = RiskCoreRepository()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        repo.upsert_decision(
            conn,
            RiskDecision(
                risk_decision_id="risk-old",
                thesis_id="thesis-old",
                decision="BLOCK",
                risk_status="BLOCKED",
                blockers=["THESIS_BLOCKED"],
            ),
        )
        repo.upsert_decision(
            conn,
            RiskDecision(
                risk_decision_id="risk-new",
                thesis_id="thesis-new",
                decision="REJECT",
                risk_status="HIGH",
                risk_score=0.8,
            ),
        )
        rows = repo.list_decisions(conn, limit=5, decision="REJECT")

    assert len(rows) == 1
    assert rows[0]["risk_decision_id"] == "risk-new"


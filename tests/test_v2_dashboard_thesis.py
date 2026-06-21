from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import app
from app.neural_mesh.thesis_profiles import ThesisProfile
from app.repositories.thesis_profile_repository import ThesisProfileRepository


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in ("thesis_profile_evidence_items", "thesis_profile_runs", "thesis_profiles"):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")


def test_dashboard_thesis_empty_truth(postgres_test_schema) -> None:
    _prepare()
    client = TestClient(app)

    response = client.get("/dashboard/api/v2/thesis")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    assert payload["total_thesis_profiles"] == 0
    assert payload["latest_thesis_profiles"] == []


def test_dashboard_thesis_reports_runtime_profile_counts(postgres_test_schema) -> None:
    _prepare()
    profile = ThesisProfile(
        thesis_id="thesis-dashboard",
        market_id="market-dashboard",
        status="INCOMPLETE",
        thesis_type="HOLD_FOR_MORE_EVIDENCE",
        why_now="Runtime coordinator evidence exists but Risk and Exit are missing.",
        confidence=0.7,
        missing_evidence=["NO_RISK_CORE", "NO_EXIT_FOUNDATION"],
        invalidation_rules=["invalidate_if_orderbook_becomes_stale"],
        risk_notes=["NO_RISK_CORE"],
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        ThesisProfileRepository().upsert_profile(conn, profile)

    client = TestClient(app)
    response = client.get("/dashboard/api/v2/thesis")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["total_thesis_profiles"] == 1
    assert payload["incomplete_thesis_profiles"] == 1
    assert payload["paper_candidate_allowed_count"] == 0
    assert payload["paper_ready"] is False

from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.paper_eligibility import PaperEligibilityCandidate
from app.repositories.paper_eligibility_repository import PaperEligibilityRepository, paper_eligibility_from_row

from paper_eligibility_fixtures import prepare_paper_eligibility_schema


def test_paper_eligibility_repository_persists_candidate(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    repo = PaperEligibilityRepository()
    candidate = PaperEligibilityCandidate(
        eligibility_id="eligibility-repo",
        status="BLOCKED",
        eligibility_blockers=["MISSING_EXIT_PLAN"],
        missing_requirements=["MISSING_EXIT_PLAN"],
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        row, created = repo.upsert_candidate(conn, candidate)
    assert created is True
    loaded = paper_eligibility_from_row(row)
    assert loaded.eligibility_id == "eligibility-repo"
    assert loaded.paper_intent_allowed is False
    assert loaded.execution_allowed is False


def test_paper_eligibility_repository_recent_returns_latest(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    repo = PaperEligibilityRepository()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        repo.upsert_candidate(conn, PaperEligibilityCandidate(eligibility_id="eligibility-old", status="BLOCKED"))
        repo.upsert_candidate(conn, PaperEligibilityCandidate(eligibility_id="eligibility-new", status="INCOMPLETE"))
    with DatabaseConnectionFactory().connect() as conn:
        rows = repo.list_candidates(conn, limit=1)
    assert rows[0]["eligibility_id"] == "eligibility-new"

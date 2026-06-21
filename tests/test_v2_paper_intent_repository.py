from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.paper_intents import PaperIntent
from app.repositories.paper_intent_repository import PaperIntentRepository, paper_intent_from_row

from paper_intent_fixtures import prepare_paper_intent_schema, seed_eligible_candidate


def test_paper_intent_repository_upserts_and_lists(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_eligible_candidate("repo")
    repo = PaperIntentRepository()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        candidates = repo.list_candidates(conn, limit=10)
        intent = PaperIntent(
            paper_intent_id=f"paper_intent_{candidates[0]['eligibility_id']}",
            eligibility_id=candidates[0]["eligibility_id"],
            thesis_id=candidates[0]["thesis_id"],
            risk_decision_id=candidates[0]["risk_decision_id"],
            exit_plan_id=candidates[0]["exit_plan_id"],
            market_id=candidates[0]["market_id"],
            side=candidates[0]["side"],
        )
        _, created = repo.upsert_paper_intent(conn, intent)
        rows = repo.list_intents(conn, limit=10)

    assert created is True
    assert len(rows) == 1
    assert paper_intent_from_row(rows[0]).paper_only is True

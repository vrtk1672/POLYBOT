from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.paper_intents import PaperIntent
from app.repositories.paper_intent_repository import PaperIntentRepository

from decision_autopsy_helpers import SESSION_ID, prepare_autopsy_fixture, seed_runtime_decision


def test_same_eligibility_upsert_is_idempotent(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    repo = PaperIntentRepository()
    intent = PaperIntent(
        paper_intent_id="intent-eligibility-once",
        eligibility_id="eligibility-duplicate",
        thesis_id="thesis",
        risk_decision_id="risk",
        exit_plan_id="exit",
        market_id="market-dup",
        side="YES",
        evidence={"source": "test"},
    )
    duplicate = intent.model_copy(update={"paper_intent_id": "intent-eligibility-twice"})

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        first, first_created = repo.upsert_paper_intent(conn, intent)
        second, second_created = repo.upsert_paper_intent(conn, duplicate)
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM paper_intents WHERE eligibility_id='eligibility-duplicate'"
        ).fetchone()["count"]
        summary = repo.summary(conn, limit=10)["paper_intent_gate_idempotency"]

    assert first_created is True
    assert second_created is False
    assert int(count) == 1
    assert second["paper_intent_id"] == first["paper_intent_id"]
    marker = second["evidence"]["paper_intent_gate_idempotency"]
    assert marker["skip_reason"] == "ALREADY_INTENT_EXISTS_FOR_ELIGIBILITY"
    assert marker["duplicate_crash_prevented"] is True
    assert summary["duplicate_eligibility_encountered"] == 1
    assert summary["duplicate_skipped_safely"] == 1


def test_runtime_intent_eligibility_is_current_session_scoped(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="paper_runtime_decision_scope_test",
        market_id="market-scope",
        side="YES",
        decision="ENTER",
        score=61.99,
        blockers=[],
    )

    from app.services.paper_intents import PaperIntentGateService

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_intents_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT paper_intent_id, eligibility_id, paper_session_id, evidence
            FROM paper_intents
            WHERE market_id='market-scope'
            """
        ).fetchone()
    assert row is not None
    assert row["paper_session_id"] == SESSION_ID
    assert row["paper_intent_id"].endswith(SESSION_ID)
    assert row["eligibility_id"].startswith("paper_runtime_decision_")
    assert row["eligibility_id"].endswith(f"_{SESSION_ID}")
    assert row["evidence"]["original_eligibility_id"].startswith("paper_runtime_decision_")

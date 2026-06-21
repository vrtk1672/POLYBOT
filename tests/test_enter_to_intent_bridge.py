from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_intents import PaperIntentGateService

from decision_autopsy_helpers import SESSION_ID, prepare_autopsy_fixture, seed_runtime_decision


def test_current_session_enter_creates_session_scoped_paper_intent(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="decision-current-enter",
        market_id="market-enter",
        side="YES",
        decision="ENTER",
        score=61.99,
        blockers=[],
    )

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_intents_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT paper_intent_id, paper_session_id, evidence->>'paper_runtime_decision_id' AS decision_id
            FROM paper_intents
            WHERE market_id = 'market-enter' AND side = 'YES'
            """
        ).fetchone()
    assert row is not None
    assert row["paper_session_id"] == SESSION_ID
    assert row["decision_id"]
    assert row["paper_intent_id"].endswith(SESSION_ID)


def test_blocked_enter_does_not_force_paper_intent(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="decision-blocked-enter",
        market_id="market-blocked",
        side="YES",
        decision="ENTER",
        score=61.99,
        blockers=["EXIT_NOT_READY"],
    )

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_intents_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM paper_intents").fetchone()["count"]
    assert int(count) == 0

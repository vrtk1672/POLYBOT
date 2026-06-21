from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.paper_intents import PaperIntent
from app.repositories.paper_intent_repository import PaperIntentRepository
from app.services.paper_session import PaperSessionService
from paper_session_helpers import prepare_paper_session_fixture


def test_reset_creates_new_active_session_with_balance_1000(postgres_test_schema) -> None:
    prepare_paper_session_fixture()

    result = PaperSessionService().reset(balance=1000, reason="test reset", created_by="test")

    assert result["status"] == "COMPLETED"
    assert result["requested_balance"] == 1000.0
    assert result["current_session_counts"]["paper_intents"] == 0
    assert result["current_session_counts"]["paper_orders"] == 0
    assert result["current_session_counts"]["paper_fills"] == 0
    assert result["current_session_counts"]["paper_positions"] == 0
    assert result["current_session_counts"]["open_paper_positions"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        active = conn.execute("SELECT * FROM paper_sessions WHERE status='ACTIVE'").fetchone()
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
    assert active["starting_balance"] == 1000
    assert account["current_balance"] == 1000
    assert account["available_balance"] == 1000
    assert account["locked_balance"] == 0


def test_new_paper_intent_attaches_to_active_session(postgres_test_schema) -> None:
    prepare_paper_session_fixture()
    reset = PaperSessionService().reset(balance=1000, reason="test reset", created_by="test")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        PaperIntentRepository().upsert_paper_intent(
            conn,
            PaperIntent(
                paper_intent_id="new-intent",
                eligibility_id="new-elig",
                thesis_id="new-thesis",
                risk_decision_id="new-risk",
                exit_plan_id="new-exit",
                market_id="market-b",
                side="NO",
                intended_price=0.4,
                confidence=0.7,
            ),
        )
    status = PaperSessionService().status()
    assert status["current_session_counts"]["paper_intents"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT paper_session_id FROM paper_intents WHERE paper_intent_id='new-intent'").fetchone()
    assert row["paper_session_id"] == reset["new_session_id"]

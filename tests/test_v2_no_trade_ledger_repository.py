from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.paper_intents import NoTradeLedgerRecord
from app.repositories.paper_intent_repository import PaperIntentRepository, no_trade_record_from_row

from paper_intent_fixtures import prepare_paper_intent_schema


def test_no_trade_repository_upserts_and_lists(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    repo = PaperIntentRepository()
    record = NoTradeLedgerRecord(
        no_trade_id="no_trade_repo",
        eligibility_id="eligibility-repo",
        market_id="market-repo",
        no_trade_reason="RISK_NOT_APPROVED",
        no_trade_category="RISK_BLOCKED",
        blockers=["RISK_NOT_APPROVED"],
        missing_requirements=["RISK_NOT_APPROVED"],
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        _, created = repo.upsert_no_trade_record(conn, record)
        rows = repo.list_no_trade(conn, limit=10)

    assert created is True
    assert len(rows) == 1
    assert no_trade_record_from_row(rows[0]).blockers == ["RISK_NOT_APPROVED"]

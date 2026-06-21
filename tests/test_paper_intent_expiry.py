from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.opportunity_memory import OpportunityMemoryService

from opportunity_mesh_fixtures import prepare_opportunity_mesh_fixture, seed_paper_intent


def test_pending_intent_older_than_threshold_expires_and_is_not_deleted(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_paper_intent(
        intent_id="intent-expire-old",
        eligibility_id="eligibility-expire-old",
        market_id="market-expire",
        seconds_old=900,
        execution_block_reason="STALE_PAPER_INTENT",
    )

    result = OpportunityMemoryService().expire_stale_intents(limit=10)

    assert result["status"] == "OK"
    assert result["expired_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT intent_status, expired_at, intent_lifecycle_reason, opportunity_memory_id
            FROM paper_intents
            WHERE paper_intent_id='intent-expire-old'
            """
        ).fetchone()
        memory_count = conn.execute("SELECT COUNT(*) AS count FROM opportunity_memory").fetchone()["count"]

    assert row is not None
    assert row["intent_status"] == "EXPIRED_NO_EXECUTION"
    assert row["expired_at"] is not None
    assert "STALE_PAPER_INTENT" in row["intent_lifecycle_reason"]
    assert row["opportunity_memory_id"]
    assert int(memory_count) == 1


def test_fresh_pending_intent_does_not_expire(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_paper_intent(
        intent_id="intent-fresh",
        eligibility_id="eligibility-fresh",
        market_id="market-fresh",
        seconds_old=30,
    )

    result = OpportunityMemoryService().expire_stale_intents(limit=10)

    assert result["expired_count"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        status = conn.execute(
            "SELECT intent_status FROM paper_intents WHERE paper_intent_id='intent-fresh'"
        ).fetchone()["intent_status"]
    assert status == "CREATED"

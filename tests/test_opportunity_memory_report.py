from __future__ import annotations

from app.services.opportunity_memory import OpportunityMemoryService

from opportunity_mesh_fixtures import prepare_opportunity_mesh_fixture, seed_paper_intent


def test_opportunity_memory_and_expired_intent_views_are_non_empty_after_expiry(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_paper_intent(
        intent_id="intent-report-expired",
        eligibility_id="eligibility-report-expired",
        market_id="market-report-expired",
        side="NO",
        seconds_old=900,
        execution_block_reason="REFRESH_REQUIRED_BEFORE_EXECUTION",
    )
    service = OpportunityMemoryService()
    service.expire_stale_intents(limit=10)

    memory = service.opportunity_memory(limit=10)
    expired = service.expired_intents(limit=10)

    assert memory["status"] == "OK"
    assert memory["counts"]["WAITING_FOR_NEW_EVIDENCE"] == 1
    assert memory["items"][0]["last_reason"].startswith("EXPIRED_NO_EXECUTION")
    assert expired["status"] == "OK"
    assert expired["counts"]["EXPIRED_NO_EXECUTION"] == 1
    assert expired["items"][0]["paper_intent_id"] == "intent-report-expired"

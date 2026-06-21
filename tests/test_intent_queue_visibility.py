from __future__ import annotations

from app.services.opportunity_mesh_coordinator import OpportunityMeshCoordinator
from app.services.opportunity_memory import OpportunityMemoryService

from opportunity_mesh_fixtures import prepare_opportunity_mesh_fixture, seed_paper_intent


def test_active_intent_appears_in_intent_queue(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_paper_intent(
        intent_id="intent-visible",
        eligibility_id="eligibility-visible",
        market_id="market-visible",
    )

    payload = OpportunityMeshCoordinator().intent_queue(limit=10)

    assert payload["stuck_count"] == 0
    assert payload["items"][0]["paper_intent_id"] == "intent-visible"
    assert payload["items"][0]["execution_status"] == "INTENT_PENDING_EXECUTION"
    assert payload["items"][0]["next_action"] == "EXECUTE_PAPER_INTENT"


def test_expired_intent_appears_in_intent_queue_with_memory_link(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_paper_intent(
        intent_id="intent-queue-expired",
        eligibility_id="eligibility-queue-expired",
        market_id="market-queue-expired",
        seconds_old=900,
    )
    OpportunityMemoryService().expire_stale_intents(limit=10)

    payload = OpportunityMeshCoordinator().intent_queue(limit=10)
    item = payload["items"][0]

    assert item["paper_intent_id"] == "intent-queue-expired"
    assert item["execution_status"] == "INTENT_EXPIRED"
    assert item["expired"] is True
    assert item["opportunity_memory_id"]

from __future__ import annotations

from app.services.opportunity_mesh_coordinator import OpportunityMeshCoordinator

from opportunity_mesh_fixtures import prepare_opportunity_mesh_fixture, seed_paper_intent


def test_created_intent_without_execution_after_threshold_is_stuck(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_paper_intent(
        intent_id="intent-stuck",
        eligibility_id="eligibility-stuck",
        market_id="market-stuck",
        seconds_old=1200,
        execution_block_reason="MISSING_TRUSTED_ORDERBOOK",
    )

    payload = OpportunityMeshCoordinator().intent_queue(limit=10)

    item = payload["items"][0]
    assert payload["stuck_count"] == 1
    assert item["execution_status"] == "INTENT_STUCK"
    assert item["stuck"] is True
    assert item["next_action"] == "REFRESH_ORDERBOOK_OR_EXPIRE_INTENT"

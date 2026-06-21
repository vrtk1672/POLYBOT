from __future__ import annotations

from app.services.opportunity_mesh_coordinator import OpportunityMeshCoordinator
from app.services.opportunity_memory import OpportunityMemoryService

from opportunity_mesh_fixtures import prepare_opportunity_mesh_fixture, seed_paper_intent, seed_runtime_decision


def test_expired_intent_does_not_block_new_runtime_decision_revision(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_paper_intent(
        intent_id="intent-expired-old-revision",
        eligibility_id="eligibility-expired-old-revision",
        market_id="market-new-revision",
        side="YES",
        runtime_decision_id="decision-old-revision",
        seconds_old=900,
    )
    OpportunityMemoryService().expire_stale_intents(limit=10)
    seed_runtime_decision(
        decision_id="decision-new-revision",
        market_id="market-new-revision",
        side="YES",
        score=62.0,
        evidence={"orderbook_best_ask": 0.50, "paper_defense": {"defense_level": 20, "profile": {"adjusted_threshold": 42}}},
    )

    payload = OpportunityMeshCoordinator().opportunity_mesh(limit=20)
    item = next(row for row in payload["items"] if row.get("runtime_decision_id") == "decision-new-revision")

    assert item["lifecycle_state"] == "READY_FOR_INTENT"
    assert item["next_action"] == "CREATE_PAPER_INTENT"

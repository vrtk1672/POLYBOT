from __future__ import annotations

from app.services.opportunity_mesh_coordinator import OpportunityMeshCoordinator

from opportunity_mesh_fixtures import prepare_opportunity_mesh_fixture, seed_paper_intent, seed_runtime_decision


def test_duplicate_active_intent_is_lifecycle_state_and_later_candidate_continues(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_runtime_decision(
        decision_id="decision-duplicate",
        market_id="market-duplicate",
        blockers=["DUPLICATE_ACTIVE_PAPER_INTENT"],
        paper_enter_allowed=False,
    )
    seed_paper_intent(
        intent_id="intent-duplicate",
        eligibility_id="eligibility-duplicate",
        market_id="market-duplicate",
        runtime_decision_id="decision-duplicate",
    )
    seed_runtime_decision(decision_id="decision-next", market_id="market-next", score=66.0)

    payload = OpportunityMeshCoordinator().opportunity_mesh(limit=20)

    by_decision = {item["runtime_decision_id"]: item for item in payload["items"]}
    assert by_decision["decision-duplicate"]["lifecycle_state"] == "HAS_ACTIVE_INTENT"
    assert by_decision["decision-duplicate"]["consumption_policy"] == "CONSUME_ROUTE_TO_EXECUTION"
    assert by_decision["decision-duplicate"]["next_action"] == "CHECK_INTENT_EXECUTION"
    assert by_decision["decision-duplicate"]["execution_status"] == "INTENT_PENDING_EXECUTION"
    assert by_decision["decision-next"]["lifecycle_state"] == "READY_FOR_INTENT"
    assert payload["candidate_consumption"]["routed_to_execution"] == 1
    assert payload["candidate_consumption"]["created_intents"] == 1

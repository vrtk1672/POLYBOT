from __future__ import annotations

from app.services.opportunity_mesh_coordinator import OpportunityMeshCoordinator

from opportunity_mesh_fixtures import prepare_opportunity_mesh_fixture, seed_runtime_decision


def test_blocked_candidate_does_not_stop_candidate_consumption(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_runtime_decision(
        decision_id="decision-blocked",
        market_id="market-blocked",
        decision="BLOCK",
        blockers=["THESIS_NOT_SUPPORTED"],
        paper_enter_allowed=False,
    )
    seed_runtime_decision(decision_id="decision-after-block", market_id="market-after-block", score=64.0)

    payload = OpportunityMeshCoordinator().candidate_consumption(limit=20)

    consumption = payload["candidate_consumption"]
    assert consumption["candidates_consumed"] == 2
    assert consumption["skipped_blocked"] == 1
    assert consumption["created_intents"] == 1
    policies = {item["runtime_decision_id"]: item["consumption_policy"] for item in payload["items"]}
    assert policies["decision-blocked"] == "CONSUME_SKIP_BLOCKED_CONTINUE"
    assert policies["decision-after-block"] == "CONSUME_CREATE_INTENT"

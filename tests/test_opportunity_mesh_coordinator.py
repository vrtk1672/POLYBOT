from __future__ import annotations

from app.services.opportunity_mesh_coordinator import OpportunityMeshCoordinator
from app.services.opportunity_memory import OpportunityMemoryService

from opportunity_mesh_fixtures import prepare_opportunity_mesh_fixture, seed_paper_intent, seed_runtime_decision


def test_opportunity_mesh_classifies_ready_blocked_and_defense_softened(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_runtime_decision(decision_id="decision-ready", market_id="market-ready", score=61.0)
    seed_runtime_decision(
        decision_id="decision-learning",
        market_id="market-learning",
        score=45.0,
        evidence={
            "paper_defense": {
                "defense_level": 20,
                "ignored_blockers": ["THESIS_NOT_SUPPORTED"],
                "softened_blockers": ["EXIT_NOT_READY"],
                "profile": {"adjusted_threshold": 42},
            }
        },
    )
    seed_runtime_decision(
        decision_id="decision-integrity",
        market_id="market-integrity",
        decision="BLOCK",
        blockers=["MISSING_TOKEN_ID"],
        paper_enter_allowed=False,
    )

    payload = OpportunityMeshCoordinator().opportunity_mesh(limit=20)

    states = {item["runtime_decision_id"]: item["lifecycle_state"] for item in payload["items"]}
    assert states["decision-ready"] == "READY_FOR_INTENT"
    assert states["decision-learning"] == "ALLOWED_FOR_LEARNING"
    assert states["decision-integrity"] == "BLOCKED_INTEGRITY"
    assert payload["summary"]["ready_for_intent"] == 2
    assert payload["summary"]["blocked_integrity"] == 1
    assert payload["safety"]["paper_only"] is True


def test_opportunity_mesh_reports_expired_intent_state(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_paper_intent(
        intent_id="intent-mesh-expired",
        eligibility_id="eligibility-mesh-expired",
        market_id="market-mesh-expired",
        seconds_old=900,
    )
    OpportunityMemoryService().expire_stale_intents(limit=10)

    payload = OpportunityMeshCoordinator().opportunity_mesh(limit=20)

    assert payload["summary"]["intent_expired"] == 1
    item = next(row for row in payload["items"] if row.get("paper_intent_id") == "intent-mesh-expired")
    assert item["lifecycle_state"] == "INTENT_EXPIRED"
    assert item["next_action"] == "WAIT_FOR_NEW_EVIDENCE"

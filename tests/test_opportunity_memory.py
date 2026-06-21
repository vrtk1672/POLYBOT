from __future__ import annotations

from app.services.opportunity_memory import OpportunityMemoryService

from opportunity_mesh_fixtures import prepare_opportunity_mesh_fixture, seed_paper_intent


def test_expired_intent_creates_waiting_opportunity_memory(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_paper_intent(
        intent_id="intent-memory",
        eligibility_id="eligibility-memory",
        market_id="market-memory",
        side="YES",
        seconds_old=900,
        evidence={
            "source_evidence": {
                "market_id": "market-memory",
                "condition_id": "condition-market-memory",
                "side": "YES",
                "token_id": "token-market-memory-YES",
                "opportunity_score": 55.46,
                "decision": "ENTER",
                "paper_defense": {"defense_level": 20, "profile": {"adjusted_threshold": 42}},
            }
        },
    )

    OpportunityMemoryService().expire_stale_intents(limit=10)
    payload = OpportunityMemoryService().opportunity_memory(limit=10)

    assert payload["status"] == "OK"
    assert payload["counts"]["WAITING_FOR_NEW_EVIDENCE"] == 1
    item = payload["items"][0]
    assert item["market_id"] == "market-memory"
    assert item["side"] == "YES"
    assert item["status"] == "WAITING_FOR_NEW_EVIDENCE"
    assert item["evidence_fingerprint"]

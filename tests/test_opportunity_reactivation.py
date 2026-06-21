from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.paper_intents import PaperIntent
from app.repositories.paper_intent_repository import PaperIntentRepository
from app.services.opportunity_memory import OpportunityMemoryService

from opportunity_mesh_fixtures import (
    SESSION_ID,
    prepare_opportunity_mesh_fixture,
    seed_paper_intent,
    seed_runtime_decision,
)


def _source_evidence(score: float) -> dict[str, object]:
    return {
        "market_id": "market-reactivate",
        "condition_id": "condition-market-reactivate",
        "side": "YES",
        "token_id": "token-market-reactivate-YES",
        "decision": "ENTER",
        "opportunity_score": score,
        "paper_defense": {"defense_level": 20, "profile": {"adjusted_threshold": 42}},
        "paper_mode_policy": {"paper_enter_allowed": True, "blockers": [], "warnings": []},
    }


def test_same_evidence_waits_for_new_evidence(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_paper_intent(
        intent_id="intent-same-evidence",
        eligibility_id="eligibility-same-evidence",
        market_id="market-reactivate",
        side="YES",
        seconds_old=900,
        evidence={"source_evidence": _source_evidence(55.46)},
    )
    service = OpportunityMemoryService()
    service.expire_stale_intents(limit=10)
    seed_runtime_decision(
        decision_id="decision-same-evidence",
        market_id="market-reactivate",
        side="YES",
        score=55.46,
        evidence=_source_evidence(55.46),
    )

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            "SELECT * FROM paper_runtime_decisions WHERE decision_id='decision-same-evidence'"
        ).fetchone()
        gate = service.evaluate_runtime_decision(conn, dict(row), paper_session_id=SESSION_ID)

    assert gate["same_evidence_waiting"] is True
    assert gate["status"] == "WAITING_FOR_NEW_EVIDENCE"


def test_changed_evidence_can_reactivate_and_links_previous_memory(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_paper_intent(
        intent_id="intent-before-reactivation",
        eligibility_id="eligibility-before-reactivation",
        market_id="market-reactivate",
        side="YES",
        seconds_old=900,
        evidence={"source_evidence": _source_evidence(55.46)},
    )
    service = OpportunityMemoryService()
    service.expire_stale_intents(limit=10)
    intent = PaperIntent(
        paper_intent_id="intent-after-reactivation",
        eligibility_id="eligibility-after-reactivation",
        thesis_id="thesis",
        risk_decision_id="risk",
        exit_plan_id="exit",
        market_id="market-reactivate",
        side="YES",
        evidence={"quantity": 1.0, "source_evidence": _source_evidence(60.0)},
    )

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        row, created = PaperIntentRepository().upsert_paper_intent(conn, intent)
        attached = service.attach_intent_metadata(conn, row)
        event_count = conn.execute("SELECT COUNT(*) AS count FROM opportunity_reactivation_events").fetchone()["count"]
        memory_status = conn.execute("SELECT status FROM opportunity_memory LIMIT 1").fetchone()["status"]

    assert created is True
    assert attached["reactivated_from_memory_id"]
    assert int(event_count) == 1
    assert memory_status == "REACTIVATED"

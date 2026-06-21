from __future__ import annotations

from app.control_center.paper_actionability import PaperActionabilityService
from app.db.connection import DatabaseConnectionFactory
from app.services.paper_intents import PaperIntentGateService
from app.services.system_power import SystemPowerService

from paper_intent_fixtures import prepare_paper_intent_schema, seed_eligible_candidate, table_exists


def test_phase10_precheck_does_not_create_paper_intents_when_paper_off(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    SystemPowerService().turn_on(actor="test", reason="phase10_precheck")
    seed_eligible_candidate("phase10-precheck")

    with DatabaseConnectionFactory().connect() as conn:
        before = _count(conn, "paper_intents")
    actionability = PaperActionabilityService().list_actionability(limit=10)
    result = PaperIntentGateService().build_intents(limit=10, write_intents=True, write_no_trade=True)
    with DatabaseConnectionFactory().connect() as conn:
        after = _count(conn, "paper_intents")

    assert actionability["status"] == "REAL"
    assert result["status"] == "BLOCKED"
    assert result["error_summary"] == "PAPER_SIMULATION_OFF_NO_INTENT_CREATED"
    assert after == before


def test_historical_paper_intents_are_not_deleted_by_paper_off_guard(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    SystemPowerService().turn_on(actor="test", reason="phase10_historical")
    seed_eligible_candidate("phase10-historical")

    # Simulate historical paper truth in a test-only way, then turn Paper Simulation off.
    from app.control_center.paper_simulation import PaperSimulationActionRequest, PaperSimulationControlService

    PaperSimulationControlService().enable(PaperSimulationActionRequest(actor="test", reason="create historical"))
    PaperIntentGateService().build_intents(limit=10, write_intents=True, write_no_trade=True)
    PaperSimulationControlService().disable(PaperSimulationActionRequest(actor="test", reason="guard test"))
    with DatabaseConnectionFactory().connect() as conn:
        historical = _count(conn, "paper_intents")

    PaperIntentGateService().build_intents(limit=10, write_intents=True, write_no_trade=True)

    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_intents") == historical


def _count(conn, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)

from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_intents import PaperIntentGateService
from app.services.system_power import SystemPowerService

from paper_intent_fixtures import prepare_paper_intent_schema, seed_eligible_candidate, table_exists


ARTIFACT_TABLES = (
    "paper_intents",
    "paper_orders",
    "paper_fills",
    "paper_positions",
    "paper_position_closes",
    "live_orders",
    "positions",
)


def test_data_only_system_on_creates_no_paper_artifacts_when_paper_off(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    SystemPowerService().turn_on(actor="test", reason="data_only_no_artifacts")
    seed_eligible_candidate("data-only-no-artifacts")

    before = _counts()
    result = PaperIntentGateService().build_intents(limit=10, write_intents=True, write_no_trade=True)
    after = _counts()

    assert result["status"] == "BLOCKED"
    assert result["error_summary"] == "PAPER_SIMULATION_OFF_NO_INTENT_CREATED"
    for table in ARTIFACT_TABLES:
        assert after[table] == before[table]


def test_data_only_explanation_records_without_paper_intents(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    SystemPowerService().turn_on(actor="test", reason="data_only_explanation")
    seed_eligible_candidate("data-only-explanation")

    result = PaperIntentGateService().build_intents(limit=10, write_intents=True, write_no_trade=True)

    assert result["paper_intents_created"] == 0
    assert result["no_trade_records_created"] >= 1
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_intents") == 0
        row = conn.execute("SELECT blockers, evidence FROM no_trade_log ORDER BY created_at DESC LIMIT 1").fetchone()
    assert "PAPER_SIMULATION_OFF_NO_INTENT_CREATED" in row["blockers"]
    assert row["evidence"]["bridge_outcome"] == "BLOCKED_BY_PAPER_SIMULATION"


def _counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {table: _count(conn, table) for table in ARTIFACT_TABLES}


def _count(conn, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)

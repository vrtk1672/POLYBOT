from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import app
from app.services.truth_state import TruthStateService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "truth_state_decision_links",
            "truth_state_transitions",
            "truth_state_registry",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def test_fresh_critical_source_can_authorize(postgres_test_schema) -> None:
    _prepare()
    result = TruthStateService().classify_source(
        source_type="SAME_MARKET_GUARD",
        created_at_source=datetime.now(UTC),
        updated_at_source=datetime.now(UTC),
    )

    assert result["truth_state"] == "ACTIVE_FRESH"
    assert result["decision_permission"] == "CAN_AUTHORIZE"


def test_stale_critical_source_requires_refresh(postgres_test_schema) -> None:
    _prepare()
    result = TruthStateService().classify_source(
        source_type="SAME_MARKET_GUARD",
        created_at_source=datetime.now(UTC) - timedelta(hours=2),
        updated_at_source=datetime.now(UTC) - timedelta(hours=2),
    )

    assert result["truth_state"] == "REFRESH_REQUIRED"
    assert result["decision_permission"] == "MUST_REFRESH"


def test_stale_context_source_is_last_known_not_authorizing(postgres_test_schema) -> None:
    _prepare()
    result = TruthStateService().classify_source(
        source_type="PAYOUT_ODDS",
        created_at_source=datetime.now(UTC) - timedelta(hours=2),
        updated_at_source=datetime.now(UTC) - timedelta(hours=2),
    )

    assert result["truth_state"] == "LAST_KNOWN"
    assert result["decision_permission"] == "CAN_INFORM_ONLY"


def test_closed_position_is_historical_memory(postgres_test_schema) -> None:
    _prepare()
    result = TruthStateService().classify_source(
        source_type="PAPER_POSITION_CLOSED",
        created_at_source=datetime.now(UTC),
        metadata={"closed": True},
    )

    assert result["truth_state"] == "HISTORICAL_ONLY"
    assert result["decision_permission"] == "CAN_TEACH_ONLY"


def test_register_truth_writes_transition_and_dashboard_truth(postgres_test_schema) -> None:
    _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        row = TruthStateService().register_truth(
            conn,
            source_table="same_market_side_guard_decisions",
            source_record_id="guard-fresh-test",
            source_type="SAME_MARKET_GUARD",
            subject_type="PAPER_CANDIDATE",
            subject_id="candidate-truth-test",
            market_id="truth-market",
            side="YES",
            created_at_source=datetime.now(UTC),
            updated_at_source=datetime.now(UTC),
            metadata={"decision": "ALLOW"},
        )

    assert row["truth_state"] == "ACTIVE_FRESH"
    assert row["decision_permission"] == "CAN_AUTHORIZE"

    payload = TestClient(app).get("/dashboard/api/v2/truth-state").json()
    assert payload["mock_data"] is False
    assert payload["total_truth_records"] == 1
    assert payload["decision_permission_counts"]["CAN_AUTHORIZE"] == 1


def test_truth_state_audit_does_not_create_paper_artifacts(postgres_test_schema) -> None:
    _prepare()
    before = _safety_counts()
    payload = TestClient(app).post("/truth-state/audit", json={"limit": 5, "dry_run": False}).json()
    after = _safety_counts()

    assert payload["mock_data"] is False
    assert payload["trading_mutation"] is False
    assert before == after


def _safety_counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {
            table: _count(conn, table)
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "paper_capital_ledger", "live_orders", "orders_v2", "fills_v2", "positions")
        }


def _count(conn, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])

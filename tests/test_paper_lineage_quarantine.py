from __future__ import annotations

from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.paper_dashboard_truth import PaperDashboardTruthService
from app.services.paper_lineage_quarantine import PaperLineageQuarantineService


class _Power:
    def get_power_state(self) -> dict[str, object]:
        return {"power": "OFF", "system_power": "OFF", "runtime_work_allowed": False}


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_lineage_quarantine",
            "brain_dialogue_events",
            "paper_trade_ledger",
            "paper_position_closes",
            "paper_daily_pnl",
            "paper_fills",
            "paper_position_events",
            "paper_positions",
            "paper_order_events",
            "paper_orders",
            "paper_signals",
            "paper_runs",
            "paper_intents",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _seed_legacy_position() -> str:
    run_id = uuid4()
    signal_id = uuid4()
    order_id = uuid4()
    position_id = uuid4()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_runs (id, mode, started_at, ended_at, status, metadata_json)
            VALUES (%s, 'EXECUTION_AWARE_PAPER', now(), now(), 'COMPLETED', '{}'::jsonb)
            """,
            (run_id,),
        )
        conn.execute(
            """
            INSERT INTO paper_signals (
                id, paper_run_id, market_id, signal_type, intended_outcome,
                trade_type, bucket_type, guard_result, reason_code, reason_text, payload_json
            )
            VALUES (%s, %s, 'legacy-market', 'WOULD_ENTER', 'YES', 'PAPER_ENTRY', 'test', 'PASS', 'would_enter', 'test', %s)
            """,
            (signal_id, run_id, Jsonb({"stage": "would_enter"})),
        )
        conn.execute(
            """
            INSERT INTO paper_orders (
                id, paper_run_id, paper_signal_id, market_id, intended_outcome,
                action, intended_price, intended_size, notional, status,
                fill_ratio, filled_size, remaining_size, avg_fill_price,
                min_size_check_passed, payload_json
            )
            VALUES (%s, %s, %s, 'legacy-market', 'YES', 'BUY', 0.4, 10, 4, 'FILLED', 1, 10, 0, 0.4, true, %s)
            """,
            (order_id, run_id, signal_id, Jsonb({"execution_result": {"result_status": "FILLED"}})),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size,
                avg_entry, mark_price, unrealized, realized, current_status,
                thesis_state, invalidation_state, opened_at, updated_at,
                payload_json
            )
            VALUES (%s, %s, 'legacy-market', 'YES', 10, 0.4, 0.42, 0.2, 0, 'OPEN', 'ACTIVE', 'NONE', now(), now(), %s)
            """,
            (position_id, run_id, Jsonb({"last_paper_order_id": str(order_id)})),
        )
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (
                cycle_id, mode, status, started_at, finished_at,
                scanner_started, scanner_finished, intelligence_started,
                intelligence_finished, metadata_json
            )
            VALUES (%s, 'PAPER', 'COMPLETED', now(), now(), true, true, true, true, '{}'::jsonb)
            ON CONFLICT (cycle_id) DO NOTHING
            """,
            (f"test-cycle-{position_id}",),
        )
    return str(position_id)


def _service() -> PaperLineageQuarantineService:
    return PaperLineageQuarantineService(system_power=_Power())


def test_quarantine_detects_and_preserves_fillless_position(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_legacy_position()

    before = PaperDashboardTruthService().get_summary()
    result = _service().run_quarantine(actor="test")
    after = PaperDashboardTruthService().get_summary()

    assert before["positions_without_fills_count"] == 1
    assert before["positions_without_open_ledger_count"] == 1
    assert before["readiness_status"] == "RED"
    assert result["quarantined_count"] == 1
    assert after["positions_without_fills_count"] == 0
    assert after["positions_without_open_ledger_count"] == 0
    assert after["raw_positions_without_fills_count"] == 1
    assert after["raw_positions_without_open_ledger_count"] == 1
    assert after["quarantined_paper_positions_count"] == 1
    assert after["open_paper_positions"] == 0
    assert after["paper_lineage_readiness_status"] == "OK"
    with DatabaseConnectionFactory().connect() as conn:
        position = conn.execute("SELECT * FROM paper_positions WHERE id=%s", (position_id,)).fetchone()
        fills = conn.execute("SELECT COUNT(*) AS count FROM paper_fills").fetchone()["count"]
        ledger = conn.execute("SELECT COUNT(*) AS count FROM paper_trade_ledger").fetchone()["count"]
        quarantine = conn.execute("SELECT COUNT(*) AS count FROM paper_lineage_quarantine").fetchone()["count"]
    assert position is not None
    assert position["excluded_from_active_paper_truth"] is True
    assert position["current_status"] == "QUARANTINED"
    assert fills == 0
    assert ledger == 0
    assert quarantine == 1


def test_quarantine_is_idempotent(postgres_test_schema) -> None:
    _prepare()
    _seed_legacy_position()

    first = _service().run_quarantine(actor="test")
    second = _service().run_quarantine(actor="test")

    assert first["quarantined_count"] == 1
    assert second["quarantined_count"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_lineage_quarantine").fetchone()["count"] == 1


def test_soak_readiness_can_be_green_with_only_quarantined_legacy_rows(postgres_test_schema) -> None:
    _prepare()
    _seed_legacy_position()

    before = PaperDashboardTruthService().get_soak_readiness()
    _service().run_quarantine(actor="test")
    after = PaperDashboardTruthService().get_soak_readiness()

    assert before["readiness_status"] == "RED"
    assert before["can_start_4h_soak"] is False
    assert after["readiness_status"] == "GREEN"
    assert after["can_start_4h_soak"] is True
    assert after["preflight_counts"]["quarantined_paper_positions_count"] == 1
    assert "QUARANTINED_LEGACY_PAPER_POSITIONS_PRESENT" in after["warnings"]


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])

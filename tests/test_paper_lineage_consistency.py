from __future__ import annotations

from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_dashboard_truth import PaperDashboardTruthService
from test_paper_execution_service import _prepare, _seed_intent, _service


def test_dashboard_detects_position_without_fill(postgres_test_schema) -> None:
    _prepare()
    run_id = uuid4()
    signal_id = uuid4()
    order_id = uuid4()
    position_id = uuid4()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_runs (id, mode, started_at, ended_at, status, metadata_json)
            VALUES (%s, 'LEGACY_PAPER', now(), now(), 'COMPLETED', '{}'::jsonb)
            """,
            (run_id,),
        )
        conn.execute(
            """
            INSERT INTO paper_signals (
                id, paper_run_id, market_id, signal_type, intended_outcome,
                trade_type, bucket_type, guard_result, reason_code, reason_text, payload_json
            )
            VALUES (%s, %s, 'legacy-market', 'WOULD_ENTER', 'YES', 'PAPER_ENTRY', 'test', 'PASS', 'test', 'test', '{}'::jsonb)
            """,
            (signal_id, run_id),
        )
        conn.execute(
            """
            INSERT INTO paper_orders (
                id, paper_run_id, paper_signal_id, market_id, intended_outcome,
                action, intended_price, intended_size, notional, status,
                fill_ratio, filled_size, remaining_size, min_size_check_passed, payload_json
            )
            VALUES (%s, %s, %s, 'legacy-market', 'YES', 'BUY', 0.4, 1, 0.4, 'FILLED', 1, 1, 0, true, '{}'::jsonb)
            """,
            (order_id, run_id, signal_id),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry,
                mark_price, unrealized, realized, current_status, thesis_state,
                invalidation_state, opened_at, updated_at, payload_json
            )
            VALUES (%s, %s, 'legacy-market', 'YES', 1, 0.4, 0.4, 0, 0, 'OPEN', 'ACTIVE', 'NONE', now(), now(), %s)
            """,
            (position_id, run_id, Jsonb({"last_paper_order_id": str(order_id)})),
        )

    payload = PaperDashboardTruthService().get_summary()

    assert payload["positions_without_fills_count"] == 1
    assert payload["positions_without_open_ledger_count"] == 1
    assert payload["paper_lineage_consistency_status"] == "RED"
    assert payload["readiness_status"] == "RED"


def test_safe_execution_does_not_reopen_closed_position_from_same_intent(postgres_test_schema) -> None:
    _prepare()
    intent_id = _seed_intent()
    _service().run_execution(correlation_id="first")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        position = conn.execute("SELECT * FROM paper_positions").fetchone()
        conn.execute(
            """
            UPDATE paper_positions
            SET current_status='CLOSED', closed_at=now(), updated_at=now()
            WHERE id=%s
            """,
            (position["id"],),
        )
        conn.execute(
            """
            UPDATE paper_intents
            SET intent_status='CLOSED', closed_at=now(), updated_at=now()
            WHERE paper_intent_id=%s
            """,
            (intent_id,),
        )

    second = _service().run_execution(correlation_id="second")

    assert second["orders_created"] == 0
    assert second["fills_created"] == 0
    assert second["positions_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_fills").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_positions").fetchone()["count"] == 1

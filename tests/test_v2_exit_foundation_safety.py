from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.exit_foundation import ExitFoundationService
from app.services.mesh_blockers import MeshBlockersService


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _count(conn, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def test_exit_foundation_creates_no_executable_artifacts(postgres_test_schema) -> None:
    run_migrations()
    before: dict[str, int] = {}
    with DatabaseConnectionFactory().connect() as conn:
        for table in ("paper_orders", "order_intents", "fills_v2", "positions", "live_orders"):
            before[table] = _count(conn, table)

    result = ExitFoundationService().build_exit_plans(limit=10)

    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        for table in ("paper_orders", "order_intents", "fills_v2", "positions", "live_orders"):
            assert _count(conn, table) == before[table]
        if _table_exists(conn, "exit_plans"):
            safety = conn.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE paper_intent_allowed = true) AS paper_allowed,
                    COUNT(*) FILTER (WHERE execution_allowed = true) AS execution_allowed
                FROM exit_plans
                WHERE created_from = 'exit_foundation'
                """
            ).fetchone()
            assert safety["paper_allowed"] == 0
            assert safety["execution_allowed"] == 0


def test_mesh_blockers_exit_foundation_resolves_only_when_plans_exist(postgres_test_schema) -> None:
    run_migrations()
    blockers = MeshBlockersService().get_mesh_blockers()

    assert "NO_EXIT_FOUNDATION" in blockers["blocked_by"]

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO exit_plans (
                exit_plan_id, market_id, side, engine, risk_gate_run_id,
                entry_price, entry_size, max_hold_seconds,
                invalidation_rule_json, liquidity_exit_check_json,
                emergency_exit_json, exit_mode, plan_status, created_from,
                insufficient_data, insufficient_data_reasons_json, status,
                exit_type, invalidation_rules, emergency_exit_rules,
                liquidity_exit_check, time_exit_check, missing_exit_evidence,
                blockers, warnings, paper_intent_allowed, paper_exit_ready,
                execution_allowed, generated_by, producer_name,
                is_runtime_generated, is_dry_run_generated, created_at, updated_at
            )
            VALUES (
                'exit-safety', null, null, 'EXIT_FOUNDATION', 'risk-safety',
                0, 0, 3600, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
                'PAPER_SIM_EXIT', 'INSUFFICIENT_DATA', 'exit_foundation',
                true, '["RISK_BLOCKED"]'::jsonb, 'BLOCKED',
                'BLOCKED_NO_ENTRY_EXIT', '["ORDERBOOK_STALE"]'::jsonb,
                '["MANUAL_KILL"]'::jsonb, '{"max_spread":0.08}'::jsonb,
                '{"max_hold_seconds":3600}'::jsonb, '["MISSING_RISK_APPROVAL"]'::jsonb,
                '["RISK_BLOCKED"]'::jsonb, '[]'::jsonb, false, false, false,
                'runtime', 'exit_foundation', true, false, now(), now()
            )
            """
        )

    blockers_after = MeshBlockersService().get_mesh_blockers()

    assert "NO_EXIT_FOUNDATION" not in blockers_after["blocked_by"]
    assert "EXIT_PLANS_ALL_BLOCKED" in blockers_after["blocked_by"]

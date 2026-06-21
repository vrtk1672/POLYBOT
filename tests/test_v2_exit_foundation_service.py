from __future__ import annotations

import json

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.exit_foundation import ExitFoundationService


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "exit_plan_rules",
            "exit_plan_runs",
            "exit_plans",
            "risk_decisions",
            "thesis_profiles",
            "orderbook_snapshots",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _seed_risk(
    risk_id: str = "risk-runtime",
    *,
    decision: str = "BLOCK",
    risk_status: str = "BLOCKED",
    risk_approved: bool = False,
    market_id: str | None = "market-exit",
    side: str | None = "YES",
    orderbook: bool = True,
    mid_price: float = 0.5,
    blockers: list[str] | None = None,
) -> None:
    thesis_id = f"thesis-{risk_id}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        orderbook_id = None
        if orderbook and market_id:
            orderbook_id = conn.execute(
                """
                INSERT INTO orderbook_snapshots (
                    orderbook_snapshot_id, market_id, best_bid, best_ask, spread,
                    mid_price, liquidity_score, source, snapshot_status, is_stale,
                    collected_at, created_at
                )
                VALUES (%s, %s, %s, %s, 0.03, %s, 0.8, 'test', 'OK', false, now(), now())
                RETURNING id
                """,
                (f"book-{risk_id}", market_id, mid_price - 0.015, mid_price + 0.015, mid_price),
            ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO thesis_profiles (
                thesis_id, market_id, side, status, thesis_type, why_now,
                expected_move, confidence, evidence, missing_evidence,
                invalidation_rules, risk_notes, orderbook_snapshot_id,
                generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, paper_candidate_allowed, risk_required,
                exit_required, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, 'COMPLETE', 'RUNTIME_COORDINATOR_THESIS',
                'Exit test thesis.', 'UNKNOWN', 0.8, '{}'::jsonb,
                '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, %s,
                'runtime', 'thesis_profile_builder', true, false, false,
                true, true, now(), now()
            )
            """,
            (thesis_id, market_id, side, orderbook_id),
        )
        conn.execute(
            """
            INSERT INTO risk_decisions (
                risk_decision_id, thesis_id, market_id, decision, risk_status,
                risk_score, confidence, max_position_size, max_loss,
                market_risk_score, liquidity_risk_score, spread_risk_score,
                missing_data_risk_score, confidence_risk_score,
                daily_exposure_risk_score, risk_reasons, blockers, warnings,
                required_missing_evidence, source_thesis_status,
                orderbook_snapshot_id, paper_candidate_allowed,
                execution_allowed, risk_approved, exit_required,
                generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, 0.8, 10, 5,
                0.1, 0.1, 0.1, 0.0, 0.0, 0.0,
                %s::jsonb, %s::jsonb, '[]'::jsonb, '[]'::jsonb,
                'COMPLETE', %s, false, false, %s, true,
                'runtime', 'risk_core', true, false, now(), now()
            )
            """,
            (
                risk_id,
                thesis_id,
                market_id,
                decision,
                risk_status,
                0.1 if risk_approved else 1.0,
                json.dumps(blockers or []),
                json.dumps(blockers or []),
                orderbook_id,
                risk_approved,
            ),
        )


def test_block_risk_decision_creates_blocked_exit_plan(postgres_test_schema) -> None:
    _prepare()
    _seed_risk(decision="BLOCK", risk_approved=False, blockers=["THESIS_BLOCKED"])

    result = ExitFoundationService().build_exit_plans(limit=10)

    assert result["mock_data"] is False
    assert result["risk_decisions_checked"] == 1
    assert result["exit_plans_created"] == 1
    assert result["blocked_exit_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM exit_plans WHERE created_from = 'exit_foundation'").fetchone()
    assert row["status"] == "BLOCKED"
    assert row["paper_exit_ready"] is False
    assert row["paper_intent_allowed"] is False
    assert row["execution_allowed"] is False


def test_reject_risk_decision_creates_blocked_exit_plan(postgres_test_schema) -> None:
    _prepare()
    _seed_risk("risk-rejected", decision="REJECT", risk_status="HIGH", risk_approved=False)

    result = ExitFoundationService().build_exit_plans(limit=10)

    assert result["blocked_exit_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        blockers = conn.execute("SELECT blockers FROM exit_plans WHERE created_from = 'exit_foundation'").fetchone()["blockers"]
    assert "RISK_REJECTED" in blockers


def test_missing_market_orderbook_side_and_risk_approval_block_complete_exit(postgres_test_schema) -> None:
    _prepare()
    _seed_risk("risk-missing-market", market_id=None, orderbook=False)
    _seed_risk("risk-missing-book", orderbook=False)
    _seed_risk("risk-missing-side", side=None)

    result = ExitFoundationService().build_exit_plans(limit=10)

    assert result["complete_exit_count"] == 0
    assert result["missing_market_count"] == 1
    assert result["missing_orderbook_count"] >= 2
    assert result["missing_side_count"] == 1
    assert result["missing_risk_approval_count"] == 3


def test_approved_risk_with_market_side_and_orderbook_can_create_complete_exit(postgres_test_schema) -> None:
    _prepare()
    _seed_risk("risk-approved", decision="APPROVE", risk_status="LOW", risk_approved=True, mid_price=0.98)

    result = ExitFoundationService().build_exit_plans(limit=10)

    assert result["complete_exit_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM exit_plans WHERE created_from = 'exit_foundation'").fetchone()
    assert row["status"] == "COMPLETE"
    assert float(row["target_exit"]) == 0.99
    assert 0.01 <= float(row["stop_loss"]) <= 0.99
    assert row["max_hold_seconds"] == 3600
    assert row["paper_intent_allowed"] is False
    assert row["execution_allowed"] is False
    assert row["invalidation_rules"]
    assert row["emergency_exit_rules"]
    assert row["liquidity_exit_check"]

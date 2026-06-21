from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.control_center.query_service import ControlCenterQueryService
from app.control_center.truth_contract import ControlCenterFreshnessState
from app.control_center.truth_hardening import classify_freshness, truth_from_freshness
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.runtime.health_truth import HealthTruthService
from app.services.paper_dashboard_truth import PaperDashboardTruthService


def test_fresh_object_becomes_active_fresh() -> None:
    freshness, age = classify_freshness(datetime.now(UTC), stale_after_seconds=60)

    assert freshness == ControlCenterFreshnessState.FRESH
    assert age is not None
    assert truth_from_freshness(freshness, has_history=True).value == "ACTIVE_FRESH"


def test_missing_source_becomes_missing_unknown() -> None:
    freshness, age = classify_freshness(None, stale_after_seconds=60)

    assert freshness == ControlCenterFreshnessState.MISSING
    assert age is None
    assert truth_from_freshness(freshness, has_history=False).value == "UNKNOWN"


def test_registered_service_does_not_imply_running(postgres_test_schema) -> None:
    _prepare_core_tables()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO service_health (service_name, service_type, status, updated_at)
            VALUES ('decorative_service', 'test', 'RUNNING', now())
            ON CONFLICT (service_name) DO UPDATE SET status='RUNNING', updated_at=now()
            """
        )

    payload = ControlCenterQueryService().organs()
    services = {row["service_name"]: row for row in payload["data"]["services"]}

    assert services["decorative_service"]["runtime_state"] == "REGISTERED"
    assert services["decorative_service"]["readiness_state"] == "PARTIAL"
    assert payload["readiness_state"] == "PARTIAL"


def test_stale_runtime_cycle_becomes_stale(postgres_test_schema) -> None:
    _prepare_core_tables()
    stale_at = datetime.now(UTC) - timedelta(hours=2)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        _seed_system_state(conn)
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (
                cycle_id, mode, status, started_at, scanner_started, metadata_json
            )
            VALUES ('stale-running-cycle', 'DATA_ONLY', 'RUNNING', %s, true, '{}'::jsonb)
            """,
            (stale_at,),
        )

    payload = HealthTruthService().get_health_truth()

    assert payload["active_cycle_truth"]["freshness_state"] == "STALE"
    assert payload["active_cycle_truth"]["runtime_state"] == "STALE"


def test_historical_paper_ledger_success_does_not_imply_current_readiness(postgres_test_schema) -> None:
    _prepare_core_tables()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        _seed_system_state(conn)
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (
                cycle_id, mode, status, started_at, finished_at,
                scanner_started, scanner_finished, metadata_json
            )
            VALUES ('fresh-completed-cycle', 'DATA_ONLY', 'COMPLETED', now(), now(), true, true, '{}'::jsonb)
            """
        )
        conn.execute(
            """
            INSERT INTO paper_daily_pnl (
                pnl_date, realized_pnl, unrealized_pnl, net_pnl, gross_profit,
                gross_loss, closed_trades_count, winning_trades_count, losing_trades_count
            )
            VALUES (CURRENT_DATE, 1, 0, 1, 1, 0, 1, 1, 0)
            """
        )

    payload = PaperDashboardTruthService().get_summary()

    assert payload["paper_ledger_health_status"] == "GREEN"
    assert payload["readiness_state"] == "BLOCKED"
    assert "MISSING_ORDERBOOK_SOURCE" in payload["paper_execution_blockers"]
    assert payload["paper_execution_explanation"]["historical_success_does_not_imply_readiness"] is True


def test_current_stale_truth_overrides_historical_rows(postgres_test_schema) -> None:
    _prepare_core_tables()
    old = datetime.now(UTC) - timedelta(hours=3)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        _seed_system_state(conn)
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (
                cycle_id, mode, status, started_at, finished_at,
                scanner_started, scanner_finished, metadata_json
            )
            VALUES ('fresh-cycle-with-old-paper', 'DATA_ONLY', 'COMPLETED', now(), now(), true, true, '{}'::jsonb)
            """
        )
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, side, best_bid, best_ask,
                spread, mid_price, liquidity_score, source, snapshot_status,
                is_stale, snapshot_at, collected_at, created_at
            )
            VALUES ('old-book', 'market-1', 'YES', 0.4, 0.5, 0.1, 0.45, 0.8, 'test', 'OK', true, %s, %s, %s)
            """,
            (old, old, old),
        )
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, market_id, side, price_basis, orderbook_snapshot_id,
                intended_price, max_slippage, confidence, intent_status, intent_type,
                intent_reason, evidence, blockers, paper_only, live, execution_allowed,
                order_intent_created, generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, created_at, updated_at
            )
            VALUES (
                'old-intent', 'eligibility-old', 'thesis-old', 'risk-old', 'exit-old',
                'market-1', 'YES', 'ORDERBOOK_LIMIT', 1, 0.5, 0, 0.8, 'CREATED',
                'PAPER_ENTRY_INTENT', 'historical row', '{}'::jsonb, '[]'::jsonb,
                true, false, false, false, 'test', 'test', true, false, %s, %s
            )
            """,
            (old, old),
        )

    payload = PaperDashboardTruthService().get_summary()

    assert payload["truth_state"] == "LAST_KNOWN"
    assert payload["freshness_state"] == "STALE"
    assert payload["readiness_state"] == "BLOCKED"
    assert "STALE_ORDERBOOK_SOURCE" in payload["paper_execution_blockers"]
    assert "STALE_PAPER_INTENT_SOURCE" in payload["paper_execution_blockers"]


def _prepare_core_tables() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "system_state",
            "service_health",
            "runtime_cycles_v2",
            "paper_daily_pnl",
            "paper_intents",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "orderbook_snapshots",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _seed_system_state(conn) -> None:
    conn.execute(
        """
        INSERT INTO system_state (
            current_mode, state_status, kill_switch_active, cooldown_active,
            attack_mode_active, reason, actor, system_power, metadata_json
        )
        VALUES ('DATA_ONLY', 'ACTIVE', false, false, false, 'truth hardening test', 'pytest', 'OFF', '{}'::jsonb)
        """
    )


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.routes import create_router
from app.control_center.paper_readiness import PaperReadinessService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


class _Governor:
    def __init__(self, allow: bool = True) -> None:
        self.allow = allow

    def can_execute(self, action) -> bool:
        return self.allow


def test_system_power_off_blocks_paper_readiness(postgres_test_schema) -> None:
    _prepare(system_power="OFF", paper_simulation=True)

    payload = _service().get_readiness()

    assert payload["paper_readiness_state"] in {"NOT_READY", "BLOCKED"}
    assert payload["system_power_state"] == "OFF"
    assert "SYSTEM_POWER_OFF" in payload["blockers"]


def test_paper_simulation_off_is_explicit_blocker(postgres_test_schema) -> None:
    _prepare(paper_simulation=False)

    payload = _service().get_readiness()

    assert payload["paper_simulation_state"] == "OFF"
    assert "PAPER_SIMULATION_OFF" in payload["blockers"]


def test_governor_denial_is_explicit_blocker(postgres_test_schema) -> None:
    _prepare()

    payload = _service(allow=False).get_readiness()

    assert payload["governor_allows_paper"] is False
    assert "GOVERNOR_DENIED_PAPER" in payload["blockers"]


def test_stale_orderbook_blocks_execution(postgres_test_schema) -> None:
    _prepare(orderbook_age=timedelta(minutes=10), trusted_orderbook=True)

    payload = _service().get_readiness()

    assert payload["orderbook_state"] == "STALE"
    assert payload["paper_execution_readiness_state"] == "BLOCKED_BY_DATA"
    assert "STALE_ORDERBOOK" in payload["blockers"]


def test_missing_trusted_orderbook_blocks_execution(postgres_test_schema) -> None:
    _prepare(trusted_orderbook=False)

    payload = _service().get_readiness()

    assert payload["trusted_orderbook_state"] == "MISSING"
    assert "MISSING_TRUSTED_ORDERBOOK" in payload["blockers"]


def test_historical_paper_ledger_does_not_make_readiness_ready(postgres_test_schema) -> None:
    _prepare(seed_intent=False)
    _seed_historical_paper_ledger()

    payload = _service().get_readiness()

    assert payload["counts"]["paper_orders"] == 1
    assert payload["counts"]["paper_fills"] == 1
    assert payload["paper_readiness_state"] != "READY"
    assert "NO_FRESH_PAPER_INTENTS" in payload["blockers"]


def test_fresh_candidate_without_fresh_intent_is_waiting_not_ready(postgres_test_schema) -> None:
    _prepare(seed_intent=False)

    payload = _service().get_readiness()

    assert payload["candidate_state"] == "HAS_ELIGIBLE"
    assert payload["intent_state"] == "NO_INTENTS"
    assert payload["paper_readiness_state"] == "PARTIAL"
    assert payload["paper_execution_readiness_state"] == "WAITING_FOR_REFRESH"


def test_fresh_intent_with_stale_orderbook_is_not_executable(postgres_test_schema) -> None:
    _prepare(orderbook_age=timedelta(minutes=10), trusted_orderbook=True)

    payload = _service().get_readiness()

    assert payload["intent_state"] == "HAS_FRESH_INTENTS"
    assert payload["paper_execution_readiness_state"] == "BLOCKED_BY_DATA"
    assert payload["paper_readiness_state"] != "READY"


def test_risk_blocked_produces_risk_blocker(postgres_test_schema) -> None:
    _prepare(risk_approved=False)

    payload = _service().get_readiness()

    assert payload["risk_state"] == "BLOCKED"
    assert "RISK_BLOCKED" in payload["blockers"]


def test_exit_not_ready_produces_exit_blocker(postgres_test_schema) -> None:
    _prepare(exit_ready=False)

    payload = _service().get_readiness()

    assert payload["exit_state"] == "NOT_READY"
    assert "EXIT_NOT_READY" in payload["blockers"]


def test_capital_blocked_produces_capital_blocker(postgres_test_schema) -> None:
    _prepare(capital_available=0)

    payload = _service().get_readiness()

    assert payload["capital_state"] == "BLOCKED"
    assert "CAPITAL_NOT_OK" in payload["blockers"]


def test_full_readiness_requires_all_gates(postgres_test_schema) -> None:
    _prepare()

    payload = _service().get_readiness()

    assert payload["paper_readiness_state"] == "READY"
    assert payload["paper_execution_readiness_state"] == "EXECUTABLE"
    assert payload["blockers"] == []


def test_response_includes_required_truth_fields(postgres_test_schema) -> None:
    _prepare(paper_simulation=False)

    payload = _service().get_readiness()

    for key in ("source", "last_updated", "freshness_state", "readiness_state", "blockers", "warnings", "errors", "required_to_be_ready"):
        assert key in payload
    assert payload["source"]["paper_intents"] == "paper_intents"
    assert payload["readiness_state"] == payload["paper_readiness_state"]


def test_readiness_endpoint_does_not_create_paper_artifacts(postgres_test_schema) -> None:
    _prepare(seed_intent=False)
    before = _paper_artifact_counts()
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())

    response = TestClient(app).get("/dashboard/api/v2/control/paper-readiness")

    assert response.status_code == 200
    assert _paper_artifact_counts() == before


def _service(*, allow: bool = True) -> PaperReadinessService:
    governor = _Governor(allow=allow)
    return PaperReadinessService(connection_factory=DatabaseConnectionFactory(), governor=governor)


def _prepare(
    *,
    system_power: str = "ON",
    paper_simulation: bool = True,
    orderbook_age: timedelta = timedelta(seconds=5),
    trusted_orderbook: bool = True,
    seed_intent: bool = True,
    risk_approved: bool = True,
    exit_ready: bool = True,
    capital_available: float = 1000,
) -> None:
    run_migrations()
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "lifecycle_governance_sources",
            "lifecycle_governance_decisions",
            "paper_execution_runs",
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
            "paper_eligibility_candidates",
            "exit_plans",
            "risk_decisions",
            "orderbook_snapshots",
            "market_snapshots_v2",
            "runtime_cycles_v2",
            "service_health",
            "system_state",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO system_state (
                current_mode, state_status, kill_switch_active, cooldown_active,
                attack_mode_active, reason, actor, system_power, metadata_json
            )
            VALUES ('DATA_ONLY', 'ACTIVE', false, false, false, 'paper readiness test', 'pytest', %s, %s)
            """,
            (
                system_power,
                Jsonb({"paper_simulation": {"enabled": paper_simulation, "last_changed_at": now.isoformat()}}),
            ),
        )
        conn.execute(
            """
            INSERT INTO service_health (service_name, service_type, status, last_heartbeat_at, details_json)
            VALUES ('scheduler', 'runtime', 'RUNNING', %s, '{}'::jsonb)
            ON CONFLICT (service_name) DO UPDATE
            SET status = EXCLUDED.status, last_heartbeat_at = EXCLUDED.last_heartbeat_at, updated_at = now()
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (cycle_id, mode, status, started_at, finished_at, metadata_json)
            VALUES ('paper-ready-cycle', 'DATA_ONLY', 'COMPLETED', %s, %s, '{}'::jsonb)
            """,
            (now - timedelta(seconds=10), now),
        )
        conn.execute(
            """
            INSERT INTO market_snapshots_v2 (
                snapshot_id, market_id, cycle_id, current_price_yes, current_price_no,
                best_bid, best_ask, spread, liquidity, data_completeness_score, stale, snapshot_at
            )
            VALUES ('market-ready-snapshot', 'paper-ready-market', 'paper-ready-cycle', 0.52, 0.48, 0.50, 0.52, 0.02, 100, 1, false, %s)
            """,
            (now,),
        )
        snapshot_at = now - orderbook_age
        snapshot_status = "OK" if trusted_orderbook else "ERROR"
        best_ask = 0.52 if trusted_orderbook else None
        orderbook_row = conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, side, best_bid, best_ask,
                spread, mid_price, liquidity_score, source, snapshot_status,
                is_stale, snapshot_at, collected_at, created_at
            )
            VALUES ('book-ready', 'paper-ready-market', 'YES', 0.50, %s, 0.02, 0.51, 0.8, 'test', %s, false, %s, %s, %s)
            RETURNING id
            """,
            (best_ask, snapshot_status, snapshot_at, snapshot_at, now),
        ).fetchone()
        orderbook_id = orderbook_row["id"]
        conn.execute(
            """
            INSERT INTO risk_decisions (
                risk_decision_id, thesis_id, market_id, decision, risk_status,
                risk_score, confidence, risk_approved, blockers, created_at, updated_at
            )
            VALUES ('risk-ready', 'thesis-ready', 'paper-ready-market', %s, %s, 0.1, 0.9, %s, %s, %s, %s)
            """,
            (
                "APPROVE" if risk_approved else "BLOCK",
                "LOW" if risk_approved else "BLOCKED",
                risk_approved,
                Jsonb([] if risk_approved else ["RISK_BLOCKED"]),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO exit_plans (
                exit_plan_id, market_id, side, engine, entry_price, entry_size,
                exit_mode, plan_status, status, exit_type, risk_decision_ref,
                paper_exit_ready, blockers, created_at, updated_at
            )
            VALUES ('exit-ready', 'paper-ready-market', 'YES', 'EXIT_FOUNDATION', 0.52, 10,
                'PAPER_SIM_EXIT', %s, %s, 'BASIC_PROTECTIVE_EXIT', 'risk-ready',
                %s, %s, %s, %s)
            """,
            (
                "ACTIVE" if exit_ready else "INSUFFICIENT_DATA",
                "COMPLETE" if exit_ready else "BLOCKED",
                exit_ready,
                Jsonb([] if exit_ready else ["EXIT_NOT_READY"]),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                market_id, side, status, eligibility_score, eligibility_blockers,
                missing_requirements, evidence, orderbook_snapshot_id, link_confidence,
                lineage_trusted, risk_approved, exit_ready, not_dry_run, created_at, updated_at
            )
            VALUES ('eligibility-ready', 'thesis-ready', 'risk-ready', 'exit-ready',
                'paper-ready-market', 'YES', %s, 1, %s, '[]'::jsonb,
                %s, %s, 1, true, %s, %s, true, %s, %s)
            """,
            (
                "ELIGIBLE" if risk_approved and exit_ready else "BLOCKED",
                Jsonb([] if risk_approved and exit_ready else ["RISK_BLOCKED" if not risk_approved else "EXIT_NOT_READY"]),
                Jsonb({"orderbook_best_ask": 0.52, "orderbook_mid_price": 0.51}),
                orderbook_id,
                risk_approved,
                exit_ready,
                now,
                now,
            ),
        )
        if seed_intent:
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
                VALUES ('paper-intent-ready', 'eligibility-ready', 'thesis-ready', 'risk-ready',
                    'exit-ready', 'paper-ready-market', 'YES', 'ORDERBOOK_LIMIT', %s,
                    0.55, 0.05, 0.9, 'CREATED', 'PAPER_ENTRY_INTENT',
                    'test intent', %s, '[]'::jsonb, true, false, false,
                    false, 'test', 'paper_readiness_test', true, false, %s, %s)
                """,
                (orderbook_id, Jsonb({"quantity": 10, "intended_notional": 5}), now, now),
            )
        conn.execute(
            """
            INSERT INTO lifecycle_governance_decisions (
                decision_id, subject_type, subject_id, market_id, side,
                actionability_class, allow_paper_intent, allow_paper_execution,
                critical_blockers_json, reason, created_at
            )
            VALUES ('lifecycle-ready', 'PAPER_INTENT', 'paper-intent-ready', 'paper-ready-market', 'YES',
                %s, %s, %s, %s, 'test governance', %s)
            """,
            (
                "ACTIONABLE_SMALL_PAPER" if risk_approved and exit_ready else "HARD_BLOCK",
                risk_approved and exit_ready,
                risk_approved and exit_ready,
                Jsonb([] if risk_approved and exit_ready else ["LIFECYCLE_GOVERNANCE_DENIED"]),
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO paper_accounts (
                account_id, name, currency, initial_balance, current_balance,
                available_balance, locked_balance, open_exposure, max_open_positions, status, updated_at
            )
            VALUES ('paper_default', 'Default Paper Account', 'USD', 1000, 1000, %s, 0, 0, 3, 'ACTIVE', %s)
            ON CONFLICT (account_id) DO UPDATE SET
                available_balance = EXCLUDED.available_balance,
                current_balance = EXCLUDED.current_balance,
                locked_balance = 0,
                open_exposure = 0,
                max_open_positions = 3,
                updated_at = EXCLUDED.updated_at
            """,
            (capital_available, now),
        )


def _seed_historical_paper_ledger() -> None:
    old = datetime.now(UTC) - timedelta(days=5)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_runs (id, mode, started_at, ended_at, status, metadata_json)
            VALUES (%s, 'PAPER_SIM', %s, %s, 'COMPLETED', '{}'::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            (uuid4(), old, old),
        )
        run_id = conn.execute("SELECT id FROM paper_runs LIMIT 1").fetchone()["id"]
        signal_id = uuid4()
        order_id = uuid4()
        conn.execute(
            """
            INSERT INTO paper_signals (
                id, paper_run_id, market_id, signal_type, intended_outcome,
                trade_type, bucket_type, confidence, intended_price, intended_size,
                guard_result, reason_code, reason_text, payload_json
            )
            VALUES (%s, %s, 'old-market', 'WOULD_ENTER', 'YES', 'PAPER_ENTRY',
                'PAPER_INTENT', 0.8, 0.5, 1, 'PASS', 'old', 'old', '{}'::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            (signal_id, run_id),
        )
        conn.execute(
            """
            INSERT INTO paper_orders (
                id, paper_run_id, paper_signal_id, market_id, intended_outcome,
                action, intended_price, intended_size, notional, status, fill_ratio,
                filled_size, remaining_size, avg_fill_price, min_size_check_passed,
                payload_json, created_at
            )
            VALUES (%s, %s, %s, 'old-market', 'YES', 'BUY', 0.5, 1, 0.5,
                'FILLED', 1, 1, 0, 0.5, true, '{}'::jsonb, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (order_id, run_id, signal_id, old),
        )
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, market_id, side, price_basis, intended_price,
                max_slippage, confidence, intent_status, intent_type,
                intent_reason, evidence, blockers, paper_only, live, execution_allowed,
                order_intent_created, generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, created_at, updated_at
            )
            VALUES ('old-intent', 'old-eligibility', 'old-thesis', 'old-risk',
                'old-exit', 'old-market', 'YES', 'ORDERBOOK_LIMIT', 0.5,
                0, 0.8, 'CLOSED', 'PAPER_ENTRY_INTENT',
                'old historical intent', '{"quantity":1}'::jsonb, '[]'::jsonb,
                true, false, false, false, 'test', 'paper_readiness_test',
                true, false, %s, %s)
            ON CONFLICT (paper_intent_id) DO NOTHING
            """,
            (old, old),
        )
        conn.execute(
            """
            INSERT INTO paper_fills (
                paper_fill_id, paper_order_id, market_id, side, fill_price,
                quantity, price_basis, source_intent_id, metadata_json, created_at
            )
            VALUES ('old-fill', %s, 'old-market', 'YES', 0.5, 1, 'ORDERBOOK_LIMIT', 'old-intent', '{}'::jsonb, %s)
            ON CONFLICT (paper_fill_id) DO NOTHING
            """,
            (order_id, old),
        )


def _paper_artifact_counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {
            table: _count(conn, table)
            for table in ("paper_orders", "paper_fills", "paper_positions", "paper_position_closes")
        }


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _count(conn, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok", "source": "dummy-market-service"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}

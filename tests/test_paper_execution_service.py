from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.paper_execution import PaperExecutionService


class _Power:
    def __init__(self, on: bool = True) -> None:
        self.on = on

    def get_power_state(self) -> dict[str, object]:
        return {"power": "ON" if self.on else "OFF", "runtime_work_allowed": self.on}


class _Governor:
    def __init__(self, allow: bool = True) -> None:
        self.allow = allow

    def can_execute(self, action) -> bool:
        return self.allow


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "lifecycle_governance_sources",
            "lifecycle_governance_decisions",
            "trade_lifecycle_brain_contributions",
            "trade_lifecycle_plan_sources",
            "trade_lifecycle_plans",
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
            "orderbook_snapshots",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _service(*, on: bool = True, allow: bool = True) -> PaperExecutionService:
    return PaperExecutionService(system_power=_Power(on), governor=_Governor(allow))


def _seed_intent(
    *,
    market_id: str = "paper-exec-market",
    side: str = "YES",
    intended_price: float | None = 0.55,
    quantity: float | None = 10,
    best_ask: float | None = 0.52,
    stale: bool = False,
    intent_updated_at: datetime | None = None,
    omit_market: bool = False,
    omit_side: bool = False,
) -> str:
    now = datetime.now(UTC)
    intent_id = f"paper-intent-{uuid4().hex}"
    intent_updated_at = intent_updated_at or now
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        snapshot_id = None
        if best_ask is not None:
            row = conn.execute(
                """
                INSERT INTO orderbook_snapshots (
                    orderbook_snapshot_id, market_id, side, best_bid, best_ask,
                    spread, mid_price, liquidity_score, source, snapshot_status,
                    is_stale, snapshot_at, collected_at, created_at
                )
                VALUES (%s, %s, %s, 0.50, %s, 0.02, 0.51, 0.8, 'test', 'OK', %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    f"book-{intent_id}",
                    market_id,
                    side,
                    best_ask,
                    stale,
                    now - (timedelta(minutes=10) if stale else timedelta(seconds=5)),
                    now - (timedelta(minutes=10) if stale else timedelta(seconds=5)),
                    now,
                ),
            ).fetchone()
            snapshot_id = row["id"]
        evidence = {}
        if quantity is not None:
            evidence["quantity"] = quantity
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, coordinator_decision_id, market_id, side,
                price_basis, orderbook_snapshot_id, intended_price, max_slippage,
                confidence, intent_status, intent_type, intent_reason, evidence,
                blockers, paper_only, live, execution_allowed, order_intent_created,
                generated_by, producer_name, is_runtime_generated, is_dry_run_generated,
                created_at, updated_at
            )
            VALUES (
                %s, %s, 'thesis-test', 'risk-test',
                'exit-test', NULL, %s, %s,
                'ORDERBOOK_LIMIT', %s, %s, 0,
                0.8, 'CREATED', 'PAPER_ENTRY_INTENT', 'test executable paper intent', %s,
                '[]'::jsonb, true, false, false, false,
                'test', 'paper_execution_test', true, false,
                %s, %s
            )
            """,
            (
                intent_id,
                f"eligibility-{intent_id}",
                "" if omit_market else market_id,
                "" if omit_side else side,
                snapshot_id,
                intended_price,
                Jsonb(evidence),
                intent_updated_at,
                intent_updated_at,
            ),
        )
        if not omit_market and not omit_side and intended_price is not None:
            _seed_lifecycle_plan(conn, subject_type="PAPER_INTENT", subject_id=intent_id, market_id=market_id, side=side)
    return intent_id


def _seed_lifecycle_plan(
    conn,
    *,
    subject_type: str,
    subject_id: str,
    market_id: str,
    side: str,
    plan_status: str = "PARTIAL",
    strategy_type: str = "WATCH_ONLY",
    decision_class: str = "PAPER_INTENT_READY_CONTEXT",
    missing_inputs: list[str] | None = None,
) -> str:
    plan_id = f"trade-lifecycle-test-{subject_id}"
    conn.execute(
        """
        INSERT INTO trade_lifecycle_plans (
            plan_id, subject_type, subject_id, market_id, condition_id, side, token_id, mesh_session_id,
            strategy_type, plan_status, decision_class, economic_thesis, entry_thesis, exit_thesis,
            hold_to_resolution_thesis, invalidation_rules_json, capital_plan_json, monitoring_plan_json,
            risk_summary_json, liquidity_summary_json, payout_summary_json, exit_hold_summary_json,
            capital_efficiency_summary_json, same_market_summary_json, coordinator_judgment_json,
            missing_inputs_json, source_refs_json, metadata_json
        )
        VALUES (
            %s,%s,%s,%s,'condition-test',%s,'token-test',NULL,
            %s,%s,%s,'test economic thesis','test entry thesis','test exit thesis',
            'test hold thesis','[]'::jsonb,'{}'::jsonb,'[]'::jsonb,
            '{"decision":"APPROVE"}'::jsonb,'{"status":"OK"}'::jsonb,'{"evaluation_id":"payout-test"}'::jsonb,
            '{"decision":"WAIT"}'::jsonb,'{"recommendation":"CAPITAL_WATCH"}'::jsonb,
            '{"decision":"ALLOW"}'::jsonb,'{"final_action":"PAPER_INTENT_READY_CONTEXT"}'::jsonb,
            %s::jsonb,'{}'::jsonb,'{"test_fixture":true}'::jsonb
        )
        ON CONFLICT (plan_id) DO UPDATE SET
            plan_status=EXCLUDED.plan_status,
            strategy_type=EXCLUDED.strategy_type,
            decision_class=EXCLUDED.decision_class,
            missing_inputs_json=EXCLUDED.missing_inputs_json,
            updated_at=now()
        """,
        (
            plan_id,
            subject_type,
            subject_id,
            market_id,
            side,
            strategy_type,
            plan_status,
            decision_class,
            Jsonb(missing_inputs or ["MEMORY_CONTEXT_MISSING"]),
        ),
    )
    return plan_id


def test_system_off_blocks_paper_execution(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()

    result = _service(on=False).run_execution(correlation_id="off")

    assert result["status"] == "SYSTEM_POWER_OFF"
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 0
        assert _count(conn, "paper_fills") == 0
        assert _count(conn, "paper_positions") == 0


def test_system_on_respects_data_only_paper_permission(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()

    result = _service(allow=False).run_execution(correlation_id="mode-blocked")

    assert result["status"] == "PAPER_BLOCKED_BY_MODE"
    assert result["orders_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 0


def test_no_valid_paper_intents_creates_no_orders_fills_positions(postgres_test_schema) -> None:
    _prepare()

    result = _service().run_execution(correlation_id="no-intents")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["orders_created"] == 0


def test_stale_paper_intent_requires_refresh_before_execution(postgres_test_schema) -> None:
    _prepare()
    _seed_intent(intent_updated_at=datetime.now(UTC) - timedelta(hours=2))

    result = _service().run_execution(correlation_id="stale-intent")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["block_reasons_json"]["STALE_PAPER_INTENT"] == 1
    assert result["block_reasons_json"]["REFRESH_REQUIRED_BEFORE_EXECUTION"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0


def test_valid_paper_intent_creates_order_fill_and_position(postgres_test_schema) -> None:
    _prepare()
    intent_id = _seed_intent()

    result = _service().run_execution(correlation_id="valid")

    assert result["status"] == "OK"
    assert result["orders_created"] == 1
    assert result["fills_created"] == 1
    assert result["positions_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        order = conn.execute("SELECT * FROM paper_orders").fetchone()
        fill = conn.execute("SELECT * FROM paper_fills").fetchone()
        position = conn.execute("SELECT * FROM paper_positions").fetchone()
    assert order["status"] == "FILLED"
    assert fill["source_intent_id"] == intent_id
    assert float(fill["fill_price"]) == 0.52
    assert position["current_status"] == "OPEN"
    assert position["payload_json"]["source_intent_id"] == intent_id


def test_duplicate_run_does_not_duplicate_order_fill_or_position(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()

    first = _service().run_execution(correlation_id="first")
    second = _service().run_execution(correlation_id="second")

    assert first["orders_created"] == 1
    assert second["orders_created"] == 0
    assert second["status"] == "NO_VALID_PAPER_INTENTS"
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 1
        assert _count(conn, "paper_fills") == 1
        assert _count(conn, "paper_positions") == 1
        intent = conn.execute("SELECT * FROM paper_intents").fetchone()
    assert intent["intent_status"] == "POSITION_OPENED"
    assert intent["executed_at"] is not None
    assert intent["consumed_at"] is not None


def test_missing_required_fields_block_intent(postgres_test_schema) -> None:
    _prepare()
    _seed_intent(omit_market=True)
    _seed_intent(omit_side=True)
    _seed_intent(quantity=None)

    result = _service().run_execution(correlation_id="missing-fields")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["orders_created"] == 0
    reasons = result["block_reasons_json"]
    assert reasons["MISSING_MARKET_ID"] == 1
    assert reasons["MISSING_SIDE"] == 1
    assert reasons["MISSING_QUANTITY"] == 1


def test_missing_or_stale_orderbook_blocks_fill(postgres_test_schema) -> None:
    _prepare()
    _seed_intent(best_ask=None)
    _seed_intent(stale=True)

    result = _service().run_execution(correlation_id="bad-orderbook")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["fills_created"] == 0
    assert result["block_reasons_json"]["NO_EXECUTABLE_PAPER_PRICE"] == 2


def test_limit_not_marketable_blocks_execution(postgres_test_schema) -> None:
    _prepare()
    _seed_intent(intended_price=0.50, best_ask=0.52)

    result = _service().run_execution(correlation_id="limit-block")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["block_reasons_json"]["LIMIT_NOT_MARKETABLE"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 0


def _count(conn, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])

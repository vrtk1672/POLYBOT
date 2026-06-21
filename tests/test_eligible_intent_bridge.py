from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.routes import create_router
from app.control_center.eligible_intent_bridge import EligibleIntentBridgeService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.paper_intents import PaperIntentGateService


class _Governor:
    def __init__(self, allow: bool = True) -> None:
        self.allow = allow

    def can_execute(self, action) -> bool:
        return self.allow


class _RuntimeReadiness:
    def __init__(self, life: str = "ALIVE") -> None:
        self.life = life

    def get_readiness(self) -> dict[str, Any]:
        return {"data": {"runtime_life_state": self.life, "system_power_state": "ON", "warnings": [], "errors": []}}


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}


def test_existing_intent_returns_already_has_intent(postgres_test_schema) -> None:
    candidate_id = _prepare_case("existing-intent")
    _seed_intent(candidate_id)

    payload = _bridge().list_bridge()

    item = _item(payload, candidate_id)
    assert item["bridge_outcome"] == "ALREADY_HAS_INTENT"
    assert item["existing_intent_id"] == f"paper_intent_{candidate_id}"


def test_system_power_off_blocks_runtime(postgres_test_schema) -> None:
    candidate_id = _prepare_case("power-off", system_power="OFF")

    item = _item(_bridge().list_bridge(), candidate_id)

    assert item["bridge_outcome"] == "BLOCKED_BY_RUNTIME"
    assert "SYSTEM_POWER_OFF" in item["blockers"]


def test_paper_simulation_off_blocks_bridge(postgres_test_schema) -> None:
    candidate_id = _prepare_case("paper-off", paper_simulation=False)

    item = _item(_bridge().list_bridge(), candidate_id)

    assert item["bridge_outcome"] == "BLOCKED_BY_PAPER_SIMULATION"
    assert "PAPER_SIMULATION_OFF" in item["blockers"]


def test_governor_denial_blocks_bridge(postgres_test_schema) -> None:
    candidate_id = _prepare_case("governor-denied")

    item = _item(_bridge(allow=False).list_bridge(), candidate_id)

    assert item["bridge_outcome"] == "BLOCKED_BY_GOVERNOR"
    assert "GOVERNOR_DENIED_PAPER" in item["blockers"]


def test_stale_orderbook_waits_for_refresh(postgres_test_schema) -> None:
    candidate_id = _prepare_case("stale-book", orderbook_age=timedelta(minutes=10))

    item = _item(_bridge().list_bridge(), candidate_id)

    assert item["bridge_outcome"] == "WAITING_FOR_REFRESH"
    assert "STALE_ORDERBOOK" in item["blockers"]


def test_missing_executable_price_blocks_by_price(postgres_test_schema) -> None:
    candidate_id = _prepare_case("missing-price", evidence={})

    item = _item(_bridge().list_bridge(), candidate_id)

    assert item["bridge_outcome"] == "BLOCKED_BY_PRICE"
    assert "MISSING_EXECUTABLE_PRICE" in item["blockers"]
    assert "quantity" in item["missing_data"]


def test_missing_quantity_blocks_by_price_or_data(postgres_test_schema) -> None:
    candidate_id = _prepare_case("missing-quantity", evidence={"orderbook_best_ask": ""})

    item = _item(_bridge().list_bridge(), candidate_id)

    assert item["bridge_outcome"] in {"BLOCKED_BY_PRICE", "BLOCKED_BY_DATA"}
    assert "MISSING_QUANTITY" in item["blockers"]


def test_capital_block_returns_capital_outcome(postgres_test_schema) -> None:
    candidate_id = _prepare_case("capital-block", capital_available=0)

    item = _item(_bridge().list_bridge(), candidate_id)

    assert item["bridge_outcome"] == "BLOCKED_BY_CAPITAL"
    assert "CAPITAL_NOT_OK" in item["blockers"]


def test_lifecycle_denial_returns_lifecycle_outcome(postgres_test_schema) -> None:
    candidate_id = _prepare_case("lifecycle-denied", lifecycle_allow=False)

    item = _item(_bridge().list_bridge(), candidate_id)

    assert item["bridge_outcome"] == "BLOCKED_BY_LIFECYCLE"
    assert "LIFECYCLE_GOVERNANCE_DENIED" in item["blockers"]


def test_risk_inconsistency_returns_risk_outcome(postgres_test_schema) -> None:
    candidate_id = _prepare_case("risk-block", risk_approved=False)

    item = _item(_bridge().list_bridge(), candidate_id)

    assert item["bridge_outcome"] == "BLOCKED_BY_RISK"
    assert "RISK_NOT_APPROVED" in item["blockers"]


def test_exit_inconsistency_returns_exit_outcome(postgres_test_schema) -> None:
    candidate_id = _prepare_case("exit-block", exit_ready=False)

    item = _item(_bridge().list_bridge(), candidate_id)

    assert item["bridge_outcome"] == "BLOCKED_BY_EXIT"
    assert "EXIT_NOT_READY" in item["blockers"]


def test_eligible_without_intent_is_explained_and_gap_counted(postgres_test_schema) -> None:
    candidate_id = _prepare_case("gap")

    payload = _bridge().list_bridge()
    item = _item(payload, candidate_id)

    assert item["bridge_outcome"] == "READY_FOR_INTENT"
    assert item["can_create_intent_now"] is True
    assert payload["eligible_intent_gap"]["eligible_without_intent"] == 1
    assert payload["eligible_intent_gap"]["explained_without_intent"] == 1
    assert payload["eligible_intent_gap"]["unexplained_without_intent"] == 0


def test_read_only_endpoint_creates_no_paper_artifacts(postgres_test_schema) -> None:
    _prepare_case("read-only")
    before = _artifact_counts()
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())

    response = TestClient(app).get("/dashboard/api/v2/control/eligible-intent-bridge")

    assert response.status_code == 200
    assert _artifact_counts() == before


def test_normal_gate_records_no_trade_bridge_outcome_when_power_off(postgres_test_schema) -> None:
    candidate_id = _prepare_case("normal-bridge", system_power="OFF")

    result = PaperIntentGateService().build_intents(limit=10, write_intents=True, write_no_trade=True)

    assert result["paper_intents_created"] == 0
    assert result["no_trade_records_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        no_trade = conn.execute("SELECT * FROM no_trade_log WHERE eligibility_id=%s", (candidate_id,)).fetchone()
        assert no_trade is not None
        assert no_trade["evidence"]["bridge_outcome"] == "BLOCKED_BY_RUNTIME"
        assert "SYSTEM_POWER_OFF" in no_trade["blockers"]


def test_single_candidate_endpoint_returns_bridge_detail(postgres_test_schema) -> None:
    candidate_id = _prepare_case("detail")
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())

    response = TestClient(app).get(f"/dashboard/api/v2/control/eligible-intent-bridge/{candidate_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate"]["candidate_id"] == candidate_id
    assert payload["candidate"]["bridge_outcome"] in {"READY_FOR_INTENT", "BLOCKED_BY_RUNTIME"}


def _bridge(*, allow: bool = True, life: str = "ALIVE") -> EligibleIntentBridgeService:
    return EligibleIntentBridgeService(
        connection_factory=DatabaseConnectionFactory(),
        governor=_Governor(allow=allow),
        runtime_readiness=_RuntimeReadiness(life=life),
    )


def _prepare_case(
    suffix: str,
    *,
    system_power: str = "ON",
    paper_simulation: bool = True,
    orderbook_age: timedelta = timedelta(seconds=5),
    evidence: dict[str, Any] | None = None,
    capital_available: float = 1000,
    lifecycle_allow: bool = True,
    risk_approved: bool = True,
    exit_ready: bool = True,
) -> str:
    run_migrations()
    now = datetime.now(UTC)
    candidate_id = f"eligibility-{suffix}"
    market_id = f"market-{suffix}"
    thesis_id = f"thesis-{suffix}"
    risk_id = f"risk-{suffix}"
    exit_id = f"exit-{suffix}"
    evidence = {"orderbook_best_ask": 0.52, "orderbook_mid_price": 0.51} if evidence is None else evidence
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "no_trade_runs",
            "paper_intent_runs",
            "no_trade_log",
            "paper_intents",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "lifecycle_governance_decisions",
            "paper_eligibility_candidates",
            "exit_plans",
            "risk_decisions",
            "orderbook_snapshots",
            "paper_accounts",
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
            VALUES ('DATA_ONLY', 'ACTIVE', false, false, false, 'bridge test', 'pytest', %s, %s)
            """,
            (system_power, Jsonb({"paper_simulation": {"enabled": paper_simulation, "last_changed_at": now.isoformat()}})),
        )
        snapshot_at = now - orderbook_age
        orderbook_id = conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, side, best_bid, best_ask,
                spread, mid_price, liquidity_score, source, snapshot_status,
                is_stale, snapshot_at, collected_at, created_at
            )
            VALUES (%s, %s, 'YES', 0.50, 0.52, 0.02, 0.51, 0.8, 'test', 'OK',
                false, %s, %s, %s)
            RETURNING id
            """,
            (f"book-{suffix}", market_id, snapshot_at, snapshot_at, now),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO risk_decisions (
                risk_decision_id, thesis_id, market_id, decision, risk_status,
                risk_score, confidence, risk_approved, blockers, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, 0.1, 0.9, %s, %s, %s, %s)
            """,
            (
                risk_id,
                thesis_id,
                market_id,
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
            VALUES (%s, %s, 'YES', 'EXIT_FOUNDATION', 0.52, 10,
                'PAPER_SIM_EXIT', %s, %s, 'BASIC_PROTECTIVE_EXIT', %s,
                %s, %s, %s, %s)
            """,
            (
                exit_id,
                market_id,
                "ACTIVE" if exit_ready else "INSUFFICIENT_DATA",
                "COMPLETE" if exit_ready else "BLOCKED",
                risk_id,
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
                lineage_trusted, risk_approved, exit_ready, not_dry_run,
                paper_intent_allowed, execution_allowed, generated_by, producer_name,
                is_runtime_generated, is_dry_run_generated, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, 'YES', 'ELIGIBLE', 1, '[]'::jsonb,
                '[]'::jsonb, %s, %s, 1, true, %s, %s, true, false, false,
                'runtime', 'paper_eligibility_gate', true, false, %s, %s)
            """,
            (candidate_id, thesis_id, risk_id, exit_id, market_id, Jsonb(evidence), orderbook_id, risk_approved, exit_ready, now, now),
        )
        conn.execute(
            """
            INSERT INTO lifecycle_governance_decisions (
                decision_id, subject_type, subject_id, market_id, side,
                actionability_class, allow_paper_intent, allow_paper_execution,
                critical_blockers_json, reason, created_at
            )
            VALUES (%s, 'PAPER_CANDIDATE', %s, %s, 'YES', %s, %s, %s, %s, 'bridge test', %s)
            """,
            (
                f"lifecycle-{suffix}",
                candidate_id,
                market_id,
                "ACTIONABLE_SMALL_PAPER" if lifecycle_allow else "HARD_BLOCK",
                lifecycle_allow,
                lifecycle_allow,
                Jsonb([] if lifecycle_allow else ["LIFECYCLE_GOVERNANCE_DENIED"]),
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
            """,
            (capital_available, now),
        )
    return candidate_id


def _seed_intent(candidate_id: str) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        candidate = conn.execute("SELECT * FROM paper_eligibility_candidates WHERE eligibility_id=%s", (candidate_id,)).fetchone()
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
            VALUES (%s, %s, %s, %s, %s, %s, 'YES', 'ORDERBOOK_BEST_ASK', %s,
                0.52, 0.02, 1, 'CREATED', 'PAPER_ENTRY_INTENT',
                'test intent', '{}'::jsonb, '[]'::jsonb, true, false, false,
                false, 'test', 'paper_intent_gate', true, false, now(), now())
            """,
            (
                f"paper_intent_{candidate_id}",
                candidate_id,
                candidate["thesis_id"],
                candidate["risk_decision_id"],
                candidate["exit_plan_id"],
                candidate["market_id"],
                candidate["orderbook_snapshot_id"],
            ),
        )


def _item(payload: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for item in payload["items"]:
        if item["candidate_id"] == candidate_id:
            return item
    raise AssertionError(f"candidate not found: {candidate_id}")


def _artifact_counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {table: _count_table(conn, table) for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "no_trade_log")}


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)

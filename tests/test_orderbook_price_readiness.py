from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.routes import create_router
from app.control_center.candidate_explanations import CandidateExplanationLedgerService
from app.control_center.eligible_intent_bridge import EligibleIntentBridgeService
from app.control_center.orderbook_price_readiness import OrderbookPriceReadinessService
from app.control_center.paper_readiness import PaperReadinessService
from app.control_center.runtime_supervisor import RuntimeSupervisorService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


class _Governor:
    def can_execute(self, action) -> bool:
        return True


class _Runtime:
    def get_readiness(self) -> dict[str, Any]:
        return {"data": {"runtime_life_state": "ALIVE", "system_power_state": "ON", "warnings": [], "errors": []}}


class _OrderbookRefresher:
    def run(self, **kwargs) -> dict[str, Any]:
        return {
            "watch_items_checked": 0,
            "orderbooks_refreshed": 0,
            "snapshots_created": 0,
            "events_published": 0,
            "blocker_counts": {"ORDERBOOK_REFRESH_NOT_WIRED": 1},
            "safety_counts_before": {},
            "safety_counts_after": {},
            "live_orders_delta": 0,
            "real_orders_delta": 0,
        }


def test_missing_orderbook_returns_missing_blocker(postgres_test_schema) -> None:
    candidate_id = _prepare_case("missing-book", seed_orderbook=False)

    item = _item(candidate_id)

    assert item["orderbook_state"] == "MISSING"
    assert item["price_path_state"] == "BLOCKED_MISSING_ORDERBOOK"
    assert "MISSING_ORDERBOOK" in item["blockers"]


def test_stale_orderbook_requires_refresh(postgres_test_schema) -> None:
    candidate_id = _prepare_case("stale-book", orderbook_age=timedelta(minutes=10))

    item = _item(candidate_id)

    assert item["orderbook_state"] == "STALE"
    assert item["price_path_state"] == "WAITING_FOR_ORDERBOOK_REFRESH"
    assert item["refresh_before_execution_state"] == "REQUIRED"
    assert "STALE_ORDERBOOK" in item["blockers"]


def test_fresh_trusted_orderbook_is_price_ready(postgres_test_schema) -> None:
    candidate_id = _prepare_case("fresh-book")

    item = _item(candidate_id)

    assert item["trusted_orderbook_state"] == "TRUSTED_FRESH"
    assert item["price_path_state"] == "PRICE_READY"
    assert item["entry_price_source"] == "BEST_ASK"
    assert item["exit_liquidity_state"] in {"EXIT_LIQUIDITY_READY", "EXIT_LIQUIDITY_WEAK"}


def test_missing_token_and_side_are_explicit(postgres_test_schema) -> None:
    missing_token = _prepare_case("missing-token", expected_token=None, market_tokens=False)
    missing_side = _prepare_case("missing-side", side=None, expected_token=None, market_tokens=False, reset=False)

    token_item = _item(missing_token)
    side_item = _item(missing_side)

    assert token_item["price_path_state"] == "BLOCKED_MISSING_TOKEN"
    assert "token_id" in token_item["missing_data"]
    assert side_item["price_path_state"] == "BLOCKED_MISSING_SIDE"
    assert "side" in side_item["missing_data"]


def test_entry_price_source_is_not_guessed_when_bid_ask_missing(postgres_test_schema) -> None:
    candidate_id = _prepare_case("partial-book", best_ask=None, mid_price=None)

    item = _item(candidate_id)

    assert item["entry_price_source"] == "MISSING"
    assert item["entry_price"] is None
    assert "MISSING_EXECUTABLE_PRICE" in item["blockers"]


def test_paper_readiness_includes_price_path_state(postgres_test_schema) -> None:
    _prepare_case("paper-price", paper_simulation=False)

    payload = PaperReadinessService(
        connection_factory=DatabaseConnectionFactory(),
        governor=_Governor(),
        runtime_readiness=_Runtime(),
    ).get_readiness()

    assert payload["paper_simulation_state"] == "OFF"
    assert payload["paper_readiness_state"] == "BLOCKED"
    assert payload["price_path_state"] in {"PRICE_READY", "WAITING_FOR_ORDERBOOK_REFRESH", "BLOCKED_MISSING_ORDERBOOK"}
    assert "price_ready_candidates" in payload["counts"]


def test_candidate_explanation_and_bridge_include_price_path(postgres_test_schema) -> None:
    candidate_id = _prepare_case("integrated", orderbook_age=timedelta(minutes=10))

    explanation = CandidateExplanationLedgerService(connection_factory=DatabaseConnectionFactory()).get_explanation(candidate_id)["candidate"]
    bridge = EligibleIntentBridgeService(
        connection_factory=DatabaseConnectionFactory(),
        governor=_Governor(),
        runtime_readiness=_Runtime(),
    ).get_bridge(candidate_id)["candidate"]

    assert explanation["evidence"]["orderbook"]["price_path"]["orderbook_age_seconds"] is not None
    assert "Orderbook must be refreshed within execution TTL." in explanation["required_to_pass"]
    assert bridge["source_evidence"]["price"]["price_path"]["price_path_state"] == "WAITING_FOR_ORDERBOOK_REFRESH"
    assert "STALE_ORDERBOOK" in bridge["blockers"]


def test_endpoint_is_read_only_and_creates_no_paper_artifacts(postgres_test_schema) -> None:
    _prepare_case("readonly")
    before = _artifact_counts()
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())

    response = TestClient(app).get("/dashboard/api/v2/control/orderbook-price-readiness")

    assert response.status_code == 200
    assert _artifact_counts() == before


def test_supervisor_orderbook_refresh_exposes_explicit_blocker(postgres_test_schema) -> None:
    result = RuntimeSupervisorService(governor=_Governor(), orderbook_refresher=_OrderbookRefresher())._run_orderbook_refresher_module()

    assert result.module == "orderbook_refresher"
    assert result.status == "COMPLETED"
    assert "ORDERBOOK_REFRESH_NOT_WIRED" in result.warnings


def _item(candidate_id: str) -> dict[str, Any]:
    payload = OrderbookPriceReadinessService(connection_factory=DatabaseConnectionFactory()).get_readiness(candidate_id=candidate_id)
    assert payload["items"], payload
    return payload["items"][0]


def _prepare_case(
    suffix: str,
    *,
    seed_orderbook: bool = True,
    orderbook_age: timedelta = timedelta(seconds=5),
    expected_token: str | None = "token-yes",
    side: str | None = "YES",
    best_ask: float | None = 0.52,
    mid_price: float | None = 0.51,
    market_tokens: bool = True,
    paper_simulation: bool = True,
    reset: bool = True,
) -> str:
    run_migrations()
    now = datetime.now(UTC)
    candidate_id = f"eligibility-{suffix}"
    market_id = f"market-{suffix}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        if reset:
            for table in (
                "trusted_orderbook_evidence_links",
                "paper_intents",
                "paper_orders",
                "paper_fills",
                "paper_positions",
                "paper_eligibility_candidates",
                "no_trade_log",
                "lifecycle_governance_decisions",
                "exit_plans",
                "risk_decisions",
                "thesis_profiles",
                "orderbook_snapshots",
                "market_snapshots_v2",
                "markets_v2",
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
            VALUES ('DATA_ONLY', 'ACTIVE', false, false, false, 'orderbook price test', 'pytest', 'ON', %s)
            """,
            (Jsonb({"paper_simulation": {"enabled": paper_simulation, "last_changed_at": now.isoformat()}}),),
        )
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (cycle_id, mode, status, started_at, finished_at, metadata_json)
            VALUES (%s, 'DATA_ONLY', 'COMPLETED', %s, %s, '{}'::jsonb)
            """,
            (f"cycle-{suffix}", now - timedelta(seconds=10), now),
        )
        conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, question, condition_id, yes_token_id, no_token_id,
                active, closed, archived, accepting_orders, last_seen_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, true, false, false, true, %s, %s)
            """,
            (
                market_id,
                f"Question {suffix}?",
                f"condition-{suffix}",
                "token-yes" if market_tokens else None,
                "token-no" if market_tokens else None,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO market_snapshots_v2 (
                snapshot_id, market_id, current_price_yes, current_price_no,
                best_bid, best_ask, spread, liquidity, data_completeness_score, stale, snapshot_at
            )
            VALUES (%s, %s, 0.52, 0.48, 0.50, 0.52, 0.02, 100, 1, false, %s)
            """,
            (f"snapshot-{suffix}", market_id, now),
        )
        orderbook_id = None
        if seed_orderbook:
            snapshot_at = now - orderbook_age
            orderbook_id = conn.execute(
                """
                INSERT INTO orderbook_snapshots (
                    orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask,
                    spread, mid_price, depth_1c, depth_2c, depth_5c,
                    depth_bid_2c, liquidity_score, source, snapshot_status,
                    is_stale, snapshot_at, collected_at, created_at
                )
                VALUES (%s, %s, %s, %s, 0.50, %s, 0.02, %s, 100, 200, 500,
                    100, 0.8, 'test', 'OK', false, %s, %s, %s)
                RETURNING id
                """,
                (f"book-{suffix}", market_id, expected_token, side, best_ask, mid_price, snapshot_at, snapshot_at, now),
            ).fetchone()["id"]
            if expected_token and side:
                conn.execute(
                    """
                    INSERT INTO trusted_orderbook_evidence_links (
                        link_id, candidate_id, market_id, side, expected_token_id,
                        orderbook_snapshot_id, orderbook_snapshot_ref, orderbook_token_id,
                        trusted, trust_status, trust_reason, best_bid, best_ask,
                        mid_price, spread, liquidity_score, age_seconds,
                        freshness_threshold_seconds, evidence_json, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, 'TRUSTED',
                        'TRUSTED_ORDERBOOK', 0.50, %s, %s, 0.02, 0.8, 0,
                        180, '{}'::jsonb, %s)
                    """,
                    (
                        f"trusted-{suffix}",
                        candidate_id,
                        market_id,
                        side,
                        expected_token,
                        orderbook_id,
                        f"book-{suffix}",
                        expected_token,
                        best_ask,
                        mid_price,
                        now,
                    ),
                )
        conn.execute(
            """
            INSERT INTO risk_decisions (
                risk_decision_id, thesis_id, market_id, decision, risk_status,
                risk_score, confidence, risk_approved, blockers, created_at, updated_at
            )
            VALUES (%s, %s, %s, 'APPROVE', 'LOW', 0.1, 0.9, true, '[]'::jsonb, %s, %s)
            """,
            (f"risk-{suffix}", f"thesis-{suffix}", market_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO exit_plans (
                exit_plan_id, market_id, side, engine, entry_price, entry_size,
                exit_mode, plan_status, status, exit_type, risk_decision_ref,
                paper_exit_ready, blockers, created_at, updated_at
            )
            VALUES (%s, %s, %s, 'EXIT_FOUNDATION', 0.52, 10,
                'PAPER_SIM_EXIT', 'ACTIVE', 'COMPLETE', 'BASIC_PROTECTIVE_EXIT',
                %s, true, '[]'::jsonb, %s, %s)
            """,
            (f"exit-{suffix}", market_id, side or "YES", f"risk-{suffix}", now, now),
        )
        conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                market_id, side, status, eligibility_score, eligibility_blockers,
                missing_requirements, evidence, orderbook_snapshot_id, link_confidence,
                lineage_trusted, risk_approved, exit_ready, not_dry_run,
                paper_intent_allowed, execution_allowed, generated_by, producer_name,
                is_runtime_generated, is_dry_run_generated, expected_token_id, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'ELIGIBLE', 1, '[]'::jsonb,
                '[]'::jsonb, %s, %s, 1, true, true, true, true,
                false, false, 'runtime', 'paper_eligibility_gate',
                true, false, %s, %s, %s)
            """,
            (
                candidate_id,
                f"thesis-{suffix}",
                f"risk-{suffix}",
                f"exit-{suffix}",
                market_id,
                side,
                Jsonb({"orderbook_best_ask": best_ask, "orderbook_mid_price": mid_price}),
                orderbook_id,
                expected_token,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO lifecycle_governance_decisions (
                decision_id, subject_type, subject_id, market_id, side,
                actionability_class, allow_paper_intent, allow_paper_execution,
                critical_blockers_json, reason, created_at
            )
            VALUES (%s, 'PAPER_CANDIDATE', %s, %s, %s,
                'ACTIONABLE_SMALL_PAPER', true, true, '[]'::jsonb, 'test', %s)
            """,
            (f"lifecycle-{suffix}", candidate_id, market_id, side or "YES", now),
        )
        conn.execute(
            """
            INSERT INTO paper_accounts (
                account_id, name, currency, initial_balance, current_balance,
                available_balance, locked_balance, open_exposure, max_open_positions, status, updated_at
            )
            VALUES ('paper_default', 'Default Paper Account', 'USD', 1000, 1000, 1000, 0, 0, 3, 'ACTIVE', %s)
            ON CONFLICT (account_id) DO UPDATE SET available_balance = 1000, updated_at = EXCLUDED.updated_at
            """,
            (now,),
        )
    return candidate_id


def _artifact_counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {table: _count_table(conn, table) for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions")}


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}

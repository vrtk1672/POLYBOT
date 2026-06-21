from __future__ import annotations

from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeAction, RuntimeMode
from app.runtime.system_power import SystemPower
from app.services.paper_execution import PaperExecutionService
from app.services.paper_intents import PaperIntentGateService


class _Power:
    def get_power_state(self) -> dict[str, object]:
        return {"power": "ON", "runtime_work_allowed": True}


class _Governor:
    def get_current_state(self) -> RuntimeState:
        return RuntimeState(
            current_mode=RuntimeMode.PAPER,
            previous_mode=RuntimeMode.DATA_ONLY,
            state_status="ACTIVE",
            kill_switch_active=False,
            cooldown_active=False,
            attack_mode_active=False,
            reason="test",
            actor="test",
            system_power=SystemPower.ON,
            metadata_json={"paper_simulation": {"enabled": True}},
        )

    def can_execute(self, action, metadata=None) -> bool:
        value = action.value if isinstance(action, RuntimeAction) else str(action)
        return value == RuntimeAction.RUN_PAPER_SIMULATION.value


class _Actionability:
    def list_actionability(self, **kwargs):
        return {"items": []}


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_runtime_decision_runs",
            "paper_runtime_decisions",
            "paper_observation_policy_reviews",
            "paper_execution_runs",
            "paper_capital_ledger",
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
            "paper_intent_runs",
            "no_trade_runs",
            "paper_intents",
            "no_trade_log",
            "orderbook_snapshots",
            "same_market_side_guard_decisions",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _seed_policy_review(*, market_id: str = "runtime-market-1", side: str = "YES", risk_state: str = "RISK_OK") -> None:
    now = datetime.now(UTC)
    token_id = f"{market_id}-{side.lower()}-token"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid,
                best_ask, spread, mid_price, liquidity_score, source,
                snapshot_status, is_stale, snapshot_at, collected_at, created_at
            )
            VALUES (%s,%s,%s,%s,0.50,0.52,0.02,0.51,0.8,'test','OK',false,%s,%s,%s)
            """,
            (f"book-{market_id}-{side}", market_id, token_id, side, now - timedelta(seconds=5), now - timedelta(seconds=5), now),
        )
        conn.execute(
            """
            INSERT INTO paper_observation_policy_reviews (
                paper_observation_policy_review_id, source_type,
                proactive_candidate_seed_id, seed_mesh_inquiry_id, adapter_payload_id,
                opportunity_score_id, market_id, condition_id, side, token_id,
                observation_policy_state, decision_band, opportunity_score,
                edge_state, thesis_state, risk_state, capital_state, exit_state,
                lifecycle_state, orderbook_state, token_verification_state,
                candidate_event_scope_state, lineage_state,
                observation_allowed_by_policy, data_only,
                observation_policy_review_only, execution_allowed, paper_allowed,
                shadow_allowed, live_allowed, max_observation_notional,
                max_open_positions, time_stop_seconds, hard_blockers_json,
                soft_blockers_json, policy_blockers_json, required_to_pass_json,
                lineage_json, limits_json, metadata_json, policy_reason
            )
            VALUES (
                %s,'PROACTIVE_SEED_MESH',%s,%s,%s,%s,%s,%s,%s,%s,
                'OBSERVATION_POLICY_ELIGIBLE','PAPER_OBSERVATION',62,
                'EDGE_SUPPORTED','THESIS_SUPPORTED',%s,'CAPITAL_WATCH','EXIT_READY',
                'DATA_ONLY_RESEARCH','FRESH','TOKENS_VERIFIED',
                'CANDIDATE_SCOPED','COMPLETE',
                true,true,true,false,false,false,false,5,
                1,3600,%s,%s,'[]'::jsonb,'[]'::jsonb,
                %s,'{}'::jsonb,'{}'::jsonb,'test policy review'
            )
            """,
            (
                f"review-{market_id}-{side}",
                f"seed-{market_id}-{side}",
                f"inq-{market_id}-{side}",
                f"payload-{market_id}-{side}",
                f"score-{market_id}-{side}",
                market_id,
                f"condition-{market_id}",
                side,
                token_id,
                risk_state,
                Jsonb(["risk_blocked"] if risk_state == "RISK_BLOCKED" else []),
                Jsonb(["capital_watch_not_full_paper_ready"]),
                Jsonb({"source_event_id": f"event-{market_id}", "proactive_candidate_seed_id": f"seed-{market_id}-{side}"}),
            ),
        )


def test_unified_decision_creates_intent_and_paper_adapter_ledger(postgres_test_schema) -> None:
    _prepare()
    _seed_policy_review()

    intent_result = PaperIntentGateService(
        system_power=_Power(),
        governor=_Governor(),
        paper_actionability=_Actionability(),
    ).build_intents(limit=20, write_intents=True, write_no_trade=True)

    assert intent_result["paper_intents_created"] == 1
    assert intent_result["eligible_candidates"] >= 1

    execution_result = PaperExecutionService(system_power=_Power(), governor=_Governor()).run_execution(correlation_id="runtime-chain")

    assert execution_result["status"] == "OK"
    assert execution_result["orders_created"] == 1
    assert execution_result["fills_created"] == 1
    assert execution_result["positions_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        intent = conn.execute("SELECT * FROM paper_intents").fetchone()
        fill_count = conn.execute("SELECT COUNT(*) AS count FROM paper_fills").fetchone()["count"]
        live_count = _count(conn, "live_orders")
        shadow_count = _count(conn, "shadow_orders")
    assert intent["evidence"]["paper_runtime_decision_id"]
    assert intent["live"] is False
    assert intent["execution_allowed"] is False
    assert fill_count == 1
    assert live_count == 0
    assert shadow_count == 0


def test_true_hard_blocker_is_rejected_with_exact_reason(postgres_test_schema) -> None:
    _prepare()
    _seed_policy_review(market_id="runtime-market-blocked", risk_state="RISK_BLOCKED")

    result = PaperIntentGateService(
        system_power=_Power(),
        governor=_Governor(),
        paper_actionability=_Actionability(),
    ).build_intents(limit=20, write_intents=True, write_no_trade=True)

    assert result["paper_intents_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        blockers = conn.execute("SELECT blockers FROM no_trade_log ORDER BY id DESC LIMIT 1").fetchone()["blockers"]
    assert "RISK_HARD_BLOCKED" in blockers
    assert _count_table("paper_orders") == 0


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])


def _count(conn, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _count_table(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        return _count(conn, table)

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeAction, RuntimeMode, RuntimePermissions
from app.runtime.system_power import SystemPower
from app.services.source_refresh_orchestrator import SourceRefreshOrchestrator


def test_fresh_orderbook_snapshot_produces_orderbook_and_technical_signals(postgres_test_schema) -> None:
    run_migrations()
    _clean_signal_tables()
    now = datetime.now(UTC)
    _insert_snapshot("market-derived", "token-derived", "YES", 0.44, 0.46, now - timedelta(seconds=30))
    _insert_snapshot("market-derived", "token-derived", "YES", 0.45, 0.47, now)

    result = SourceRefreshOrchestrator(governor=_Governor()).run_cycle(candidate_limit=5, news_limit=1, whale_limit=1)

    assert result["derived_signals_created"] >= 2
    assert _count("orderbook_signals") >= 1
    assert _count("market_technical_signals") >= 1
    assert _count("liquidity_signals") >= 1
    assert _count("time_signals") >= 1
    assert _count("fee_reward_signals") >= 1


def test_market_memory_does_not_invent_history_without_technical_inputs(postgres_test_schema) -> None:
    run_migrations()
    _clean_signal_tables()

    result = SourceRefreshOrchestrator(governor=_Governor()).run_cycle(candidate_limit=5, news_limit=1, whale_limit=1)

    memory = next(item for item in result["contracts"] if item["source_name"] == "market_memory_v2")
    assert memory["refresh_state"] in {"REFRESHING_NO_NEW_DATA", "NO_REFRESH_PRODUCER"}
    assert _count("market_memory_v2") == 0


class _Governor:
    def __init__(self) -> None:
        self.state = RuntimeState(
            current_mode=RuntimeMode.DATA_ONLY,
            previous_mode=None,
            state_status="ACTIVE",
            kill_switch_active=False,
            cooldown_active=False,
            attack_mode_active=False,
            reason="test",
            actor="test",
            system_power=SystemPower.ON,
        )

    def get_current_state(self) -> RuntimeState:
        return self.state

    def can_execute(self, action: RuntimeAction | str, metadata=None) -> bool:
        value = action.value if isinstance(action, RuntimeAction) else str(action)
        return value in {RuntimeAction.COLLECT_DATA.value, RuntimeAction.RUN_INTELLIGENCE.value}

    def assert_can_execute(self, action: RuntimeAction | str, metadata=None) -> None:
        if not self.can_execute(action, metadata=metadata):
            raise RuntimeError("blocked")

    def get_permissions(self) -> RuntimePermissions:
        return RuntimePermissions(can_collect_data=True, can_run_intelligence=True)


def _clean_signal_tables() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in ("source_refresh_status", "source_refresh_cycles", "market_technical_signals", "orderbook_signals", "liquidity_signals", "time_signals", "fee_reward_signals", "market_memory_v2", "orderbook_snapshots"):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _insert_snapshot(market_id: str, token_id: str, side: str, bid: float, ask: float, ts: datetime) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask, spread, mid_price,
                depth_1c, depth_2c, depth_5c, bid_depth_json, ask_depth_json,
                snapshot_at, raw_orderbook_json, snapshot_status, is_stale, collected_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, (%s + %s) / 2,
                150, 400, 750,
                '[{\"price\":0.44,\"size\":250},{\"price\":0.43,\"size\":200}]'::jsonb,
                '[{\"price\":0.46,\"size\":200},{\"price\":0.47,\"size\":200}]'::jsonb,
                %s, '{}'::jsonb, 'OK', false, %s
            )
            """,
            (f"snapshot-{market_id}-{ts.timestamp()}", market_id, token_id, side, bid, ask, ask - bid, bid, ask, ts, ts),
        )


def _count(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        if not _table_exists(conn, table):
            return 0
        return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])

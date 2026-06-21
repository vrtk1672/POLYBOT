from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.control_center.runtime_supervisor import RuntimeSupervisorService, RuntimeSupervisorStartRequest, RuntimeSupervisorStore
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeAction, RuntimeMode, RuntimePermissions
from app.runtime.system_power import SystemPower
from app.services.source_refresh_orchestrator import SourceRefreshOrchestrator, registry


def test_source_refresh_orchestrator_has_decision_critical_registry_entries() -> None:
    names = {item.source_name for item in registry()}

    assert {"clob_orderbook", "orderbook_signals", "market_movement", "market_technical_signals", "payout", "news", "whale", "market_memory_v2"}.issubset(names)
    assert all(item.safe_to_refresh_data_only for item in registry())


def test_source_refresh_orchestrator_records_contracts_and_no_artifacts(postgres_test_schema) -> None:
    run_migrations()
    _clean_tables()
    _insert_orderbook_snapshot("market-source-refresh", "token-yes", "YES", datetime.now(UTC))
    before = _artifact_counts()

    result = SourceRefreshOrchestrator(governor=_Governor()).run_cycle(candidate_limit=5, news_limit=1, whale_limit=1)

    assert result["orchestrator_state"] == "ACTIVE"
    assert result["sources_checked"] >= 8
    assert result["derived_signals_created"] >= 2
    states = {item["source_name"]: item["refresh_state"] for item in result["contracts"]}
    assert states["orderbook_signals"] in {"FRESH", "REFRESHING_BUT_NOT_DIRECTIONAL"}
    assert states["market_technical_signals"] in {"FRESH", "REFRESHING_BUT_NOT_DIRECTIONAL"}
    assert states["payout"] in {"FRESH", "REFRESHING_NO_NEW_DATA", "STALE_BY_TTL"}
    assert _count("source_refresh_status") >= len(registry())
    assert _artifact_counts() == before


def test_supervisor_calls_source_refresh_orchestrator_during_system_on_cycle() -> None:
    fake = _FakeSourceRefreshOrchestrator()
    store = RuntimeSupervisorStore()
    supervisor = RuntimeSupervisorService(
        governor=_Governor(),
        query_service=_QueryService(),
        store=store,
        paper_simulation=_PaperControl(),
        source_refresh_orchestrator=fake,
        run_in_background=False,
        sleep_between_cycles=False,
    )

    result = supervisor.start(RuntimeSupervisorStartRequest(actor="pytest", reason="source refresh", interval_seconds=30))

    assert fake.calls == 1
    assert result.source_refresh_orchestrator_state == "ACTIVE"
    assert result.source_refresh_cycles_completed == 1
    assert result.sources_refreshed_this_cycle == 3
    assert result.derived_signals_created_this_cycle == 2


class _FakeSourceRefreshOrchestrator:
    def __init__(self) -> None:
        self.calls = 0

    def run_cycle(self, *, candidate_limit: int) -> dict[str, Any]:
        self.calls += 1
        return {
            "status": "OK",
            "orchestrator_state": "ACTIVE",
            "sources_checked": 4,
            "sources_refreshed": 3,
            "sources_failed": 0,
            "sources_no_new_data": 1,
            "derived_signals_created": 2,
            "trading_mutation": False,
        }


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


class _PaperControl:
    def status_record(self, include_paper_truth: bool = False):
        class _Record:
            enabled = False
            status = "DISABLED"
            warnings: list[str] = []
            errors: list[str] = []

        return _Record()


class _QueryService:
    def overview(self):
        return _envelope("runtime_state", {"source_counts": {"event_log": 1}})

    def live_flow(self):
        return _envelope("event_log", {"events": [{"id": "event"}], "count": 1})

    def organs(self):
        return _envelope("service_health", {"services": [], "count": 0})

    def closest_actionable(self):
        return _envelope("risk_evidence", {"candidates": [], "count": 0})

    def risk_evidence(self):
        return _envelope("risk_evidence", {})

    def positions(self):
        return _envelope("paper_positions", {"positions": []})

    def lifecycle_governance(self):
        return _envelope("lifecycle_governance", {})

    def pnl_ledger(self):
        return _envelope("paper_daily_pnl", {})

    def no_trade(self):
        return _envelope("no_trade_log", {"records": []})

    def ai(self):
        return _envelope("ai_context_router", {})

    def logs(self):
        return _envelope("event_log", {"events": []})

    def truth_state(self):
        return _envelope("truth_state_registry", {})


def _envelope(source: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"status": "REAL", "source": source, "last_updated": datetime.now(UTC).isoformat(), "truth_state": "ACTIVE_FRESH", "data": data, "warnings": [], "errors": []}


def _clean_tables() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "source_refresh_status",
            "source_refresh_cycles",
            "market_technical_signals",
            "orderbook_signals",
            "liquidity_signals",
            "time_signals",
            "fee_reward_signals",
            "market_memory_v2",
            "orderbook_snapshots",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "paper_position_closes",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _insert_orderbook_snapshot(market_id: str, token_id: str, side: str, ts: datetime) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask, spread, mid_price,
                depth_1c, depth_2c, depth_5c, bid_depth_json, ask_depth_json,
                snapshot_at, raw_orderbook_json, snapshot_status, is_stale, collected_at
            )
            VALUES (
                'snapshot-source-refresh-1', %s, %s, %s, 0.51, 0.53, 0.02, 0.52,
                120, 300, 600,
                '[{\"price\":0.51,\"size\":200},{\"price\":0.50,\"size\":150}]'::jsonb,
                '[{\"price\":0.53,\"size\":150},{\"price\":0.54,\"size\":150}]'::jsonb,
                %s, '{}'::jsonb, 'OK', false, %s
            )
            """,
            (market_id, token_id, side, ts, ts),
        )


def _artifact_counts() -> dict[str, int]:
    return {table: _count(table) for table in ("paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "live_orders", "positions")}


def _count(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        if not _table_exists(conn, table):
            return 0
        return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.full_monitor_run import FullMonitorRunRecord
from app.control_center.full_monitor_run_service import FullMonitorRunStore
from app.control_center.runtime_readiness import RuntimeReadinessService
from app.control_center.runtime_supervisor import RuntimeSupervisorStore
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_power_off_is_stopped_or_blocked_with_explicit_blocker(postgres_test_schema) -> None:
    _prepare_runtime_tables(system_power="OFF")
    _insert_service_health("scheduler", "runtime", "BLOCKED_BY_MODE")

    payload = _service().get_readiness()

    assert payload["system_power_state"] == "OFF"
    assert payload["runtime_life_state"] in {"STOPPED", "BLOCKED"}
    assert payload["readiness_state"] != "READY"
    assert "SYSTEM_POWER_OFF" in payload["blockers"]


def test_scheduler_blocked_by_mode_is_explicit(postgres_test_schema) -> None:
    _prepare_runtime_tables(system_power="ON")
    _insert_service_health("scheduler", "runtime", "BLOCKED_BY_MODE")

    payload = _service().get_readiness()

    assert payload["scheduler_state"] == "RUNNING_BLOCKED"
    assert payload["scheduler_blocked_reason"] == "SCHEDULER_BLOCKED_BY_MODE"
    assert payload["runtime_life_state"] == "BLOCKED"


def test_registered_supervisor_without_process_heartbeat_is_not_running(postgres_test_schema) -> None:
    _prepare_runtime_tables(system_power="ON")
    _insert_service_health("scheduler", "runtime", "RUNNING", heartbeat=True)
    _insert_successful_cycle("fresh-success", datetime.now(UTC))

    payload = _service(runtime_supervisor_store=RuntimeSupervisorStore()).get_readiness()

    assert payload["supervisor_state"] == "REGISTERED_NOT_RUNNING"
    assert payload["runtime_supervisor_truth_scope"] == "PROCESS_LOCAL"
    assert payload["runtime_life_state"] == "ALIVE"


def test_stale_running_cycle_is_not_active_fresh(postgres_test_schema) -> None:
    _prepare_runtime_tables(system_power="ON")
    _insert_service_health("scheduler", "runtime", "RUNNING", heartbeat=True)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (cycle_id, mode, status, started_at, metadata_json)
            VALUES ('stale-active', 'DATA_ONLY', 'RUNNING', %s, '{}'::jsonb)
            """,
            (datetime.now(UTC) - timedelta(hours=2),),
        )

    payload = _service().get_readiness()

    assert payload["active_cycle_state"] == "RUNNING_STALE"
    assert payload["active_cycle"]["truth_state"] != "ACTIVE_FRESH"
    assert payload["runtime_life_state"] in {"STALE", "BLOCKED"}
    assert "ACTIVE_CYCLE_STALE" in payload["blockers"]


def test_fresh_last_successful_cycle_is_fresh(postgres_test_schema) -> None:
    _prepare_runtime_tables(system_power="ON")
    _insert_service_health("scheduler", "runtime", "RUNNING", heartbeat=True)
    _insert_successful_cycle("fresh-success", datetime.now(UTC))

    payload = _service().get_readiness()

    assert payload["last_successful_cycle_state"] == "FRESH"
    assert payload["last_successful_cycle"]["truth_state"] == "ACTIVE_FRESH"


def test_missing_last_successful_cycle_is_called_out(postgres_test_schema) -> None:
    _prepare_runtime_tables(system_power="ON")
    _insert_service_health("scheduler", "runtime", "RUNNING", heartbeat=True)

    payload = _service().get_readiness()

    assert payload["last_successful_cycle_state"] == "MISSING"
    assert any("No successful runtime cycle is recorded." in warning for warning in payload["warnings"])
    assert payload["runtime_life_state"] != "ALIVE"


def test_full_monitor_run_is_diagnostic_and_never_makes_runtime_alive(postgres_test_schema) -> None:
    _prepare_runtime_tables(system_power="ON")
    full_monitor_store = FullMonitorRunStore()
    full_monitor_store.set_current(
        FullMonitorRunRecord(
            run_id="diagnostic-run",
            status="RUNNING",
            started_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
            requested_duration_minutes=1,
            duration_minutes=1,
            audit_id="test-audit",
            actor="pytest",
            reason="diagnostic scope test",
        )
    )

    payload = _service(full_monitor_run_store=full_monitor_store).get_readiness()

    assert payload["full_monitor_run_state"] == "DIAGNOSTIC_RUNNING"
    assert payload["full_monitor_run_label"] == "DIAGNOSTIC_ONLY"
    assert payload["runtime_life_state"] != "ALIVE"
    assert "FULL_MONITOR_RUN_DIAGNOSTIC_ONLY" in payload["warnings"]


def test_runtime_readiness_endpoint_shape_and_get_is_read_only(postgres_test_schema) -> None:
    _prepare_runtime_tables(system_power="OFF")
    before = _table_count("paper_orders")
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())

    response = TestClient(app).get("/dashboard/api/v2/control/runtime-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]
    assert payload["data"]["runtime_life_state"] == payload["runtime_life_state"]
    assert payload["full_monitor_run_label"] == "DIAGNOSTIC_ONLY"
    assert _table_count("paper_orders") == before


def _service(
    *,
    runtime_supervisor_store: RuntimeSupervisorStore | None = None,
    full_monitor_run_store: FullMonitorRunStore | None = None,
) -> RuntimeReadinessService:
    return RuntimeReadinessService(
        connection_factory=DatabaseConnectionFactory(),
        runtime_supervisor_store=runtime_supervisor_store or RuntimeSupervisorStore(),
        full_monitor_run_store=full_monitor_run_store or FullMonitorRunStore(),
    )


def _prepare_runtime_tables(*, system_power: str) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "system_state",
            "system_state_history",
            "system_power_transitions",
            "service_health",
            "runtime_cycles_v2",
            "paper_orders",
            "paper_fills",
            "paper_positions",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO system_state (
                current_mode, state_status, kill_switch_active, cooldown_active,
                attack_mode_active, reason, actor, system_power, metadata_json
            )
            VALUES ('DATA_ONLY', 'ACTIVE', false, false, false, 'runtime readiness test', 'pytest', %s, '{}'::jsonb)
            """,
            (system_power,),
        )


def _insert_service_health(service_name: str, service_type: str, status: str, *, heartbeat: bool = False) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO service_health (service_name, service_type, status, last_heartbeat_at, details_json)
            VALUES (%s, %s, %s, %s, '{}'::jsonb)
            ON CONFLICT (service_name) DO UPDATE
            SET service_type = EXCLUDED.service_type,
                status = EXCLUDED.status,
                last_heartbeat_at = EXCLUDED.last_heartbeat_at,
                updated_at = now()
            """,
            (service_name, service_type, status, datetime.now(UTC) if heartbeat else None),
        )


def _insert_successful_cycle(cycle_id: str, finished_at: datetime) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (cycle_id, mode, status, started_at, finished_at, metadata_json)
            VALUES (%s, 'DATA_ONLY', 'COMPLETED', %s, %s, '{}'::jsonb)
            """,
            (cycle_id, finished_at - timedelta(seconds=10), finished_at),
        )


def _table_count(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        if not _table_exists(conn, table):
            return 0
        return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok", "source": "dummy-market-service"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}

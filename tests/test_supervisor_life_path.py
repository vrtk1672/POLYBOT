from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.full_monitor_run import FullMonitorRunRecord
from app.control_center.full_monitor_run_service import FullMonitorRunStore
from app.control_center.runtime_supervisor import RuntimeSupervisorRecord, RuntimeSupervisorStore
from app.control_center.supervisor_life_path import SupervisorLifePathService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_power_off_life_path_is_stopped_with_explicit_blocker(postgres_test_schema) -> None:
    _prepare_tables(system_power="OFF")

    payload = _service().get_life_path()

    assert payload["supervisor_life_state"] == "STOPPED"
    assert payload["system_power_state"] == "OFF"
    assert "SYSTEM_POWER_OFF" in payload["blockers"]
    assert payload["full_monitor_run_label"] == "DIAGNOSTIC_ONLY"
    assert payload["readiness_state"] == "BLOCKED"


def test_running_supervisor_exposes_fresh_heartbeat_and_cycles(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    _prepare_tables(system_power="ON", transition_at=now - timedelta(minutes=2))
    _insert_event("event-supervisor-life", now - timedelta(seconds=40))
    _insert_candidate("candidate-supervisor-life", now - timedelta(seconds=30))
    supervisor_store = RuntimeSupervisorStore()
    supervisor_store.set(
        RuntimeSupervisorRecord(
            supervisor_status="RUNNING",
            system_power="ON",
            mode="DATA_ONLY",
            session_id="session-life",
            started_at=(now - timedelta(minutes=1)).isoformat(),
            updated_at=now.isoformat(),
            last_cycle_at=now.isoformat(),
            cycles_completed=2,
            current_cycle_status="COMPLETED",
            paper_simulation_enabled=False,
            paper_simulation_status="DISABLED",
            paper_orders_created=0,
            paper_fills_created=0,
            paper_positions_opened=0,
        )
    )

    payload = _service(runtime_supervisor_store=supervisor_store).get_life_path()

    assert payload["supervisor_life_state"] == "ALIVE"
    assert payload["supervisor_state"] == "ALIVE"
    assert payload["cycle_state"] == "CYCLE_COMPLETED"
    assert payload["cycles_completed_since_system_on"] == 2
    assert payload["events_updated"] is True
    assert payload["candidates_updated"] is True
    assert payload["paper_readiness"]["paper_simulation_state"] == "OFF"
    assert payload["counts"]["paper_orders"] == 0
    assert payload["counts"]["paper_fills"] == 0
    assert payload["counts"]["paper_positions"] == 0


def test_full_monitor_run_is_diagnostic_and_does_not_make_life_alive(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    _prepare_tables(system_power="ON", transition_at=now - timedelta(minutes=1))
    full_monitor_store = FullMonitorRunStore()
    full_monitor_store.set_current(
        FullMonitorRunRecord(
            run_id="diagnostic-only",
            status="RUNNING",
            started_at=now.isoformat(),
            updated_at=now.isoformat(),
            requested_duration_minutes=1,
            duration_minutes=1,
            audit_id="audit-diagnostic",
            actor="pytest",
            reason="diagnostic only",
        )
    )

    payload = _service(full_monitor_run_store=full_monitor_store).get_life_path()

    assert payload["full_monitor_run_label"] == "DIAGNOSTIC_ONLY"
    assert payload["full_monitor_run_state"] == "DIAGNOSTIC_RUNNING"
    assert payload["supervisor_life_state"] != "ALIVE"
    assert "SUPERVISOR_REGISTERED_NOT_RUNNING" in payload["blockers"]
    assert any("diagnostic-only" in warning for warning in payload["warnings"])


def test_stale_supervisor_heartbeat_becomes_stale(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    stale = now - timedelta(minutes=10)
    _prepare_tables(system_power="ON", transition_at=now - timedelta(minutes=20))
    supervisor_store = RuntimeSupervisorStore()
    supervisor_store.set(
        RuntimeSupervisorRecord(
            supervisor_status="RUNNING",
            system_power="ON",
            mode="DATA_ONLY",
            session_id="stale-session",
            started_at=stale.isoformat(),
            updated_at=stale.isoformat(),
            last_cycle_at=stale.isoformat(),
            cycles_completed=1,
            current_cycle_status="COMPLETED",
        )
    )

    payload = _service(runtime_supervisor_store=supervisor_store).get_life_path()

    assert payload["supervisor_life_state"] == "STALE"
    assert payload["supervisor_state"] == "STALE"
    assert "SUPERVISOR_STALE" in payload["blockers"]
    assert payload["freshness_state"] == "STALE"


def test_registered_without_running_supervisor_is_not_alive(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    _prepare_tables(system_power="ON", transition_at=now - timedelta(minutes=1))

    payload = _service(runtime_supervisor_store=RuntimeSupervisorStore()).get_life_path()

    assert payload["supervisor_state"] == "REGISTERED_NOT_RUNNING"
    assert payload["supervisor_life_state"] == "BLOCKED"
    assert "SUPERVISOR_REGISTERED_NOT_RUNNING" in payload["blockers"]


def test_supervisor_life_path_endpoint_shape_and_get_is_read_only(postgres_test_schema) -> None:
    _prepare_tables(system_power="OFF")
    before = _artifact_counts()
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())

    response = TestClient(app).get("/dashboard/api/v2/control/supervisor-life-path")

    assert response.status_code == 200
    payload = response.json()
    for field in (
        "supervisor_life_state",
        "system_power_state",
        "runtime_life_state",
        "supervisor_state",
        "cycle_state",
        "cycles_completed_since_system_on",
        "events_updated",
        "candidates_updated",
        "runtime_readiness_updated",
        "paper_readiness_updated",
        "full_monitor_run_label",
        "full_monitor_run_state",
        "blockers",
        "warnings",
        "errors",
        "source",
        "last_updated",
    ):
        assert field in payload
    assert payload["full_monitor_run_label"] == "DIAGNOSTIC_ONLY"
    assert _artifact_counts() == before


def _service(
    *,
    runtime_supervisor_store: RuntimeSupervisorStore | None = None,
    full_monitor_run_store: FullMonitorRunStore | None = None,
) -> SupervisorLifePathService:
    return SupervisorLifePathService(
        connection_factory=DatabaseConnectionFactory(),
        runtime_supervisor_store=runtime_supervisor_store or RuntimeSupervisorStore(),
        full_monitor_run_store=full_monitor_run_store or FullMonitorRunStore(),
        runtime_readiness=_FakeRuntimeReadiness(),
        paper_readiness=_FakePaperReadiness(),
    )


class _FakeRuntimeReadiness:
    def get_readiness(self) -> dict[str, Any]:
        return {
            "runtime_life_state": "ALIVE",
            "system_power_state": "ON",
            "scheduler_state": "RUNNING_FRESH",
            "supervisor_state": "ALIVE",
            "blockers": [],
            "generated_at": datetime.now(UTC).isoformat(),
        }


class _FakePaperReadiness:
    def get_readiness(self) -> dict[str, Any]:
        return {
            "paper_readiness_state": "BLOCKED",
            "paper_execution_readiness_state": "BLOCKED_BY_PAPER_SIMULATION",
            "paper_simulation_state": "OFF",
            "blockers": ["PAPER_SIMULATION_OFF"],
            "last_updated": datetime.now(UTC).isoformat(),
        }


def _prepare_tables(*, system_power: str, transition_at: datetime | None = None) -> None:
    run_migrations()
    transition_at = transition_at or datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "event_log",
            "paper_eligibility_candidates",
            "runtime_cycles_v2",
            "service_health",
            "system_state",
            "system_state_history",
            "system_power_transitions",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "paper_position_closes",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO system_state (
                current_mode, state_status, kill_switch_active, cooldown_active,
                attack_mode_active, reason, actor, system_power, system_power_transition_at, metadata_json
            )
            VALUES ('DATA_ONLY', 'ACTIVE', false, false, false, 'supervisor life test', 'pytest', %s, %s, '{}'::jsonb)
            """,
            (system_power, transition_at),
        )


def _insert_event(event_id: str, created_at: datetime) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO event_log (
                event_id, event_type, aggregate_type, aggregate_id, source_service,
                correlation_id, occurred_at, stored_at, payload_json, metadata_json
            )
            VALUES (%s, 'test.event', 'test', %s, 'pytest', %s, %s, %s, '{}'::jsonb, '{}'::jsonb)
            """,
            (event_id, event_id, event_id, created_at, created_at),
        )


def _insert_candidate(candidate_id: str, updated_at: datetime) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, market_id, side, status, eligibility_score,
                eligibility_blockers, missing_requirements, evidence, lineage_trusted,
                risk_approved, exit_ready, generated_by, producer_name, updated_at
            )
            VALUES (%s, 'market-life', 'YES', 'ELIGIBLE', 0.9, '[]'::jsonb, '[]'::jsonb,
                    '{}'::jsonb, true, true, true, 'pytest', 'pytest', %s)
            """,
            (candidate_id, updated_at),
        )


def _artifact_counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {
            table: _count_table(conn, table)
            for table in (
                "paper_orders",
                "paper_fills",
                "paper_positions",
                "paper_position_closes",
                "live_orders",
                "orders_v2",
                "fills_v2",
                "positions",
            )
        }


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok", "source": "dummy-market-service"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}

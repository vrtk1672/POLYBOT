from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.system_power_routes import create_system_power_router
from app.control_center.runtime_supervisor import (
    DEFAULT_RUNTIME_SUPERVISOR_STORE,
    RuntimeSupervisorRecord,
)
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import app


def test_system_power_api_get_and_transitions(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    current = client.get("/system/power")
    assert current.status_code == 200
    assert current.json()["power"] == "ON"

    off = client.post("/system/power/off", json={"actor": "operator", "reason": "manual_system_off", "correlation_id": "api-off"})
    assert off.status_code == 200
    assert off.json()["power"] == "OFF"
    assert off.json()["runtime_work_allowed"] is False

    on = client.post("/system/power/on", json={"actor": "operator", "reason": "manual_system_on", "correlation_id": "api-on"})
    assert on.status_code == 200
    assert on.json()["power"] == "ON"
    assert on.json()["runtime_work_allowed"] is True
    assert on.json()["supervisor"]["supervisor_status"] in {"STARTING", "RUNNING", "DEGRADED"}

    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM system_power_transitions").fetchone()["count"]
    assert count == 2


def test_system_power_on_starts_retained_runtime_supervisor(monkeypatch, postgres_test_schema) -> None:
    run_migrations()
    DEFAULT_RUNTIME_SUPERVISOR_STORE.set(RuntimeSupervisorRecord(supervisor_status="STOPPED"))

    class _Supervisor:
        def start(self, payload):
            record = RuntimeSupervisorRecord(
                supervisor_status="RUNNING",
                system_power="ON",
                mode="DATA_ONLY",
                session_id="system-power-retained-supervisor",
                updated_at="2026-06-15T00:00:00+00:00",
                last_cycle_at="2026-06-15T00:00:00+00:00",
                cycles_completed=1,
                current_cycle_status="COMPLETED",
                actor=payload.actor,
                reason=payload.reason,
            )
            DEFAULT_RUNTIME_SUPERVISOR_STORE.set(record)
            return record

        def stop(self, payload):
            record = RuntimeSupervisorRecord(
                supervisor_status="STOPPED",
                system_power="OFF",
                mode="DATA_ONLY",
                session_id="system-power-retained-supervisor",
                updated_at="2026-06-15T00:01:00+00:00",
                stopped_at="2026-06-15T00:01:00+00:00",
                cycles_completed=1,
                current_cycle_status="STOPPED",
                actor=payload.actor,
                reason=payload.reason,
            )
            DEFAULT_RUNTIME_SUPERVISOR_STORE.set(record)
            return record

    monkeypatch.setattr("app.api.system_power_routes.build_runtime_supervisor", lambda *, governor=None: _Supervisor())
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(create_system_power_router())
    client = TestClient(test_app)

    on = client.post("/system/power/on", json={"actor": "operator", "reason": "manual_system_on"})

    assert on.status_code == 200
    assert on.json()["power"] == "ON"
    assert on.json()["supervisor"]["supervisor_status"] == "RUNNING"
    retained = DEFAULT_RUNTIME_SUPERVISOR_STORE.get()
    assert retained is not None
    assert retained.supervisor_status == "RUNNING"
    assert retained.session_id == "system-power-retained-supervisor"

    off = client.post("/system/power/off", json={"actor": "operator", "reason": "manual_system_off"})

    assert off.status_code == 200
    assert off.json()["power"] == "OFF"
    assert off.json()["supervisor"]["supervisor_status"] == "STOPPED"
    retained = DEFAULT_RUNTIME_SUPERVISOR_STORE.get()
    assert retained is not None
    assert retained.supervisor_status == "STOPPED"


def test_system_power_route_surfaces_supervisor_start_without_db(monkeypatch) -> None:
    DEFAULT_RUNTIME_SUPERVISOR_STORE.set(RuntimeSupervisorRecord(supervisor_status="STOPPED"))

    def _fake_system_action(action, payload):
        assert action == "system-on"
        record = RuntimeSupervisorRecord(
            supervisor_status="RUNNING",
            system_power="ON",
            mode="DATA_ONLY",
            session_id="route-supervisor",
            cycles_completed=1,
            current_cycle_status="COMPLETED",
        )
        DEFAULT_RUNTIME_SUPERVISOR_STORE.set(record)
        return {
            "status": "ACCEPTED",
            "action": action,
            "audit_id": "audit-route",
            "warnings": [],
            "errors": [],
            "result": {
                "power": "ON",
                "system_power": "ON",
                "runtime_work_allowed": True,
                "supervisor": record.to_action_result(),
                "paper_simulation": {"enabled": False, "status": "DISABLED"},
                "execution_enabled": False,
                "paper_execution_enabled": False,
            },
        }

    monkeypatch.setattr("app.api.system_power_routes._system_action", _fake_system_action)
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(create_system_power_router())
    response = TestClient(test_app).post("/system/power/on", json={"actor": "operator", "reason": "manual_system_on"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["power"] == "ON"
    assert payload["supervisor"]["supervisor_status"] == "RUNNING"
    assert payload["system_power_action"]["status"] == "ACCEPTED"
    retained = DEFAULT_RUNTIME_SUPERVISOR_STORE.get()
    assert retained is not None
    assert retained.session_id == "route-supervisor"


def test_system_power_api_requires_actor_and_reason(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    missing_reason = client.post("/system/power/off", json={"actor": "operator"})
    missing_actor = client.post("/system/power/on", json={"reason": "manual_system_on"})

    assert missing_reason.status_code == 400
    assert missing_actor.status_code == 400

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.runtime_routes import create_runtime_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.runtime.health_truth import HealthTruthService
from app.runtime.state_governor import StateGovernor


def _client(postgres_test_schema) -> TestClient:
    run_migrations()
    factory = DatabaseConnectionFactory()
    governor = StateGovernor(connection_factory=factory)
    governor.ensure_initial_state()
    app = FastAPI()
    app.include_router(
        create_runtime_router(
            governor=governor,
            health_service=HealthTruthService(connection_factory=factory),
        )
    )
    return TestClient(app)


def test_get_runtime_state_returns_current_mode(postgres_test_schema) -> None:
    response = _client(postgres_test_schema).get("/runtime/state")
    assert response.status_code == 200
    assert response.json()["state"]["current_mode"] == "DATA_ONLY"


def test_get_runtime_health_returns_health(postgres_test_schema) -> None:
    response = _client(postgres_test_schema).get("/runtime/health")
    assert response.status_code == 200
    assert response.json()["current_mode"] == "DATA_ONLY"


def test_mode_request_requires_reason(postgres_test_schema) -> None:
    response = _client(postgres_test_schema).post(
        "/runtime/mode/request",
        json={"to_mode": "PAPER", "actor": "operator"},
    )
    assert response.status_code == 422


def test_mode_request_blocks_invalid_transition(postgres_test_schema) -> None:
    response = _client(postgres_test_schema).post(
        "/runtime/mode/request",
        json={"to_mode": "SMALL_LIVE", "actor": "operator", "reason": "too soon"},
    )
    assert response.status_code == 409
    assert "blocked_reason" in response.json()["detail"]


def test_kill_sets_kill(postgres_test_schema) -> None:
    response = _client(postgres_test_schema).post(
        "/runtime/kill",
        json={"actor": "operator", "reason": "manual emergency"},
    )
    assert response.status_code == 200
    assert response.json()["state"]["current_mode"] == "KILL"


def test_resume_resumes_to_data_only(postgres_test_schema) -> None:
    client = _client(postgres_test_schema)
    client.post("/runtime/kill", json={"actor": "operator", "reason": "manual emergency"})
    response = client.post(
        "/runtime/resume",
        json={"actor": "operator", "reason": "investigated", "target_mode": "DATA_ONLY"},
    )
    assert response.status_code == 200
    assert response.json()["state"]["current_mode"] == "DATA_ONLY"

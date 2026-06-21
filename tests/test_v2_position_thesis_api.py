from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.position_thesis_routes import create_position_thesis_router
from app.db.connection import DatabaseConnectionFactory


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM impact_links")
        conn.execute("DELETE FROM position_thesis_validation_events")
        conn.execute("DELETE FROM position_thesis_profiles")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM entity_market_links")
        conn.execute("DELETE FROM event_entities")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_position_thesis_router())
    return TestClient(app)


def _payload(position_id: str = "position-api") -> dict[str, object]:
    return {
        "position_id": position_id,
        "market_id": "market-api",
        "side": "YES",
        "entry_thesis": "API thesis explains why this future position would exist.",
        "profit_drivers": ["clear catalyst"],
        "invalidation_drivers": ["catalyst fails"],
        "watch_entities": ["issuer"],
        "danger_signals": ["resolution_ambiguous"],
        "take_profit_rules": ["review profit if market reprices"],
        "partial_exit_rules": ["review partial de-risk if confidence falls"],
        "emergency_exit_rules": ["review immediately if invalidation triggers"],
        "status": "ACTIVE",
        "reviewed_by": "operator",
        "reviewed_at": datetime.now(UTC).isoformat(),
    }


def test_thesis_api_empty_db_returns_truth(postgres_test_schema) -> None:
    _clear()
    with _client() as client:
        profiles = client.get("/thesis/profiles")
        summary = client.get("/thesis/summary")

    assert profiles.status_code == 200
    assert profiles.json()["mock_data"] is False
    assert profiles.json()["profiles"] == []
    assert summary.json()["mock_data"] is False
    assert summary.json()["total_thesis_profiles"] == 0


def test_thesis_api_create_get_and_validate(postgres_test_schema) -> None:
    _clear()
    with _client() as client:
        created = client.post("/thesis/profiles", json=_payload()).json()["profile"]
        by_id = client.get(f"/thesis/profiles/{created['thesis_id']}").json()
        by_position = client.get("/thesis/positions/position-api").json()
        validation = client.get("/thesis/positions/position-api/validation").json()

    assert created["paper_ready"] is True
    assert by_id["profile"]["thesis_id"] == created["thesis_id"]
    assert by_position["profile"]["position_id"] == "position-api"
    assert validation["mock_data"] is False
    assert validation["paper_ready"] is True


def test_thesis_api_status_mutations(postgres_test_schema) -> None:
    _clear()
    with _client() as client:
        created = client.post("/thesis/profiles", json=_payload("position-status-api")).json()["profile"]
        reviewed = client.post(f"/thesis/profiles/{created['thesis_id']}/needs-review").json()["profile"]
        invalidated = client.post(f"/thesis/profiles/{created['thesis_id']}/invalidate").json()["profile"]

    assert reviewed["status"] == "NEEDS_REVIEW"
    assert reviewed["paper_ready"] is False
    assert invalidated["status"] == "INVALIDATED"
    assert invalidated["live_ready"] is False


def test_thesis_api_rejects_executable_language(postgres_test_schema) -> None:
    _clear()
    payload = _payload("position-reject")
    payload["emergency_exit_rules"] = ["EXECUTE immediately"]

    with _client() as client:
        response = client.post("/thesis/profiles", json=payload)

    assert response.status_code == 422

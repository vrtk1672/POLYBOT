from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.event_routes import create_event_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.events.event_bus import EventBus
from app.events.types import EventType


def _client(postgres_test_schema) -> tuple[TestClient, EventBus]:
    run_migrations()
    factory = DatabaseConnectionFactory()
    bus = EventBus(connection_factory=factory)
    app = FastAPI()
    app.include_router(create_event_router(connection_factory=factory, event_bus=bus))
    return TestClient(app), bus


def test_get_recent_returns_events(postgres_test_schema) -> None:
    client, bus = _client(postgres_test_schema)
    bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"ok": True}, source_service="test")
    response = client.get("/events/recent")
    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_get_dlq_returns_dlq(postgres_test_schema) -> None:
    client, bus = _client(postgres_test_schema)
    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "bad", lambda event: (_ for _ in ()).throw(RuntimeError("fail")))
    envelope = bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"ok": True}, source_service="test")
    bus.dispatch_event(envelope)
    bus.dispatch_event(envelope)
    response = client.get("/events/dlq")
    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_replay_requires_reason(postgres_test_schema) -> None:
    client, _bus = _client(postgres_test_schema)
    response = client.post("/events/replay", json={"requested_by": "operator", "event_id": "x"})
    assert response.status_code == 422


def test_replay_rejects_empty_filter_and_event_id(postgres_test_schema) -> None:
    client, _bus = _client(postgres_test_schema)
    response = client.post("/events/replay", json={"requested_by": "operator", "reason": "none"})
    assert response.status_code == 400


def test_lag_returns_metrics(postgres_test_schema) -> None:
    client, _bus = _client(postgres_test_schema)
    response = client.get("/events/lag")
    assert response.status_code == 200
    assert "events_per_minute" in response.json()


def test_payloads_are_redacted(postgres_test_schema) -> None:
    client, bus = _client(postgres_test_schema)
    bus.publish(
        EventType.RUNTIME_CYCLE_STARTED.value,
        {"api_secret": "do-not-show", "safe": "ok"},
        source_service="test",
    )
    response = client.get("/events/recent")
    payload = response.json()["events"][0]["payload_json"]
    assert payload["api_secret"] == "<redacted>"
    assert payload["safe"] == "ok"

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.news_routes import create_news_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _client(postgres_test_schema) -> TestClient:
    run_migrations()
    app = FastAPI()
    app.include_router(create_news_router(connection_factory=DatabaseConnectionFactory()))
    return TestClient(app)


def test_news_read_endpoints_work_without_fake_data(postgres_test_schema) -> None:
    client = _client(postgres_test_schema)
    assert client.get("/news/recent").json()["count"] == 0
    assert client.get("/news/sources").json()["count"] == 0
    assert client.get("/news/market/missing").json()["count"] == 0
    assert client.get("/news/impact/top").json()["count"] == 0


def test_manual_requires_title_and_reason_then_processes_item(postgres_test_schema) -> None:
    client = _client(postgres_test_schema)
    assert client.post("/news/manual", json={"title": "x"}).status_code == 422
    response = client.post(
        "/news/manual",
        json={"source_id": "manual", "title": "BTC test headline for market linking only", "summary": "safe", "category": "crypto", "reason": "test"},
    )
    assert response.status_code == 200
    assert response.json()["normalized_event_id"]
    assert client.get("/news/recent").json()["count"] == 1


def test_collect_requires_reason(postgres_test_schema) -> None:
    client = _client(postgres_test_schema)
    assert client.post("/news/collect", json={"limit_per_source": 1}).status_code == 422


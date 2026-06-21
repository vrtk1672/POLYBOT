from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.services.source_status import SourceStatusService


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}


class _FakeHttpClient:
    def __init__(self, *, fail: set[str] | None = None) -> None:
        self.fail = fail or set()
        self.calls: list[dict[str, Any]] = []

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, int]:
        self.calls.append({"method": "GET", "url": url, "params": params, "headers": headers})
        if any(token in url for token in self.fail):
            raise RuntimeError(f"forced failure for {url}")
        if "gamma-api.polymarket.com" in url:
            return (
                [
                    {
                        "id": "event-1",
                        "markets": [
                            {
                                "id": "market-1",
                                "conditionId": "0x" + "a" * 64,
                                "clobTokenIds": '["token-yes","token-no"]',
                                "active": True,
                                "closed": False,
                                "acceptingOrders": True,
                                "enableOrderBook": True,
                            }
                        ],
                    }
                ],
                11,
            )
        if "clob.polymarket.com/book" in url:
            return (
                {
                    "market": "0x" + "a" * 64,
                    "asset_id": "token-yes",
                    "bids": [{"price": "0.42", "size": "100"}],
                    "asks": [{"price": "0.44", "size": "120"}],
                    "last_trade_price": "0.43",
                },
                12,
            )
        if "data-api.polymarket.com/trades" in url:
            return ([{"asset": "token-yes", "price": 0.43, "size": 10}], 13)
        raise AssertionError(f"unexpected URL: {url}")


def _client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    return TestClient(app)


def _sources_by_name(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["source_name"]: item for item in payload["sources"]}


def test_source_status_endpoint_returns_mock_data_false(monkeypatch) -> None:
    class _FakeSourceStatusService:
        def get_dashboard_source_status(self) -> dict[str, object]:
            return {
                "status": "OK",
                "mock_data": False,
                "stale": False,
                "updated_at": "2026-05-21T00:00:00+00:00",
                "sources": [],
                "degraded_sources": [],
            }

    monkeypatch.setattr("app.api.routes.SourceStatusService", _FakeSourceStatusService)
    with _client() as client:
        response = client.get("/dashboard/api/v2/source-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "OK"
    assert payload["mock_data"] is False
    assert payload["stale"] is False


def test_gamma_and_clob_sources_become_active_with_read_only_checks(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    fake_http = _FakeHttpClient()
    payload = SourceStatusService(http_client=fake_http).get_dashboard_source_status(persist=False)
    sources = _sources_by_name(payload)

    assert payload["status"] == "OK"
    assert sources["polymarket_gamma"]["runtime_status"] == "ACTIVE"
    assert sources["polymarket_clob_orderbook"]["runtime_status"] == "ACTIVE"
    assert sources["polymarket_clob_prices"]["runtime_status"] == "ACTIVE"
    assert sources["polymarket_clob_spreads"]["runtime_status"] == "ACTIVE"
    assert sources["polymarket_clob_orderbook"]["read_only"] is True
    assert sources["polymarket_clob_orderbook"]["mutation_allowed"] is False
    assert all(call["method"] == "GET" for call in fake_http.calls)
    assert not any("POLY_PRIVATE_KEY" in str(call) for call in fake_http.calls)


def test_clob_probe_uses_only_orderbook_enabled_gamma_markets(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    class _MixedGammaHttp(_FakeHttpClient):
        def get_json(
            self,
            url: str,
            *,
            params: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
        ) -> tuple[Any, int]:
            if "gamma-api.polymarket.com" in url:
                self.calls.append({"method": "GET", "url": url, "params": params, "headers": headers})
                return (
                    [
                        {
                            "id": "event-1",
                            "markets": [
                                {
                                    "id": "stale-market",
                                    "clobTokenIds": '["stale-token"]',
                                    "active": True,
                                    "closed": False,
                                    "acceptingOrders": False,
                                    "enableOrderBook": True,
                                },
                                {
                                    "id": "book-market",
                                    "clobTokenIds": '["book-token"]',
                                    "active": True,
                                    "closed": False,
                                    "acceptingOrders": True,
                                    "enableOrderBook": True,
                                },
                            ],
                        }
                    ],
                    11,
                )
            return super().get_json(url, params=params, headers=headers)

    fake_http = _MixedGammaHttp()
    payload = SourceStatusService(http_client=fake_http).get_dashboard_source_status(persist=False)
    sources = _sources_by_name(payload)

    assert sources["polymarket_clob_orderbook"]["runtime_status"] == "ACTIVE"
    clob_calls = [call for call in fake_http.calls if "clob.polymarket.com/book" in call["url"]]
    assert [call["params"]["token_id"] for call in clob_calls] == ["book-token"]


def test_optional_news_and_social_placeholders_do_not_crash(monkeypatch) -> None:
    monkeypatch.delenv("NEWS_API_KEY", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    payload = SourceStatusService(http_client=_FakeHttpClient()).get_dashboard_source_status(persist=False)
    sources = _sources_by_name(payload)

    assert sources["news_provider"]["runtime_status"] == "DISABLED"
    assert sources["news_provider"]["key_required"] is True
    assert sources["news_provider"]["key_present"] is False
    assert sources["reddit_or_social_provider"]["runtime_status"] == "DISABLED"
    assert sources["reddit_or_social_provider"]["key_required"] is True
    assert sources["reddit_or_social_provider"]["key_present"] is False


def test_ollama_probe_falls_back_to_docker_host_for_localhost(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL_FAST", "qwen3:4b")
    monkeypatch.setenv("OLLAMA_MODEL_PRIMARY", "qwen3:4b")
    monkeypatch.setenv("OLLAMA_MODEL_REASONING", "qwen3:4b")

    class _OllamaFallbackHttp(_FakeHttpClient):
        def get_json(
            self,
            url: str,
            *,
            params: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
        ) -> tuple[Any, int]:
            self.calls.append({"method": "GET", "url": url, "params": params, "headers": headers})
            if "localhost:11434" in url:
                raise RuntimeError("connection refused")
            if "host.docker.internal:11434" in url:
                return ({"models": [{"name": "qwen3:4b"}]}, 14)
            return super().get_json(url, params=params, headers=headers)

    fake_http = _OllamaFallbackHttp()
    payload = SourceStatusService(http_client=fake_http).get_dashboard_source_status(persist=False)
    sources = _sources_by_name(payload)

    assert sources["ollama_local_model"]["runtime_status"] == "ACTIVE"
    assert sources["ollama_local_model"]["endpoint_url"] == "http://host.docker.internal:11434/api/tags"
    assert sources["ollama_local_model"]["details_json"]["missing_configured_models"] == []


def test_source_failure_becomes_degraded_not_exception(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    payload = SourceStatusService(
        http_client=_FakeHttpClient(fail={"clob.polymarket.com/book"})
    ).get_dashboard_source_status(persist=False)
    sources = _sources_by_name(payload)

    assert payload["status"] == "DEGRADED"
    assert sources["polymarket_gamma"]["runtime_status"] == "ACTIVE"
    assert sources["polymarket_clob_orderbook"]["runtime_status"] == "DEGRADED"
    assert sources["polymarket_clob_prices"]["runtime_status"] == "DEGRADED"
    assert sources["polymarket_clob_spreads"]["runtime_status"] == "DEGRADED"


def test_source_checks_do_not_require_live_or_private_key(monkeypatch) -> None:
    for key in (
        "POLY_PRIVATE_KEY",
        "POLY_FUNDER",
        "POLY_API_KEY",
        "POLY_API_SECRET",
        "POLY_API_PASSPHRASE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
    monkeypatch.setenv("LIVE_KILL_SWITCH", "true")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    payload = SourceStatusService(http_client=_FakeHttpClient()).get_dashboard_source_status(persist=False)

    assert payload["status"] == "OK"
    for item in payload["sources"]:
        assert item["read_only"] is True
        assert item["mutation_allowed"] is False


def test_source_status_persists_only_to_docker_test_database(monkeypatch) -> None:
    database_url = os.getenv("POLYBOT_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if "polybot_test" not in database_url:
        pytest.skip("requires POLYBOT_DATABASE_URL or DATABASE_URL pointing at polybot_test")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    payload = SourceStatusService(http_client=_FakeHttpClient()).get_dashboard_source_status()
    assert payload["status"] == "OK"

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        db_name = conn.execute("SELECT current_database() AS db").fetchone()["db"]
        count = conn.execute("SELECT COUNT(*) AS count FROM source_status").fetchone()["count"]
        live_count = conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"]
    assert db_name == "polybot_test"
    assert count >= 4
    assert live_count == 0

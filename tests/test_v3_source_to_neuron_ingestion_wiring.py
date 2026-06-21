from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.services.system_power import SystemPowerService
from app.source_to_neuron.service import SourceToNeuronIngestionService


class _FakeSourceStatus:
    def get_dashboard_source_status(self, *, persist: bool = True) -> dict[str, Any]:
        return {
            "mock_data": False,
            "status": "OK",
            "sources": [
                {"source_name": "polymarket_gamma", "runtime_status": "ACTIVE"},
                {"source_name": "polymarket_clob_orderbook", "runtime_status": "ACTIVE"},
                {"source_name": "polymarket_activity_readonly", "runtime_status": "ACTIVE"},
                {"source_name": "ollama_local_model", "runtime_status": "ACTIVE"},
            ],
            "degraded_sources": [],
        }


class _FakeHttp:
    def __init__(self, *, large_trade: bool = True) -> None:
        self.large_trade = large_trade

    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> tuple[str, int]:
        return (
            """
            <rss><channel>
              <item>
                <title>Prediction markets react to election polling update</title>
                <link>https://example.test/news/prediction-market-poll</link>
                <guid>rss-item-1</guid>
                <description>Polymarket traders watched new election polling.</description>
                <pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate>
              </item>
            </channel></rss>
            """,
            3,
        )

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, int]:
        if "newsapi.org" in url:
            return (
                {
                    "status": "ok",
                    "articles": [
                        {
                            "title": "Polymarket volume rises after prediction market debate",
                            "description": "A source-backed NewsAPI article.",
                            "url": "https://example.test/newsapi/article-1",
                            "publishedAt": "2026-06-01T10:01:00Z",
                            "author": "Example",
                        }
                    ],
                },
                5,
            )
        if "gamma-api.polymarket.com" in url:
            return (
                [
                    {
                        "id": "event-1",
                        "markets": [
                            {
                                "id": "market-v39",
                                "question": "Will the test market resolve Yes?",
                                "active": True,
                                "closed": False,
                                "acceptingOrders": True,
                                "enableOrderBook": True,
                                "clobTokenIds": ["token-yes-v39", "token-no-v39"],
                            }
                        ],
                    }
                ],
                7,
            )
        if "clob.polymarket.com" in url and "/book" in url:
            return (
                {
                    "bids": [{"price": "0.48", "size": "1200"}, {"price": "0.47", "size": "500"}],
                    "asks": [{"price": "0.52", "size": "1100"}, {"price": "0.53", "size": "450"}],
                    "last_trade_price": "0.50",
                },
                4,
            )
        if "data-api.polymarket.com" in url and "/trades" in url:
            size = "5000" if self.large_trade else "10"
            return (
                [
                    {
                        "id": "trade-v39-large" if self.large_trade else "trade-v39-small",
                        "market": "market-v39",
                        "asset": "token-yes-v39",
                        "proxyWallet": "0xabc",
                        "side": "YES",
                        "action": "BUY",
                        "size": size,
                        "price": "0.50",
                        "timestamp": "2026-06-01T10:02:00Z",
                    }
                ],
                6,
            )
        raise AssertionError(f"unexpected get_json url={url}")

    def post_json(
        self,
        url: str,
        *,
        json_payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, int]:
        assert "/api/generate" in url
        return {"response": "{\"status\":\"OK\",\"summary\":\"local context updated\",\"confidence\":0.66}"}, 9


def _prepare(monkeypatch, *, large_trade: bool = True) -> SourceToNeuronIngestionService:
    run_migrations()
    SystemPowerService().turn_on(actor="pytest", reason="source to neuron tests")
    monkeypatch.setenv("NEWS_RSS_FEEDS", "https://example.test/feed.xml")
    monkeypatch.setenv("NEWS_API_KEY", "secret-news-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL_FAST", "qwen3:4b")
    monkeypatch.setenv("SOURCE_TO_NEURON_WHALE_USD_THRESHOLD", "1000")
    return SourceToNeuronIngestionService(http_client=_FakeHttp(large_trade=large_trade), source_status=_FakeSourceStatus())


def _count(table: str, where: str | None = None) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
        if not exists:
            return 0
        sql = f"SELECT COUNT(*) AS count FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return int(conn.execute(sql).fetchone()["count"] or 0)


def _safety_counts() -> dict[str, int]:
    return {
        table: _count(table)
        for table in (
            "live_orders",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "paper_intents",
            "paper_capital_ledger",
            "risk_decisions",
            "exit_plans",
            "coordinator_decisions",
            "brain_outputs",
            "orders_v2",
            "fills_v2",
            "positions",
        )
    }


def test_system_off_blocks_source_to_neuron_ingestion(postgres_test_schema, monkeypatch) -> None:
    service = _prepare(monkeypatch)
    SystemPowerService().turn_off(actor="pytest", reason="source to neuron off")
    before = _count("neural_events")

    result = service.run_once()

    assert result["status"] == "SYSTEM_POWER_OFF"
    assert result["events_created"] == 0
    assert _count("neural_events") == before


def test_configured_sources_map_to_correct_neuron_events(postgres_test_schema, monkeypatch) -> None:
    service = _prepare(monkeypatch)

    result = service.run_once(limit_per_source=1)

    assert result["mock_data"] is False
    assert result["trading_mutation_detected"] is False
    created_types = {item["event_type"] for item in result["latest_items"]}
    assert "NEWS_DETECTED" in created_types
    assert "MARKET_REPRICING" in created_types
    assert "ORDERBOOK_REFRESHED" in created_types
    assert "SPREAD_CHANGED" in created_types
    assert "LIQUIDITY_CHANGED" in created_types
    assert "WHALE_DETECTED" in created_types
    assert "AI_CONTEXT_UPDATED" in created_types
    assert _count("news_sources") >= 1
    assert _count("news_normalized_events") >= 1
    assert _count("orderbook_snapshots") >= 1
    assert _count("whale_events") >= 1
    assert _count("ai_responses") >= 1


def test_no_large_trade_does_not_create_fake_whale_event(postgres_test_schema, monkeypatch) -> None:
    service = _prepare(monkeypatch, large_trade=False)

    result = service.run_once(limit_per_source=1)

    assert result["whale_status"] == "NO_WHALE_EVENT_FOUND"
    assert _count("neural_events", "event_type = 'WHALE_DETECTED'") == 0
    assert _count("whale_events") == 0


def test_neural_events_create_sessions_awareness_brains_and_dialogue(postgres_test_schema, monkeypatch) -> None:
    service = _prepare(monkeypatch)

    result = service.run_once(limit_per_source=1)

    assert result["sessions_updated"] >= 1
    assert result["awareness_domains_updated"] >= 1
    assert result["brain_opinions_created"] >= 1
    assert result["coordinator_decisions_created"] >= 1
    assert _count("brain_dialogue_events", "component IN ('News Neuron','Orderbook Neuron','Liquidity Neuron','Whale Neuron','AI Context Brain','Market Neuron')") >= 1


def test_dashboard_returns_mock_data_false(postgres_test_schema, monkeypatch) -> None:
    _prepare(monkeypatch).run_once(limit_per_source=1)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/source-to-neuron-flow")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert "events_created" in payload


def test_run_endpoint_respects_system_off_without_provider_calls(postgres_test_schema) -> None:
    run_migrations()
    SystemPowerService().turn_off(actor="pytest", reason="source to neuron route off")
    client = TestClient(create_app())

    response = client.post("/source-to-neuron/run", json={"limit_per_source": 1})

    assert response.status_code == 200
    assert response.json()["status"] == "SYSTEM_POWER_OFF"


def test_openai_anthropic_auth_only_does_not_create_fake_ai_context(postgres_test_schema, monkeypatch) -> None:
    service = _prepare(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-anthropic-key")

    result = service.run_once(limit_per_source=1, include_ollama_generation=False)
    serialized = json.dumps(result, sort_keys=True, default=str)

    assert result["provider_status"]["openai_api"]["runtime_status"] == "READY_AUTH_ONLY"
    assert result["provider_status"]["anthropic_api"]["runtime_status"] == "READY_AUTH_ONLY"
    assert _count("neural_events", "event_type = 'AI_CONTEXT_UPDATED'") == 0
    assert "secret-openai-key" not in serialized
    assert "secret-anthropic-key" not in serialized


def test_no_trading_mutation(postgres_test_schema, monkeypatch) -> None:
    service = _prepare(monkeypatch)
    before = _safety_counts()

    service.run_once(limit_per_source=1)

    assert _safety_counts() == before

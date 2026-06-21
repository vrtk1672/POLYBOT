from __future__ import annotations

import json
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.system_power import SystemPowerService
from app.source_to_neuron.service import SourceToNeuronIngestionService
from test_v3_source_to_neuron_ingestion_wiring import _FakeHttp, _FakeSourceStatus, _count, _safety_counts


class _TimeoutThenSuccessHttp(_FakeHttp):
    def __init__(self) -> None:
        super().__init__()
        self.post_payloads: list[dict[str, Any]] = []

    def post_json(
        self,
        url: str,
        *,
        json_payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, int]:
        self.post_payloads.append(json_payload)
        if len(self.post_payloads) == 1:
            raise TimeoutError("ollama generation timed out")
        return {"response": "{\"status\":\"OK\",\"summary\":\"fallback context ok\",\"confidence\":0.61}"}, 8


def _prepare_service(monkeypatch, http: Any | None = None) -> SourceToNeuronIngestionService:
    run_migrations()
    SystemPowerService().turn_on(actor="pytest", reason="source yellow fixes")
    monkeypatch.setenv("NEWS_RSS_FEEDS", "https://example.test/feed.xml")
    monkeypatch.setenv("SOURCE_TO_NEURON_WHALE_USD_THRESHOLD", "1000")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL_FAST", "fast-model")
    monkeypatch.setenv("OLLAMA_MODEL_PRIMARY", "slow-model")
    return SourceToNeuronIngestionService(http_client=http or _FakeHttp(), source_status=_FakeSourceStatus())


def test_ollama_timeout_uses_bounded_fast_fallback_without_fake_context(postgres_test_schema, monkeypatch) -> None:
    http = _TimeoutThenSuccessHttp()
    service = _prepare_service(monkeypatch, http=http)

    result = service.run_once(limit_per_source=1)

    assert any(item["event_type"] == "AI_CONTEXT_UPDATED" for item in result["latest_items"])
    assert len(http.post_payloads) >= 2
    assert http.post_payloads[0]["model"] == "fast-model"
    assert http.post_payloads[0]["options"]["num_predict"] <= 48
    assert http.post_payloads[1]["options"]["num_predict"] <= 48
    assert _count("ai_responses") == 1


def test_rss_env_registration_is_idempotent(postgres_test_schema, monkeypatch) -> None:
    service = _prepare_service(monkeypatch)

    first = service.run_once(limit_per_source=1, include_ollama_generation=False)
    second = service.run_once(limit_per_source=1, include_ollama_generation=False)

    assert first["trading_mutation_detected"] is False
    assert second["trading_mutation_detected"] is False
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM news_sources WHERE metadata_json->>'configured_from_env' = 'true'").fetchone()["count"]
    assert int(count) == 1


def test_newsapi_collector_is_bounded_and_source_backed(postgres_test_schema, monkeypatch) -> None:
    monkeypatch.setenv("NEWS_API_KEY", "secret-newsapi-key")
    service = _prepare_service(monkeypatch)

    result = service.run_once(limit_per_source=1, include_ollama_generation=False)
    serialized = json.dumps(result, sort_keys=True, default=str)

    assert result["trading_mutation_detected"] is False
    assert "secret-newsapi-key" not in serialized
    with DatabaseConnectionFactory().connect() as conn:
        newsapi_source = conn.execute("SELECT * FROM news_sources WHERE source_id='newsapi_v3'").fetchone()
        raw_count = conn.execute("SELECT COUNT(*) AS count FROM news_raw_events WHERE source_id='newsapi_v3'").fetchone()["count"]
        normalized_count = conn.execute("SELECT COUNT(*) AS count FROM news_normalized_events WHERE source_id='newsapi_v3'").fetchone()["count"]
    assert newsapi_source is not None
    assert int(raw_count) == 1
    assert int(normalized_count) == 1


def test_source_to_neuron_no_trading_mutation(postgres_test_schema, monkeypatch) -> None:
    service = _prepare_service(monkeypatch)
    before = _safety_counts()

    result = service.run_once(limit_per_source=1, include_ollama_generation=False)

    assert result["trading_mutation_detected"] is False
    assert _safety_counts() == before

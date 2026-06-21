from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.services.ai_context_router import (
    AIContextRouterConfig,
    AIContextRouterService,
    _clean_operator_ai_output,
    _config_from_env,
)
from app.services.system_power import SystemPowerService
from app.source_to_neuron.service import SourceToNeuronIngestionService
from test_v3_source_to_neuron_ingestion_wiring import _FakeSourceStatus, _safety_counts


class _ProviderHttp:
    def __init__(self, outcomes: dict[str, Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def post_json(
        self,
        url: str,
        *,
        json_payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[Any, int]:
        if "/api/generate" in url:
            provider = "ollama"
        elif "openai" in url:
            provider = "openai"
        elif "anthropic" in url:
            provider = "anthropic"
        else:
            provider = "unknown"
        self.calls.append(
            {
                "provider": provider,
                "url": url,
                "payload": json_payload,
                "headers": {key: "[REDACTED]" for key in (headers or {})},
                "timeout_seconds": timeout_seconds,
            }
        )
        outcome = self.outcomes.get(provider)
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, dict):
            return outcome, 10
        if provider == "ollama":
            return {"response": outcome or "{\"status\":\"OK\",\"summary\":\"ollama ok\",\"confidence\":0.7}"}, 10
        if provider == "openai":
            return {"choices": [{"message": {"content": outcome or "{\"status\":\"OK\",\"summary\":\"openai ok\",\"confidence\":0.8}"}}]}, 11
        if provider == "anthropic":
            return {"content": [{"type": "text", "text": outcome or "{\"status\":\"OK\",\"summary\":\"anthropic ok\",\"confidence\":0.9}"}]}, 12
        raise AssertionError(f"unexpected url {url}")


class _SourceHttp(_ProviderHttp):
    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> tuple[str, int]:
        return (
            """
            <rss><channel><item>
              <title>Prediction markets react to AI router test</title>
              <link>https://example.test/router</link>
              <guid>router-rss-1</guid>
              <description>Source backed router test.</description>
              <pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate>
            </item></channel></rss>
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
        if "gamma-api.polymarket.com" in url:
            return (
                [
                    {
                        "id": "event-router-1",
                        "markets": [
                            {
                                "id": "market-router",
                                "question": "Will the router test market resolve Yes?",
                                "active": True,
                                "closed": False,
                                "acceptingOrders": True,
                                "enableOrderBook": True,
                                "clobTokenIds": ["router-token-yes", "router-token-no"],
                            }
                        ],
                    }
                ],
                7,
            )
        if "clob.polymarket.com" in url and "/book" in url:
            return {"bids": [{"price": "0.48", "size": "100"}], "asks": [{"price": "0.52", "size": "100"}]}, 4
        if "data-api.polymarket.com" in url and "/trades" in url:
            return [], 6
        raise AssertionError(f"unexpected get_json url={url}")


def _prepare(monkeypatch, http: Any, *, provider_order: tuple[str, ...] = ("ollama", "openai", "anthropic")) -> AIContextRouterService:
    run_migrations()
    SystemPowerService().turn_on(actor="pytest", reason="ai context router tests")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL_FAST", "fast-model")
    monkeypatch.setenv("AI_CONTEXT_PROVIDER_ORDER", "ollama,openai,anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-anthropic-key")
    return AIContextRouterService(
        http_client=http,
        config=AIContextRouterConfig(
            provider_order=provider_order,
            provider_timeout_seconds=2,
            total_timeout_seconds=5,
            max_prompt_chars=500,
            max_response_tokens=64,
            cloud_fallback_enabled=True,
            ai_required=False,
            ollama_timeout_fast_seconds=2,
            ollama_timeout_primary_seconds=2,
            ollama_timeout_reasoning_seconds=2,
        ),
    )


def _count(table: str, where: str | None = None) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
        if not exists:
            return 0
        sql = f"SELECT COUNT(*) AS count FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return int(conn.execute(sql).fetchone()["count"] or 0)


def test_stage26b_timeout_defaults_are_bounded(monkeypatch) -> None:
    for name in (
        "AI_CONTEXT_PROVIDER_TIMEOUT_SECONDS",
        "AI_CONTEXT_TOTAL_TIMEOUT_SECONDS",
        "OLLAMA_TIMEOUT_SECONDS",
        "OLLAMA_TIMEOUT_FAST_SECONDS",
        "OLLAMA_TIMEOUT_PRIMARY_SECONDS",
        "OLLAMA_TIMEOUT_REASONING_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    config = _config_from_env()

    assert config.provider_timeout_seconds == 90
    assert config.total_timeout_seconds == 120
    assert config.ollama_timeout_fast_seconds == 60
    assert config.ollama_timeout_primary_seconds == 90
    assert config.ollama_timeout_reasoning_seconds == 120


def test_stage26b_timeout_env_supports_role_specific_values(monkeypatch) -> None:
    monkeypatch.setenv("AI_CONTEXT_PROVIDER_TIMEOUT_SECONDS", "88")
    monkeypatch.setenv("AI_CONTEXT_TOTAL_TIMEOUT_SECONDS", "119")
    monkeypatch.setenv("OLLAMA_TIMEOUT_FAST_SECONDS", "60")
    monkeypatch.setenv("OLLAMA_TIMEOUT_PRIMARY_SECONDS", "90")
    monkeypatch.setenv("OLLAMA_TIMEOUT_REASONING_SECONDS", "120")

    config = _config_from_env()

    assert config.provider_timeout_seconds == 88
    assert config.total_timeout_seconds == 119
    assert config.ollama_timeout_fast_seconds == 60
    assert config.ollama_timeout_primary_seconds == 90
    assert config.ollama_timeout_reasoning_seconds == 120


def test_stage26b_timeout_env_caps_unbounded_values(monkeypatch) -> None:
    monkeypatch.setenv("AI_CONTEXT_PROVIDER_TIMEOUT_SECONDS", "999")
    monkeypatch.setenv("AI_CONTEXT_TOTAL_TIMEOUT_SECONDS", "999")
    monkeypatch.setenv("OLLAMA_TIMEOUT_FAST_SECONDS", "999")
    monkeypatch.setenv("OLLAMA_TIMEOUT_PRIMARY_SECONDS", "999")
    monkeypatch.setenv("OLLAMA_TIMEOUT_REASONING_SECONDS", "999")

    config = _config_from_env()

    assert config.provider_timeout_seconds == 120
    assert config.total_timeout_seconds == 120
    assert config.ollama_timeout_fast_seconds == 120
    assert config.ollama_timeout_primary_seconds == 120
    assert config.ollama_timeout_reasoning_seconds == 120


def test_stage26b_prompt_cleanup_removes_visible_reasoning_preamble() -> None:
    raw = (
        "Okay, the user wants a JSON answer. First I need to reason about the request.\n\n"
        '{"status":"OK","summary":"local ai ready","confidence":0.7}'
    )

    assert _clean_operator_ai_output(raw) == '{"status":"OK","summary":"local ai ready","confidence":0.7}'


def test_stage26b_prompt_cleanup_preserves_normal_answer() -> None:
    answer = '{"status":"OK","summary":"already clean","confidence":0.8}'

    assert _clean_operator_ai_output(answer) == answer


def test_ollama_success_returns_ollama_and_skips_fallback(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp({"ollama": "{\"status\":\"OK\",\"summary\":\"ollama ok\",\"confidence\":0.71}"})
    router = _prepare(monkeypatch, http)

    result = router.route_context(prompt="source backed test", correlation_id="router_ollama_success")

    assert result["status"] == "OK"
    assert result["selected_provider"] == "ollama"
    assert [call["provider"] for call in http.calls] == ["ollama"]
    assert _count("neural_events", "event_type = 'AI_CONTEXT_UPDATED'") == 1


def test_ollama_uses_keep_alive_and_thinking_fallback(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp({"ollama": {"response": "", "thinking": "{\"status\":\"OK\",\"summary\":\"thinking ok\",\"confidence\":0.72}"}})
    router = _prepare(monkeypatch, http)
    monkeypatch.setenv("AI_CONTEXT_OLLAMA_KEEP_ALIVE", "5m")

    result = router.route_context(prompt="source backed test", correlation_id="router_ollama_thinking")

    assert result["status"] == "OK"
    assert result["selected_provider"] == "ollama"
    assert http.calls[0]["payload"]["keep_alive"] == "5m"
    assert result["event"]["payload_json"]["summary"] == "thinking ok"


def test_ollama_timeout_falls_back_to_openai(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp({"ollama": TimeoutError("ollama generation timed out"), "openai": "{\"status\":\"OK\",\"summary\":\"openai fallback\",\"confidence\":0.8}"})
    router = _prepare(monkeypatch, http)

    result = router.route_context(prompt="source backed test", correlation_id="router_openai_fallback")

    assert result["status"] == "OK"
    assert result["selected_provider"] == "openai"
    assert [call["provider"] for call in http.calls] == ["ollama", "ollama", "openai"]
    reasons = [attempt.get("reason") for attempt in result["providers_attempted"]]
    assert "OLLAMA_TIMEOUT" in json.dumps(reasons)


def test_openai_timeout_falls_back_to_anthropic(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp(
        {
            "ollama": TimeoutError("ollama timed out"),
            "openai": TimeoutError("openai timed out"),
            "anthropic": "{\"status\":\"OK\",\"summary\":\"anthropic fallback\",\"confidence\":0.9}",
        }
    )
    router = _prepare(monkeypatch, http)

    result = router.route_context(prompt="source backed test", correlation_id="router_anthropic_fallback")

    assert result["status"] == "OK"
    assert result["selected_provider"] == "anthropic"
    assert [call["provider"] for call in http.calls] == ["ollama", "ollama", "openai", "anthropic"]


def test_all_providers_fail_publishes_unavailable(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp({"ollama": TimeoutError("ollama timed out"), "openai": RuntimeError("openai failed"), "anthropic": RuntimeError("anthropic failed")})
    router = _prepare(monkeypatch, http)

    result = router.route_context(prompt="source backed test", correlation_id="router_all_fail")

    assert result["status"] == "AI_CONTEXT_UNAVAILABLE"
    assert result["runtime_continues"] is True
    assert _count("neural_events", "event_type = 'AI_CONTEXT_UNAVAILABLE'") == 1
    assert _count("ai_responses") == 0


def test_openai_429_is_rate_limited_not_generic_crash(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp(
        {
            "ollama": TimeoutError("ollama timed out"),
            "openai": RuntimeError("429 Too Many Requests"),
            "anthropic": RuntimeError("anthropic failed"),
        }
    )
    router = _prepare(monkeypatch, http)

    result = router.route_context(prompt="source backed test", correlation_id="router_openai_429")

    assert result["status"] == "AI_CONTEXT_UNAVAILABLE"
    assert "OPENAI_RATE_LIMITED" in json.dumps(result["providers_attempted"])


def test_openai_insufficient_quota_is_classified_precisely(postgres_test_schema, monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(
        429,
        request=request,
        json={"error": {"type": "insufficient_quota", "code": "insufficient_quota", "message": "You exceeded your current quota"}},
    )
    http = _ProviderHttp(
        {
            "ollama": TimeoutError("ollama timed out"),
            "openai": httpx.HTTPStatusError("quota", request=request, response=response),
            "anthropic": RuntimeError("anthropic failed"),
        }
    )
    router = _prepare(monkeypatch, http)

    result = router.route_context(prompt="source backed test", correlation_id="router_openai_quota")

    assert result["status"] == "AI_CONTEXT_UNAVAILABLE"
    assert "OPENAI_QUOTA_EXCEEDED" in json.dumps(result["providers_attempted"])


def test_anthropic_404_is_degraded_not_generic_crash(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp(
        {
            "ollama": TimeoutError("ollama timed out"),
            "openai": RuntimeError("openai failed"),
            "anthropic": RuntimeError("404 Not Found"),
        }
    )
    router = _prepare(monkeypatch, http)

    result = router.route_context(prompt="source backed test", correlation_id="router_anthropic_404")

    assert result["status"] == "AI_CONTEXT_UNAVAILABLE"
    assert "ANTHROPIC_DEGRADED" in json.dumps(result["providers_attempted"])


def test_anthropic_current_default_model_is_tried_first(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp(
        {
            "ollama": TimeoutError("ollama timed out"),
            "openai": RuntimeError("openai failed"),
            "anthropic": "{\"status\":\"OK\",\"summary\":\"anthropic current model\",\"confidence\":0.9}",
        }
    )
    router = _prepare(monkeypatch, http)
    monkeypatch.delenv("AI_CONTEXT_ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    result = router.route_context(prompt="source backed test", correlation_id="router_anthropic_current_default")

    assert result["status"] == "OK"
    assert result["selected_provider"] == "anthropic"
    anthropic_call = [call for call in http.calls if call["provider"] == "anthropic"][0]
    assert anthropic_call["payload"]["model"] == "claude-haiku-4-5-20251001"


def test_cloud_fallback_disabled_skips_openai_and_anthropic(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp({"ollama": TimeoutError("ollama timed out")})
    router = _prepare(monkeypatch, http)

    result = router.route_context(prompt="source backed test", correlation_id="router_cloud_disabled", cloud_fallback_enabled=False)

    assert result["status"] == "AI_CONTEXT_UNAVAILABLE"
    assert [call["provider"] for call in http.calls] == ["ollama", "ollama"]
    assert "CLOUD_FALLBACK_DISABLED" in json.dumps(result["providers_attempted"])


def test_no_secrets_in_result_or_dashboard(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp({"ollama": TimeoutError("ollama timed out"), "openai": "{\"status\":\"OK\",\"summary\":\"openai fallback\",\"confidence\":0.8}"})
    router = _prepare(monkeypatch, http)

    result = router.route_context(prompt="source backed test", correlation_id="router_secret_check")
    dashboard = TestClient(create_app()).get("/dashboard/api/v2/ai-context-router").json()
    serialized = json.dumps({"result": result, "dashboard": dashboard}, sort_keys=True, default=str)

    assert "secret-openai-key" not in serialized
    assert "secret-anthropic-key" not in serialized
    assert dashboard["mock_data"] is False


def test_provider_timeout_is_passed_to_http_client(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp({"ollama": "{\"status\":\"OK\",\"summary\":\"ollama ok\",\"confidence\":0.71}"})
    router = _prepare(monkeypatch, http)

    router.route_context(prompt="source backed test", correlation_id="router_timeout_check")

    assert http.calls[0]["timeout_seconds"] == 2


def test_ollama_payload_disables_thinking_and_requests_final_json(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp({"ollama": "{\"status\":\"OK\",\"summary\":\"ollama ok\",\"confidence\":0.71}"})
    router = _prepare(monkeypatch, http)

    router.route_context(prompt="source backed test", correlation_id="router_prompt_check")

    payload = http.calls[0]["payload"]
    assert payload["think"] is False
    assert "Return only the final answer" in payload["prompt"]
    assert "cannot create trades" in payload["prompt"]


def test_total_timeout_stops_without_cloud_calls(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp({"ollama": TimeoutError("ollama timed out")})
    router = AIContextRouterService(
        http_client=http,
        config=AIContextRouterConfig(
            provider_order=("ollama", "openai", "anthropic"),
            provider_timeout_seconds=2,
            total_timeout_seconds=0.001,
            max_prompt_chars=500,
            max_response_tokens=64,
            cloud_fallback_enabled=True,
            ai_required=False,
            ollama_timeout_fast_seconds=2,
            ollama_timeout_primary_seconds=2,
            ollama_timeout_reasoning_seconds=2,
        ),
    )
    run_migrations()
    SystemPowerService().turn_on(actor="pytest", reason="ai context router tests")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL_FAST", "fast-model")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-anthropic-key")

    result = router.route_context(prompt="source backed test", correlation_id="router_total_timeout")

    assert result["status"] == "AI_CONTEXT_UNAVAILABLE"
    assert [call["provider"] for call in http.calls] in ([], ["ollama"], ["ollama", "ollama"])
    assert "AI_CONTEXT_TOTAL_TIMEOUT" in json.dumps(result["providers_attempted"]) or result["final_reason"].endswith("_TIMEOUT")


def test_source_to_neuron_uses_router_and_preserves_trading_counts(postgres_test_schema, monkeypatch) -> None:
    run_migrations()
    SystemPowerService().turn_on(actor="pytest", reason="ai context router source integration")
    monkeypatch.setenv("NEWS_RSS_FEEDS", "https://example.test/feed.xml")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL_FAST", "fast-model")
    monkeypatch.setenv("AI_CONTEXT_PROVIDER_ORDER", "ollama,openai,anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai-key")
    http = _SourceHttp({"ollama": TimeoutError("ollama timed out"), "openai": "{\"status\":\"OK\",\"summary\":\"openai fallback\",\"confidence\":0.8}"})
    service = SourceToNeuronIngestionService(http_client=http, source_status=_FakeSourceStatus())
    before = _safety_counts()

    result = service.run_once(limit_per_source=1)

    assert result["trading_mutation_detected"] is False
    assert _safety_counts() == before
    assert result["ai_context_router"]["selected_provider"] == "openai"
    assert any(item["event_type"] == "AI_CONTEXT_UPDATED" for item in result["latest_items"])
    ollama_calls = [call for call in http.calls if call["provider"] == "ollama"]
    assert ollama_calls
    assert ollama_calls[0]["timeout_seconds"] == 60


def test_system_off_blocks_runtime_router_mutation(postgres_test_schema, monkeypatch) -> None:
    http = _ProviderHttp({"ollama": "{\"status\":\"OK\",\"summary\":\"ollama ok\",\"confidence\":0.71}"})
    router = _prepare(monkeypatch, http)
    SystemPowerService().turn_off(actor="pytest", reason="system off router block")
    before = _count("neural_events")
    router_runs_before = _count("ai_context_router_runs")

    result = router.route_context(prompt="source backed test", correlation_id="router_system_off")

    assert result["status"] == "SYSTEM_POWER_OFF"
    assert _count("neural_events") == before
    assert _count("ai_context_router_runs") == router_runs_before
    assert http.calls == []

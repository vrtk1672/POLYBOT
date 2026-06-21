from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.runtime_intelligence import RuntimeIntelligenceService


class _FakeHttpResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _FakeHttpClient:
    def __init__(self, html_text: str) -> None:
        self._html_text = html_text
        self.calls: list[str] = []

    def get(self, url: str, headers: dict[str, str] | None = None):  # noqa: ANN001
        self.calls.append(url)
        return _FakeHttpResponse(self._html_text)


class _FakeAnthropicMessages:
    def create(self, **kwargs):  # noqa: ANN003
        payload = {
            "summary_text": "AP runtime digest detected a market-relevant macro headline.",
            "relevance_level": "HIGH",
            "contradiction_risk": "LOW",
            "operator_takeaway": "Keep the fresh AP event in operator context.",
            "watch_items": ["Track follow-up coverage."],
        }
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))])


class _FakeAnthropicClient:
    def __init__(self) -> None:
        self.messages = _FakeAnthropicMessages()


class _StaticAnthropicMessages:
    def __init__(self, content_blocks: list[str]) -> None:
        self._content_blocks = content_blocks

    def create(self, **kwargs):  # noqa: ANN003
        return SimpleNamespace(content=[SimpleNamespace(text=block) for block in self._content_blocks])


class _StaticAnthropicClient:
    def __init__(self, content_blocks: list[str]) -> None:
        self.messages = _StaticAnthropicMessages(content_blocks)


@pytest.mark.parametrize("enable_ai", [False, True])
def test_runtime_intelligence_refresh_registers_tier1_sources_and_ingests_ap_news(
    postgres_test_schema,
    enable_ai: bool,
) -> None:
    run_migrations()
    html = """
    <html>
      <body>
        <a href="https://apnews.com/article/polymarket-runtime-news-1">Federal Reserve signals policy path after inflation data surprise</a>
        <a href="https://apnews.com/article/polymarket-runtime-news-2">New sanctions package raises geopolitical risk for energy markets</a>
      </body>
    </html>
    """
    settings = Settings(
        intelligence_news_enabled=True,
        intelligence_ai_enabled=enable_ai,
        intelligence_refresh_interval_seconds=60,
        intelligence_news_max_items_per_source=5,
    )
    service = RuntimeIntelligenceService(
        settings=settings,
        http_client=_FakeHttpClient(html),
        cognition_client=_FakeAnthropicClient() if enable_ai else None,
    )

    result = service.refresh(cycle_id="runtime-cycle-1", scored_markets=[])

    assert result is not None
    assert len(result.news_run_ids) == 1
    if enable_ai:
        assert result.ai_digest_alert_id is not None
    else:
        assert result.ai_digest_alert_id is None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        sources = conn.execute(
            """
            SELECT source_key, is_enabled, metadata_json
            FROM intelligence_sources
            ORDER BY source_key ASC
            """
        ).fetchall()
        runs = conn.execute(
            """
            SELECT run_type, status
            FROM intelligence_ingestion_runs
            ORDER BY started_at ASC, id ASC
            """
        ).fetchall()
        normalized = conn.execute(
            """
            SELECT normalized_title, status, canonical_url
            FROM external_events_normalized
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
        alerts = conn.execute(
            """
            SELECT event_class, payload_json
            FROM alert_events
            WHERE event_class = 'AI_INTELLIGENCE_DIGEST'
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()

    source_by_key = {row["source_key"]: row for row in sources}
    assert source_by_key["ap_top_news"]["is_enabled"] is True
    assert source_by_key["reuters_world"]["is_enabled"] is False
    assert source_by_key["bloomberg_markets"]["is_enabled"] is False
    assert source_by_key["ft_news_feed"]["is_enabled"] is False
    assert source_by_key["reuters_world"]["metadata_json"]["integration_status"] == "disabled_access_blocked"
    assert len(runs) == 1
    assert runs[0]["run_type"] == "SITE_FETCH"
    assert runs[0]["status"] == "COMPLETED"
    assert len(normalized) == 2
    assert all(row["status"] == "READY" for row in normalized)
    assert all(str(row["canonical_url"]).startswith("https://apnews.com/article/") for row in normalized)
    if enable_ai:
        assert len(alerts) == 1
        assert alerts[0]["payload_json"]["purpose"] == "runtime_news_digest"
    else:
        assert alerts == []


def test_runtime_intelligence_ai_digest_falls_back_for_markdown_wrapped_json(postgres_test_schema) -> None:
    run_migrations()
    html = """
    <html>
      <body>
        <a href="https://apnews.com/article/polymarket-runtime-news-1">Federal Reserve signals policy path after inflation data surprise</a>
      </body>
    </html>
    """
    client = _StaticAnthropicClient(
        [
            "```json\n"
            "{\"summary_text\":\"Wrapped JSON digest\",\"relevance_level\":\"high\","
            "\"contradiction_risk\":\"low\",\"operator_takeaway\":\"Keep watch.\","
            "\"watch_items\":[\"Track follow-up coverage.\"]}\n```"
        ]
    )
    service = RuntimeIntelligenceService(
        settings=Settings(
            intelligence_news_enabled=True,
            intelligence_ai_enabled=True,
            intelligence_refresh_interval_seconds=60,
            intelligence_news_max_items_per_source=5,
        ),
        http_client=_FakeHttpClient(html),
        cognition_client=client,
    )

    result = service.refresh(cycle_id="runtime-cycle-markdown", scored_markets=[])

    assert result is not None
    assert result.ai_digest_alert_id is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        alert = conn.execute(
            """
            SELECT payload_json
            FROM alert_events
            WHERE id = %s
            LIMIT 1
            """,
            (result.ai_digest_alert_id,),
        ).fetchone()

    assert alert is not None
    assert alert["payload_json"]["fallback_used"] is False
    assert alert["payload_json"]["digest"]["summary_text"] == "Wrapped JSON digest"


def test_runtime_intelligence_ai_digest_falls_back_for_plain_text_without_crashing(postgres_test_schema) -> None:
    run_migrations()
    html = """
    <html>
      <body>
        <a href="https://apnews.com/article/polymarket-runtime-news-1">Federal Reserve signals policy path after inflation data surprise</a>
      </body>
    </html>
    """
    service = RuntimeIntelligenceService(
        settings=Settings(
            intelligence_news_enabled=True,
            intelligence_ai_enabled=True,
            intelligence_refresh_interval_seconds=60,
            intelligence_news_max_items_per_source=5,
        ),
        http_client=_FakeHttpClient(html),
        cognition_client=_StaticAnthropicClient(
            [
                "Material macro update: the headline matters, but I am not returning JSON.",
                "Watch inflation and rate-path follow-through.",
            ]
        ),
    )

    result = service.refresh(cycle_id="runtime-cycle-plain-text", scored_markets=[])

    assert result is not None
    assert result.ai_digest_alert_id is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        alert = conn.execute(
            """
            SELECT body_text, payload_json
            FROM alert_events
            WHERE id = %s
            LIMIT 1
            """,
            (result.ai_digest_alert_id,),
        ).fetchone()

    assert alert is not None
    assert alert["payload_json"]["fallback_used"] is True
    assert alert["payload_json"]["fallback_reason"] == "plain_text"
    assert "AI digest fallback used:" in alert["body_text"]

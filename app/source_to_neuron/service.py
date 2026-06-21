from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from app.ai_brain.redaction import redact_dict, redact_text
from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.neural_bus.repository import table_exists
from app.neural_bus.service import NeuralEventBusService
from app.neural_bus.types import NeuralEventType
from app.news_neuron.collector import NewsCollector
from app.news_neuron.contracts import NewsSource, NewsSourceType
from app.news_neuron.service import NewsNeuronService
from app.news_neuron.source_registry import NewsSourceRegistry
from app.repositories.ai_request_repository import AIRequestRepository
from app.repositories.news_normalized_event_repository import NewsNormalizedEventRepository
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository
from app.repositories.source_status_repository import SourceStatusRepository
from app.repositories.whale_event_repository import WhaleEventRepository
from app.services.ai_context_router import AIContextRouterService
from app.services.brain_dialogue import BrainDialogueService
from app.services.source_status import DEFAULT_CLOB_BASE_URL, DEFAULT_DATA_API_BASE_URL, SourceStatusService
from app.services.system_power import SystemPowerService
from app.whale_neuron.contracts import (
    WhaleActionType,
    WhaleEvent,
    WhaleEventClassification,
    WhaleSide,
    WhaleSourceType,
)


DEFAULT_NEWSAPI_URL = "https://newsapi.org/v2/everything"
DEFAULT_GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
SOURCE_COMPONENTS = (
    "News Neuron",
    "Market Neuron",
    "Orderbook Neuron",
    "Liquidity Neuron",
    "Whale Neuron",
    "AI Context Brain",
)


class SourceToNeuronBlocked(RuntimeError):
    pass


class SourceHttpClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, int]:
        ...

    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> tuple[str, int]:
        ...

    def post_json(
        self,
        url: str,
        *,
        json_payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[Any, int]:
        ...


class HttpxSourceClient:
    def __init__(self, *, timeout_seconds: float = 10.0, user_agent: str = "POLYBOT-source-to-neuron/3.9") -> None:
        self._timeout_seconds = timeout_seconds
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, int]:
        started = time.perf_counter()
        with httpx.Client(timeout=self._timeout_seconds, follow_redirects=True, headers=self._merge(headers)) as client:
            response = client.get(url, params=params)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms

    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> tuple[str, int]:
        started = time.perf_counter()
        text_headers = self._merge(headers)
        text_headers["Accept"] = "application/rss+xml, application/xml, text/xml, text/html, */*"
        with httpx.Client(timeout=self._timeout_seconds, follow_redirects=True, headers=text_headers) as client:
            response = client.get(url)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.text, latency_ms

    def post_json(
        self,
        url: str,
        *,
        json_payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[Any, int]:
        started = time.perf_counter()
        timeout = timeout_seconds if timeout_seconds is not None else self._timeout_seconds
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=self._merge(headers)) as client:
            response = client.post(url, json=json_payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms

    def _merge(self, headers: dict[str, str] | None) -> dict[str, str]:
        merged = dict(self._headers)
        if headers:
            merged.update(headers)
        return merged


class SourceToNeuronIngestionService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        neural_bus: NeuralEventBusService | None = None,
        http_client: SourceHttpClient | None = None,
        source_status: SourceStatusService | None = None,
        news_service: NewsNeuronService | None = None,
        news_registry: NewsSourceRegistry | None = None,
        news_collector: NewsCollector | None = None,
        ai_context_router: AIContextRouterService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._bus = neural_bus or NeuralEventBusService(connection_factory=self._factory, system_power=self._system_power)
        self._http = http_client or HttpxSourceClient()
        self._source_status = source_status or SourceStatusService(connection_factory=self._factory)
        self._news_service = news_service or NewsNeuronService(connection_factory=self._factory)
        self._news_registry = news_registry or NewsSourceRegistry(connection_factory=self._factory)
        self._news_collector = news_collector or NewsCollector(
            connection_factory=self._factory,
            fetch_text=lambda url: self._http.get_text(url)[0],
        )
        self._snapshotter = OrderbookSnapshotter(connection_factory=self._factory)
        self._orderbooks = OrderbookSnapshotRepository()
        self._normalized_news = NewsNormalizedEventRepository()
        self._whales = WhaleEventRepository()
        self._ai_requests = AIRequestRepository()
        self._source_status_repo = SourceStatusRepository()
        self._ai_context_router = ai_context_router or AIContextRouterService(
            connection_factory=self._factory,
            system_power=self._system_power,
            neural_bus=self._bus,
            http_client=self._http,  # type: ignore[arg-type]
        )

    def run_once(
        self,
        *,
        limit_per_source: int = 1,
        include_cloud_ai_generation: bool = True,
        include_ollama_generation: bool = True,
    ) -> dict[str, Any]:
        power = self._system_power.get_power_state()
        if str(power.get("power") or "OFF").upper() != "ON" or not power.get("runtime_work_allowed"):
            return {
                "mock_data": False,
                "status": "SYSTEM_POWER_OFF",
                "blocked": True,
                "events_created": 0,
                "errors": [],
                "message": "Source-to-neuron ingestion is blocked while SYSTEM is OFF.",
            }
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DB_UNAVAILABLE", "blocked": True, "events_created": 0, "errors": []}

        run_id = f"source_to_neuron_{uuid4().hex}"
        before = self._safety_counts()
        result: dict[str, Any] = {
            "mock_data": False,
            "status": "OK",
            "run_id": run_id,
            "blocked": False,
            "providers_checked": [],
            "provider_status": {},
            "events_created": 0,
            "events_by_type": {},
            "sessions_updated": 0,
            "awareness_domains_updated": 0,
            "brain_opinions_created": 0,
            "coordinator_decisions_created": 0,
            "latest_items": [],
            "errors": [],
            "missing_providers": [],
            "degraded_providers": [],
            "whale_status": "NOT_CHECKED",
            "secrets_exposed": False,
        }

        self._refresh_source_status(result)
        gamma_events = self._ingest_gamma(run_id=run_id, limit=limit_per_source, result=result)
        self._ingest_rss(run_id=run_id, limit=limit_per_source, result=result)
        self._ingest_newsapi(run_id=run_id, limit=limit_per_source, result=result)
        self._ingest_clob_orderbook(run_id=run_id, gamma_events=gamma_events, limit=limit_per_source, result=result)
        self._ingest_clob_activity(run_id=run_id, limit=limit_per_source, result=result)
        self._ingest_ai_context(
            run_id=run_id,
            enabled=include_ollama_generation,
            include_cloud_fallback=include_cloud_ai_generation,
            result=result,
        )
        if not include_ollama_generation:
            self._record_cloud_ai_status(run_id=run_id, include_generation=False, result=result)
        self._ingest_position_pnl(run_id=run_id, result=result)

        try:
            BrainDialogueService(connection_factory=self._factory, system_power=self._system_power).materialize_recent(limit_per_source=50)
        except Exception as exc:
            result["errors"].append(_error("dialogue", exc))

        after = self._safety_counts()
        result["safety_before"] = before
        result["safety_after"] = after
        result["trading_mutation_detected"] = before != after
        result["events_by_type"] = dict(Counter(item["event_type"] for item in result["latest_items"] if item.get("event_type")))
        result["events_created"] = int(sum(result["events_by_type"].values()))
        self._attach_downstream_counts(result)
        return _json_safe(result)

    def dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard("DB_UNAVAILABLE")
        with self._factory.connect() as conn:
            if not table_exists(conn, "neural_events"):
                return _empty_dashboard("MISSING_TABLES")
            latest = conn.execute(
                """
                SELECT *
                FROM neural_events
                WHERE source_component = ANY(%s)
                   OR metadata_json->>'source_to_neuron' = 'true'
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (list(SOURCE_COMPONENTS), limit),
            ).fetchall()
            by_type = conn.execute(
                """
                SELECT event_type, COUNT(*) AS count
                FROM neural_events
                WHERE source_component = ANY(%s)
                   OR metadata_json->>'source_to_neuron' = 'true'
                GROUP BY event_type
                ORDER BY event_type
                """,
                (list(SOURCE_COMPONENTS),),
            ).fetchall()
            source_rows = conn.execute("SELECT * FROM source_status ORDER BY source_name").fetchall() if table_exists(conn, "source_status") else []
            sessions = _count_table(conn, "mesh_session_events", "linked_at >= now() - interval '1 day'")
            awareness = _count_table(conn, "mesh_awareness_sources", "linked_at >= now() - interval '1 day'")
            opinions = _count_table(conn, "mesh_brain_opinions", "created_at >= now() - interval '1 day'")
            decisions = _count_table(conn, "mesh_coordinator_decisions", "created_at >= now() - interval '1 day'")
        provider_status = {str(row["source_name"]): _json_safe(dict(row)) for row in source_rows}
        degraded = [
            name
            for name, row in provider_status.items()
            if str(row.get("runtime_status") or "").upper() in {"DEGRADED", "MISSING", "DISABLED"}
        ]
        return {
            "mock_data": False,
            "status": "OK",
            "generated_at": datetime.now(UTC).isoformat(),
            "provider_status": provider_status,
            "source_status": provider_status,
            "neuron_status": _neuron_status(latest),
            "events_created": {str(row["event_type"]): int(row["count"] or 0) for row in by_type},
            "sessions_updated": sessions,
            "awareness_domains_updated": awareness,
            "brain_opinions_created": opinions,
            "coordinator_decisions_created": decisions,
            "latest_items": [_json_safe(dict(row)) for row in latest],
            "errors": [row for row in provider_status.values() if row.get("last_error_at")],
            "missing_providers": _missing_providers(),
            "degraded_providers": degraded,
            "secrets_exposed": False,
        }

    def _refresh_source_status(self, result: dict[str, Any]) -> None:
        try:
            status = self._source_status.get_dashboard_source_status(persist=True)
            result["provider_status"] = {str(item["source_name"]): item for item in status.get("sources") or []}
            result["providers_checked"] = list(result["provider_status"].keys())
            result["degraded_providers"] = list(status.get("degraded_sources") or [])
        except Exception as exc:
            result["errors"].append(_error("source_status", exc))

    def _ingest_rss(self, *, run_id: str, limit: int, result: dict[str, Any]) -> None:
        urls = _csv_env("NEWS_RSS_FEEDS")
        if not urls:
            result["missing_providers"].append("NEWS_RSS_FEEDS")
            return
        for url in urls[: max(limit, 1)]:
            source_id = f"rss_env_{_digest(url)[:16]}"
            try:
                self._news_registry.register_source(
                    NewsSource(
                        source_id=source_id,
                        name=f"RSS Feed {source_id[-8:]}",
                        source_type=NewsSourceType.RSS,
                        category="general",
                        url=url,
                        feed_url=url,
                        enabled=True,
                        reliability_score=0.55,
                        metadata={"source_to_neuron": True, "configured_from_env": True},
                    )
                )
                raw_events = self._news_collector.collect_from_source(source_id, limit=limit)
                for raw in raw_events[:limit]:
                    summary = self._news_service.process_raw_event(raw, analyze_with_ai=False)
                    self._publish_news(summary, run_id=run_id, provider="rss", result=result)
                self._record_provider_status(
                    source_name="rss_source_to_neuron",
                    source_type="news",
                    configured=True,
                    key_required=False,
                    key_present=False,
                    endpoint_url=url,
                    runtime_status="ACTIVE" if raw_events else "DEGRADED",
                    freshness_status="FRESH" if raw_events else "STALE",
                    notes="RSS feed item ingested through News Neuron." if raw_events else "RSS feed returned no source-to-neuron items.",
                    details={"source_id": source_id, "item_count": len(raw_events)},
                )
            except Exception as exc:
                result["errors"].append(_error(f"rss:{_safe_url_label(url)}", exc))
                self._record_provider_status(
                    source_name="rss_source_to_neuron",
                    source_type="news",
                    configured=True,
                    key_required=False,
                    key_present=False,
                    endpoint_url=url,
                    runtime_status="DEGRADED",
                    freshness_status="STALE",
                    notes=_redact_error_summary(exc),
                    details={"source_id": source_id},
                )

    def _ingest_newsapi(self, *, run_id: str, limit: int, result: dict[str, Any]) -> None:
        key = os.getenv("NEWS_API_KEY")
        if not key:
            result["missing_providers"].append("NEWS_API_KEY")
            return
        try:
            payload, latency_ms = self._http.get_json(
                os.getenv("NEWSAPI_BASE_URL") or DEFAULT_NEWSAPI_URL,
                params={
                    "q": "polymarket OR prediction markets",
                    "pageSize": max(1, min(limit, 5)),
                    "sortBy": "publishedAt",
                    "language": "en",
                    "apiKey": key,
                },
            )
            articles = payload.get("articles", []) if isinstance(payload, dict) else []
            self._news_registry.register_source(
                NewsSource(
                    source_id="newsapi_v3",
                    name="NewsAPI",
                    source_type=NewsSourceType.API,
                    category="general",
                    url="https://newsapi.org",
                    enabled=True,
                    reliability_score=0.60,
                    metadata={"source_to_neuron": True, "latency_ms": latency_ms},
                )
            )
            for article in articles[:limit]:
                summary = self._news_service.process_manual_news(
                    {
                        "source_id": "newsapi_v3",
                        "external_id": article.get("url") or article.get("title"),
                        "url": article.get("url"),
                        "title": article.get("title") or "",
                        "summary": article.get("description"),
                        "body_text": article.get("content"),
                        "author": article.get("author"),
                        "published_at": article.get("publishedAt"),
                        "language": "en",
                        "raw_payload": redact_dict(article),
                    },
                    analyze_with_ai=False,
                )
                self._publish_news(summary, run_id=run_id, provider="newsapi", result=result)
            self._record_provider_status(
                source_name="newsapi_source_to_neuron",
                source_type="news",
                configured=True,
                key_required=True,
                key_present=True,
                key_name="NEWS_API_KEY",
                endpoint_url=os.getenv("NEWSAPI_BASE_URL") or DEFAULT_NEWSAPI_URL,
                runtime_status="ACTIVE" if articles else "DEGRADED",
                freshness_status="FRESH" if articles else "STALE",
                latency_ms=latency_ms,
                notes="NewsAPI articles ingested through News Neuron." if articles else "NewsAPI returned no source-to-neuron articles.",
                details={"article_count": len(articles), "events_attempted": min(len(articles), limit)},
            )
        except Exception as exc:
            result["degraded_providers"].append("newsapi")
            result["errors"].append(_error("newsapi", exc))
            self._record_provider_status(
                source_name="newsapi_source_to_neuron",
                source_type="news",
                configured=True,
                key_required=True,
                key_present=True,
                key_name="NEWS_API_KEY",
                endpoint_url=os.getenv("NEWSAPI_BASE_URL") or DEFAULT_NEWSAPI_URL,
                runtime_status="DEGRADED",
                freshness_status="STALE",
                notes=_redact_error_summary(exc),
                details={},
            )

    def _publish_news(self, summary: dict[str, Any], *, run_id: str, provider: str, result: dict[str, Any]) -> None:
        news_event_id = summary.get("normalized_event_id")
        if not news_event_id:
            return
        with self._factory.connect() as conn:
            row = self._normalized_news.get_event(conn, str(news_event_id))
        payload = _json_safe(dict(row or {}))
        links = summary.get("links") or []
        market_id = str(links[0]["market_id"]) if links else None
        event = self._publish_event(
            NeuralEventType.NEWS_DETECTED,
            source_component="News Neuron",
            source_type="neuron",
            market_id=market_id,
            payload={
                **payload,
                "provider": provider,
                "source_refs": [{"source_table": "news_normalized_events", "source_record_id": news_event_id}],
            },
            source_table="news_normalized_events",
            source_record_id=str(news_event_id),
            correlation_id=run_id,
            metadata={"source_to_neuron": True, "provider": provider},
        )
        if event["created"]:
            result["latest_items"].append(_event_item(event["row"], provider=provider, neuron="News Neuron"))

    def _ingest_gamma(self, *, run_id: str, limit: int, result: dict[str, Any]) -> list[dict[str, Any]]:
        endpoint = f"{(os.getenv('POLYBOT_GAMMA_BASE_URL') or DEFAULT_GAMMA_BASE_URL).rstrip('/')}/events"
        try:
            payload, latency_ms = self._http.get_json(
                endpoint,
                params={"active": "true", "closed": "false", "limit": max(1, min(limit, 10)), "order": "volume_24hr", "ascending": "false"},
            )
            events = payload if isinstance(payload, list) else payload.get("events", []) if isinstance(payload, dict) else []
            if not events:
                return []
            market = _first_gamma_market(events)
            market_id = str(market.get("id") or market.get("conditionId") or "") if market else None
            event = self._publish_event(
                NeuralEventType.MARKET_REPRICING,
                source_component="Market Neuron",
                source_type="market",
                market_id=market_id,
                payload={
                    "provider": "polymarket_gamma",
                    "event_count": len(events),
                    "sample_market_id": market_id,
                    "sample_question": market.get("question") if market else None,
                    "latency_ms": latency_ms,
                    "source_refs": [{"source_table": "source_status", "source_record_id": "polymarket_gamma"}],
                },
                source_table="source_status",
                source_record_id=f"polymarket_gamma:{run_id}",
                correlation_id=run_id,
                metadata={"source_to_neuron": True, "provider": "polymarket_gamma"},
            )
            if event["created"]:
                result["latest_items"].append(_event_item(event["row"], provider="polymarket_gamma", neuron="Market Neuron"))
            return events
        except Exception as exc:
            result["degraded_providers"].append("polymarket_gamma")
            result["errors"].append(_error("polymarket_gamma", exc))
            return []

    def _ingest_clob_orderbook(self, *, run_id: str, gamma_events: list[dict[str, Any]], limit: int, result: dict[str, Any]) -> None:
        candidate = _first_token_candidate(gamma_events)
        if not candidate:
            result["degraded_providers"].append("polymarket_clob_orderbook")
            result["errors"].append({"source": "polymarket_clob_orderbook", "error_type": "NO_TOKEN", "error_summary": "No Gamma token candidate available."})
            return
        token_id, market_id, side = candidate
        endpoint = f"{(os.getenv('POLYMARKET_CLOB_HOST') or DEFAULT_CLOB_BASE_URL).rstrip('/')}/book"
        try:
            raw, latency_ms = self._http.get_json(endpoint, params={"token_id": token_id})
            collected_at = datetime.now(UTC)
            snapshot = self._snapshotter.normalize_orderbook(
                raw if isinstance(raw, dict) else {},
                market_id=market_id or "__unknown_market__",
                token_id=token_id,
                side=side,
                source="polymarket_clob_source_to_neuron",
                correlation_id=run_id,
                raw_payload_ref=f"clob:/book:{token_id}:{collected_at.isoformat()}",
                collected_at=collected_at,
                freshness_window_seconds=120,
            )
            with self._factory.connect() as conn, conn.transaction():
                self._orderbooks.append_snapshot(conn, snapshot)
            payload = {
                **asdict(snapshot),
                "latency_ms": latency_ms,
                "provider": "polymarket_clob",
                "source_refs": [{"source_table": "orderbook_snapshots", "source_record_id": snapshot.orderbook_snapshot_id}],
            }
            orderbook = self._publish_event(
                NeuralEventType.ORDERBOOK_REFRESHED,
                source_component="Orderbook Neuron",
                source_type="neuron",
                market_id=snapshot.market_id,
                payload=payload,
                source_table="orderbook_snapshots",
                source_record_id=snapshot.orderbook_snapshot_id,
                correlation_id=run_id,
                metadata={"source_to_neuron": True, "provider": "polymarket_clob", "token_id": token_id},
            )
            if orderbook["created"]:
                result["latest_items"].append(_event_item(orderbook["row"], provider="polymarket_clob", neuron="Orderbook Neuron"))
            for event_type, component in (
                (NeuralEventType.SPREAD_CHANGED, "Liquidity Neuron"),
                (NeuralEventType.LIQUIDITY_CHANGED, "Liquidity Neuron"),
            ):
                event = self._publish_event(
                    event_type,
                    source_component=component,
                    source_type="neuron",
                    market_id=snapshot.market_id,
                    payload=payload,
                    source_table="orderbook_snapshots",
                    source_record_id=f"{snapshot.orderbook_snapshot_id}:{event_type.value}",
                    correlation_id=run_id,
                    metadata={"source_to_neuron": True, "provider": "polymarket_clob", "token_id": token_id},
                )
                if event["created"]:
                    result["latest_items"].append(_event_item(event["row"], provider="polymarket_clob", neuron=component))
        except Exception as exc:
            result["degraded_providers"].append("polymarket_clob_orderbook")
            result["errors"].append(_error("polymarket_clob_orderbook", exc))

    def _ingest_clob_activity(self, *, run_id: str, limit: int, result: dict[str, Any]) -> None:
        endpoint = f"{(os.getenv('POLYBOT_POLYMARKET_DATA_API_BASE_URL') or DEFAULT_DATA_API_BASE_URL).rstrip('/')}/trades"
        threshold = _float_env("SOURCE_TO_NEURON_WHALE_USD_THRESHOLD", 1000.0)
        try:
            payload, latency_ms = self._http.get_json(endpoint, params={"limit": max(1, min(limit * 20, 100)), "offset": 0})
            trades = payload if isinstance(payload, list) else payload.get("trades", []) if isinstance(payload, dict) else []
            whale = next((trade for trade in trades if _trade_notional(trade) >= threshold), None)
            if not whale:
                result["whale_status"] = "NO_WHALE_EVENT_FOUND"
                return
            event_model = _whale_event_from_trade(whale, threshold=threshold, latency_ms=latency_ms)
            with self._factory.connect() as conn, conn.transaction():
                row, created = self._whales.insert_event(conn, event_model)
            if not created:
                return
            event = self._publish_event(
                NeuralEventType.WHALE_DETECTED,
                source_component="Whale Neuron",
                source_type="neuron",
                market_id=row.get("market_id") if row.get("market_id") != "__none__" else None,
                payload={
                    **_json_safe(dict(row)),
                    "provider": "polymarket_activity_readonly",
                    "threshold_usd": threshold,
                    "source_refs": [{"source_table": "whale_events", "source_record_id": row.get("whale_event_id")}],
                },
                source_table="whale_events",
                source_record_id=str(row.get("whale_event_id") or row.get("id")),
                correlation_id=run_id,
                metadata={"source_to_neuron": True, "provider": "polymarket_activity_readonly"},
            )
            if event["created"]:
                result["whale_status"] = "WHALE_DETECTED"
                result["latest_items"].append(_event_item(event["row"], provider="polymarket_activity_readonly", neuron="Whale Neuron"))
        except Exception as exc:
            result["degraded_providers"].append("polymarket_activity_readonly")
            result["errors"].append(_error("polymarket_activity_readonly", exc))

    def _ingest_ollama(self, *, run_id: str, enabled: bool, result: dict[str, Any]) -> None:
        base_url = os.getenv("OLLAMA_BASE_URL")
        models = _ollama_generation_models()
        if not base_url or not models:
            result["missing_providers"].append("OLLAMA_BASE_URL_OR_MODEL")
            return
        if not enabled:
            result["provider_status"]["ollama_context_generation"] = {"status": "DISABLED_BY_POLICY"}
            return
        attempts: list[dict[str, Any]] = []
        for endpoint_base in _ollama_bases(base_url):
            for model in models:
                for prompt_payload in _ollama_prompt_payloads(model):
                    try:
                        attempts.append({"endpoint": endpoint_base, "model": model, "prompt_mode": prompt_payload["prompt_mode"]})
                        prompt = str(prompt_payload["prompt"])
                        payload, latency_ms = self._http.post_json(
                            f"{endpoint_base}/api/generate",
                            json_payload=prompt_payload["payload"],
                        )
                        text = str(payload.get("response") if isinstance(payload, dict) else payload)
                        structured = _parse_ai_response(text)
                        ai_request_id = f"ai_req_source_to_neuron_{_digest(run_id + model)[:24]}"
                        ai_response_id = f"ai_resp_source_to_neuron_{_digest(run_id + text)[:24]}"
                        with self._factory.connect() as conn, conn.transaction():
                            self._ai_requests.insert_request(
                                conn,
                                ai_request_id=ai_request_id,
                                request_hash=_digest(prompt),
                                correlation_id=run_id,
                                source_service="AI Context Brain",
                                task_type="CONTEXT_SUMMARY",
                                model_route="LOCAL_FAST",
                                selected_model=model,
                                status="PENDING",
                                budget_allowed=True,
                                metadata={"source_to_neuron": True, "provider": "ollama", "endpoint": endpoint_base, "prompt_mode": prompt_payload["prompt_mode"]},
                            )
                            self._ai_requests.finish_request(
                                conn,
                                ai_request_id=ai_request_id,
                                status="LOCAL_COMPLETED",
                                latency_ms=latency_ms,
                                input_tokens=max(1, len(prompt) // 4),
                                output_tokens=max(1, len(text) // 4),
                            )
                            self._ai_requests.insert_response(
                                conn,
                                ai_response_id=ai_response_id,
                                ai_request_id=ai_request_id,
                                response_hash=_digest(text),
                                model_name=model,
                                task_type="CONTEXT_SUMMARY",
                                structured_output=structured,
                                raw_output_redacted=redact_text(text),
                                confidence=float(structured.get("confidence") or 0.5),
                                recommended_action="OBSERVE",
                                risk_flags=[],
                                metadata={"source_to_neuron": True, "provider": "ollama", "prompt_mode": prompt_payload["prompt_mode"]},
                            )
                        event = self._publish_event(
                            NeuralEventType.AI_CONTEXT_UPDATED,
                            source_component="AI Context Brain",
                            source_type="brain",
                            payload={
                                "provider": "ollama",
                                "model": model,
                                "status": "COMPLETED",
                                "summary": structured.get("summary"),
                                "confidence": structured.get("confidence", 0.5),
                                "prompt_mode": prompt_payload["prompt_mode"],
                                "source_refs": [{"source_table": "ai_responses", "source_record_id": ai_response_id}],
                            },
                            source_table="ai_responses",
                            source_record_id=ai_response_id,
                            correlation_id=run_id,
                            metadata={"source_to_neuron": True, "provider": "ollama", "generation": "local_timeout_safe_context"},
                        )
                        if event["created"]:
                            result["latest_items"].append(_event_item(event["row"], provider="ollama", neuron="AI Context Brain"))
                        self._record_provider_status(
                            source_name="ollama_context_generation",
                            source_type="ai_context",
                            configured=True,
                            key_required=False,
                            key_present=False,
                            endpoint_url=f"{endpoint_base}/api/generate",
                            runtime_status="ACTIVE",
                            freshness_status="FRESH",
                            latency_ms=latency_ms,
                            notes="Ollama local context generated with bounded timeout-safe prompt policy.",
                            details={"model": model, "event_created": bool(event["created"]), "prompt_mode": prompt_payload["prompt_mode"], "attempts": attempts},
                        )
                        return
                    except Exception as exc:
                        last = exc
                        continue
        result["degraded_providers"].append("ollama")
        error = last if "last" in locals() else RuntimeError("Ollama context failed")
        result["errors"].append(_error("ollama", error))
        self._record_provider_status(
            source_name="ollama_context_generation",
            source_type="ai_context",
            configured=True,
            key_required=False,
            key_present=False,
            endpoint_url="ollama /api/generate",
            runtime_status="DEGRADED",
            freshness_status="STALE",
            notes=_redact_error_summary(error),
            details={"models": models, "attempts": attempts, "fallback_policy": "bounded_prompt_fast_model_first"},
        )

    def _ingest_ai_context(
        self,
        *,
        run_id: str,
        enabled: bool,
        include_cloud_fallback: bool,
        result: dict[str, Any],
    ) -> None:
        prompt = (
            "Return source-backed AI context for this bounded POLYBOT source-to-neuron run. "
            "Use only the fact that provider, news, orderbook, whale, and PnL evidence may have been collected in this run. "
            "Do not recommend a trade. Do not create intents, orders, fills, positions, or PnL."
        )
        try:
            routed = self._ai_context_router.route_context(
                prompt=prompt,
                source_component="AI Context Brain",
                correlation_id=run_id,
                source_to_neuron=True,
                enabled=enabled,
                cloud_fallback_enabled=include_cloud_fallback,
                metadata={"source_to_neuron": True, "bounded_runtime_context": True},
            )
            result["ai_context_router"] = routed
            result["provider_status"]["ai_context_router"] = {
                "runtime_status": "ACTIVE" if routed.get("status") == "OK" else "DEGRADED",
                "selected_provider": routed.get("selected_provider"),
                "final_reason": routed.get("final_reason"),
                "secret_value_exposed": False,
            }
            if routed.get("status") == "OK" and routed.get("event"):
                result["latest_items"].append(
                    _event_item(
                        routed["event"],
                        provider=str(routed.get("selected_provider") or "ai_context_router"),
                        neuron="AI Context Brain",
                    )
                )
            elif routed.get("status") == "AI_CONTEXT_UNAVAILABLE":
                result["degraded_providers"].append("ai_context_router")
                if routed.get("event"):
                    result["latest_items"].append(_event_item(routed["event"], provider="ai_context_router", neuron="AI Context Brain"))
            elif routed.get("status") in {"DISABLED_BY_POLICY", "SYSTEM_POWER_OFF"}:
                result["provider_status"]["ai_context_router"]["runtime_status"] = "DISABLED"
        except Exception as exc:
            result["degraded_providers"].append("ai_context_router")
            result["errors"].append(_error("ai_context_router", exc))

    def _record_cloud_ai_status(self, *, run_id: str, include_generation: bool, result: dict[str, Any]) -> None:
        for env_var, provider in (("OPENAI_API_KEY", "openai"), ("ANTHROPIC_API_KEY", "anthropic")):
            if os.getenv(env_var):
                result["provider_status"][f"{provider}_api"] = {
                    "runtime_status": "READY_AUTH_ONLY" if not include_generation else "GENERATION_DISABLED_BY_DEFAULT",
                    "generation_created_event": False,
                    "secret_value_exposed": False,
                }
            else:
                result["missing_providers"].append(env_var)

    def _ingest_position_pnl(self, *, run_id: str, result: dict[str, Any]) -> None:
        with self._factory.connect() as conn:
            if not table_exists(conn, "paper_trade_ledger"):
                return
            rows = conn.execute(
                """
                SELECT *
                FROM paper_trade_ledger
                WHERE realized_pnl IS NOT NULL OR unrealized_pnl IS NOT NULL
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ).fetchall()
        for row in rows:
            event = self._publish_event(
                NeuralEventType.PNL_CHANGED,
                source_component="PnL Neuron",
                source_type="paper",
                market_id=row.get("market_id"),
                position_id=str(row.get("position_id")) if row.get("position_id") else None,
                payload={**_json_safe(dict(row)), "source_refs": [{"source_table": "paper_trade_ledger", "source_record_id": row.get("ledger_id") or row.get("id")}]},
                source_table="paper_trade_ledger",
                source_record_id=str(row.get("ledger_id") or row.get("id")),
                correlation_id=run_id,
                metadata={"source_to_neuron": True, "provider": "internal_paper_pnl"},
            )
            if event["created"]:
                result["latest_items"].append(_event_item(event["row"], provider="internal_paper_pnl", neuron="PnL Neuron"))

    def _publish_event(self, event_type: NeuralEventType, **kwargs: Any) -> dict[str, Any]:
        before = self._count("neural_events")
        row = self._bus.publish_event(event_type, **kwargs)
        after = self._count("neural_events")
        return {"created": after > before, "row": row}

    def _count(self, table: str) -> int:
        with self._factory.connect() as conn:
            if not table_exists(conn, table):
                return 0
            return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)

    def _record_provider_status(
        self,
        *,
        source_name: str,
        source_type: str,
        configured: bool,
        key_required: bool,
        key_present: bool,
        endpoint_url: str | None,
        runtime_status: str,
        freshness_status: str,
        notes: str,
        details: dict[str, Any],
        key_name: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        if not self._factory.enabled:
            return
        try:
            with self._factory.connect() as conn, conn.transaction():
                if not table_exists(conn, "source_status"):
                    return
                self._source_status_repo.upsert_status(
                    conn,
                    {
                        "source_name": source_name,
                        "source_type": source_type,
                        "configured": configured,
                        "key_required": key_required,
                        "key_present": key_present,
                        "key_name": key_name,
                        "endpoint_url": endpoint_url,
                        "runtime_status": runtime_status,
                        "freshness_status": freshness_status,
                        "latency_ms": latency_ms,
                        "details_json": details,
                        "notes": notes,
                    },
                )
        except Exception:
            return

    def _safety_counts(self) -> dict[str, Any]:
        with self._factory.connect() as conn:
            output = {table: _count_table(conn, table) for table in _safety_tables()}
            if table_exists(conn, "paper_accounts"):
                row = conn.execute(
                    """
                    SELECT current_balance, available_balance, locked_balance, open_exposure
                    FROM paper_accounts
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """
                ).fetchone()
                output["paper_account_balances"] = _json_safe(dict(row)) if row else {}
            return output

    def _attach_downstream_counts(self, result: dict[str, Any]) -> None:
        with self._factory.connect() as conn:
            result["sessions_updated"] = _count_table(conn, "mesh_session_events", "linked_at >= now() - interval '10 minutes'")
            result["awareness_domains_updated"] = _count_table(conn, "mesh_awareness_sources", "linked_at >= now() - interval '10 minutes'")
            result["brain_opinions_created"] = _count_table(conn, "mesh_brain_opinions", "created_at >= now() - interval '10 minutes'")
            result["coordinator_decisions_created"] = _count_table(conn, "mesh_coordinator_decisions", "created_at >= now() - interval '10 minutes'")


def _event_item(event: dict[str, Any], *, provider: str, neuron: str) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "market_id": event.get("market_id"),
        "candidate_id": event.get("candidate_id"),
        "position_id": event.get("position_id"),
        "provider": provider,
        "neuron": neuron,
        "source_table": event.get("source_table"),
        "source_record_id": event.get("source_record_id"),
        "created_at": event.get("created_at"),
    }


def _first_gamma_market(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in events:
        markets = event.get("markets")
        if isinstance(markets, list):
            for market in markets:
                if isinstance(market, dict) and _market_is_open_orderbook_candidate(market):
                    return market
        if isinstance(event, dict) and _market_is_open_orderbook_candidate(event):
            return event
    return None


def _first_token_candidate(events: list[dict[str, Any]]) -> tuple[str, str | None, str | None] | None:
    market = _first_gamma_market(events)
    if not market:
        return None
    market_id = str(market.get("id") or market.get("conditionId") or "") or None
    tokens = _token_ids(market.get("clobTokenIds") or market.get("clob_token_ids") or market.get("tokens") or market.get("outcomes"))
    if not tokens:
        return None
    return tokens[0], market_id, "YES"


def _market_is_open_orderbook_candidate(market: dict[str, Any]) -> bool:
    return not (
        market.get("active") is False
        or market.get("closed") is True
        or market.get("acceptingOrders") is False
        or market.get("enableOrderBook") is False
    )


def _token_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            ids = []
            for item in value:
                token = item.get("token_id") or item.get("tokenId") or item.get("id") or item.get("clobTokenId")
                if token:
                    ids.append(str(token))
            return ids
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                return _token_ids(parsed)
            except Exception:
                return []
        return [stripped]
    return []


def _whale_event_from_trade(trade: dict[str, Any], *, threshold: float, latency_ms: int | None) -> WhaleEvent:
    market_id = _first_text(trade, "market", "market_id", "conditionId", "condition_id")
    asset_id = _first_text(trade, "asset", "asset_id", "token_id")
    trader = _first_text(trade, "proxyWallet", "wallet", "wallet_address", "trader", "maker_address")
    side_raw = str(_first_text(trade, "side", "outcome") or "UNKNOWN").upper()
    action_raw = str(_first_text(trade, "action", "type") or "UNKNOWN").upper()
    side = WhaleSide.YES if "YES" in side_raw else WhaleSide.NO if "NO" in side_raw else WhaleSide.UNKNOWN
    action = WhaleActionType.BUY if "BUY" in action_raw else WhaleActionType.SELL if "SELL" in action_raw else WhaleActionType.UNKNOWN
    size = _float(_first_text(trade, "size", "shares", "amount"))
    price = _float(_first_text(trade, "price"))
    notional = _trade_notional(trade)
    trade_ref = _first_text(trade, "transactionHash", "transaction_hash", "tx_hash", "id", "order_id") or _digest(trade)
    return WhaleEvent(
        whale_event_id=f"whale_clob_{_digest(trade_ref)[:24]}",
        source_id="polymarket_activity_readonly",
        whale_id=trader,
        wallet_address=trader,
        market_id=market_id,
        asset_id=asset_id,
        side=side,
        action_type=action,
        size_usd=notional,
        size_shares=size,
        price=price,
        notional=notional,
        tx_hash=trade_ref,
        event_time=_parse_datetime(_first_text(trade, "timestamp", "createdAt", "created_at")) or datetime.now(UTC),
        raw_event={**redact_dict(trade), "latency_ms": latency_ms, "threshold_usd": threshold},
        normalized_event={"notional": notional, "threshold_usd": threshold},
        event_classification=WhaleEventClassification.MARKET_MOVER if notional >= threshold else WhaleEventClassification.NOISE,
        confidence=0.65,
    )


def _trade_notional(trade: dict[str, Any]) -> float:
    for key in ("notional", "notional_usd", "size_usd", "amount_usd", "usdcSize"):
        value = _float(trade.get(key))
        if value > 0:
            return value
    size = _float(_first_text(trade, "size", "shares", "amount"))
    price = _float(_first_text(trade, "price"))
    return round(size * price, 6) if size and price else 0.0


def _parse_ai_response(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return redact_dict(parsed)
    except Exception:
        pass
    return {"status": "OK", "summary": redact_text(text) or "Ollama context response received.", "confidence": 0.5}


def _ollama_bases(base_url: str) -> list[str]:
    normalized = base_url.rstrip("/")
    bases = [normalized]
    if normalized in {"http://localhost:11434", "http://127.0.0.1:11434"}:
        bases.append("http://host.docker.internal:11434")
    return bases


def _ollama_generation_models() -> list[str]:
    configured = (
        os.getenv("OLLAMA_MODEL_FAST"),
        os.getenv("OLLAMA_MODEL_PRIMARY"),
        os.getenv("OLLAMA_MODEL_REASONING"),
    )
    return list(dict.fromkeys(str(item).strip() for item in configured if str(item or "").strip()))


def _ollama_prompt_payloads(model: str) -> list[dict[str, Any]]:
    prompts = [
        (
            "bounded_json",
            'Return only JSON: {"status":"OK","summary":"source context ok","confidence":0.5}',
            48,
        ),
        (
            "timeout_safe_minimal",
            '{"status":"OK","summary":"ok","confidence":0.5}',
            24,
        ),
    ]
    payloads = []
    for prompt_mode, prompt, num_predict in prompts:
        payloads.append(
            {
                "prompt_mode": prompt_mode,
                "prompt": prompt,
                "payload": {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "keep_alive": "0s",
                    "options": {
                        "temperature": 0,
                        "num_predict": num_predict,
                        "num_ctx": 512,
                    },
                },
            }
        )
    return payloads


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in str(os.getenv(name) or "").split(",") if item.strip()]


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except Exception:
        return default


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _first_text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if value is None:
        return None
    try:
        text = str(value)
        if text.isdigit():
            number = int(text)
            if number > 10_000_000_000:
                number = int(number / 1000)
            return datetime.fromtimestamp(number, tz=UTC)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        return None


def _digest(value: Any) -> str:
    payload = json.dumps(redact_dict(value if isinstance(value, dict) else {"value": value}), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_url_label(url: str) -> str:
    return url.split("://", 1)[-1].split("/", 1)[0][:80]


def _error(source: str, exc: Exception) -> dict[str, str]:
    return {"source": source, "error_type": type(exc).__name__, "error_summary": _redact_error_summary(exc)}


def _redact_error_summary(exc: Exception) -> str:
    text = redact_text(str(exc) or type(exc).__name__)
    text = re.sub(
        r"(?i)(api[_-]?key|apikey|token|secret|passphrase|authorization)=([^&\s]+)",
        r"\1=***",
        text,
    )
    text = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._\-]+", r"\1***", text)
    return text[:240]


def _count_table(conn: Any, table: str, where: str | None = None) -> int:
    if not table_exists(conn, table):
        return 0
    sql = f"SELECT COUNT(*) AS count FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return int(conn.execute(sql).fetchone()["count"] or 0)


def _safety_tables() -> tuple[str, ...]:
    return (
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


def _neuron_status(rows: list[Any]) -> dict[str, Any]:
    components = Counter(str(dict(row).get("source_component")) for row in rows)
    return {component: {"events": count, "status": "ACTIVE" if count else "SILENT"} for component, count in components.items()}


def _missing_providers() -> list[str]:
    missing = []
    for env_var in ("CRYPTOPANIC_API_KEY", "X_BEARER_TOKEN", "REDDIT_CLIENT_ID", "TELEGRAM_API_ID", "DISCORD_BOT_TOKEN"):
        if not os.getenv(env_var):
            missing.append(env_var)
    return missing


def _empty_dashboard(status: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "provider_status": {},
        "source_status": {},
        "neuron_status": {},
        "events_created": {},
        "sessions_updated": 0,
        "awareness_domains_updated": 0,
        "brain_opinions_created": 0,
        "coordinator_decisions_created": 0,
        "latest_items": [],
        "errors": [],
        "missing_providers": [],
        "degraded_providers": [],
        "secrets_exposed": False,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value.__class__.__name__ == "UUID":
        return str(value)
    if value.__class__.__name__ == "Decimal":
        return float(value)
    return value

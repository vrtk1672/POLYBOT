from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from uuid import uuid4

import httpx

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.news_neuron.contracts import NewsSourceType, RawNewsEvent
from app.news_neuron.news_errors import NewsSourceUnavailable
from app.news_neuron.source_registry import NewsSourceRegistry
from app.repositories.news_raw_event_repository import NewsRawEventRepository


FetchText = Callable[[str], str]


class NewsCollector:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
        fetch_text: FetchText | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._repo = NewsRawEventRepository()
        self._registry = NewsSourceRegistry(connection_factory=self._factory, event_bus=self._event_bus)
        self._fetch_text = fetch_text or _default_fetch_text

    def collect_manual(self, payload: dict[str, Any]) -> tuple[RawNewsEvent, bool]:
        source_id = str(payload.get("source_id") or "manual")
        event = RawNewsEvent(
            raw_event_id=str(payload.get("raw_event_id") or f"news_raw_{uuid4().hex}"),
            source_id=source_id,
            external_id=str(payload.get("external_id")) if payload.get("external_id") else None,
            url=str(payload.get("url")) if payload.get("url") else None,
            title=str(payload.get("title") or "").strip(),
            summary=str(payload.get("summary")) if payload.get("summary") else None,
            body_text=str(payload.get("body_text")) if payload.get("body_text") else None,
            author=str(payload.get("author")) if payload.get("author") else None,
            published_at=_parse_time(payload.get("published_at")),
            language=str(payload.get("language")) if payload.get("language") else None,
            raw_payload=payload,
        )
        return self._persist(event)

    def collect_from_source(self, source_id: str, *, limit: int = 20) -> list[RawNewsEvent]:
        source = self._registry.get_source(source_id)
        if not source:
            raise NewsSourceUnavailable(f"news source {source_id} is not registered")
        if not source.get("enabled"):
            return []
        try:
            if source["source_type"] == NewsSourceType.RSS.value:
                events = self.collect_rss(source, limit=limit)
            else:
                events = []
            self._registry.update_fetch_status(source_id, success=True)
            return events
        except Exception as exc:
            self._registry.update_fetch_status(source_id, success=False, error_message=str(exc))
            raise

    def collect_all_enabled(self, *, limit_per_source: int = 10) -> list[RawNewsEvent]:
        collected: list[RawNewsEvent] = []
        for source in self._registry.list_sources(enabled=True):
            try:
                collected.extend(self.collect_from_source(source["source_id"], limit=limit_per_source))
            except Exception:
                continue
        return collected

    def collect_rss(self, source: dict[str, Any], *, limit: int = 20) -> list[RawNewsEvent]:
        feed_url = source.get("feed_url")
        if not feed_url:
            return []
        xml_text = self._fetch_text(str(feed_url))
        items = _parse_rss_items(xml_text)[:limit]
        events: list[RawNewsEvent] = []
        for item in items:
            event, _created = self.collect_manual(
                {
                    "source_id": source["source_id"],
                    "external_id": item.get("guid") or item.get("link"),
                    "url": item.get("link"),
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "published_at": item.get("published_at"),
                    "raw_payload": item,
                }
            )
            events.append(event)
        return events

    def _persist(self, event: RawNewsEvent) -> tuple[RawNewsEvent, bool]:
        if not self._factory.enabled:
            self._publish_raw(event)
            return event, True
        with self._factory.connect() as conn, conn.transaction():
            row, created = self._repo.insert_raw_event(conn, event)
        persisted = RawNewsEvent(
            raw_event_id=row["raw_event_id"],
            source_id=row["source_id"],
            external_id=row.get("external_id"),
            url=row.get("url"),
            title=row["title"],
            summary=row.get("summary"),
            body_text=row.get("body_text"),
            author=row.get("author"),
            published_at=row.get("published_at"),
            collected_at=row.get("collected_at"),
            language=row.get("language"),
            content_hash=row["content_hash"],
            raw_payload=row.get("raw_payload_json") or {},
        )
        if created:
            self._publish_raw(persisted)
        return persisted, created

    def _publish_raw(self, event: RawNewsEvent) -> None:
        try:
            self._event_bus.publish(
                EventType.NEWS_RAW_COLLECTED.value,
                {"raw_event_id": event.raw_event_id, "source_id": event.source_id, "content_hash": event.content_hash, "title": event.title[:160]},
                source_service="news_neuron",
                aggregate_type="news_raw_event",
                aggregate_id=event.raw_event_id,
            )
        except Exception:
            pass


def _default_fetch_text(url: str) -> str:
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _parse_rss_items(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    output: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        output.append(
            {
                "title": _text(item, "title"),
                "summary": _text(item, "description"),
                "link": _text(item, "link"),
                "guid": _text(item, "guid"),
                "published_at": _text(item, "pubDate"),
            }
        )
    return [item for item in output if item.get("title")]


def _text(item: ET.Element, tag: str) -> str | None:
    child = item.find(tag)
    return child.text.strip() if child is not None and child.text else None


def _parse_time(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        parsed = parsedate_to_datetime(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            return None


def content_hash_for(title: str, summary: str | None = None, url: str | None = None) -> str:
    return hashlib.sha256("|".join([title.strip().lower(), summary or "", url or ""]).encode("utf-8")).hexdigest()


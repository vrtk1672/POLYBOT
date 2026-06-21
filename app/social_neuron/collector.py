from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.social_raw_event_repository import SocialRawEventRepository
from app.repositories.social_source_repository import SocialSourceRepository
from app.social_neuron.contracts import RawSocialEvent, SocialPlatform
from app.social_neuron.social_errors import SocialNeuronError


class SocialCollector:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._sources = SocialSourceRepository()
        self._raw = SocialRawEventRepository()

    def collect_from_source(self, source_id: str, *, limit: int = 10) -> list[RawSocialEvent]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            source = self._sources.get_source(conn, source_id)
        if not source:
            raise SocialNeuronError(f"unknown social source: {source_id}")
        source_type = source["source_type"]
        if source_type == "MANUAL":
            return []
        if source_type == "RSS_MIRROR":
            return self.collect_rss_mirror(source)[:limit]
        if source_type == "PUBLIC_TREND_API":
            return self.collect_public_trend_api(source)[:limit]
        return []

    def collect_rss_mirror(self, source: dict[str, Any]) -> list[RawSocialEvent]:
        return []

    def collect_public_trend_api(self, source: dict[str, Any]) -> list[RawSocialEvent]:
        return []

    def collect_all_enabled(self, *, limit_per_source: int = 10) -> list[RawSocialEvent]:
        if not self._factory.enabled:
            return []
        events: list[RawSocialEvent] = []
        with self._factory.connect() as conn:
            sources = self._sources.list_sources(conn, enabled=True)
        for source in sources:
            try:
                events.extend(self.collect_from_source(source["source_id"], limit=limit_per_source))
                self._update_fetch_status(source["source_id"], success=True)
            except Exception as exc:
                self._update_fetch_status(source["source_id"], success=False, error_message=str(exc))
        return events

    def collect_manual(self, payload: dict[str, Any]) -> tuple[RawSocialEvent, bool]:
        event = RawSocialEvent(
            source_id=str(payload.get("source_id") or "manual"),
            platform=SocialPlatform(str(payload.get("platform") or "manual")),
            external_id=payload.get("external_id"),
            url=payload.get("url"),
            author_id=payload.get("author_id"),
            author_handle=payload.get("author_handle"),
            text=str(payload["text"]),
            raw_text=payload.get("raw_text") or payload.get("text"),
            published_at=payload.get("published_at"),
            language=payload.get("language"),
            engagement=payload.get("engagement") or {},
            raw_payload=payload,
        )
        if not self._factory.enabled:
            return event, True
        with self._factory.connect() as conn:
            row, created = self._raw.insert_event(conn, event)
            conn.commit()
        if created:
            self._publish(EventType.SOCIAL_RAW_COLLECTED, {"raw_social_event_id": event.raw_social_event_id, "source_id": event.source_id, "platform": event.platform.value, "content_hash": event.content_hash})
        else:
            event.raw_social_event_id = row["raw_social_event_id"]
        return event, created

    def _update_fetch_status(self, source_id: str, *, success: bool, error_message: str | None = None) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn:
            self._sources.update_fetch_status(conn, source_id, success=success, error_message=error_message)
            conn.commit()

    def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="social_neuron", aggregate_type="social_raw_event", aggregate_id=payload.get("raw_social_event_id"), metadata={"non_trading_event": True})
        except Exception:
            pass

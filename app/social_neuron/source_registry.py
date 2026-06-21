from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.social_source_repository import SocialSourceRepository
from app.social_neuron.contracts import SocialPlatform, SocialSource, SocialSourceType


DEFAULT_CATEGORIES = ("crypto", "politics", "sports", "macro", "weather", "legal", "geopolitics", "entertainment", "polymarket", "general")


class SocialSourceRegistry:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repo = SocialSourceRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def register_source(self, source: SocialSource) -> tuple[dict, bool]:
        if not self._factory.enabled:
            return source.model_dump(mode="json"), True
        with self._factory.connect() as conn:
            row, created = self._repo.upsert_source(conn, source)
            conn.commit()
        if created:
            self._publish(EventType.SOCIAL_SOURCE_REGISTERED, {"source_id": source.source_id, "platform": source.platform.value, "category": source.category})
        return row, created

    def enable_source(self, source_id: str) -> None:
        self._set_enabled(source_id, True)

    def disable_source(self, source_id: str) -> None:
        self._set_enabled(source_id, False)

    def get_source(self, source_id: str) -> dict | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._repo.get_source(conn, source_id)

    def list_sources(self, *, enabled: bool | None = None, platform: str | None = None, category: str | None = None) -> list[dict]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return self._repo.list_sources(conn, enabled=enabled, platform=platform, category=category)

    def update_fetch_status(self, source_id: str, *, success: bool, error_message: str | None = None) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn:
            self._repo.update_fetch_status(conn, source_id, success=success, error_message=error_message)
            conn.commit()

    def seed_default_sources(self) -> list[str]:
        manual = SocialSource(source_id="manual", name="Manual Social", source_type=SocialSourceType.MANUAL, platform=SocialPlatform.MANUAL, category="general")
        self.register_source(manual)
        return list(DEFAULT_CATEGORIES)

    def _set_enabled(self, source_id: str, enabled: bool) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn:
            self._repo.set_enabled(conn, source_id, enabled)
            conn.commit()

    def _publish(self, event_type: EventType, payload: dict) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="social_neuron", aggregate_type="social_source", aggregate_id=payload.get("source_id"), metadata={"non_trading_event": True})
        except Exception:
            pass

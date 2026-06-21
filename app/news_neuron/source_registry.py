from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.news_neuron.contracts import NewsSource, NewsSourceType
from app.repositories.news_source_repository import NewsSourceRepository


DEFAULT_SOURCE_CATEGORIES = (
    "general",
    "finance",
    "crypto",
    "politics",
    "sports",
    "weather",
    "legal",
    "regulation",
    "security",
    "geopolitics",
    "polymarket",
)


class NewsSourceRegistry:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repo = NewsSourceRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def register_source(self, source: NewsSource) -> dict[str, Any]:
        if not self._factory.enabled:
            return source.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            row, created = self._repo.upsert_source(conn, source)
        if created:
            self._publish(EventType.NEWS_SOURCE_REGISTERED.value, {"source_id": source.source_id, "category": source.category})
        return row

    def enable_source(self, source_id: str) -> None:
        self._set_enabled(source_id, True)

    def disable_source(self, source_id: str) -> None:
        self._set_enabled(source_id, False)

    def _set_enabled(self, source_id: str, enabled: bool) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repo.set_enabled(conn, source_id, enabled)

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._repo.get_source(conn, source_id)

    def list_sources(self, *, enabled: bool | None = None, category: str | None = None) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return self._repo.list_sources(conn, enabled=enabled, category=category)

    def update_fetch_status(self, source_id: str, *, success: bool, error_message: str | None = None) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repo.update_fetch_status(conn, source_id, success=success, error_message=error_message)

    def seed_default_sources(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for category in DEFAULT_SOURCE_CATEGORIES:
            rows.append(
                self.register_source(
                    NewsSource(
                        source_id=f"default_{category}",
                        name=f"Default {category.title()} Registry Slot",
                        source_type=NewsSourceType.MANUAL,
                        category=category,
                        enabled=False,
                        reliability_score=0.5,
                        metadata={"seeded": True, "feed_configured": False},
                    )
                )
            )
        return rows

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="news_neuron", aggregate_type="news_source", aggregate_id=payload.get("source_id"))
        except Exception:
            pass


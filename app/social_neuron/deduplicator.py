from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.social_normalized_event_repository import SocialNormalizedEventRepository
from app.social_neuron.contracts import NormalizedSocialEvent, stable_hash


class SocialDeduplicator:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._events = SocialNormalizedEventRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def compute_group_hash(self, event: NormalizedSocialEvent) -> str:
        basis = event.url or " ".join(event.normalized_text.split()[:12])
        return stable_hash({"basis": basis, "platform": event.platform.value})

    def find_existing_group(self, event: NormalizedSocialEvent) -> str | None:
        if not self._factory.enabled:
            return None
        group_hash = self.compute_group_hash(event)
        with self._factory.connect() as conn:
            row = conn.execute("SELECT dedup_group_id FROM social_normalized_events WHERE dedup_group_id = %s LIMIT 1", (group_hash,)).fetchone()
        return row["dedup_group_id"] if row else None

    def deduplicate(self, event: NormalizedSocialEvent) -> str:
        group_id = self.find_existing_group(event) or self.compute_group_hash(event)
        event.dedup_group_id = group_id
        if self._factory.enabled:
            with self._factory.connect() as conn:
                self._events.set_dedup_group(conn, event.social_event_id, group_id)
                conn.commit()
        self._publish(EventType.SOCIAL_EVENT_DEDUPED, {"social_event_id": event.social_event_id, "dedup_group_id": group_id})
        return group_id

    def _publish(self, event_type: EventType, payload: dict) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="social_neuron", aggregate_type="social_event", aggregate_id=payload.get("social_event_id"), metadata={"non_trading_event": True})
        except Exception:
            pass

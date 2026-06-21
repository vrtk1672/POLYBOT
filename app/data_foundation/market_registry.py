from __future__ import annotations

import json
from typing import Any

from app.data_foundation.contracts import MarketRecord
from app.data_foundation.market_family_classifier import MarketFamilyClassifier
from app.data_foundation.market_lifecycle_tracker import MarketLifecycleTracker
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.market_registry_repository import MarketRegistryRepository
from app.utils.time_utils import parse_datetime


class MarketRegistry:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = MarketRegistryRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._classifier = MarketFamilyClassifier(connection_factory=self._factory)
        self._lifecycle = MarketLifecycleTracker(connection_factory=self._factory, event_bus=self._event_bus)

    def normalize_market(self, raw_market: dict[str, Any]) -> MarketRecord:
        market_id = str(raw_market.get("id") or raw_market.get("market_id") or raw_market.get("conditionId") or "")
        if not market_id:
            raise ValueError("market_id is required")
        tokens = _token_map(raw_market)
        classification = self._classifier.classify(raw_market)
        return MarketRecord(
            market_id=market_id,
            condition_id=raw_market.get("conditionId") or raw_market.get("condition_id"),
            question=str(raw_market.get("question") or raw_market.get("title") or "Untitled market"),
            slug=raw_market.get("slug"),
            category=classification.get("category") or raw_market.get("category"),
            market_family=classification.get("market_family"),
            yes_token_id=tokens.get("yes"),
            no_token_id=tokens.get("no"),
            outcome_tokens_json=tokens,
            resolution_source=raw_market.get("resolutionSource") or raw_market.get("resolution_source"),
            accepting_orders=_bool(raw_market.get("acceptingOrders") if "acceptingOrders" in raw_market else raw_market.get("accepting_orders")),
            closed=bool(raw_market.get("closed", False)),
            archived=bool(raw_market.get("archived", False)),
            active=bool(raw_market.get("active", True)),
            close_time=parse_datetime(raw_market.get("endDate") or raw_market.get("close_time")),
            resolution_time=parse_datetime(raw_market.get("resolutionTime") or raw_market.get("resolution_time")),
            raw_market_json=raw_market,
            metadata_json={"classifier": classification},
        )

    def upsert_market(self, record: MarketRecord) -> tuple[dict[str, Any] | None, bool]:
        if not self._factory.enabled:
            return None, False
        with self._factory.connect() as conn, conn.transaction():
            previous = self._repository.get_market(conn, record.market_id)
            row, created = self._repository.upsert_market(conn, record)
        self._classifier.persist(record.market_id, record.metadata_json.get("classifier") or {})
        event_type, previous_status, new_status = self._lifecycle.detect_lifecycle_change(previous, row)
        if event_type:
            self._lifecycle.persist_lifecycle_event(
                record.market_id,
                event_type,
                previous_status=previous_status,
                new_status=new_status,
                metadata={"created": created},
            )
        if created:
            self._publish_discovered(record)
        return row, created

    def get_market(self, market_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._repository.get_market(conn, market_id)

    def list_active_markets(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return self._repository.list_active_markets(conn, limit)

    def mark_market_seen(self, market_id: str) -> None:
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.mark_market_seen(conn, market_id)

    def mark_market_closed(self, market_id: str) -> None:
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                previous = self._repository.get_market(conn, market_id)
                self._repository.mark_market_closed(conn, market_id)
        self._lifecycle.persist_lifecycle_event(market_id, "CLOSED", previous_status="OPEN" if previous else None, new_status="CLOSED")

    def _publish_discovered(self, record: MarketRecord) -> None:
        try:
            self._event_bus.publish(
                EventType.MARKET_DISCOVERED.value,
                {"market_id": record.market_id, "question": record.question, "market_family": record.market_family},
                source_service="data_foundation",
                aggregate_type="market",
                aggregate_id=record.market_id,
                metadata={"non_trading_event": True},
            )
        except Exception:
            return


def _token_map(raw_market: dict[str, Any]) -> dict[str, str]:
    token_ids = raw_market.get("clobTokenIds") or raw_market.get("outcomeTokens") or raw_market.get("tokens")
    if isinstance(token_ids, str):
        try:
            token_ids = json.loads(token_ids)
        except json.JSONDecodeError:
            token_ids = []
    if isinstance(token_ids, list):
        return {
            "yes": str(token_ids[0]) if len(token_ids) > 0 and token_ids[0] else None,
            "no": str(token_ids[1]) if len(token_ids) > 1 and token_ids[1] else None,
        }
    if isinstance(token_ids, dict):
        return {str(key): str(value) for key, value in token_ids.items() if value}
    return {}


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}

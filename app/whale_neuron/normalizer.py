from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.whale_event_repository import WhaleEventRepository
from app.whale_neuron.contracts import WhaleActionType, WhaleEvent, WhaleEventClassification, WhaleSide, bounded, stable_hash
from app.whale_neuron.redaction import redact_dict


class WhaleEventNormalizer:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._repo = WhaleEventRepository()

    def normalize_raw_event(self, raw_event: dict[str, Any]) -> WhaleEvent:
        event_time = raw_event.get("event_time") or raw_event.get("timestamp") or datetime.now(UTC)
        if isinstance(event_time, str):
            event_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        size_usd = self.normalize_size_usd(raw_event)
        price = _float(raw_event.get("price"))
        size_shares = _float(raw_event.get("size_shares") or raw_event.get("shares") or raw_event.get("size"))
        notional = size_usd if size_usd is not None else (price * size_shares if price is not None and size_shares is not None else None)
        whale_id = self.normalize_wallet_or_whale_id(raw_event)
        event_id = raw_event.get("whale_event_id") or f"whale_evt_{stable_hash({'source': raw_event.get('source_id'), 'whale': whale_id, 'market': raw_event.get('market_id'), 'side': raw_event.get('side'), 'action': raw_event.get('action_type'), 'size': size_usd, 'time': event_time})[:24]}"
        confidence = 0.85 if size_usd and size_usd >= 5000 else 0.35
        normalized = {
            "source_id": raw_event.get("source_id", "manual"),
            "whale_id": whale_id,
            "market_id": self.normalize_market_id(raw_event.get("market_id")),
            "side": self.normalize_side(raw_event.get("side")),
            "action_type": self.normalize_action_type(raw_event.get("action_type")),
            "size_usd": size_usd,
            "notional": notional,
        }
        return WhaleEvent(
            whale_event_id=event_id,
            source_id=normalized["source_id"],
            whale_id=whale_id,
            wallet_address=raw_event.get("wallet_address"),
            trader_label=raw_event.get("trader_label"),
            market_id=normalized["market_id"],
            asset_id=raw_event.get("asset_id"),
            side=normalized["side"],
            action_type=normalized["action_type"],
            size_usd=size_usd,
            size_shares=size_shares,
            price=price,
            notional=notional,
            tx_hash=raw_event.get("tx_hash"),
            order_id=raw_event.get("order_id"),
            event_time=event_time,
            raw_event=redact_dict(raw_event),
            normalized_event=redact_dict(normalized),
            event_classification=WhaleEventClassification.UNKNOWN,
            confidence=bounded(confidence),
        )

    def normalize_wallet_or_whale_id(self, raw_event: dict[str, Any]) -> str:
        return str(raw_event.get("whale_id") or raw_event.get("wallet_address") or raw_event.get("trader_label") or f"unknown_{stable_hash(raw_event)[:12]}")

    def normalize_market_id(self, market_id: Any) -> str | None:
        return None if market_id in (None, "", "<market_id>") else str(market_id)

    def normalize_side(self, value: Any) -> WhaleSide:
        text = str(value or "UNKNOWN").upper()
        return WhaleSide.YES if text in {"YES", "Y", "LONG"} else WhaleSide.NO if text in {"NO", "N", "SHORT"} else WhaleSide.UNKNOWN

    def normalize_action_type(self, value: Any) -> WhaleActionType:
        text = str(value or "UNKNOWN").upper()
        return WhaleActionType(text) if text in WhaleActionType.__members__ else WhaleActionType.UNKNOWN

    def normalize_size_usd(self, raw_event: dict[str, Any]) -> float | None:
        return _float(raw_event.get("size_usd") or raw_event.get("notional") or raw_event.get("usd_size"))

    def compute_notional(self, size_shares: float | None, price: float | None, size_usd: float | None) -> float | None:
        return size_usd if size_usd is not None else (size_shares * price if size_shares is not None and price is not None else None)

    def classify_confidence(self, event: WhaleEvent) -> float:
        return bounded((0.4 if event.size_usd else 0.2) + (0.25 if event.wallet_address else 0) + (0.2 if event.market_id else 0))

    def persist_whale_event(self, event: WhaleEvent) -> tuple[dict[str, Any], bool]:
        if not self._factory.enabled:
            return event.model_dump(mode="json"), True
        with self._factory.connect() as conn, conn.transaction():
            row, created = self._repo.insert_event(conn, event)
        if created:
            self._publish(EventType.WHALE_EVENT_CREATED, {"whale_event_id": event.whale_event_id, "whale_id": event.whale_id, "market_id": event.market_id})
            self._publish(EventType.WHALE_EVENT_NORMALIZED, {"whale_event_id": event.whale_event_id, "classification": event.event_classification.value})
        return row, created

    def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        self._event_bus.publish(event_type.value, redact_dict(payload), "whale_neuron", aggregate_type="whale_event", aggregate_id=str(payload.get("whale_event_id") or "unknown"))


def _float(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else max(0.0, float(value))
    except (TypeError, ValueError):
        return None


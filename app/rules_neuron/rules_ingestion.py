from __future__ import annotations

import hashlib
import re
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.market_registry_repository import MarketRegistryRepository
from app.repositories.market_rules_repository import MarketRulesRepository
from app.rules_neuron.contracts import RulesInput


class RulesIngestion:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._markets = MarketRegistryRepository()
        self._rules = MarketRulesRepository()

    def load_rules_from_market(self, market_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._rules.get_rules(conn, market_id)

    def load_rules_from_data_foundation(self, market_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if not self._factory.enabled:
            return None, None
        with self._factory.connect() as conn:
            return self._markets.get_market(conn, market_id), self._rules.get_rules(conn, market_id)

    def build_rules_input(self, market_id: str) -> RulesInput:
        market, rules = self.load_rules_from_data_foundation(market_id)
        if market is None:
            raise ValueError(f"market not found: {market_id}")
        rules = rules or {}
        raw_market = market.get("raw_market_json") or {}
        rules_text = self.normalize_rules_text(rules.get("rules_text"))
        rules_hash = rules.get("rules_hash") or self.compute_rules_hash(rules_text, rules.get("resolution_source") or market.get("resolution_source"), rules.get("deadline_at"))
        payload = RulesInput(
            market_id=market_id,
            rules_text=rules_text,
            resolution_source=rules.get("resolution_source") or market.get("resolution_source"),
            resolution_source_url=rules.get("resolution_source_url"),
            deadline_at=rules.get("deadline_at"),
            close_time=market.get("close_time"),
            question=market.get("question"),
            category=market.get("category"),
            market_family=market.get("market_family"),
            raw_market_json={
                **raw_market,
                "resolution_source_status": rules.get("resolution_source_status"),
                "resolution_source_type": rules.get("resolution_source_type"),
                "resolution_source_evidence": rules.get("resolution_source_evidence"),
                "resolution_source_confidence": rules.get("resolution_source_confidence"),
                "resolution_source_penalty": rules.get("resolution_source_penalty"),
                "resolution_source_hard_block": rules.get("resolution_source_hard_block"),
            },
            metadata={
                "rules_hash": rules_hash,
                "rules_missing": not bool(rules_text),
                "resolution_source_status": rules.get("resolution_source_status"),
                "resolution_source_type": rules.get("resolution_source_type"),
            },
        )
        self._publish(payload, rules_hash)
        return payload

    def persist_or_update_market_rules_if_needed(self) -> None:
        return None

    def normalize_rules_text(self, text: str | None) -> str | None:
        if not text:
            return None
        return re.sub(r"\s+", " ", str(text)).strip()

    def compute_rules_hash(self, rules_text: object, resolution_source: object, deadline: object) -> str:
        material = "|".join(str(value or "").strip().lower() for value in (rules_text, resolution_source, deadline))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _publish(self, rules_input: RulesInput, rules_hash: str | None) -> None:
        try:
            self._event_bus.publish(
                EventType.RULES_INGESTED.value,
                {"market_id": rules_input.market_id, "rules_hash": rules_hash, "rules_text_present": bool(rules_input.rules_text)},
                source_service="rules_neuron",
                aggregate_type="market",
                aggregate_id=rules_input.market_id,
                metadata={"non_trading_event": True},
            )
        except Exception:
            pass

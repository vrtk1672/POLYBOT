from __future__ import annotations

import hashlib
from typing import Any

from app.data_foundation.contracts import MarketRulesRecord
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.market_rules_repository import MarketRulesRepository
from app.rules_neuron.resolution_source_parser import extract_resolution_source_truth
from app.utils.time_utils import parse_datetime


class MarketRulesStore:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = MarketRulesRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def extract_rules(self, raw_market: dict[str, Any], *, market_id: str) -> MarketRulesRecord:
        rules_text = raw_market.get("rules") or raw_market.get("description") or raw_market.get("resolutionCriteria")
        extraction = extract_resolution_source_truth(
            str(rules_text) if rules_text else None,
            raw_market,
            market_family=raw_market.get("market_family"),
            question=raw_market.get("question"),
            category=raw_market.get("category"),
        )
        resolution_source = extraction.source_name
        deadline = parse_datetime(raw_market.get("endDate") or raw_market.get("deadline"))
        rules_hash = self.compute_rules_hash(rules_text, resolution_source, deadline.isoformat() if deadline else None)
        return MarketRulesRecord(
            market_id=market_id,
            rules_text=str(rules_text) if rules_text else None,
            resolution_source=str(resolution_source) if resolution_source else None,
            resolution_source_url=extraction.source_url,
            resolution_source_status=extraction.status,
            resolution_source_type=extraction.source_type,
            resolution_source_evidence=extraction.evidence,
            resolution_source_confidence=extraction.confidence,
            resolution_source_penalty=extraction.penalty,
            resolution_source_hard_block=extraction.hard_block,
            settlement_method=raw_market.get("settlementMethod") or raw_market.get("settlement_method"),
            deadline_at=deadline,
            rules_hash=rules_hash,
            ambiguity_flags_json=_ambiguity_flags(bool(rules_text), extraction.status),
            raw_rules_json={
                "rules": rules_text,
                "resolution_source": resolution_source,
                "resolution_source_status": extraction.status,
                "resolution_source_type": extraction.source_type,
                "resolution_source_evidence": extraction.evidence,
                "resolution_source_confidence": extraction.confidence,
                "resolution_source_penalty": extraction.penalty,
                "resolution_source_hard_block": extraction.hard_block,
                "deadline": raw_market.get("endDate") or raw_market.get("deadline"),
                "rules_missing": not bool(rules_text),
            },
        )

    def compute_rules_hash(self, rules_text: object, resolution_source: object, deadline: object) -> str:
        material = "|".join(str(value or "").strip().lower() for value in (rules_text, resolution_source, deadline))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def upsert_rules(self, record: MarketRulesRecord) -> tuple[dict[str, Any] | None, bool]:
        if not self._factory.enabled:
            return None, False
        with self._factory.connect() as conn, conn.transaction():
            row, changed = self._repository.upsert_rules(conn, record)
        if changed:
            self._publish(record)
        return row, changed

    def get_rules(self, market_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._repository.get_rules(conn, market_id)

    def rules_coverage_stats(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"markets_with_rules": 0, "markets_missing_rules": 0}
        with self._factory.connect() as conn:
            return dict(self._repository.coverage_stats(conn))

    def _publish(self, record: MarketRulesRecord) -> None:
        try:
            self._event_bus.publish(
                EventType.RULES_SNAPSHOT_CREATED.value,
                {"market_id": record.market_id, "rules_hash": record.rules_hash, "rules_missing": not bool(record.rules_text)},
                source_service="data_foundation",
                aggregate_type="market",
                aggregate_id=record.market_id,
                metadata={"non_trading_event": True},
            )
        except Exception:
            return


def _ambiguity_flags(rules_present: bool, resolution_source_status: str) -> list[str]:
    flags: list[str] = []
    if not rules_present:
        flags.append("rules_missing")
    if resolution_source_status == "MISSING":
        flags.append("resolution_source_missing")
    if resolution_source_status == "AMBIGUOUS":
        flags.append("resolution_source_ambiguous")
    if resolution_source_status == "FAMILY_DERIVED":
        flags.append("resolution_source_family_derived")
    return flags

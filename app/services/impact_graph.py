from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.impact_graph import (
    EntityMarketLink,
    EventEntity,
    ImpactLink,
    PositionThesisProfile,
    SignalMarketLink,
    SignalPositionLink,
    entity_market_link_from_row,
    event_entity_from_row,
    impact_link_from_row,
    position_thesis_profile_from_row,
    signal_market_link_from_row,
    signal_position_link_from_row,
)
from app.neural_mesh.contracts import signal_from_row
from app.repositories.impact_graph_repository import ImpactGraphRepository


class ImpactGraphService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: ImpactGraphRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or ImpactGraphRepository()

    def create_event_entity(self, entity: EventEntity | dict[str, Any]) -> dict[str, Any]:
        item = entity if isinstance(entity, EventEntity) else EventEntity(**entity)
        if not self._factory.enabled:
            return item.to_api_dict()
        with self._factory.connect() as conn, conn.transaction():
            if item.source_signal_id and not self._repository.signal_exists(conn, item.source_signal_id):
                raise ValueError(f"source signal does not exist: {item.source_signal_id}")
            row = self._repository.create_event_entity(conn, item)
        return event_entity_from_row(row).to_api_dict()

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_entity(conn, entity_id)
        return event_entity_from_row(row).to_api_dict() if row else None

    def list_entities(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_entities(conn, limit=limit)
        return [event_entity_from_row(dict(row)).to_api_dict() for row in rows]

    def link_entity_to_market(self, link: EntityMarketLink | dict[str, Any]) -> dict[str, Any]:
        item = link if isinstance(link, EntityMarketLink) else EntityMarketLink(**link)
        if not self._factory.enabled:
            return item.to_api_dict()
        with self._factory.connect() as conn, conn.transaction():
            if not self._repository.entity_exists(conn, item.entity_id):
                raise ValueError(f"entity does not exist: {item.entity_id}")
            if item.evidence_signal_id and not self._repository.signal_exists(conn, item.evidence_signal_id):
                raise ValueError(f"evidence signal does not exist: {item.evidence_signal_id}")
            row = self._repository.link_entity_to_market(conn, item)
        return entity_market_link_from_row(row).to_api_dict()

    def link_signal_to_market(self, link: SignalMarketLink | dict[str, Any]) -> dict[str, Any]:
        item = link if isinstance(link, SignalMarketLink) else SignalMarketLink(**link)
        if not self._factory.enabled:
            return item.to_api_dict()
        with self._factory.connect() as conn, conn.transaction():
            if not self._repository.signal_exists(conn, item.signal_id):
                raise ValueError(f"signal does not exist: {item.signal_id}")
            row = self._repository.link_signal_to_market(conn, item)
        return signal_market_link_from_row(row).to_api_dict()

    def link_signal_to_position(self, link: SignalPositionLink | dict[str, Any]) -> dict[str, Any]:
        item = link if isinstance(link, SignalPositionLink) else SignalPositionLink(**link)
        if not self._factory.enabled:
            return item.to_api_dict()
        with self._factory.connect() as conn, conn.transaction():
            if not self._repository.signal_exists(conn, item.signal_id):
                raise ValueError(f"signal does not exist: {item.signal_id}")
            row = self._repository.link_signal_to_position(conn, item)
        return signal_position_link_from_row(row).to_api_dict()

    def create_position_thesis_profile(self, thesis: PositionThesisProfile | dict[str, Any]) -> dict[str, Any]:
        item = thesis if isinstance(thesis, PositionThesisProfile) else PositionThesisProfile(**thesis)
        if not self._factory.enabled:
            return item.to_api_dict()
        with self._factory.connect() as conn, conn.transaction():
            row = self._repository.create_position_thesis_profile(conn, item)
        return position_thesis_profile_from_row(row).to_api_dict()

    def get_position_thesis_profile(self, position_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_position_thesis_profile(conn, position_id)
        return position_thesis_profile_from_row(row).to_api_dict() if row else None

    def create_impact_link(self, link: ImpactLink | dict[str, Any]) -> dict[str, Any]:
        item = link if isinstance(link, ImpactLink) else ImpactLink(**link)
        if not self._factory.enabled:
            return item.to_api_dict()
        with self._factory.connect() as conn, conn.transaction():
            self._validate_impact_references(conn, item)
            row = self._repository.create_impact_link(conn, item)
        return impact_link_from_row(row).to_api_dict()

    def get_impact_link(self, impact_link_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_impact_link(conn, impact_link_id)
        return impact_link_from_row(row).to_api_dict() if row else None

    def list_signal_market_links(self, signal_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_signal_market_links(conn, signal_id, limit=limit)
        return [signal_market_link_from_row(dict(row)).to_api_dict() for row in rows]

    def list_signal_position_links(self, signal_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_signal_position_links(conn, signal_id, limit=limit)
        return [signal_position_link_from_row(dict(row)).to_api_dict() for row in rows]

    def list_market_impacts(self, market_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_market_impacts(conn, market_id, limit=limit)
        return [impact_link_from_row(dict(row)).to_api_dict() for row in rows]

    def list_position_impacts(self, position_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_position_impacts(conn, position_id, limit=limit)
        return [impact_link_from_row(dict(row)).to_api_dict() for row in rows]

    def list_unlinked_signals(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_unlinked_signals(conn, limit=limit)
        return [signal_from_row(dict(row)).to_api_dict() for row in rows]

    def get_impact_graph_summary(self, *, limit: int = 10) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        return {
            "status": "OK",
            "mock_data": False,
            "updated_at": datetime.now().astimezone().isoformat(),
            "entities_total": summary["entities_total"],
            "signal_market_links_total": summary["signal_market_links_total"],
            "signal_position_links_total": summary["signal_position_links_total"],
            "impact_links_total": summary["impact_links_total"],
            "unlinked_signals": summary["unlinked_signals"],
            "links_by_status": [_json_safe(dict(row)) for row in summary["links_by_status"]],
            "impacts_by_direction": [_json_safe(dict(row)) for row in summary["impacts_by_direction"]],
            "cortex_action_hints": [_json_safe(dict(row)) for row in summary["cortex_action_hints"]],
            "latest_impacts": [_json_safe(impact_link_from_row(dict(row)).to_api_dict()) for row in summary["latest_impacts"]],
            "positions_with_thesis": summary["positions_with_thesis"],
            "signals_without_market_link": summary["signals_without_market_link"],
        }

    def _validate_impact_references(self, conn, item: ImpactLink) -> None:
        if item.signal_id and not self._repository.signal_exists(conn, item.signal_id):
            raise ValueError(f"signal does not exist: {item.signal_id}")
        if item.entity_id and not self._repository.entity_exists(conn, item.entity_id):
            raise ValueError(f"entity does not exist: {item.entity_id}")
        if item.thesis_id and not self._repository.thesis_exists(conn, item.thesis_id):
            raise ValueError(f"thesis does not exist: {item.thesis_id}")
        if item.brain_output_id and not self._repository.brain_output_exists(conn, item.brain_output_id):
            raise ValueError(f"brain output does not exist: {item.brain_output_id}")
        if item.coordinator_decision_id and not self._repository.coordinator_decision_exists(conn, item.coordinator_decision_id):
            raise ValueError(f"coordinator decision does not exist: {item.coordinator_decision_id}")


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "OK",
        "mock_data": False,
        "updated_at": datetime.now().astimezone().isoformat(),
        "entities_total": 0,
        "signal_market_links_total": 0,
        "signal_position_links_total": 0,
        "impact_links_total": 0,
        "unlinked_signals": 0,
        "links_by_status": [],
        "impacts_by_direction": [],
        "cortex_action_hints": [],
        "latest_impacts": [],
        "positions_with_thesis": 0,
        "signals_without_market_link": 0,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value

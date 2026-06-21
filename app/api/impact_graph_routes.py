from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.services.impact_graph import ImpactGraphService


class EventEntityRequest(BaseModel):
    entity_type: str = "unknown"
    entity_name: str
    normalized_name: str | None = None
    source_signal_id: str | None = None
    source_event_id: str | None = None
    source_name: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityMarketLinkRequest(BaseModel):
    entity_id: str
    market_id: str
    link_type: str
    link_status: str = "suggested"
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_signal_id: str | None = None
    evidence_event_id: str | None = None
    evidence_text: str | None = None
    created_by: str | None = None


class SignalMarketLinkRequest(BaseModel):
    signal_id: str
    market_id: str
    link_type: str
    link_status: str = "suggested"
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None
    created_by: str | None = None


class SignalPositionLinkRequest(BaseModel):
    signal_id: str
    position_id: str
    market_id: str | None = None
    link_type: str
    link_status: str = "suggested"
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None
    created_by: str | None = None


class PositionThesisRequest(BaseModel):
    market_id: str
    side: str | None = None
    entry_thesis: str
    profit_drivers: list[str] = Field(default_factory=list)
    invalidation_drivers: list[str] = Field(default_factory=list)
    watch_entities: list[str] = Field(default_factory=list)
    danger_signals: list[str] = Field(default_factory=list)
    take_profit_rules: list[str] = Field(default_factory=list)
    partial_exit_rules: list[str] = Field(default_factory=list)
    emergency_exit_rules: list[str] = Field(default_factory=list)
    status: str = "ACTIVE"


class ImpactLinkRequest(BaseModel):
    signal_id: str | None = None
    event_id: str | None = None
    entity_id: str | None = None
    market_id: str | None = None
    position_id: str | None = None
    thesis_id: str | None = None
    brain_output_id: str | None = None
    coordinator_decision_id: str | None = None
    impact_scope: str
    impact_direction: str = "unknown"
    impact_status: str = "suggested"
    impact_strength: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    urgency: float | None = Field(default=None, ge=0, le=1)
    cortex_action_hint: str = "UNKNOWN"
    reasoning_summary: str | None = None
    created_by: str | None = None
    ttl_seconds: int | None = Field(default=None, ge=0)


def create_impact_graph_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    service: ImpactGraphService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/impact", tags=["impact-graph"])
    factory = connection_factory or DatabaseConnectionFactory()
    impact = service or ImpactGraphService(connection_factory=factory)

    @router.get("/entities")
    async def list_entities(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        entities = impact.list_entities(limit=limit)
        return {"status": "OK", "mock_data": False, "count": len(entities), "entities": entities}

    @router.get("/entities/{entity_id}")
    async def get_entity(entity_id: str) -> dict[str, Any]:
        entity = impact.get_entity(entity_id)
        return {"status": "OK" if entity else "MISSING", "mock_data": False, "entity_id": entity_id, "entity": entity}

    @router.get("/signals/{signal_id}/markets")
    async def signal_markets(signal_id: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        links = impact.list_signal_market_links(signal_id, limit=limit)
        return {"status": "OK", "mock_data": False, "signal_id": signal_id, "count": len(links), "links": links}

    @router.get("/signals/{signal_id}/positions")
    async def signal_positions(signal_id: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        links = impact.list_signal_position_links(signal_id, limit=limit)
        return {"status": "OK", "mock_data": False, "signal_id": signal_id, "count": len(links), "links": links}

    @router.get("/markets/{market_id}")
    async def market_impacts(market_id: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        impacts = impact.list_market_impacts(market_id, limit=limit)
        return {"status": "OK", "mock_data": False, "market_id": market_id, "count": len(impacts), "impacts": impacts}

    @router.get("/positions/{position_id}")
    async def position_impacts(position_id: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        impacts = impact.list_position_impacts(position_id, limit=limit)
        return {"status": "OK", "mock_data": False, "position_id": position_id, "count": len(impacts), "impacts": impacts}

    @router.get("/positions/{position_id}/thesis")
    async def position_thesis(position_id: str) -> dict[str, Any]:
        thesis = impact.get_position_thesis_profile(position_id)
        return {"status": "OK" if thesis else "MISSING", "mock_data": False, "position_id": position_id, "thesis": thesis}

    @router.get("/links/{impact_link_id}")
    async def get_impact_link(impact_link_id: str) -> dict[str, Any]:
        link = impact.get_impact_link(impact_link_id)
        return {"status": "OK" if link else "MISSING", "mock_data": False, "impact_link_id": impact_link_id, "impact_link": link}

    @router.get("/unlinked-signals")
    async def unlinked_signals(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        signals = impact.list_unlinked_signals(limit=limit)
        return {"status": "OK", "mock_data": False, "count": len(signals), "signals": signals}

    @router.post("/entities")
    async def create_entity(payload: EventEntityRequest) -> dict[str, Any]:
        entity = impact.create_event_entity(payload.model_dump())
        return {"status": "OK", "mock_data": False, "entity": entity}

    @router.post("/link/entity-market")
    async def create_entity_market_link(payload: EntityMarketLinkRequest) -> dict[str, Any]:
        link = impact.link_entity_to_market(payload.model_dump())
        return {"status": "OK", "mock_data": False, "link": link}

    @router.post("/link/signal-market")
    async def create_signal_market_link(payload: SignalMarketLinkRequest) -> dict[str, Any]:
        link = impact.link_signal_to_market(payload.model_dump())
        return {"status": "OK", "mock_data": False, "link": link}

    @router.post("/link/signal-position")
    async def create_signal_position_link(payload: SignalPositionLinkRequest) -> dict[str, Any]:
        link = impact.link_signal_to_position(payload.model_dump())
        return {"status": "OK", "mock_data": False, "link": link}

    @router.post("/positions/{position_id}/thesis")
    async def create_position_thesis(position_id: str, payload: PositionThesisRequest) -> dict[str, Any]:
        thesis = impact.create_position_thesis_profile({"position_id": position_id, **payload.model_dump()})
        return {"status": "OK", "mock_data": False, "thesis": thesis}

    @router.post("/links")
    async def create_impact_link(payload: ImpactLinkRequest) -> dict[str, Any]:
        link = impact.create_impact_link(payload.model_dump())
        return {"status": "OK", "mock_data": False, "impact_link": link}

    return router

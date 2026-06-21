from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.repositories.whale_category_repository import WhaleCategoryRepository
from app.repositories.whale_event_repository import WhaleEventRepository
from app.repositories.whale_follow_decision_repository import WhaleFollowDecisionRepository
from app.repositories.whale_market_score_repository import WhaleMarketScoreRepository
from app.repositories.whale_performance_repository import WhalePerformanceRepository
from app.repositories.whale_profile_repository import WhaleProfileRepository
from app.repositories.whale_registry_repository import WhaleRegistryRepository
from app.repositories.whale_source_repository import WhaleSourceRepository
from app.whale_neuron.service import WhaleNeuronService


class WhaleScanRequest(BaseModel):
    source_id: str | None = None
    limit_per_source: int = Field(default=10, ge=1, le=100)
    reason: str = Field(min_length=1)


class ManualWhaleRequest(BaseModel):
    source_id: str = "manual"
    whale_id: str | None = None
    wallet_address: str | None = None
    trader_label: str | None = None
    market_id: str | None = None
    side: str = "UNKNOWN"
    action_type: str
    size_usd: float | None = Field(default=None, ge=0)
    size_shares: float | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, ge=0)
    event_time: str | None = None
    reason: str = Field(min_length=1)


def create_whale_router(*, connection_factory: DatabaseConnectionFactory | None = None, whale_service: WhaleNeuronService | None = None) -> APIRouter:
    router = APIRouter(prefix="/whales", tags=["whale-neuron"])
    factory = connection_factory or DatabaseConnectionFactory()
    service = whale_service or WhaleNeuronService(connection_factory=factory)
    registry = WhaleRegistryRepository()
    profiles = WhaleProfileRepository()
    categories = WhaleCategoryRepository()
    events = WhaleEventRepository()
    scores = WhaleMarketScoreRepository()
    decisions = WhaleFollowDecisionRepository()
    performance = WhalePerformanceRepository()
    sources = WhaleSourceRepository()

    @router.get("")
    async def list_whales(
        status: str | None = None,
        category: str | None = None,
        min_follow_value: float | None = Query(default=None, ge=0, le=1),
        max_noise_score: float | None = Query(default=None, ge=0, le=1),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        if not factory.enabled:
            return {"items": [], "count": 0}
        with factory.connect() as conn:
            rows = registry.list_v27(conn, status=status, limit=limit)
            items = []
            for row in rows:
                whale_id = row.get("whale_id") or row.get("wallet_address")
                profile = profiles.latest_profile(conn, str(whale_id)) if whale_id else None
                cats = categories.list_for_whale(conn, str(whale_id), limit=20) if whale_id else []
                if category and not any(cat.get("category") == category for cat in cats):
                    continue
                if min_follow_value is not None and float((profile or {}).get("follow_value") or 0) < min_follow_value:
                    continue
                if max_noise_score is not None and float((profile or {}).get("noise_score") or 1) > max_noise_score:
                    continue
                items.append({"whale": _serialize(row), "profile": _serialize(profile), "categories": [_serialize(cat) for cat in cats]})
        return {"items": items, "count": len(items)}

    @router.get("/events/recent")
    async def recent_events(
        limit: int = Query(default=100, ge=1, le=500),
        market_id: str | None = None,
        whale_id: str | None = None,
        event_classification: str | None = None,
    ) -> dict[str, Any]:
        if not factory.enabled:
            return {"items": [], "count": 0}
        with factory.connect() as conn:
            rows = [_serialize(row) for row in events.list_recent(conn, limit=limit, market_id=market_id, whale_id=whale_id, event_classification=event_classification)]
        return {"items": rows, "count": len(rows)}

    @router.get("/scores/top")
    async def top_scores(limit: int = Query(default=50, ge=1, le=500), min_follow_value: float | None = Query(default=None, ge=0, le=1), max_noise_score: float | None = Query(default=None, ge=0, le=1)) -> dict[str, Any]:
        if not factory.enabled:
            return {"items": [], "count": 0}
        with factory.connect() as conn:
            rows = [_serialize(row) for row in scores.list_top(conn, limit=limit, min_follow_value=min_follow_value, max_noise_score=max_noise_score)]
        return {"items": rows, "count": len(rows)}

    @router.get("/sources")
    async def whale_sources(enabled: bool | None = None, source_type: str | None = None) -> dict[str, Any]:
        if not factory.enabled:
            return {"sources": [], "count": 0}
        with factory.connect() as conn:
            rows = [_serialize(row) for row in sources.list_sources(conn, enabled=enabled, source_type=source_type.upper() if source_type else None)]
        return {"sources": rows, "count": len(rows)}

    @router.get("/market/{market_id}")
    async def market_whales(market_id: str, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        if not factory.enabled:
            return {"market_id": market_id, "events": [], "scores": [], "follow_decisions": [], "count": 0}
        with factory.connect() as conn:
            event_rows = [_serialize(row) for row in events.list_recent(conn, limit=limit, market_id=market_id)]
            score_rows = [_serialize(row) for row in scores.list_by_market(conn, market_id, limit=limit)]
            decision_rows = [_serialize(row) for row in decisions.list_for_market(conn, market_id, limit=limit)]
        return {"market_id": market_id, "events": event_rows, "scores": score_rows, "follow_decisions": decision_rows, "count": len(event_rows)}

    @router.get("/{whale_id}")
    async def whale_detail(whale_id: str, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        if not factory.enabled:
            return {"whale_id": whale_id, "whale": None, "profile": None, "categories": [], "recent_events": [], "performance_history": [], "follow_decisions": []}
        with factory.connect() as conn:
            whale = registry.get_by_whale_id(conn, whale_id)
            profile = profiles.latest_profile(conn, whale_id)
            cats = categories.list_for_whale(conn, whale_id, limit=20)
            event_rows = events.list_recent(conn, limit=limit, whale_id=whale_id)
            performance_rows = performance.list_for_whale(conn, whale_id, limit=limit)
            decision_rows = decisions.list_for_whale(conn, whale_id, limit=limit)
        return {
            "whale_id": whale_id,
            "whale": _serialize(whale),
            "profile": _serialize(profile),
            "categories": [_serialize(row) for row in cats],
            "recent_events": [_serialize(row) for row in event_rows],
            "performance_history": [_serialize(row) for row in performance_rows],
            "follow_decisions": [_serialize(row) for row in decision_rows],
        }

    @router.post("/scan")
    async def scan_whales(payload: WhaleScanRequest) -> dict[str, Any]:
        try:
            return service.scan_and_process_sources(source_id=payload.source_id, limit_per_source=payload.limit_per_source)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/manual")
    async def manual_whale(payload: ManualWhaleRequest) -> dict[str, Any]:
        try:
            body = payload.model_dump(mode="json")
            body.pop("reason", None)
            return service.process_manual_whale_event(body)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    output: dict[str, Any] = {}
    for key, value in dict(row).items():
        output[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return output


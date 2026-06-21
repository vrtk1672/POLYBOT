from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.repositories.social_hype_repository import SocialHypeRepository
from app.repositories.social_market_link_repository import SocialMarketLinkRepository
from app.repositories.social_narrative_repository import SocialNarrativeRepository
from app.repositories.social_noise_repository import SocialNoiseRepository
from app.repositories.social_normalized_event_repository import SocialNormalizedEventRepository
from app.repositories.social_sentiment_repository import SocialSentimentRepository
from app.repositories.social_source_repository import SocialSourceRepository
from app.social_neuron.price_lead_lag_detector import PriceLeadLagDetector
from app.social_neuron.service import SocialNeuronService


class SocialCollectRequest(BaseModel):
    source_id: str | None = None
    limit_per_source: int = Field(default=10, ge=1, le=100)
    reason: str = Field(min_length=1)


class ManualSocialRequest(BaseModel):
    source_id: str = "manual"
    platform: str = "manual"
    text: str = Field(min_length=1)
    author_handle: str | None = None
    url: str | None = None
    published_at: str | None = None
    category: str | None = None
    reason: str = Field(min_length=1)


def create_social_router(*, connection_factory: DatabaseConnectionFactory | None = None, social_service: SocialNeuronService | None = None) -> APIRouter:
    router = APIRouter(prefix="/social", tags=["social-neuron"])
    factory = connection_factory or DatabaseConnectionFactory()
    service = social_service or SocialNeuronService(connection_factory=factory)
    sources = SocialSourceRepository()
    events = SocialNormalizedEventRepository()
    links = SocialMarketLinkRepository()
    sentiments = SocialSentimentRepository()
    hype = SocialHypeRepository()
    noise = SocialNoiseRepository()
    narratives = SocialNarrativeRepository()
    lead_lag = PriceLeadLagDetector(connection_factory=factory)

    @router.get("/recent")
    async def recent_social(
        limit: int = Query(default=100, ge=1, le=500),
        platform: str | None = None,
        category: str | None = None,
        source_id: str | None = None,
        market_id: str | None = None,
        min_hype: float | None = Query(default=None, ge=0, le=1),
    ) -> dict[str, Any]:
        if not factory.enabled:
            return {"items": [], "count": 0, "filters": _filters(platform, category, source_id, market_id, min_hype)}
        with factory.connect() as conn:
            rows = events.list_for_market(conn, market_id, limit=limit) if market_id else events.list_recent(conn, limit=limit, platform=platform, category=category, source_id=source_id)
            output = []
            for row in rows:
                item = _serialize(row)
                item["links"] = [_serialize(link) for link in links.list_by_social_event(conn, row["social_event_id"], limit=20)]
                item["hype_scores"] = []
                for link in item["links"]:
                    scores = [_serialize(score) for score in hype.list_by_market(conn, link["market_id"], limit=5)]
                    if min_hype is not None:
                        scores = [score for score in scores if float(score.get("hype_pressure") or 0) >= min_hype]
                    item["hype_scores"].extend(scores)
                output.append(item)
        return {"items": output, "count": len(output), "filters": _filters(platform, category, source_id, market_id, min_hype)}

    @router.get("/sources")
    async def social_sources(enabled: bool | None = None, platform: str | None = None, category: str | None = None) -> dict[str, Any]:
        if not factory.enabled:
            return {"sources": [], "count": 0}
        with factory.connect() as conn:
            rows = [_serialize(row) for row in sources.list_sources(conn, enabled=enabled, platform=platform, category=category)]
        return {"sources": rows, "count": len(rows)}

    @router.get("/market/{market_id}")
    async def social_for_market(market_id: str, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        if not factory.enabled:
            return {"market_id": market_id, "linked_social": [], "sentiment_scores": [], "hype_scores": [], "narratives": [], "noise_scores": [], "lead_lag": {}, "count": 0}
        with factory.connect() as conn:
            market_links = [_serialize(row) for row in links.list_by_market(conn, market_id, limit=limit)]
            sentiment_rows = [_serialize(row) for row in sentiments.list_by_market(conn, market_id, limit=limit)]
            hype_rows = [_serialize(row) for row in hype.list_by_market(conn, market_id, limit=limit)]
            narrative_rows = [_serialize(row) for row in narratives.list_by_market(conn, market_id, limit=limit)]
            noise_rows = [_serialize(row) for row in noise.list_by_market(conn, market_id, limit=limit)]
        return {"market_id": market_id, "linked_social": market_links, "sentiment_scores": sentiment_rows, "hype_scores": hype_rows, "narratives": narrative_rows, "noise_scores": noise_rows, "lead_lag": lead_lag.detect_social_price_lead_lag(market_id), "count": len(market_links)}

    @router.get("/hype/top")
    async def top_hype(limit: int = Query(default=50, ge=1, le=500), min_hype: float | None = Query(default=None, ge=0, le=1), min_confidence: float | None = Query(default=None, ge=0, le=1)) -> dict[str, Any]:
        if not factory.enabled:
            return {"items": [], "count": 0}
        with factory.connect() as conn:
            rows = [_serialize(row) for row in hype.list_top(conn, limit=limit, min_hype=min_hype, min_confidence=min_confidence)]
        return {"items": rows, "count": len(rows)}

    @router.get("/narratives")
    async def social_narratives(status: str | None = "ACTIVE", limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        if not factory.enabled:
            return {"narratives": [], "count": 0}
        with factory.connect() as conn:
            rows = [_serialize(row) for row in narratives.list_narratives(conn, status=status, limit=limit)]
        return {"narratives": rows, "count": len(rows)}

    @router.post("/collect")
    async def collect_social(payload: SocialCollectRequest) -> dict[str, Any]:
        try:
            return service.collect_and_process_sources(source_id=payload.source_id, limit_per_source=payload.limit_per_source)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/manual")
    async def manual_social(payload: ManualSocialRequest) -> dict[str, Any]:
        try:
            return service.process_manual_social(payload.model_dump(mode="json"))
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in dict(row).items():
        output[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return output


def _filters(platform: str | None, category: str | None, source_id: str | None, market_id: str | None, min_hype: float | None) -> dict[str, Any]:
    return {"platform": platform, "category": category, "source_id": source_id, "market_id": market_id, "min_hype": min_hype}

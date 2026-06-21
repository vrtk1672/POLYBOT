from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.news_neuron.service import NewsNeuronService
from app.repositories.news_ai_analysis_repository import NewsAIAnalysisRepository
from app.repositories.news_impact_repository import NewsImpactRepository
from app.repositories.news_market_link_repository import NewsMarketLinkRepository
from app.repositories.news_normalized_event_repository import NewsNormalizedEventRepository
from app.repositories.news_source_repository import NewsSourceRepository


class NewsCollectRequest(BaseModel):
    source_id: str | None = None
    limit_per_source: int = Field(default=10, ge=1, le=100)
    reason: str = Field(min_length=1)


class ManualNewsRequest(BaseModel):
    source_id: str = "manual"
    title: str = Field(min_length=1)
    summary: str | None = None
    url: str | None = None
    published_at: str | None = None
    category: str | None = None
    reason: str = Field(min_length=1)


def create_news_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    news_service: NewsNeuronService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/news", tags=["news-neuron"])
    factory = connection_factory or DatabaseConnectionFactory()
    service = news_service or NewsNeuronService(connection_factory=factory)
    sources = NewsSourceRepository()
    events = NewsNormalizedEventRepository()
    links = NewsMarketLinkRepository()
    impacts = NewsImpactRepository()
    ai_analysis = NewsAIAnalysisRepository()

    @router.get("/recent")
    async def recent_news(
        limit: int = Query(default=100, ge=1, le=500),
        category: str | None = None,
        source_id: str | None = None,
        market_id: str | None = None,
        min_impact: float | None = Query(default=None, ge=0, le=1),
    ) -> dict[str, Any]:
        if not factory.enabled:
            return {"items": [], "count": 0, "filters": _filters(category, source_id, market_id, min_impact)}
        with factory.connect() as conn:
            if market_id:
                market_links = links.list_by_market(conn, market_id, limit=limit)
                news_ids = [row["news_event_id"] for row in market_links]
                rows = [events.get_event(conn, news_id) for news_id in news_ids]
                rows = [row for row in rows if row is not None]
            else:
                rows = events.list_recent(conn, limit=limit, category=category, source_id=source_id)
            output = []
            for row in rows:
                item = _serialize(row)
                item["links"] = [_serialize(link) for link in links.list_by_news(conn, row["news_event_id"], limit=20)]
                item["impact_scores"] = [
                    _serialize(score)
                    for score in impacts.list_by_market(conn, item["links"][0]["market_id"], limit=20)
                    if item["links"] and score["news_event_id"] == row["news_event_id"] and (min_impact is None or float(score["strength"] or 0) >= min_impact)
                ] if item["links"] else []
                output.append(item)
        return {"items": output, "count": len(output), "filters": _filters(category, source_id, market_id, min_impact)}

    @router.get("/sources")
    async def news_sources(enabled: bool | None = None, category: str | None = None) -> dict[str, Any]:
        if not factory.enabled:
            return {"sources": [], "count": 0}
        with factory.connect() as conn:
            rows = [_serialize(row) for row in sources.list_sources(conn, enabled=enabled, category=category)]
        return {"sources": rows, "count": len(rows)}

    @router.get("/market/{market_id}")
    async def news_for_market(market_id: str, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        if not factory.enabled:
            return {"market_id": market_id, "linked_news": [], "impact_scores": [], "ai_analysis": [], "count": 0}
        with factory.connect() as conn:
            market_links = [_serialize(row) for row in links.list_by_market(conn, market_id, limit=limit)]
            impact_rows = [_serialize(row) for row in impacts.list_by_market(conn, market_id, limit=limit)]
            ai_rows = [_serialize(row) for row in ai_analysis.list_for_market(conn, market_id, limit=20)]
        return {"market_id": market_id, "linked_news": market_links, "impact_scores": impact_rows, "ai_analysis": ai_rows, "count": len(market_links)}

    @router.get("/impact/top")
    async def top_news_impact(
        limit: int = Query(default=50, ge=1, le=500),
        min_strength: float | None = Query(default=None, ge=0, le=1),
        min_confidence: float | None = Query(default=None, ge=0, le=1),
    ) -> dict[str, Any]:
        if not factory.enabled:
            return {"items": [], "count": 0}
        with factory.connect() as conn:
            rows = [_serialize(row) for row in impacts.list_top(conn, limit=limit, min_strength=min_strength, min_confidence=min_confidence)]
        return {"items": rows, "count": len(rows)}

    @router.post("/collect")
    async def collect_news(payload: NewsCollectRequest) -> dict[str, Any]:
        try:
            return service.collect_and_process_sources(source_id=payload.source_id, limit_per_source=payload.limit_per_source)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/manual")
    async def manual_news(payload: ManualNewsRequest) -> dict[str, Any]:
        try:
            return service.process_manual_news(payload.model_dump(mode="json"))
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in dict(row).items():
        output[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return output


def _filters(category: str | None, source_id: str | None, market_id: str | None, min_impact: float | None) -> dict[str, Any]:
    return {"category": category, "source_id": source_id, "market_id": market_id, "min_impact": min_impact}


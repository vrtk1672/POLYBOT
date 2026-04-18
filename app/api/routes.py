from fastapi import APIRouter, Query, Request


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health(request: Request) -> dict:
        return await request.app.state.market_service.health()

    @router.get("/markets/top")
    async def top_markets(
        request: Request,
        limit: int | None = Query(default=None, ge=1, le=100),
    ) -> dict:
        items = await request.app.state.market_service.top_markets(limit=limit)
        serialized = [
            item.model_dump(mode="json", exclude={"market": {"raw_market": True}})
            for item in items
        ]
        return {"count": len(items), "items": serialized}

    @router.get("/markets/raw-count")
    async def raw_count(request: Request) -> dict:
        return await request.app.state.market_service.raw_counts()

    @router.get("/markets/last-refresh")
    async def last_refresh(request: Request) -> dict:
        return await request.app.state.market_service.last_refresh()

    return router

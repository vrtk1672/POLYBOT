from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api.routes import create_router
from app.config import Settings, get_settings
from app.ingestion.gamma_client import GammaClient
from app.ingestion.market_service import MarketService
from app.logging import get_logger, setup_logging
from app.scheduler import RefreshScheduler

logger = get_logger(__name__)


def build_market_service(settings: Settings) -> MarketService:
    gamma_client = GammaClient(settings=settings)
    return MarketService(settings=settings, gamma_client=gamma_client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    market_service: MarketService = app.state.market_service
    scheduler = RefreshScheduler(
        interval_seconds=settings.refresh_interval_seconds,
        refresh_coro=market_service.refresh,
    )

    logger.info(
        "startup_complete host=%s port=%s refresh_interval_seconds=%s top_n=%s",
        settings.api_host,
        settings.api_port,
        settings.refresh_interval_seconds,
        settings.top_n,
    )
    await market_service.refresh()
    await scheduler.start()
    app.state.scheduler = scheduler

    try:
        yield
    finally:
        await scheduler.stop()
        await market_service.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    market_service = build_market_service(settings)
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.market_service = market_service
    app.include_router(create_router())
    return app


def run() -> None:
    settings = get_settings()
    app = create_app()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_config=None)


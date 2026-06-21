from contextlib import asynccontextmanager
import os

import uvicorn
from fastapi import FastAPI

from app.api.ai_routes import create_ai_router
from app.api.brain_output_routes import create_brain_output_router
from app.api.brain_routes import create_brain_router
from app.api.capital_routes import create_capital_router
from app.api.coordinator_routes import create_coordinator_router
from app.api.data_foundation_routes import create_data_foundation_router
from app.api.dry_run_provenance_routes import create_dry_run_provenance_router
from app.api.event_routes import create_event_router
from app.api.execution_v2_routes import create_execution_v2_router
from app.api.exit_routes import create_exit_router
from app.api.impact_graph_routes import create_impact_graph_router
from app.api.learning_routes import create_learning_router
from app.api.link_coverage_routes import create_link_coverage_router
from app.api.lineage_coverage_routes import create_lineage_coverage_router
from app.api.market_neuron_routes import create_market_neuron_router
from app.api.market_memory_routes import create_market_memory_router
from app.api.mesh_dry_run_routes import create_mesh_dry_run_router
from app.api.neuron_routes import create_neuron_router
from app.api.news_routes import create_news_router
from app.api.no_trade_routes import create_no_trade_router
from app.api.opportunity_routes import create_opportunity_router
from app.api.position_thesis_routes import create_position_thesis_router
from app.api.routes import create_router
from app.api.risk_routes import create_risk_router
from app.api.rules_routes import create_rules_router
from app.api.runtime_routes import create_runtime_router
from app.api.signal_processing_routes import create_signal_processing_router
from app.api.signal_quality_routes import create_signal_quality_router
from app.api.signal_routes import create_signal_router
from app.api.social_routes import create_social_router
from app.api.strategy_routes import create_strategy_router
from app.api.system_power_routes import create_system_power_router
from app.api.whale_routes import create_whale_router
from app.config import ENV_FILE_STATUS, Settings, canonical_runtime_mode, get_settings
from app.ingestion.gamma_client import GammaClient
from app.ingestion.market_service import MarketService
from app.logging import get_logger, setup_logging
from app.runtime.safe_startup import SafeStartupPolicy
from app.runtime.service_registry import ServiceRegistry
from app.scheduler import RefreshScheduler
from app.stage4 import get_stage4_settings

logger = get_logger(__name__)


def build_market_service(settings: Settings) -> MarketService:
    gamma_client = GammaClient(settings=settings)
    return MarketService(settings=settings, gamma_client=gamma_client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    market_service: MarketService = app.state.market_service
    stage4_settings = get_stage4_settings()
    startup_result = SafeStartupPolicy().initialize()
    service_registry = ServiceRegistry()
    service_registry.register_service("event_bus", "event_mesh", status="RUNNING")
    service_registry.register_service("event_store", "event_mesh", status="RUNNING")
    service_registry.register_service("event_dispatcher", "event_mesh", status="RUNNING")
    service_registry.register_service("data_foundation", "data", status="RUNNING")
    service_registry.register_service("ai_brain", "intelligence", status="RUNNING")
    service_registry.register_service("news_neuron", "intelligence", status="RUNNING")
    service_registry.register_service("rules_neuron", "intelligence", status="RUNNING")
    service_registry.register_service("social_neuron", "intelligence", status="RUNNING")
    service_registry.register_service("whale_neuron", "intelligence", status="RUNNING")
    service_registry.register_service("market_neuron", "technical_truth", status="RUNNING")
    service_registry.register_service("market_memory", "memory", status="RUNNING")
    service_registry.register_service("context_capital_brains", "brains", status="RUNNING")
    service_registry.register_service("opportunity_cortex", "opportunity", status="RUNNING")
    service_registry.register_service("strategy_router", "strategy", status="RUNNING")
    service_registry.register_service("capital_allocator", "capital", status="RUNNING")
    service_registry.register_service("risk_gate_governor", "risk", status="RUNNING")
    service_registry.register_service("execution_cortex_v2", "execution", status="RUNNING")
    service_registry.register_service("exit_cortex_v2", "exits", status="RUNNING")
    service_registry.register_service("no_trade_intelligence", "no_trade", status="RUNNING")
    service_registry.register_service("feedback_learning_loop", "learning", status="RUNNING")
    scheduler = RefreshScheduler(
        interval_seconds=settings.refresh_interval_seconds,
        refresh_coro=market_service.refresh,
        service_registry=service_registry,
        initial_delay_seconds=settings.refresh_interval_seconds,
    )

    logger.info(
        "startup_complete host=%s port=%s refresh_interval_seconds=%s top_n=%s execution_mode=%s execution_backend=%s env_loaded=%s anthropic_key_present=%s live_enabled=%s live_kill_switch=%s",
        settings.api_host,
        settings.api_port,
        settings.refresh_interval_seconds,
        settings.top_n,
        canonical_runtime_mode(os.getenv("POLYBOT_RUNTIME_MODE")),
        os.getenv("POLYBOT_EXECUTION_BACKEND") or os.getenv("EXECUTION_BACKEND") or "paper",
        ENV_FILE_STATUS.loaded,
        bool(os.getenv("ANTHROPIC_API_KEY")),
        stage4_settings.live_trading_enabled,
        stage4_settings.live_kill_switch,
    )
    logger.info("v2_runtime_startup status=%s current_mode=%s warnings=%s", startup_result.get("status"), startup_result.get("current_mode"), startup_result.get("warnings"))
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
    app.include_router(create_system_power_router())
    app.include_router(create_runtime_router())
    app.include_router(create_signal_router())
    app.include_router(create_signal_quality_router())
    app.include_router(create_signal_processing_router())
    app.include_router(create_link_coverage_router())
    app.include_router(create_lineage_coverage_router())
    app.include_router(create_dry_run_provenance_router())
    app.include_router(create_neuron_router())
    app.include_router(create_event_router())
    app.include_router(create_data_foundation_router())
    app.include_router(create_ai_router())
    app.include_router(create_news_router())
    app.include_router(create_rules_router())
    app.include_router(create_social_router())
    app.include_router(create_whale_router())
    app.include_router(create_market_neuron_router())
    app.include_router(create_market_memory_router())
    app.include_router(create_brain_router())
    app.include_router(create_brain_output_router())
    app.include_router(create_coordinator_router())
    app.include_router(create_impact_graph_router())
    app.include_router(create_position_thesis_router())
    app.include_router(create_mesh_dry_run_router())
    app.include_router(create_opportunity_router())
    app.include_router(create_strategy_router())
    app.include_router(create_capital_router())
    app.include_router(create_risk_router())
    app.include_router(create_execution_v2_router())
    app.include_router(create_exit_router())
    app.include_router(create_no_trade_router())
    app.include_router(create_learning_router())

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {"status": "ok", "app": "polybot", "ready": True}

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_config=None)

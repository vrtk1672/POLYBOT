from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.db.connection import DatabaseConnectionFactory
from app.services.signal_lineage import SignalLineageService
from app.services.neuron_signals import NeuronSignalService


def create_signal_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    signal_service: NeuronSignalService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/signals", tags=["signals"])
    factory = connection_factory or DatabaseConnectionFactory()
    service = signal_service or NeuronSignalService(connection_factory=factory)
    lineage_service = SignalLineageService(connection_factory=factory)

    @router.get("/recent")
    async def recent_signals(
        limit: int = Query(default=50, ge=1, le=500),
        neuron: str | None = None,
        market_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        signals = service.list_recent_signals(
            limit=limit,
            neuron=neuron,
            market_id=market_id,
            status=status,
        )
        return {"status": "OK", "mock_data": False, "count": len(signals), "signals": signals}

    @router.get("/market/{market_id}")
    async def market_signals(market_id: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        signals = service.list_market_signals(market_id, limit=limit)
        return {
            "status": "OK",
            "mock_data": False,
            "market_id": market_id,
            "count": len(signals),
            "signals": signals,
        }

    @router.get("/neuron/{neuron_name}")
    async def neuron_signals(neuron_name: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        signals = service.list_neuron_signals(neuron_name, limit=limit)
        return {
            "status": "OK",
            "mock_data": False,
            "neuron": neuron_name,
            "count": len(signals),
            "signals": signals,
        }

    @router.get("/correlation/{correlation_id}")
    async def correlation_signals(correlation_id: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        items = lineage_service.list_signals_by_correlation_id(correlation_id, limit=limit)
        return {"status": "OK", "mock_data": False, "correlation_id": correlation_id, "count": len(items), "signals": items}

    @router.get("/source/{source_name}")
    async def source_signals(source_name: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        items = lineage_service.list_signals_by_source(source_name, limit=limit)
        return {"status": "OK", "mock_data": False, "source_name": source_name, "count": len(items), "signals": items}

    @router.get("/producer/{producer_name}")
    async def producer_signals(producer_name: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        items = lineage_service.list_signals_by_producer(producer_name, limit=limit)
        return {"status": "OK", "mock_data": False, "producer_name": producer_name, "count": len(items), "signals": items}

    @router.get("/{signal_id}/lineage")
    async def signal_lineage(signal_id: str) -> dict[str, Any]:
        item = lineage_service.get_signal_lineage(signal_id)
        return {
            "status": "OK" if item else "MISSING",
            "mock_data": False,
            "signal_id": signal_id,
            "signal": item["signal"] if item else None,
            "lineage": item["lineage"] if item else None,
        }

    return router

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.db.connection import DatabaseConnectionFactory
from app.services.neuron_registry import NeuronRegistryService


def create_neuron_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    neuron_service: NeuronRegistryService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/neurons", tags=["neurons"])
    factory = connection_factory or DatabaseConnectionFactory()
    service = neuron_service or NeuronRegistryService(connection_factory=factory)

    @router.get("")
    async def list_neurons(
        status: str | None = None,
        category: str | None = None,
        enabled: bool | None = Query(default=None),
    ) -> dict[str, Any]:
        neurons = service.list_neurons(status=status, category=category, enabled=enabled)
        return {"status": "OK", "mock_data": False, "count": len(neurons), "neurons": neurons}

    @router.get("/{neuron_name}")
    async def get_neuron(neuron_name: str) -> dict[str, Any]:
        neuron = service.get_neuron(neuron_name)
        return {"status": "OK" if neuron else "MISSING", "mock_data": False, "neuron": neuron}

    return router

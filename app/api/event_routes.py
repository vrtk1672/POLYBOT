from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.events.dlq import DeadLetterQueue
from app.events.envelope import redact_event_data
from app.events.event_bus import EventBus
from app.events.event_errors import EventReplayDenied
from app.events.replay import EventReplayService
from app.events.types import validate_event_type
from app.repositories.event_store_repository import EventStoreRepository


class ReplayRequest(BaseModel):
    requested_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    event_id: str | None = None
    filter: dict[str, Any] = Field(default_factory=dict)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in dict(row).items():
        if key in {"payload_json", "metadata_json", "failed_payload_json", "filter_json"}:
            output[key] = redact_event_data(value or {})
        elif hasattr(value, "isoformat"):
            output[key] = value.isoformat()
        else:
            output[key] = value
    return output


def create_event_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    event_bus: EventBus | None = None,
    replay_service: EventReplayService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/events", tags=["events"])
    factory = connection_factory or DatabaseConnectionFactory()
    repository = EventStoreRepository()
    event_bus = event_bus or EventBus(connection_factory=factory)
    replay_service = replay_service or EventReplayService(connection_factory=factory, event_bus=event_bus)
    dlq = DeadLetterQueue(connection_factory=factory, repository=repository)

    @router.get("/recent")
    async def recent_events(
        limit: int = Query(default=100, ge=1, le=500),
        event_type: str | None = None,
        correlation_id: str | None = None,
        aggregate_id: str | None = None,
    ) -> dict[str, Any]:
        if event_type:
            try:
                event_type = validate_event_type(event_type)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not factory.enabled:
            return {"events": [], "count": 0, "filters": {}, "latest_stored_at": None}
        with factory.connect() as conn:
            rows = repository.list_recent_events(
                conn,
                limit=limit,
                event_type=event_type,
                correlation_id=correlation_id,
                aggregate_id=aggregate_id,
            )
        events = [_serialize_row(row) for row in rows]
        latest = events[0].get("stored_at") if events else None
        return {
            "events": events,
            "count": len(events),
            "filters": {
                "event_type": event_type,
                "correlation_id": correlation_id,
                "aggregate_id": aggregate_id,
            },
            "latest_stored_at": latest,
        }

    @router.get("/dlq")
    async def dlq_events(
        status: str = Query(default="OPEN"),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        items = [_serialize_row(row) for row in dlq.list_dlq(status=status, limit=limit)]
        open_count = 0
        if factory.enabled:
            with factory.connect() as conn:
                open_count = repository.get_event_lag(conn)["open_dlq_count"]
        return {"items": items, "count": len(items), "open_count": open_count}

    @router.post("/replay")
    async def replay_events(payload: ReplayRequest) -> dict[str, Any]:
        filters = dict(payload.filter or {})
        if payload.event_id:
            filters["event_id"] = payload.event_id
        if not filters:
            raise HTTPException(status_code=400, detail="event_id or filter is required")
        try:
            replay_id = replay_service.create_replay_job(
                requested_by=payload.requested_by,
                reason=payload.reason,
                filters=filters,
            )
            result = replay_service.run_replay_job(replay_id)
            return {"replay_id": replay_id, **result}
        except EventReplayDenied as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/lag")
    async def event_lag() -> dict[str, Any]:
        if not factory.enabled:
            return {
                "events_per_minute": 0.0,
                "failed_events": 0,
                "dlq_count": 0,
                "open_dlq_count": 0,
                "consumer_count": 0,
                "paused_consumers": 0,
                "last_event_time": None,
                "lag_by_consumer": [],
            }
        with factory.connect() as conn:
            metrics = repository.get_event_lag(conn)
        if hasattr(metrics.get("last_event_time"), "isoformat"):
            metrics["last_event_time"] = metrics["last_event_time"].isoformat()
        metrics["lag_by_consumer"] = []
        return metrics

    return router

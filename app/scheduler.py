import asyncio
from contextlib import suppress

from app.events.event_bus import EventBus
from app.events.types import EventType
from app.logging import get_logger
from app.runtime.modes import RuntimeAction
from app.runtime.runtime_errors import RuntimePermissionDenied
from app.runtime.service_registry import ServiceRegistry
from app.runtime.state_governor import StateGovernor

logger = get_logger(__name__)


class RefreshScheduler:
    def __init__(
        self,
        interval_seconds: int,
        refresh_coro,
        service_registry: ServiceRegistry | None = None,
        event_bus: EventBus | None = None,
        initial_delay_seconds: int = 0,
    ):
        self._interval_seconds = interval_seconds
        self._initial_delay_seconds = max(0, initial_delay_seconds)
        self._refresh_coro = refresh_coro
        self._service_registry = service_registry or ServiceRegistry()
        self._event_bus = event_bus or EventBus()
        self._governor = StateGovernor()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="polybot-refresh-loop")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        if self._initial_delay_seconds > 0:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._initial_delay_seconds)
                return
            except TimeoutError:
                pass
        while not self._stop_event.is_set():
            await self._run_once()

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                continue

    async def _run_once(self) -> None:
        started_event = self._publish_runtime_event(EventType.RUNTIME_CYCLE_STARTED.value, {"source": "scheduler"})
        try:
            self._service_registry.heartbeat("scheduler", status="RUNNING")
            if not self._governor.can_execute(RuntimeAction.COLLECT_DATA):
                self._service_registry.heartbeat("scheduler", status="BLOCKED_BY_MODE")
                logger.warning("refresh_cycle_blocked_by_runtime_mode")
                self._publish_runtime_event(
                    EventType.RUNTIME_CYCLE_FINISHED.value,
                    {"source": "scheduler", "status": "BLOCKED_BY_MODE"},
                    causation_id=started_event.event_id if started_event else None,
                )
                raise RuntimePermissionDenied("scheduler refresh blocked by runtime mode")
            await self._refresh_coro()
            self._service_registry.mark_success("scheduler")
            self._publish_runtime_event(
                EventType.RUNTIME_CYCLE_FINISHED.value,
                {"source": "scheduler", "status": "COMPLETED"},
                causation_id=started_event.event_id if started_event else None,
            )
        except RuntimePermissionDenied:
            pass
        except Exception:
            self._service_registry.mark_error("scheduler")
            logger.exception("refresh_cycle_failed")
            self._publish_runtime_event(
                EventType.RUNTIME_CYCLE_FINISHED.value,
                {"source": "scheduler", "status": "FAILED"},
                causation_id=started_event.event_id if started_event else None,
            )

    async def _run_once_for_test(self) -> None:
        await self._run_once()

    def _publish_runtime_event(self, event_type: str, payload: dict[str, object], *, causation_id: str | None = None):
        try:
            return self._event_bus.publish(
                event_type,
                payload,
                source_service="scheduler",
                aggregate_type="scheduler_cycle",
                correlation_id=payload.get("cycle_id") if isinstance(payload.get("cycle_id"), str) else None,
                causation_id=causation_id,
                metadata={"non_trading_event": True},
            )
        except Exception:
            logger.exception("scheduler_event_publish_failed event_type=%s", event_type)
            return None

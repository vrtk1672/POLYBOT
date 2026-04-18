import asyncio
from contextlib import suppress

from app.logging import get_logger

logger = get_logger(__name__)


class RefreshScheduler:
    def __init__(self, interval_seconds: int, refresh_coro):
        self._interval_seconds = interval_seconds
        self._refresh_coro = refresh_coro
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
        while not self._stop_event.is_set():
            try:
                await self._refresh_coro()
            except Exception:
                logger.exception("refresh_cycle_failed")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                continue


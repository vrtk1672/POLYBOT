from __future__ import annotations

from app.db.migrate import run_migrations
from app.scheduler import RefreshScheduler
from app.services.system_power import SystemPowerService


async def _noop_refresh(calls: list[str]) -> None:
    calls.append("refresh")


def test_system_off_blocks_scheduler_refresh(postgres_test_schema) -> None:
    run_migrations()
    SystemPowerService().turn_off(actor="operator", reason="manual_system_off")
    calls: list[str] = []
    scheduler = RefreshScheduler(interval_seconds=1, refresh_coro=lambda: _noop_refresh(calls))

    import asyncio

    asyncio.run(scheduler._run_once_for_test())

    assert calls == []


def test_system_on_allows_scheduler_refresh(postgres_test_schema) -> None:
    run_migrations()
    SystemPowerService().turn_on(actor="operator", reason="manual_system_on")
    calls: list[str] = []
    scheduler = RefreshScheduler(interval_seconds=1, refresh_coro=lambda: _noop_refresh(calls))

    import asyncio

    asyncio.run(scheduler._run_once_for_test())

    assert calls == ["refresh"]

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.runtime.modes import RuntimeMode
from app.runtime.state_governor import StateGovernor
from app.scheduler import RefreshScheduler
from app.services.live_runtime import LiveTradingService
from app.services.runtime_paper_trading import RuntimePaperTradingService


def _scored_market() -> ScoredMarket:
    now = datetime.now(UTC)
    return ScoredMarket(
        market=NormalizedMarket(
            market_id="market-1",
            event_id="event-1",
            event_title="Question",
            question="Question",
            yes_price=0.45,
            no_price=0.55,
            accepting_orders=True,
            raw_market={"clobTokenIds": ["yes", "no"]},
        ),
        score=80,
        breakdown=ScoreBreakdown(
            price_attractiveness=20,
            time_to_close=20,
            liquidity_volume=20,
            market_activity=20,
        ),
        reason="test",
        computed_at=now,
    )


def _setup(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    governor = StateGovernor(connection_factory=factory)
    governor.ensure_initial_state()
    return factory, governor


@pytest.mark.asyncio
async def test_scheduler_respects_kill(postgres_test_schema) -> None:
    _, governor = _setup(postgres_test_schema)
    governor.activate_kill(actor="operator", reason="stop")
    calls = 0

    async def refresh():
        nonlocal calls
        calls += 1

    scheduler = RefreshScheduler(interval_seconds=10, refresh_coro=refresh)
    await scheduler._run_once_for_test()
    assert calls == 0


def test_paper_runtime_blocked_in_data_only(postgres_test_schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup(postgres_test_schema)
    called = False

    def fake_record_cycle(self, cycle_result):
        nonlocal called
        called = True

    monkeypatch.setattr("app.services.execution_aware_paper.ExecutionAwarePaperService.record_cycle", fake_record_cycle)
    service = RuntimePaperTradingService(settings=None, connection_factory=DatabaseConnectionFactory())
    service._execution_mode = "PAPER"
    service.process_cycle(cycle_id="cycle-1", scored_markets=[_scored_market()])
    assert called is False


def test_live_runtime_blocked_outside_small_live(postgres_test_schema, monkeypatch: pytest.MonkeyPatch) -> None:
    factory, governor = _setup(postgres_test_schema)
    governor.request_mode_change(RuntimeMode.PAPER, actor="operator", reason="paper validation")

    def fail_build_plan(*args, **kwargs):
        raise AssertionError("live plan should not be built")

    monkeypatch.setattr("app.services.live_runtime.build_live_execution_plan", fail_build_plan)
    service = LiveTradingService(settings=None, connection_factory=factory)
    result = service.record_cycle(SimpleNamespace(cycle_id="cycle-1"))
    assert result is not None
    assert result.persisted_count == 0


def test_no_live_order_can_be_sent_in_paper(postgres_test_schema) -> None:
    _, governor = _setup(postgres_test_schema)
    governor.request_mode_change(RuntimeMode.PAPER, actor="operator", reason="paper validation")
    assert not governor.can_execute("SEND_LIVE_ORDER")

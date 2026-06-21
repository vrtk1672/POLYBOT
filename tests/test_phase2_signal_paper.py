from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import brain
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.services.query.paper_query_service import PaperQueryService
from app.services.recorders.phase1_cycle_persistence import Phase1CyclePersistenceService
from app.services.signal_paper import SignalPaperRunResult, SignalPaperService
from app.stage2.claude_analyst import MarketRecommendation


def _make_market(
    *,
    market_id: str,
    question: str,
    yes_price: float,
    no_price: float,
    score: float,
) -> ScoredMarket:
    now = datetime.now(UTC)
    return ScoredMarket(
        market=NormalizedMarket(
            market_id=market_id,
            event_id=f"event-{market_id}",
            event_title=question,
            question=question,
            yes_price=yes_price,
            no_price=no_price,
            last_trade_price=yes_price,
            best_bid=max(yes_price - 0.01, 0.01),
            best_ask=min(yes_price + 0.01, 0.99),
            spread=0.02,
            liquidity=10000.0,
            volume=25000.0,
            volume_24h=12000.0,
            open_interest=2000.0,
            comment_count=10,
            competitive=0.8,
            accepting_orders=True,
            updated_at=now,
            raw_market={"clobTokenIds": [f"{market_id}1", f"{market_id}2"]},
        ),
        score=score,
        breakdown=ScoreBreakdown(
            price_attractiveness=25.0,
            time_to_close=20.0,
            liquidity_volume=15.0,
            market_activity=10.0,
        ),
        reason="test score",
        computed_at=now,
    )


def _make_recommendation(
    *,
    rank: int,
    question: str,
    action: str,
    confidence: float,
    score: float,
    yes_price: float,
    no_price: float,
) -> MarketRecommendation:
    return MarketRecommendation(
        rank=rank,
        question=question,
        confidence=confidence,
        action=action,
        reason="test recommendation",
        yes_price=yes_price,
        no_price=no_price,
        score=score,
        computed_at=datetime.now(UTC).isoformat(),
    )


def _persist_cycle_for_paper() -> tuple[str, object]:
    persistence = Phase1CyclePersistenceService()
    top_scored = [
        _make_market(
            market_id="553866",
            question="Spurs",
            yes_price=0.15,
            no_price=0.85,
            score=71.2,
        ),
        _make_market(
            market_id="564198",
            question="Pistons",
            yes_price=0.20,
            no_price=0.80,
            score=70.8,
        ),
        _make_market(
            market_id="566136",
            question="PSG",
            yes_price=0.25,
            no_price=0.75,
            score=72.5,
        ),
    ]
    recommendations = [
        _make_recommendation(
            rank=1,
            question="Spurs",
            action="BUY_NO",
            confidence=0.68,
            score=71.2,
            yes_price=0.15,
            no_price=0.85,
        ),
        _make_recommendation(
            rank=2,
            question="Pistons",
            action="BUY_NO",
            confidence=0.70,
            score=70.8,
            yes_price=0.20,
            no_price=0.80,
        ),
        _make_recommendation(
            rank=3,
            question="PSG",
            action="BUY_NO",
            confidence=0.72,
            score=72.5,
            yes_price=0.25,
            no_price=0.75,
        ),
    ]
    handle = persistence.open_cycle(
        mode="PAPER_SIGNAL",
        trigger_source="pytest",
        top_n=3,
        pages_requested=1,
    )
    cycle_result = type(
        "CycleResultStub",
        (),
        {
            "top_scored": top_scored,
            "recommendations": recommendations,
            "cycle_id": handle.cycle_id,
            "all_scored": top_scored,
        },
    )()
    persistence.persist_cycle_snapshot(handle=handle, cycle_result=cycle_result)
    return handle.cycle_id, cycle_result


class FakeSignalExecutionClient:
    def __init__(self) -> None:
        self.submit_called = False

    def get_open_orders(self) -> list[dict[str, str]]:
        return []

    def get_order_book_summary(self, token_id: str) -> SimpleNamespace:
        if token_id == "5661362":
            return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size="0")
        return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size="0.1")

    def get_balance_allowance(self, *, token_id: str | None = None) -> dict[str, dict[str, str | float]]:
        return {"collateral": {"balance": "100000000", "balance_usd": 100.0}}

    def submit_order(self, intent):  # noqa: ANN001
        self.submit_called = True
        raise AssertionError("Signal Paper must never submit a real order")


def test_signal_paper_migrations_create_tables(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        tables = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
            """
        ).fetchall()
    table_names = {row["table_name"] for row in tables}
    assert {"paper_runs", "paper_signals"} <= table_names


def test_signal_paper_run_persists_selected_and_blocked_signals(postgres_test_schema) -> None:
    run_migrations()
    _, cycle_result = _persist_cycle_for_paper()
    fake_client = FakeSignalExecutionClient()
    service = SignalPaperService(execution_client=fake_client)

    result = service.record_cycle(cycle_result)
    assert result is not None
    assert fake_client.submit_called is False

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        runs = conn.execute("SELECT * FROM paper_runs").fetchall()
        signals = conn.execute(
            "SELECT * FROM paper_signals ORDER BY created_at ASC, market_id ASC"
        ).fetchall()
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()

    assert len(runs) == 1
    assert runs[0]["status"] == "COMPLETED"
    assert len(signals) == 3
    assert any(row["signal_type"] == "WOULD_ENTER" for row in signals)
    assert any(row["signal_type"] == "WOULD_BLOCK" for row in signals)
    assert any(row["signal_type"] == "WOULD_SKIP" for row in signals)
    assert len(live_orders) == 0


def test_signal_paper_query_service_returns_coherent_views(postgres_test_schema) -> None:
    run_migrations()
    cycle_id, cycle_result = _persist_cycle_for_paper()
    service = SignalPaperService(execution_client=FakeSignalExecutionClient())
    result = service.record_cycle(cycle_result)
    assert result is not None

    queries = PaperQueryService()
    summary = queries.get_paper_run_summary(result.paper_run_id)
    assert summary is not None
    assert str(summary["paper_run"]["cycle_id"]) == cycle_id
    assert summary["signal_counts"]["would_enter"] == 1
    assert summary["signal_counts"]["would_block"] == 1
    assert summary["signal_counts"]["would_skip"] == 1

    signals = queries.list_paper_signals_for_run(result.paper_run_id)
    assert len(signals) == 3
    would_enter = next(row for row in signals if row["signal_type"] == "WOULD_ENTER")
    signal_details = queries.get_paper_signal_details(str(would_enter["id"]))
    assert signal_details is not None
    assert signal_details["market_id"] == would_enter["market_id"]

    comparison = queries.compare_cycle_decision_to_paper_signal(str(would_enter["id"]))
    assert comparison is not None
    assert comparison["decision"] is not None
    assert comparison["paper_signal"]["market_id"] == comparison["decision"]["market_id"]


@pytest.mark.asyncio
async def test_signal_paper_runtime_hook_uses_separate_service(
    postgres_test_schema,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_migrations()
    _, cycle_result = _persist_cycle_for_paper()
    called: dict[str, object] = {}

    class FakeSignalPaperService:
        def record_cycle(self, cycle_result_arg) -> SignalPaperRunResult:  # noqa: ANN001
            called["cycle_id"] = cycle_result_arg.cycle_id
            return SignalPaperRunResult(
                paper_run_id="paper-run-test",
                signals_emitted_count=3,
                candidates_selected_count=1,
                selected_market_id="566136",
            )

    monkeypatch.setattr(brain, "SignalPaperService", FakeSignalPaperService)

    await brain.handle_signal_paper_path(cycle_result)

    assert called["cycle_id"] == cycle_result.cycle_id

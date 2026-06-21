from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import brain
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.services.live_execution_plan import (
    ExecutionCandidateEvaluation,
    LiveExecutionPlan,
)
from app.services.query.paper_query_service import PaperQueryService
from app.services.recorders.phase1_cycle_persistence import Phase1CyclePersistenceService
from app.services.shadow_live import ShadowLiveRunResult, ShadowLiveService
from app.services.signal_paper import SignalPaperService
from app.stage2.claude_analyst import MarketRecommendation
from app.stage4 import LiveGuard
from app.stage4.order_builder import LiveOrderIntent


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


def _persist_cycle_for_shadow() -> tuple[str, object]:
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
            confidence=0.75,
            score=71.2,
            yes_price=0.15,
            no_price=0.85,
        ),
        _make_recommendation(
            rank=2,
            question="PSG",
            action="BUY_NO",
            confidence=0.72,
            score=72.5,
            yes_price=0.25,
            no_price=0.75,
        ),
    ]
    handle = persistence.open_cycle(
        mode="SHADOW_LIVE",
        trigger_source="pytest",
        top_n=2,
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


class FakeShadowExecutionClient:
    def __init__(self) -> None:
        self.submit_called = False
        self.create_called = False

    def get_open_orders(self) -> list[dict[str, str]]:
        return []

    def get_order_book_summary(self, token_id: str) -> SimpleNamespace:
        if token_id == "5538662":
            return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size="0")
        return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size="0.1")

    def get_balance_allowance(self, *, token_id: str | None = None) -> dict[str, dict[str, str | float]]:
        return {"collateral": {"balance": "100000000", "balance_usd": 100.0}}

    def auth_context(self) -> dict[str, str]:
        return {"mode": "shadow-test"}

    def create_signed_order(self, intent):  # noqa: ANN001
        self.create_called = True
        return {"token_id": intent.token_id, "price": intent.price, "size": intent.size}

    def submit_order(self, intent):  # noqa: ANN001
        self.submit_called = True
        raise AssertionError("Shadow Live must never submit a real order")


def test_shadow_live_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {
        "shadow_runs",
        "shadow_orders",
        "shadow_order_events",
        "shadow_positions",
        "shadow_position_events",
    } <= table_names


def test_shadow_live_run_persists_blocked_and_would_submit_orders(postgres_test_schema) -> None:
    run_migrations()
    _, cycle_result = _persist_cycle_for_shadow()
    fake_client = FakeShadowExecutionClient()
    service = ShadowLiveService(execution_client=fake_client)

    result = service.record_cycle(cycle_result)
    assert result is not None
    assert fake_client.submit_called is False
    assert fake_client.create_called is True

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        runs = conn.execute("SELECT * FROM shadow_runs").fetchall()
        orders = conn.execute("SELECT * FROM shadow_orders ORDER BY created_at ASC, market_id ASC").fetchall()
        order_events = conn.execute(
            "SELECT * FROM shadow_order_events ORDER BY event_at ASC, created_at ASC"
        ).fetchall()
        positions = conn.execute("SELECT * FROM shadow_positions").fetchall()
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()

    assert len(runs) == 1
    assert runs[0]["status"] == "COMPLETED"
    assert len(orders) == 2
    assert any(row["status"] == "INVALID_REQUEST" for row in orders)
    assert any(row["status"] == "WOULD_SUBMIT" for row in orders)
    assert len(order_events) == 4
    assert len(positions) == 1
    assert positions[0]["current_status"] == "PENDING_SUBMISSION"
    assert len(live_orders) == 0


def test_shadow_live_query_service_returns_coherent_views(postgres_test_schema) -> None:
    run_migrations()
    _, cycle_result = _persist_cycle_for_shadow()
    fake_client = FakeShadowExecutionClient()
    SignalPaperService(execution_client=fake_client).record_cycle(cycle_result)
    result = ShadowLiveService(execution_client=fake_client).record_cycle(cycle_result)
    assert result is not None

    queries = PaperQueryService()
    summary = queries.get_shadow_run_summary(result.shadow_run_id)
    assert summary is not None
    assert summary["order_counts"]["blocked"] == 1
    assert summary["order_counts"]["would_submit"] == 1
    assert summary["position_counts"]["pending_submission"] == 1

    orders = queries.list_shadow_orders_for_run(result.shadow_run_id)
    assert len(orders) == 2
    selected_order = next(row for row in orders if row["status"] == "WOULD_SUBMIT")
    order_details = queries.get_shadow_order_details(str(selected_order["id"]))
    assert order_details is not None
    assert [row["new_status"] for row in order_details["events"]] == ["CREATED", "WOULD_SUBMIT"]
    assert order_details["shadow_order"]["raw_intent_json"]["execution_contract"]["backend_target"] == "shadow_live"
    assert order_details["shadow_order"]["raw_policy_json"]["execution_result"]["result_status"] == "WOULD_SUBMIT"

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        position = conn.execute("SELECT * FROM shadow_positions LIMIT 1").fetchone()
    assert position is not None
    lifecycle = queries.get_shadow_position_lifecycle(str(position["id"]))
    assert lifecycle is not None
    assert lifecycle["shadow_position"]["current_status"] == "PENDING_SUBMISSION"
    assert [row["event_type"] for row in lifecycle["events"]] == ["PENDING_SUBMISSION_CREATED"]

    comparison = queries.compare_shadow_order_to_paper_order_or_signal(str(selected_order["id"]))
    assert comparison is not None
    assert len(comparison["paper_signals"]) >= 1


def test_shadow_and_live_paths_share_execution_plan_builder(postgres_test_schema, monkeypatch: pytest.MonkeyPatch) -> None:
    run_migrations()
    _, cycle_result = _persist_cycle_for_shadow()
    calls: list[str] = []

    ranked = SimpleNamespace(
        candidate=SimpleNamespace(
            market=SimpleNamespace(market_id="566136"),
            item=SimpleNamespace(market=SimpleNamespace(market_id="566136")),
        ),
        total_rank=81.0,
        reason="shared test",
    )
    intent = LiveOrderIntent(
        market_id="566136",
        token_id="5661362",
        question="PSG",
        action="BUY_NO",
        side="BUY",
        bucket="high",
        price=0.75,
        size=1.0,
        notional_usd=0.75,
        tick_size="0.01",
        neg_risk=True,
        min_order_size=0.1,
    )
    fake_plan = LiveExecutionPlan(
        source_markets=cycle_result.top_scored,
        allowed_universe=[],
        ranked_candidates=[ranked],
        skipped=[],
        open_orders=[],
        open_orders_error=None,
        evaluations=[
            ExecutionCandidateEvaluation(
                ranked=ranked,
                market_id="566136",
                token_id="5661362",
                tick_size="0.01",
                neg_risk=True,
                min_order_size=0.1,
                balance_info={"collateral": {"balance_usd": 100.0}},
                collateral_balance=100.0,
                intent=intent,
                policy_decision=SimpleNamespace(allowed=True, reasons=[]),
                guard_decision=SimpleNamespace(allowed=True, reasons=[]),
                decision_stage="ready_to_submit",
                status="WOULD_SUBMIT",
                reason_code="would_submit",
                reason_text="shared builder",
            )
        ],
    )

    def fake_builder(*args, **kwargs):  # noqa: ANN002, ANN003
        calls.append("builder")
        return fake_plan

    class FakeLiveClient:
        def __init__(self, settings) -> None:  # noqa: ANN001
            self.submit_called = False

        def auth_context(self) -> dict[str, str]:
            return {"mode": "test"}

        def create_signed_order(self, intent_arg):  # noqa: ANN001
            return {"market_id": intent_arg.market_id}

        def submit_order(self, intent_arg):  # noqa: ANN001
            self.submit_called = True
            raise AssertionError("Shadow/live shared test must not submit")

    monkeypatch.setattr(brain, "build_live_execution_plan", fake_builder)
    monkeypatch.setattr("app.services.shadow_live.build_live_execution_plan", fake_builder)
    monkeypatch.setattr(brain, "Stage4ExecutionClient", FakeLiveClient)

    shadow_result = ShadowLiveService(execution_client=FakeShadowExecutionClient(), guard=LiveGuard(brain.get_stage4_settings())).record_cycle(cycle_result)
    assert shadow_result is not None

    import asyncio

    asyncio.run(brain.handle_live_order_path(cycle_result, live=False, armed=False))

    assert calls == ["builder", "builder"]


@pytest.mark.asyncio
async def test_shadow_live_runtime_hook_uses_separate_service(
    postgres_test_schema,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_migrations()
    _, cycle_result = _persist_cycle_for_shadow()
    called: dict[str, object] = {}

    class FakeShadowLiveService:
        def record_cycle(self, cycle_result_arg) -> ShadowLiveRunResult:  # noqa: ANN001
            called["cycle_id"] = cycle_result_arg.cycle_id
            return ShadowLiveRunResult(
                shadow_run_id="shadow-run-test",
                shadow_orders_count=2,
                candidates_selected_count=1,
                selected_market_id="566136",
            )

    monkeypatch.setattr(brain, "ShadowLiveService", FakeShadowLiveService)

    await brain.handle_shadow_live_path(cycle_result)

    assert called["cycle_id"] == cycle_result.cycle_id

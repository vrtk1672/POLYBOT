from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import brain
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.services.recorders.execution_memory import ExecutionMemoryPersistenceService
from app.services.recorders.phase1_cycle_persistence import Phase1CyclePersistenceService
from app.stage2.claude_analyst import MarketRecommendation
from app.stage4.config import Stage4Settings


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


def _make_intent(
    *,
    market_id: str = "566136",
    token_id: str = "5661362",
    action: str = "BUY_NO",
    price: float = 0.75,
    size: float = 5.0,
    notional_usd: float = 3.75,
) -> SimpleNamespace:
    return SimpleNamespace(
        market_id=market_id,
        token_id=token_id,
        question="PSG",
        action=action,
        side="BUY",
        bucket="high",
        price=price,
        size=size,
        notional_usd=notional_usd,
        tick_size="0.01",
        neg_risk=True,
        min_order_size=1.0,
    )


def _persist_cycle_for_market() -> tuple[str, object]:
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
        mode="LIVE_SUBMIT",
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


def test_execution_memory_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"live_orders", "order_status_history", "positions", "position_events"} <= table_names


def test_order_submission_persists_order_and_initial_history(postgres_test_schema) -> None:
    run_migrations()
    cycle_id, _ = _persist_cycle_for_market()
    service = ExecutionMemoryPersistenceService()
    handle = service.record_submission_requested(
        cycle_id=cycle_id,
        intent=_make_intent(),
        raw_request={"intent": {"market_id": "566136"}},
    )
    assert handle is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        orders = conn.execute("SELECT * FROM live_orders").fetchall()
        history = conn.execute("SELECT * FROM order_status_history").fetchall()
    assert len(orders) == 1
    assert orders[0]["status"] == "SUBMISSION_REQUESTED"
    assert len(history) == 1
    assert history[0]["new_status"] == "SUBMISSION_REQUESTED"


def test_order_status_history_dedupes_identical_status_lookups(postgres_test_schema) -> None:
    run_migrations()
    cycle_id, _ = _persist_cycle_for_market()
    service = ExecutionMemoryPersistenceService()
    handle = service.record_submission_requested(
        cycle_id=cycle_id,
        intent=_make_intent(),
        raw_request={"intent": {"market_id": "566136"}},
    )
    assert handle is not None
    service.record_submission_response(
        handle=handle,
        response={"response": {"orderID": "abc123", "status": "LIVE"}},
    )
    service.record_status_lookup(
        handle=handle,
        status_payload={"orderID": "abc123", "status": "LIVE"},
    )
    service.record_status_lookup(
        handle=handle,
        status_payload={"orderID": "abc123", "status": "LIVE"},
    )

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        history = conn.execute(
            "SELECT * FROM order_status_history ORDER BY event_at ASC, created_at ASC"
        ).fetchall()
    assert len(history) == 3
    assert [row["new_status"] for row in history] == [
        "SUBMISSION_REQUESTED",
        "LIVE",
        "LIVE",
    ]
    assert [row["source"] for row in history] == [
        "runtime",
        "exchange_submit",
        "status_lookup",
    ]


def test_filled_status_creates_and_updates_position(postgres_test_schema) -> None:
    run_migrations()
    cycle_id, _ = _persist_cycle_for_market()
    service = ExecutionMemoryPersistenceService()

    first = service.record_submission_requested(
        cycle_id=cycle_id,
        intent=_make_intent(size=2.0, notional_usd=1.5),
        raw_request={"intent": {"market_id": "566136"}},
    )
    assert first is not None
    service.record_status_lookup(
        handle=first,
        status_payload={"orderID": "filled-1", "status": "FILLED"},
    )

    second = service.record_submission_requested(
        cycle_id=cycle_id,
        intent=_make_intent(size=3.0, notional_usd=2.25),
        raw_request={"intent": {"market_id": "566136"}},
    )
    assert second is not None
    service.record_status_lookup(
        handle=second,
        status_payload={"orderID": "filled-2", "status": "FILLED"},
    )

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        positions = conn.execute("SELECT * FROM positions").fetchall()
        events = conn.execute(
            "SELECT * FROM position_events ORDER BY event_at ASC, created_at ASC"
        ).fetchall()

    assert len(positions) == 1
    assert float(positions[0]["size"]) == 5.0
    assert positions[0]["side"] == "NO"
    assert [row["event_type"] for row in events] == ["OPENED", "INCREASED"]


@pytest.mark.asyncio
async def test_execution_memory_runtime_smoke(
    postgres_test_schema,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_migrations()
    cycle_id, cycle_result = _persist_cycle_for_market()
    submitted_market_ids: list[str] = []

    class FakeExecutionClient:
        def auth_context(self) -> dict[str, str | int]:
            return {"signature_type": 2, "credential_source": "env"}

        def get_order_book_summary(self, token_id: str) -> SimpleNamespace:
            return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size="0.1")

        def get_balance_allowance(
            self,
            *,
            token_id: str | None = None,
        ) -> dict[str, dict[str, str | float]]:
            return {"collateral": {"balance": "100000000", "balance_usd": 100.0}}

        def get_open_orders(self) -> list[dict[str, str]]:
            return []

        def create_signed_order(self, intent):  # noqa: ANN001
            return {"market_id": intent.market_id, "token_id": intent.token_id}

        def submit_order(self, intent):  # noqa: ANN001
            submitted_market_ids.append(intent.market_id)
            return {"response": {"orderID": "abc123", "status": "LIVE", "success": True}}

        def get_order_status(self, order_id: str) -> dict[str, str]:
            return {"orderID": order_id, "status": "FILLED"}

    cycle_result.cycle_id = cycle_id
    monkeypatch.setattr(
        brain,
        "get_stage4_settings",
        lambda: Stage4Settings(
            LIVE_TRADING_ENABLED=True,
            LIVE_MAX_ORDER_USD=4,
            LIVE_MARKET_WHITELIST="",
            POLY_SIGNATURE_TYPE=2,
        ),
    )
    monkeypatch.setattr(brain, "Stage4ExecutionClient", lambda settings: FakeExecutionClient())

    await brain.handle_live_order_path(
        cycle_result,
        live=True,
        armed=True,
    )

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        orders = conn.execute("SELECT * FROM live_orders ORDER BY created_at ASC").fetchall()
        history = conn.execute(
            "SELECT * FROM order_status_history ORDER BY event_at ASC, created_at ASC"
        ).fetchall()
        positions = conn.execute("SELECT * FROM positions ORDER BY opened_at ASC").fetchall()
        position_events = conn.execute(
            "SELECT * FROM position_events ORDER BY event_at ASC, created_at ASC"
        ).fetchall()

    assert submitted_market_ids == ["566136"]
    assert len(orders) == 1
    assert str(orders[0]["cycle_id"]) == cycle_id
    assert orders[0]["decision_id"] is not None
    assert orders[0]["status"] == "FILLED"
    assert len(history) >= 3
    assert history[-1]["new_status"] == "FILLED"
    assert len(positions) == 1
    assert positions[0]["market_id"] == "566136"
    assert len(position_events) == 1
    assert position_events[0]["event_type"] == "OPENED"

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import brain
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.services.execution_aware_paper import (
    ExecutionAwarePaperRunResult,
    ExecutionAwarePaperService,
)
from app.services.query.paper_query_service import PaperQueryService
from app.services.recorders.phase1_cycle_persistence import Phase1CyclePersistenceService
from app.services.runtime_paper_trading import RuntimePaperTradingService
from app.services.signal_paper import SignalPaperService
import app.services.signal_paper as signal_paper_module
from app.stage2.claude_analyst import MarketRecommendation
from app.stage4.config import Stage4Settings


def _make_market(
    *,
    market_id: str,
    question: str,
    yes_price: float,
    no_price: float,
    spread: float,
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
            spread=spread,
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


def _persist_cycle_for_execution(*, spread: float) -> tuple[str, object]:
    persistence = Phase1CyclePersistenceService()
    top_scored = [
        _make_market(
            market_id="566136",
            question="PSG",
            yes_price=0.25,
            no_price=0.75,
            spread=spread,
            score=72.5,
        ),
    ]
    recommendations = [
        _make_recommendation(
            rank=1,
            question="PSG",
            action="BUY_NO",
            confidence=0.72,
            score=72.5,
            yes_price=0.25,
            no_price=0.75,
        ),
    ]
    handle = persistence.open_cycle(
        mode="PAPER_EXECUTION_AWARE",
        trigger_source="pytest",
        top_n=1,
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


def _persist_cycle_for_multi_execution(*, spread: float) -> tuple[str, object]:
    persistence = Phase1CyclePersistenceService()
    market_specs = [
        ("566136", "PSG", 0.25, 0.75, 72.5),
        ("553866", "Spurs", 0.15, 0.85, 71.2),
        ("564198", "Pistons", 0.20, 0.80, 70.8),
    ]
    top_scored = [
        _make_market(
            market_id=market_id,
            question=question,
            yes_price=yes_price,
            no_price=no_price,
            spread=spread,
            score=score,
        )
        for market_id, question, yes_price, no_price, score in market_specs
    ]
    recommendations = [
        _make_recommendation(
            rank=index + 1,
            question=question,
            action="BUY_NO",
            confidence=0.72 - (index * 0.01),
            score=score,
            yes_price=yes_price,
            no_price=no_price,
        )
        for index, (market_id, question, yes_price, no_price, score) in enumerate(market_specs)
    ]
    handle = persistence.open_cycle(
        mode="PAPER_EXECUTION_AWARE",
        trigger_source="pytest",
        top_n=len(top_scored),
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


class FakeSignalClient:
    def __init__(self, min_order_size: float) -> None:
        self.min_order_size = min_order_size
        self.submit_called = False

    def get_open_orders(self) -> list[dict[str, str]]:
        return []

    def get_order_book_summary(self, token_id: str) -> SimpleNamespace:
        return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size=str(self.min_order_size))

    def get_balance_allowance(self, *, token_id: str | None = None) -> dict[str, dict[str, str | float]]:
        return {"collateral": {"balance": "100000000", "balance_usd": 100.0}}

    def submit_order(self, intent):  # noqa: ANN001
        self.submit_called = True
        raise AssertionError("Execution-aware paper must never submit a real order")


class FakeSignalClientWithExistingPosition(FakeSignalClient):
    def get_open_orders(self) -> list[dict[str, str]]:
        return [{"market_id": "other-market", "exposure_type": "POSITION"}]


class FakeExecutionRefreshClient:
    def __init__(self, min_order_size: float) -> None:
        self.min_order_size = min_order_size
        self.submit_called = False

    def get_order_book_summary(self, token_id: str) -> SimpleNamespace:
        return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size=str(self.min_order_size))

    def submit_order(self, intent):  # noqa: ANN001
        self.submit_called = True
        raise AssertionError("Execution-aware paper must never submit a real order")


def _build_execution_aware_run(
    *,
    spread: float,
    signal_min_order_size: float = 0.1,
    execution_min_order_size: float = 0.1,
) -> tuple[ExecutionAwarePaperRunResult, FakeSignalClient, FakeExecutionRefreshClient]:
    _, cycle_result = _persist_cycle_for_execution(spread=spread)
    signal_client = FakeSignalClient(min_order_size=signal_min_order_size)
    signal_service = SignalPaperService(execution_client=signal_client)
    signal_run = signal_service.record_cycle(cycle_result, mode="EXECUTION_AWARE_PAPER")
    assert signal_run is not None

    execution_client = FakeExecutionRefreshClient(min_order_size=execution_min_order_size)
    execution_service = ExecutionAwarePaperService(
        signal_service=signal_service,
        execution_client=execution_client,
    )
    result = execution_service.execute_existing_run(
        paper_run_id=signal_run.paper_run_id,
        cycle_result=cycle_result,
    )
    assert result is not None
    return result, signal_client, execution_client


def test_execution_aware_paper_migrations_create_tables(postgres_test_schema) -> None:
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
        "paper_orders",
        "paper_order_events",
        "paper_positions",
        "paper_position_events",
    } <= table_names


@pytest.mark.parametrize(
    ("spread", "expected_status"),
    [
        (0.02, "FILLED"),
        (0.04, "PARTIALLY_FILLED"),
        (0.07, "OPEN"),
        (0.12, "EXPIRED"),
    ],
)
def test_execution_aware_statuses_are_persisted_deterministically(
    postgres_test_schema,
    spread: float,
    expected_status: str,
) -> None:
    run_migrations()
    result, signal_client, execution_client = _build_execution_aware_run(spread=spread)

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        order_events = conn.execute(
            "SELECT * FROM paper_order_events ORDER BY event_at ASC, created_at ASC"
        ).fetchall()
        positions = conn.execute("SELECT * FROM paper_positions").fetchall()
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()

    assert result.paper_orders_count == 1
    assert signal_client.submit_called is False
    assert execution_client.submit_called is False
    assert len(orders) == 1
    assert orders[0]["status"] == expected_status
    assert len(order_events) == 2
    assert order_events[0]["new_status"] == "CREATED"
    assert order_events[1]["new_status"] == expected_status
    assert len(live_orders) == 0

    if expected_status in {"FILLED", "PARTIALLY_FILLED"}:
        assert len(positions) == 1
        assert positions[0]["current_status"] == "OPEN"
    else:
        assert len(positions) == 0


def test_execution_aware_min_size_failure_is_persisted(
    postgres_test_schema,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_migrations()
    settings = Stage4Settings(
        _env_file=None,
        LIVE_MARKET_WHITELIST="",
        PAPER_STARTING_CAPITAL_USD=10,
        PAPER_MIN_CASH_RESERVE_PCT=0.0,
        PAPER_MAX_ALLOC_PER_TRADE_PCT=0.20,
        PAPER_MAX_TOTAL_DEPLOYMENT_PCT=1.0,
    )
    monkeypatch.setattr(signal_paper_module, "get_stage4_settings", lambda: settings)
    _, signal_client, execution_client = _build_execution_aware_run(
        spread=0.02,
        signal_min_order_size=0.1,
        execution_min_order_size=10.0,
    )

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        order = conn.execute("SELECT * FROM paper_orders LIMIT 1").fetchone()
        order_events = conn.execute(
            "SELECT * FROM paper_order_events ORDER BY event_at ASC, created_at ASC"
        ).fetchall()
        positions = conn.execute("SELECT * FROM paper_positions").fetchall()

    assert signal_client.submit_called is False
    assert execution_client.submit_called is False
    assert order is not None
    assert order["status"] == "BLOCKED_MIN_SIZE"
    assert bool(order["min_size_check_passed"]) is False
    assert order_events[-1]["reason_code"] == "below_minimum_size"
    assert len(positions) == 0


def test_execution_aware_query_layer_returns_order_and_position_views(postgres_test_schema) -> None:
    run_migrations()
    result, _, _ = _build_execution_aware_run(spread=0.04)
    queries = PaperQueryService()

    summary = queries.get_execution_aware_paper_run_summary(result.paper_run_id)
    assert summary is not None
    assert summary["order_status_counts"]["partially_filled"] == 1
    assert summary["execution_counts"]["paper_orders"] == 1
    assert summary["execution_counts"]["paper_positions"] == 1

    order_history = queries.get_paper_order_history(paper_run_id=result.paper_run_id)
    assert len(order_history["orders"]) == 1
    assert [row["new_status"] for row in order_history["events"]] == ["CREATED", "PARTIALLY_FILLED"]

    open_orders = queries.list_open_paper_orders(result.paper_run_id)
    assert len(open_orders) == 1
    assert open_orders[0]["status"] == "PARTIALLY_FILLED"

    open_positions = queries.list_open_paper_positions(result.paper_run_id)
    assert len(open_positions) == 1
    lifecycle = queries.get_paper_position_lifecycle(str(open_positions[0]["id"]))
    assert lifecycle is not None
    assert [row["event_type"] for row in lifecycle["events"]] == ["OPENED", "MARKED"]
    assert float(lifecycle["position"]["mark_price"]) == 0.75


def test_execution_aware_paper_persists_canonical_execution_contract(postgres_test_schema) -> None:
    run_migrations()
    _build_execution_aware_run(spread=0.02)

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        order = conn.execute("SELECT * FROM paper_orders LIMIT 1").fetchone()
        order_event = conn.execute(
            "SELECT * FROM paper_order_events WHERE new_status = 'FILLED' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

    assert order is not None
    contract = order["payload_json"]["execution_contract"]
    result = order["payload_json"]["execution_result"]
    assert contract["backend_target"] == "paper"
    assert contract["execution_mode"] == "paper"
    assert contract["order_type"] == "LIMIT"
    assert result["result_status"] == "FILLED"
    assert result["raw_result_json"]["adapter"] == "paper"
    assert order_event is not None
    assert order_event["payload_json"]["execution_result"]["result_status"] == "FILLED"


@pytest.mark.asyncio
async def test_execution_aware_runtime_hook_uses_separate_service(
    postgres_test_schema,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_migrations()
    _, cycle_result = _persist_cycle_for_execution(spread=0.02)
    called: dict[str, object] = {}

    class FakeExecutionAwarePaperService:
        def record_cycle(self, cycle_result_arg) -> ExecutionAwarePaperRunResult:  # noqa: ANN001
            called["cycle_id"] = cycle_result_arg.cycle_id
            return ExecutionAwarePaperRunResult(
                paper_run_id="paper-exec-run-test",
                paper_orders_count=1,
                open_orders_count=0,
                open_positions_count=1,
            )

    monkeypatch.setattr(brain, "ExecutionAwarePaperService", FakeExecutionAwarePaperService)

    await brain.handle_execution_aware_paper_path(cycle_result)

    assert called["cycle_id"] == cycle_result.cycle_id


def test_signal_paper_uses_paper_safe_capacity_instead_of_live_single_slot(
    postgres_test_schema,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_migrations()
    _, cycle_result = _persist_cycle_for_execution(spread=0.02)
    settings = Stage4Settings(
        _env_file=None,
        LIVE_MARKET_WHITELIST="",
        live_max_open_positions=1,
        paper_safe_max_open_positions=2,
    )
    monkeypatch.setattr(signal_paper_module, "get_stage4_settings", lambda: settings)

    signal_service = SignalPaperService(execution_client=FakeSignalClientWithExistingPosition(min_order_size=0.1))
    signal_run = signal_service.record_cycle(cycle_result, mode="EXECUTION_AWARE_PAPER")

    assert signal_run is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        signals = conn.execute(
            "SELECT signal_type, reason_code FROM paper_signals ORDER BY created_at ASC"
        ).fetchall()

    assert any(row["signal_type"] == "WOULD_ENTER" for row in signals)
    assert all(row["reason_code"] != "open_positions_1_meet_exceed_max_concurrent_positions_1" for row in signals)


def test_signal_paper_uses_multiple_free_paper_safe_slots_in_same_cycle(
    postgres_test_schema,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_migrations()
    _, cycle_result = _persist_cycle_for_multi_execution(spread=0.02)
    settings = Stage4Settings(
        _env_file=None,
        LIVE_MARKET_WHITELIST="",
        live_max_open_positions=1,
        paper_safe_max_open_positions=3,
        live_max_same_market_exposure=1,
    )
    monkeypatch.setattr(signal_paper_module, "get_stage4_settings", lambda: settings)

    signal_service = SignalPaperService(execution_client=FakeSignalClient(min_order_size=0.1))
    signal_run = signal_service.record_cycle(cycle_result, mode="EXECUTION_AWARE_PAPER")

    assert signal_run is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        signals = conn.execute(
            "SELECT signal_type, reason_code FROM paper_signals ORDER BY created_at ASC, market_id ASC"
        ).fetchall()

    would_enter = [row for row in signals if row["signal_type"] == "WOULD_ENTER"]
    would_skip = [row for row in signals if row["signal_type"] == "WOULD_SKIP"]

    assert len(would_enter) == 3
    assert would_skip == []


def test_signal_paper_persists_capital_snapshot_and_allocation_metadata(
    postgres_test_schema,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_migrations()
    _, cycle_result = _persist_cycle_for_execution(spread=0.02)
    settings = Stage4Settings(
        _env_file=None,
        LIVE_MARKET_WHITELIST="",
        PAPER_STARTING_CAPITAL_USD=100,
        PAPER_MIN_CASH_RESERVE_PCT=0.20,
        PAPER_MAX_ALLOC_PER_TRADE_PCT=0.25,
        PAPER_MAX_TOTAL_DEPLOYMENT_PCT=0.75,
    )
    monkeypatch.setattr(signal_paper_module, "get_stage4_settings", lambda: settings)

    signal_service = SignalPaperService(execution_client=FakeSignalClient(min_order_size=0.1))
    signal_run = signal_service.record_cycle(cycle_result, mode="EXECUTION_AWARE_PAPER")

    assert signal_run is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        signal = conn.execute(
            """
            SELECT *
            FROM paper_signals
            WHERE signal_type = 'WOULD_ENTER'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()

    assert signal is not None
    payload = signal["payload_json"]
    assert payload["capital_snapshot"]["source_mode"] == "paper"
    assert payload["capital_snapshot"]["total_equity_usd"] == 100.0
    assert payload["capital_allocation"]["action"] == "ENTER"
    assert payload["capital_allocation"]["approved_notional_usd"] == 25.0


def test_runtime_listen_only_runs_awareness_without_trading(
    postgres_test_schema,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_migrations()
    monkeypatch.setenv("POLYBOT_RUNTIME_MODE", "listen_only")
    monkeypatch.setenv("POLYBOT_EXECUTION_BACKEND", "paper")

    service = RuntimePaperTradingService()
    scored_markets = [
        _make_market(
            market_id="listen-001",
            question="Listen only market",
            yes_price=0.41,
            no_price=0.59,
            spread=0.02,
            score=70.0,
        )
    ]
    calls: list[tuple[str, object]] = []

    class _SpyExecution:
        def record_cycle(self, cycle_result) -> None:  # noqa: ANN001
            calls.append(("execution", cycle_result.cycle_id))

    class _SpyShadow:
        def record_cycle(self, cycle_result) -> None:  # noqa: ANN001
            calls.append(("shadow", cycle_result.cycle_id))

    class _SpyLive:
        def record_cycle(self, cycle_result) -> None:  # noqa: ANN001
            calls.append(("live", cycle_result.cycle_id))

    class _SpyTrade:
        def classify_markets(self, market_ids, *, source_type: str, source_ref: str):  # noqa: ANN001
            calls.append(("trade", (list(market_ids), source_type, source_ref)))
            return None

    class _SpyRanking:
        def rank_markets(self, market_ids, *, source_type: str, source_ref: str):  # noqa: ANN001
            calls.append(("ranking_v2", (list(market_ids), source_type, source_ref)))
            return None

    class _SpyNoop:
        def __init__(self, name: str) -> None:
            self._name = name

        def allocate_for_classification_run(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            calls.append((self._name, "allocate"))

        def apply_policy_to_ranking_run(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            calls.append((self._name, "policy"))

        def evaluate_markets(self, market_ids, *, source_type: str, source_ref: str) -> None:  # noqa: ANN001
            calls.append((self._name, (list(market_ids), source_type, source_ref)))

        def generate_for_markets(self, market_ids, *, source_type: str, source_ref: str) -> None:  # noqa: ANN001
            calls.append((self._name, (list(market_ids), source_type, source_ref)))

        def process_cycle(self, *, market_map) -> None:  # noqa: ANN001
            calls.append((self._name, sorted(market_map)))

    service._execution_aware_paper = _SpyExecution()
    service._shadow_live = _SpyShadow()
    service._live_trading = _SpyLive()
    service._trade_classification = _SpyTrade()
    service._bucket_allocation = _SpyNoop("bucket")
    service._ranking_v2 = _SpyRanking()
    service._ranking_policy = _SpyNoop("ranking_policy")
    service._invalidation = _SpyNoop("invalidation")
    service._exit_advisory = _SpyNoop("exit_advisory")
    service._resolution = _SpyNoop("resolution")
    service._command_intents = _SpyNoop("command_intents")
    service._lifecycle = _SpyNoop("lifecycle")

    service.process_cycle(cycle_id="listen-cycle", scored_markets=scored_markets)

    labels = [label for label, _ in calls]
    assert "execution" not in labels
    assert "shadow" not in labels
    assert "live" not in labels
    assert "trade" in labels
    assert "ranking_v2" in labels
    assert "invalidation" in labels
    assert "exit_advisory" in labels
    assert "resolution" in labels
    assert "command_intents" in labels
    assert "lifecycle" not in labels

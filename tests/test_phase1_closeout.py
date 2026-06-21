from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.services.query.phase1_query_service import Phase1QueryService
from app.services.recorders.execution_memory import ExecutionMemoryPersistenceService
from app.services.recorders.phase1_cycle_persistence import Phase1CyclePersistenceService
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


def test_closeout_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"run_artifacts", "rejection_ledger"} <= table_names


def test_run_artifacts_and_rejection_ledger_persist(postgres_test_schema) -> None:
    run_migrations()
    cycle_id, _ = _persist_cycle_for_market()

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        artifacts = conn.execute(
            "SELECT * FROM run_artifacts WHERE cycle_id = %s ORDER BY created_at ASC",
            (cycle_id,),
        ).fetchall()
        rejections = conn.execute(
            "SELECT * FROM rejection_ledger WHERE cycle_id = %s ORDER BY market_id ASC",
            (cycle_id,),
        ).fetchall()

    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "replay_snapshot"
    assert artifacts[0]["artifact_scope"] == "cycle"
    assert artifacts[0]["path"].endswith(f"{cycle_id}/cycle_snapshot.json")
    assert len(rejections) == 2
    assert {row["market_id"] for row in rejections} == {"553866", "564198"}
    assert all(row["stage"] == "adaptive_selection" for row in rejections)


def test_phase1_query_layer_returns_operator_views(postgres_test_schema) -> None:
    run_migrations()
    cycle_id, _ = _persist_cycle_for_market()
    execution = ExecutionMemoryPersistenceService()
    handle = execution.record_submission_requested(
        cycle_id=cycle_id,
        intent=_make_intent(size=2.0, notional_usd=1.5),
        raw_request={"intent": {"market_id": "566136"}},
    )
    assert handle is not None
    execution.record_submission_response(
        handle=handle,
        response={"response": {"orderID": "closeout-live-1", "status": "LIVE", "success": True}},
    )
    execution.record_status_lookup(
        handle=handle,
        status_payload={"orderID": "closeout-live-1", "status": "FILLED"},
    )

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        position_row = conn.execute("SELECT id FROM positions LIMIT 1").fetchone()
    assert position_row is not None

    queries = Phase1QueryService()
    cycle_summary = queries.get_cycle_summary(cycle_id)
    assert cycle_summary is not None
    assert cycle_summary["selected_market_id"] == "566136"
    assert cycle_summary["artifact_count"] == 1

    rejections = queries.get_cycle_rejections(cycle_id)
    assert len(rejections) == 2
    assert {row["reason_code"] for row in rejections} == {"higher_ranked_candidate"}

    skipped_market = queries.get_market_decision_details(cycle_id, "553866")
    assert skipped_market["market_snapshot"] is not None
    assert skipped_market["ranking_snapshot"] is not None
    assert skipped_market["decision"] is not None
    assert skipped_market["decision"]["decision_type"] == "SKIP"
    assert len(skipped_market["rejections"]) == 1
    assert skipped_market["artifacts"]

    order_history = queries.get_market_order_history("566136")
    assert len(order_history["orders"]) == 1
    assert [row["new_status"] for row in order_history["status_history"]] == [
        "SUBMISSION_REQUESTED",
        "LIVE",
        "FILLED",
    ]

    lifecycle = queries.get_position_lifecycle(str(position_row["id"]))
    assert lifecycle is not None
    assert lifecycle["position"]["market_id"] == "566136"
    assert [row["event_type"] for row in lifecycle["events"]] == ["OPENED"]

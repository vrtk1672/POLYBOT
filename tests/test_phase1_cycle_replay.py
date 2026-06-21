from __future__ import annotations

from datetime import UTC, datetime

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.services.recorders.phase1_cycle_persistence import Phase1CyclePersistenceService
from app.services.replay.basic_cycle_replay import BasicCycleReplayService
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


def test_phase1_cycle_replay_smoke(postgres_test_schema) -> None:
    run_migrations()
    persistence = Phase1CyclePersistenceService()
    replay = BasicCycleReplayService()

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
        mode="LIVE_DRY_RUN",
        trigger_source="pytest",
        top_n=3,
        pages_requested=1,
        metadata={"test_name": "test_phase1_cycle_replay_smoke"},
    )
    assert handle.cycle_id is not None

    cycle_result = type(
        "CycleResultStub",
        (),
        {
            "top_scored": top_scored,
            "recommendations": recommendations,
        },
    )()
    persistence.persist_cycle_snapshot(handle=handle, cycle_result=cycle_result)

    summary = replay.replay_cycle(handle.cycle_id)
    assert summary is not None
    assert summary["cycle_id"] == handle.cycle_id
    assert summary["market_count"] == 3
    assert summary["ranking_count"] >= 1
    assert summary["decision_count"] == 3
    assert summary["selected_decisions"]
    assert summary["skipped_or_blocked_decisions"]
    assert summary["selected_decisions"][0]["market_id"] == "566136"
    assert {
        item["market_id"] for item in summary["skipped_or_blocked_decisions"]
    } == {"553866", "564198"}

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        cycle_row = conn.execute(
            "SELECT * FROM cycles WHERE id = %s",
            (handle.cycle_id,),
        ).fetchone()
        market_rows = conn.execute(
            "SELECT * FROM market_snapshots WHERE cycle_id = %s",
            (handle.cycle_id,),
        ).fetchall()
        ranking_rows = conn.execute(
            "SELECT * FROM ranking_snapshots WHERE cycle_id = %s",
            (handle.cycle_id,),
        ).fetchall()
        decision_rows = conn.execute(
            "SELECT * FROM decision_ledger WHERE cycle_id = %s",
            (handle.cycle_id,),
        ).fetchall()

    assert cycle_row is not None
    assert len(market_rows) == 3
    assert len(ranking_rows) >= 1
    assert len(decision_rows) == 3
    assert any(bool(row["selected"]) for row in decision_rows)
    assert any(not bool(row["selected"]) for row in decision_rows)

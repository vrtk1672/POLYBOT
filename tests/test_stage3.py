from datetime import UTC, datetime, timedelta

from rich.console import Console

from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.stage2.claude_analyst import MarketRecommendation
from app.stage3 import database
from app.stage3.dashboard import PaperDashboard
from app.stage3.paper_trader import PaperTrader


def _market(**overrides) -> NormalizedMarket:
    now = datetime.now(UTC)
    defaults = {
        "market_id": "m1",
        "event_id": "e1",
        "event_title": "Event",
        "question": "Will POLYBOT pass Stage 3?",
        "slug": "polybot-stage3",
        "end_time": now + timedelta(days=5),
        "yes_price": 0.25,
        "no_price": 0.75,
        "last_trade_price": 0.25,
        "best_bid": 0.24,
        "best_ask": 0.26,
        "spread": 0.02,
        "liquidity": 150_000.0,
        "volume": 500_000.0,
        "volume_24h": 250_000.0,
        "open_interest": 20_000.0,
        "comment_count": 50,
        "competitive": 0.8,
        "accepting_orders": True,
        "updated_at": now,
        "raw_market": {},
    }
    defaults.update(overrides)
    return NormalizedMarket(**defaults)


def _scored_market(**market_overrides) -> ScoredMarket:
    market = _market(**market_overrides)
    return ScoredMarket(
        market=market,
        score=71.5,
        breakdown=ScoreBreakdown(
            price_attractiveness=25.0,
            time_to_close=20.0,
            liquidity_volume=15.0,
            market_activity=11.5,
        ),
        reason="Strong quantitative setup",
        computed_at=datetime.now(UTC),
    )


def _recommendation(
    action: str = "BUY_NO",
    confidence: float = 0.75,
    question: str = "Will POLYBOT pass Stage 3?",
) -> MarketRecommendation:
    return MarketRecommendation(
        rank=1,
        question=question,
        confidence=confidence,
        action=action,
        reason="Test recommendation",
        yes_price=0.25,
        no_price=0.75,
        score=71.5,
        computed_at=datetime.now(UTC).isoformat(),
    )


def test_paper_trader_creates_session_scoped_rows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "paper.db")
    console = Console(record=True)

    trader_one = PaperTrader(console=console, starting_balance=1000.0)
    trader_two = PaperTrader(console=console, starting_balance=1000.0)

    scored = _scored_market()
    trader_one.process_cycle([scored], [scored], [_recommendation()])
    trader_two.process_cycle([scored], [scored], [_recommendation()])

    assert trader_one.session_id != trader_two.session_id
    assert len(database.get_open_trades(trader_one.session_id)) == 1
    assert len(database.get_open_trades(trader_two.session_id)) == 1
    assert database.get_trade_counts(trader_one.session_id) == {"open": 1, "closed": 0}
    assert database.get_trade_counts(trader_two.session_id) == {"open": 1, "closed": 0}


def test_empty_cycle_does_not_force_close_existing_trades(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "paper.db")
    console = Console(record=True)
    trader = PaperTrader(console=console, starting_balance=1000.0)
    scored = _scored_market()

    trader.process_cycle([scored], [scored], [_recommendation()])
    result = trader.process_cycle([], [], [])

    assert result.portfolio.open_positions == 1
    assert database.get_trade_counts(trader.session_id) == {"open": 1, "closed": 0}


def test_bucket_sizing_and_thresholds(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "paper.db")
    console = Console(record=True)
    trader = PaperTrader(console=console, starting_balance=1000.0)
    scored = _scored_market()

    trader.process_cycle([scored], [scored], [_recommendation()])
    trades = database.get_open_trades(trader.session_id)
    assert len(trades) == 1
    assert trades[0].size_usd == 150.0

    weak_score = scored.model_copy(update={"score": 70.0})
    weak_conf = _recommendation(confidence=0.60)
    trader.process_cycle([weak_score], [weak_score], [weak_conf])
    assert len(database.get_open_trades(trader.session_id)) == 1


def test_dashboard_handles_zero_trades(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "paper.db")
    console = Console(record=True)
    trader = PaperTrader(console=console, starting_balance=1000.0)
    dashboard = PaperDashboard(console=console, session_id=trader.session_id, interval_seconds=1)

    dashboard.render_once(label="TEST")

    rendered = console.export_text()
    assert "PAPER DASHBOARD TEST" in rendered
    assert "Open trades: 0" in rendered
    assert "Closed trades: 0" in rendered

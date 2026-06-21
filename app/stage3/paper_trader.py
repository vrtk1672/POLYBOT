"""
Stage 3 paper trading engine.

Paper-only execution:
- opens positions from qualifying Stage 2 signals
- marks positions to market using the latest scan price
- closes positions with clearly isolated temporary rules until a true
  resolution feed is added in a later stage
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from rich.console import Console

from app.models.market import NormalizedMarket
from app.models.score import ScoredMarket
from app.stage2.claude_analyst import MarketRecommendation
from app.stage3.database import PortfolioSnapshot, TradeRecord
from gamma_crawler import edge_cents, hours_remaining, liquidity_bucket

from . import database

DEFAULT_STARTING_BALANCE = 1000.0
SIGNAL_SCORE_THRESHOLD = 70.0
SIGNAL_CONFIDENCE_THRESHOLD = 0.60
BUCKET_SIZING = {
    "safe": 0.05,
    "high": 0.10,
    "whale": 0.15,
}
TAKE_PROFIT_PCT = 0.20
STOP_LOSS_PCT = -0.12


@dataclass(slots=True)
class OpenedTrade:
    trade_id: int
    signal_id: int
    market_id: str | None
    question: str
    side: str
    entry_price: float
    size_usd: float
    bucket: str


@dataclass(slots=True)
class ClosedTrade:
    trade_id: int
    market_id: str | None
    question: str
    side: str
    exit_price: float
    realized_pnl: float
    reason: str


@dataclass(slots=True)
class TemporaryExitDecision:
    should_exit: bool
    exit_price: float | None = None
    reason: str | None = None


@dataclass(slots=True)
class CycleTradingResult:
    scan_id: int
    opened_trades: list[OpenedTrade]
    closed_trades: list[ClosedTrade]
    portfolio: PortfolioSnapshot


@dataclass(slots=True)
class PaperSessionSummary:
    starting_balance: float
    current_balance: float
    total_pnl: float
    total_pnl_pct: float
    open_trades: list[TradeRecord]
    closed_trades: list[TradeRecord]
    latest_snapshot: PortfolioSnapshot | None


def load_starting_balance() -> float:
    for key in ("PAPER_STARTING_BALANCE", "POLYBOT_PAPER_STARTING_BALANCE"):
        value = os.environ.get(key)
        if value:
            try:
                return max(float(value), 0.0)
            except ValueError:
                continue

    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            for key in ("PAPER_STARTING_BALANCE", "POLYBOT_PAPER_STARTING_BALANCE"):
                if line.startswith(f"{key}="):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    try:
                        return max(float(raw), 0.0)
                    except ValueError:
                        pass

    return DEFAULT_STARTING_BALANCE


class PaperTrader:
    def __init__(self, console: Console, starting_balance: float | None = None) -> None:
        self.console = console
        self.session_id = datetime.now(UTC).strftime("paper_%Y%m%dT%H%M%S_%fZ")
        self.starting_balance = starting_balance if starting_balance is not None else load_starting_balance()
        database.init_db()
        latest = database.get_latest_portfolio_snapshot(self.session_id)
        if latest is None:
            self._snapshot_portfolio({})

    def process_cycle(
        self,
        all_scored_markets: list[ScoredMarket],
        analyzed_markets: list[ScoredMarket],
        recommendations: list[MarketRecommendation],
    ) -> CycleTradingResult:
        if not all_scored_markets and not analyzed_markets and not recommendations:
            scan_id = database.insert_scan(
                total_markets=0,
                top_market=None,
                top_score=None,
                session_id=self.session_id,
            )
            portfolio = self._snapshot_portfolio({})
            return CycleTradingResult(
                scan_id=scan_id,
                opened_trades=[],
                closed_trades=[],
                portfolio=portfolio,
            )

        market_map = {item.market.market_id: item.market for item in all_scored_markets}
        closed_trades = self._close_trades(market_map)

        top_market = analyzed_markets[0].market.question if analyzed_markets else None
        top_score = analyzed_markets[0].score if analyzed_markets else None
        scan_id = database.insert_scan(
            total_markets=len(all_scored_markets),
            top_market=top_market,
            top_score=top_score,
            session_id=self.session_id,
        )

        opened_trades: list[OpenedTrade] = []
        rec_by_rank = {rec.rank: rec for rec in recommendations}
        for index, item in enumerate(analyzed_markets, start=1):
            rec = rec_by_rank.get(index)
            if rec is None:
                continue
            try:
                bucket = liquidity_bucket(item.market)
                signal_id = database.insert_signal(
                    scan_id=scan_id,
                    market_id=item.market.market_id,
                    question=item.market.question,
                    yes_price=item.market.yes_price,
                    edge=edge_cents(item.market),
                    score=item.score,
                    ai_action=rec.action,
                    confidence=rec.confidence,
                    reason=rec.reason,
                    bucket=bucket,
                    session_id=self.session_id,
                )
                opened_trade = self._maybe_open_trade(signal_id, item, rec, bucket)
                if opened_trade is not None:
                    opened_trades.append(opened_trade)
            except Exception as exc:
                self.console.print(
                    f"  [yellow]![/yellow] Paper signal skipped for "
                    f"{item.market.question[:60]!r}: {exc}"
                )

        portfolio = self._snapshot_portfolio(market_map)
        return CycleTradingResult(
            scan_id=scan_id,
            opened_trades=opened_trades,
            closed_trades=closed_trades,
            portfolio=portfolio,
        )

    def finalize_session(
        self,
        last_seen_markets: Mapping[str, NormalizedMarket] | None = None,
    ) -> PaperSessionSummary:
        market_map = dict(last_seen_markets or {})
        self._close_trades(market_map, session_end=True)
        latest = self._snapshot_portfolio(market_map)
        open_trades = database.get_open_trades(self.session_id)
        closed_trades = database.get_closed_trades(self.session_id)
        total_pnl = latest.total_pnl if latest is not None else 0.0
        current_balance = latest.total_balance if latest is not None else self.starting_balance
        total_pnl_pct = (total_pnl / self.starting_balance * 100.0) if self.starting_balance else 0.0
        return PaperSessionSummary(
            starting_balance=self.starting_balance,
            current_balance=current_balance,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            open_trades=open_trades,
            closed_trades=closed_trades,
            latest_snapshot=latest,
        )

    def summarize(self) -> PaperSessionSummary:
        latest = database.get_latest_portfolio_snapshot(self.session_id)
        total_balance = latest.total_balance if latest is not None else self.starting_balance
        total_pnl = latest.total_pnl if latest is not None else 0.0
        total_pnl_pct = (total_pnl / self.starting_balance * 100.0) if self.starting_balance else 0.0
        return PaperSessionSummary(
            starting_balance=self.starting_balance,
            current_balance=total_balance,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            open_trades=database.get_open_trades(self.session_id),
            closed_trades=database.get_closed_trades(self.session_id),
            latest_snapshot=latest,
        )

    def _maybe_open_trade(
        self,
        signal_id: int,
        item: ScoredMarket,
        recommendation: MarketRecommendation,
        bucket: str,
    ) -> OpenedTrade | None:
        if recommendation.action not in {"BUY_YES", "BUY_NO"}:
            return None
        if item.score <= SIGNAL_SCORE_THRESHOLD or recommendation.confidence <= SIGNAL_CONFIDENCE_THRESHOLD:
            return None
        if database.has_open_trade_for_market(item.market.market_id, self.session_id):
            return None

        entry_price = self._price_for_side(recommendation.action, item.market)
        if entry_price is None or entry_price <= 0:
            return None

        latest = database.get_latest_portfolio_snapshot(self.session_id)
        current_balance = latest.total_balance if latest is not None else self.starting_balance
        reserve_cash = latest.bucket_reserve if latest is not None else self.starting_balance
        allocation = BUCKET_SIZING.get(bucket, BUCKET_SIZING["safe"])
        size_usd = round(min(current_balance * allocation, reserve_cash), 2)
        if size_usd <= 0:
            return None

        trade_id = database.insert_paper_trade(
            signal_id=signal_id,
            market_id=item.market.market_id,
            question=item.market.question,
            side=recommendation.action,
            entry_price=entry_price,
            size_usd=size_usd,
            session_id=self.session_id,
        )
        return OpenedTrade(
            trade_id=trade_id,
            signal_id=signal_id,
            market_id=item.market.market_id,
            question=item.market.question,
            side=recommendation.action,
            entry_price=entry_price,
            size_usd=size_usd,
            bucket=bucket,
        )

    def _close_trades(
        self,
        market_map: Mapping[str, NormalizedMarket],
        session_end: bool = False,
    ) -> list[ClosedTrade]:
        closed: list[ClosedTrade] = []
        for trade in database.get_open_trades(self.session_id):
            market = market_map.get(trade.market_id or "")
            decision = self._temporary_exit_decision(trade, market, session_end=session_end)
            if not decision.should_exit or decision.exit_price is None or decision.reason is None:
                continue
            realized_pnl = self._compute_realized_pnl(trade, decision.exit_price)
            database.close_paper_trade(trade.id, decision.exit_price, realized_pnl)
            closed.append(
                ClosedTrade(
                    trade_id=trade.id,
                    market_id=trade.market_id,
                    question=trade.question,
                    side=trade.side,
                    exit_price=decision.exit_price,
                    realized_pnl=realized_pnl,
                    reason=decision.reason,
                )
            )
        return closed

    def _snapshot_portfolio(
        self,
        market_map: Mapping[str, NormalizedMarket],
    ) -> PortfolioSnapshot:
        open_trades = database.get_open_trades(self.session_id)
        closed_trades = database.get_closed_trades(self.session_id)
        realized_pnl = sum((trade.realized_pnl or 0.0) for trade in closed_trades)

        reserve_cash = self.starting_balance + realized_pnl - sum(trade.size_usd for trade in open_trades)
        reserve_cash = round(max(reserve_cash, 0.0), 2)

        bucket_totals = {"safe": 0.0, "high": 0.0, "whale": 0.0}
        open_market_value = 0.0
        for trade in open_trades:
            bucket = trade.bucket or "safe"
            bucket_totals[bucket] = bucket_totals.get(bucket, 0.0) + trade.size_usd
            market = market_map.get(trade.market_id or "")
            open_market_value += self._mark_to_market_value(trade, market)

        total_balance = round(reserve_cash + open_market_value, 2)
        total_pnl = round(total_balance - self.starting_balance, 2)
        database.insert_portfolio_snapshot(
            total_balance=total_balance,
            bucket_safe=round(bucket_totals.get("safe", 0.0), 2),
            bucket_high=round(bucket_totals.get("high", 0.0), 2),
            bucket_whale=round(bucket_totals.get("whale", 0.0), 2),
            bucket_reserve=reserve_cash,
            open_positions=len(open_trades),
            total_pnl=total_pnl,
            session_id=self.session_id,
        )
        latest = database.get_latest_portfolio_snapshot(self.session_id)
        if latest is None:
            raise RuntimeError("Portfolio snapshot was not persisted")
        return latest

    def _temporary_exit_decision(
        self,
        trade: TradeRecord,
        market: NormalizedMarket | None,
        session_end: bool = False,
    ) -> TemporaryExitDecision:
        """
        TEMPORARY exit policy until the codebase has a real resolution feed.

        Rules:
        - session end: close at the latest observable mark price
        - market absent from the latest active scan: close at the last known entry price
        - current mark reaches +20% or -12% vs entry: close at that mark
        - market time has elapsed inside the scan payload: close at the latest mark
        """
        if session_end:
            exit_price = self._price_for_side(trade.side, market) if market is not None else trade.entry_price
            return TemporaryExitDecision(True, exit_price=exit_price, reason="TEMPORARY_SESSION_END_MARK")

        if market is None:
            return TemporaryExitDecision(
                True,
                exit_price=trade.entry_price,
                reason="TEMPORARY_MISSING_FROM_ACTIVE_SCAN",
            )

        current_price = self._price_for_side(trade.side, market)
        if current_price is None:
            return TemporaryExitDecision(False)

        pnl_ratio = (current_price / trade.entry_price) - 1.0
        if pnl_ratio >= TAKE_PROFIT_PCT:
            return TemporaryExitDecision(True, exit_price=current_price, reason="TEMPORARY_TAKE_PROFIT")
        if pnl_ratio <= STOP_LOSS_PCT:
            return TemporaryExitDecision(True, exit_price=current_price, reason="TEMPORARY_STOP_LOSS")

        remaining_hours = hours_remaining(market)
        if remaining_hours is not None and remaining_hours <= 0:
            return TemporaryExitDecision(True, exit_price=current_price, reason="TEMPORARY_MARKET_TIME_ELAPSED")

        return TemporaryExitDecision(False)

    def _mark_to_market_value(
        self,
        trade: TradeRecord,
        market: NormalizedMarket | None,
    ) -> float:
        current_price = self._price_for_side(trade.side, market)
        if current_price is None or trade.entry_price <= 0:
            return round(trade.size_usd, 2)
        shares = trade.size_usd / trade.entry_price
        return round(shares * current_price, 2)

    def _compute_realized_pnl(self, trade: TradeRecord, exit_price: float) -> float:
        if trade.entry_price <= 0:
            return 0.0
        shares = trade.size_usd / trade.entry_price
        pnl = shares * exit_price - trade.size_usd
        return round(pnl, 2)

    def _price_for_side(
        self,
        side: str,
        market: NormalizedMarket | None,
    ) -> float | None:
        if market is None:
            return None
        if side == "BUY_YES":
            return market.yes_price
        if side == "BUY_NO":
            if market.no_price is not None:
                return market.no_price
            if market.yes_price is not None:
                return round(1.0 - market.yes_price, 4)
        return None

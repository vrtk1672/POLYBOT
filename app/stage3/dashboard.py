"""
Terminal dashboard for Stage 3 paper trading.
"""

from __future__ import annotations

import asyncio

from rich.console import Console
from rich.table import Table

from app.stage3.paper_trader import PaperSessionSummary

from . import database


class PaperDashboard:
    def __init__(self, console: Console, session_id: str, interval_seconds: int = 60) -> None:
        self.console = console
        self.session_id = session_id
        self.interval_seconds = interval_seconds
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(self.interval_seconds)
            if self._stop_event.is_set():
                break
            self.render_once()

    def stop(self) -> None:
        self._stop_event.set()

    def render_once(self, label: str = "LIVE") -> None:
        snapshot = database.get_latest_portfolio_snapshot(self.session_id)
        if snapshot is None:
            return

        closed = database.get_closed_trades(self.session_id)
        open_trades = database.get_open_trades(self.session_id)
        starting_balance = snapshot.total_balance - snapshot.total_pnl
        pnl_pct = (snapshot.total_pnl / starting_balance * 100.0) if starting_balance else 0.0

        self.console.rule(f"[bold cyan]PAPER DASHBOARD {label}[/bold cyan]", characters="-")
        self.console.print(
            f"  Balance: [bold]{snapshot.total_balance:.2f}[/bold] "
            f"(start {starting_balance:.2f})  |  "
            f"PnL: [bold]{snapshot.total_pnl:+.2f}[/bold] ({pnl_pct:+.2f}%)"
        )
        self.console.print(
            f"  Open trades: [bold]{len(open_trades)}[/bold]  |  "
            f"Closed trades: [bold]{len(closed)}[/bold]  |  "
            f"Reserve cash: [bold]{snapshot.bucket_reserve:.2f}[/bold]"
        )

        winners = sorted(closed, key=lambda trade: trade.realized_pnl or 0.0, reverse=True)[:3]
        losers = sorted(closed, key=lambda trade: trade.realized_pnl or 0.0)[:3]

        self.console.print(self._trade_table("Top 3 Winners", winners))
        self.console.print(self._trade_table("Top 3 Losers", losers))
        self.console.print()

    def print_final_summary(self, summary: PaperSessionSummary) -> None:
        self.console.rule("[bold cyan]PAPER SESSION SUMMARY[/bold cyan]", characters="-")
        self.console.print(
            f"  Starting balance: [bold]{summary.starting_balance:.2f}[/bold]  |  "
            f"Final balance: [bold]{summary.current_balance:.2f}[/bold]  |  "
            f"Final PnL: [bold]{summary.total_pnl:+.2f}[/bold] ({summary.total_pnl_pct:+.2f}%)"
        )
        self.console.print(
            f"  Open trades remaining: [bold]{len(summary.open_trades)}[/bold]  |  "
            f"Closed trades: [bold]{len(summary.closed_trades)}[/bold]"
        )
        self.console.print(self._trade_table("Closed Trades", summary.closed_trades))
        self.console.print(self._trade_table("Open Trades", summary.open_trades))
        self.console.print()

    def _trade_table(self, title: str, trades: list) -> Table:
        table = Table(title=title, show_lines=True, header_style="bold magenta", border_style="dim")
        table.add_column("Question", overflow="fold", max_width=46)
        table.add_column("Side", width=8)
        table.add_column("Entry", justify="right", width=7)
        table.add_column("Exit", justify="right", width=7)
        table.add_column("Size", justify="right", width=8)
        table.add_column("PnL", justify="right", width=8)

        if not trades:
            table.add_row("[dim]None[/dim]", "-", "-", "-", "-", "-")
            return table

        for trade in trades:
            table.add_row(
                trade.question,
                trade.side,
                f"{trade.entry_price:.3f}",
                f"{trade.exit_price:.3f}" if trade.exit_price is not None else "[dim]open[/dim]",
                f"{trade.size_usd:.2f}",
                f"{(trade.realized_pnl or 0.0):+.2f}",
            )
        return table

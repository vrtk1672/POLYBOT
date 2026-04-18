from rich.console import Console
from rich.table import Table

from app.models.score import ScoredMarket

console = Console()


def render_top_markets_table(markets: list[ScoredMarket]) -> None:
    table = Table(title="POLYBOT Top Opportunities", show_lines=False)
    table.add_column("Rank", justify="right")
    table.add_column("Question", overflow="fold", max_width=42)
    table.add_column("Price", justify="right")
    table.add_column("End Time", justify="left")
    table.add_column("24h Vol", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Reason", overflow="fold", max_width=34)

    for index, item in enumerate(markets, start=1):
        table.add_row(
            str(index),
            item.market.question,
            _format_price(item.market),
            item.market.end_time.isoformat() if item.market.end_time else "n/a",
            _format_number(item.market.volume_24h),
            f"{item.score:.2f}",
            item.reason,
        )

    console.print(table)


def _format_price(item) -> str:
    if item.last_trade_price is not None:
        return f"{item.last_trade_price:.3f}"
    if item.yes_price is not None:
        return f"{item.yes_price:.3f}"
    return "n/a"


def _format_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.0f}"

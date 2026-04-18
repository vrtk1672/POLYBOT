"""
gamma_crawler.py — Polymarket live market scanner.

Fetches active markets from the Gamma API, normalizes and scores them,
then prints the top N opportunities to the terminal.

Usage:
    .venv\\Scripts\\python gamma_crawler.py                  # single scan, top 10
    .venv\\Scripts\\python gamma_crawler.py --top 20          # show top 20
    .venv\\Scripts\\python gamma_crawler.py --pages 3         # fetch 300 events
    .venv\\Scripts\\python gamma_crawler.py --watch           # repeat every 5 min
    .venv\\Scripts\\python gamma_crawler.py --watch --interval 120  # repeat every 2 min
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx
from rich.console import Console
from rich.table import Table

from app.models.market import NormalizedMarket
from app.models.score import ScoredMarket
from app.scoring.opportunity_score import OpportunityScorer
from app.utils.time_utils import parse_datetime

GAMMA_BASE = "https://gamma-api.polymarket.com"
GEOBLOCK_URL = "https://polymarket.com/api/geoblock"
USER_AGENT = "POLYBOT/0.1 gamma-crawler"
PAGE_LIMIT = 100
LOGS_DIR = Path("logs")

console = Console()


# ---------------------------------------------------------------------------
# Geoblock
# ---------------------------------------------------------------------------

async def check_geoblock() -> None:
    """Exit with a clear message if Polymarket has geo-blocked this IP."""
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(GEOBLOCK_URL)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        # If the geoblock endpoint itself is unreachable, warn but continue.
        console.print(f"  [yellow]![/yellow] Geoblock check failed ({exc}) — continuing anyway")
        return

    if data.get("blocked") is True:
        country = data.get("countryCode", "unknown")
        console.print(
            f"\n[bold red]BLOCKED[/bold red] Polymarket has geo-blocked this IP "
            f"(country: {country}). Use a VPN or a permitted jurisdiction.\n"
        )
        raise SystemExit(1)

    country = data.get("countryCode", "?")
    console.print(f"  [green]+[/green] Geoblock OK (country: {country})")


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

async def fetch_events(pages: int) -> list[dict]:
    """Fetch active, non-closed events from the Gamma API with pagination."""
    all_events: list[dict] = []
    async with httpx.AsyncClient(
        base_url=GAMMA_BASE,
        timeout=20.0,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    ) as client:
        for page in range(pages):
            offset = page * PAGE_LIMIT
            params = {
                "active": "true",
                "closed": "false",
                "limit": PAGE_LIMIT,
                "offset": offset,
            }
            resp = await client.get("/events", params=params)
            resp.raise_for_status()
            chunk: list[dict] = resp.json()
            all_events.extend(chunk)
            if len(chunk) < PAGE_LIMIT:
                break  # last page reached
    return all_events


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _coerce_price(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(v, 1.0))


def _coerce_non_negative(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return max(v, 0.0)


def _coerce_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return None


def _parse_json_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, list) else []
        except json.JSONDecodeError:
            return []
    return []


def normalize_market(event: dict, market_payload: dict) -> NormalizedMarket | None:
    """Convert a raw Gamma API market payload into a NormalizedMarket.

    Returns None for markets that are inactive, closed, or not accepting orders.
    """
    if (
        not bool(market_payload.get("active", False))
        or bool(market_payload.get("closed", False))
        or not bool(market_payload.get("acceptingOrders", False))
    ):
        return None

    outcome_prices = _parse_json_list(market_payload.get("outcomePrices"))
    yes_price = _coerce_price(market_payload.get("lastTradePrice"))
    if yes_price is None and outcome_prices:
        yes_price = _coerce_price(outcome_prices[0])

    no_price = None
    if len(outcome_prices) > 1:
        no_price = _coerce_price(outcome_prices[1])
    elif yes_price is not None:
        no_price = round(1 - yes_price, 4)

    best_bid = _coerce_price(market_payload.get("bestBid"))
    best_ask = _coerce_price(market_payload.get("bestAsk"))
    spread = _coerce_non_negative(market_payload.get("spread"))
    if spread is None and best_bid is not None and best_ask is not None:
        spread = round(max(best_ask - best_bid, 0.0), 4)

    return NormalizedMarket(
        market_id=str(market_payload["id"]),
        event_id=str(event["id"]),
        event_title=str(event.get("title") or market_payload.get("question") or "Untitled event"),
        question=str(market_payload.get("question") or event.get("title") or "Untitled market"),
        slug=market_payload.get("slug"),
        end_time=parse_datetime(market_payload.get("endDate") or event.get("endDate")),
        yes_price=yes_price,
        no_price=no_price,
        last_trade_price=_coerce_price(market_payload.get("lastTradePrice")),
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        liquidity=_coerce_non_negative(
            market_payload.get("liquidityNum")
            or market_payload.get("liquidityClob")
            or market_payload.get("liquidity")
            or event.get("liquidity")
            or event.get("liquidityClob")
        ),
        volume=_coerce_non_negative(
            market_payload.get("volumeNum") or market_payload.get("volume")
        ),
        volume_24h=_coerce_non_negative(
            market_payload.get("volume24hr")
            or market_payload.get("volume24hrClob")
            or event.get("volume24hr")
        ),
        open_interest=_coerce_non_negative(
            market_payload.get("openInterest") or event.get("openInterest")
        ),
        comment_count=_coerce_int(event.get("commentCount")),
        competitive=_coerce_non_negative(
            market_payload.get("competitive") or event.get("competitive")
        ),
        accepting_orders=True,
        updated_at=parse_datetime(market_payload.get("updatedAt") or event.get("updatedAt")),
        raw_market=market_payload,
    )


def normalize_all(events: list[dict]) -> tuple[list[NormalizedMarket], int]:
    """Extract and normalize every tradable market from a list of events."""
    markets: list[NormalizedMarket] = []
    skipped = 0
    for event in events:
        for mp in event.get("markets", []):
            try:
                m = normalize_market(event, mp)
                if m is not None:
                    markets.append(m)
            except Exception:
                skipped += 1
    return markets, skipped


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_and_rank(markets: list[NormalizedMarket]) -> list[ScoredMarket]:
    scorer = OpportunityScorer()
    scored = [scorer.score_market(m) for m in markets]
    scored.sort(
        key=lambda x: (x.score, x.market.volume_24h or 0.0, x.market.liquidity or 0.0),
        reverse=True,
    )
    return scored


# ---------------------------------------------------------------------------
# Derived display metrics
# ---------------------------------------------------------------------------

def hours_remaining(market: NormalizedMarket) -> float | None:
    """Hours from now until market end_time. None if unknown."""
    if market.end_time is None:
        return None
    delta = (market.end_time - datetime.now(UTC)).total_seconds()
    return max(delta / 3600, 0.0)


def edge_cents(market: NormalizedMarket) -> int | None:
    """Profit in cents per $1 of shares bought on the cheaper side.

    If YES=0.25, buying YES gives $0.75 profit per $1 payout if YES resolves.
    Edge = (1 - cheap_price) * 100, rounded to nearest cent.
    """
    prices = [p for p in [market.yes_price, market.no_price] if p is not None]
    if not prices:
        return None
    cheap = min(prices)
    return round((1.0 - cheap) * 100)


def liquidity_bucket(market: NormalizedMarket) -> str:
    """Classify market depth for position sizing guidance.

    whale  — deep enough for large positions (liq >= $100k or 24h vol >= $200k)
    high   — medium depth  (liq >= $10k  or 24h vol >= $30k)
    safe   — shallow, small positions only
    """
    liq = market.liquidity or 0.0
    vol = market.volume_24h or 0.0
    if liq >= 100_000 or vol >= 200_000:
        return "whale"
    if liq >= 10_000 or vol >= 30_000:
        return "high"
    return "safe"


# ---------------------------------------------------------------------------
# Terminal rendering
# ---------------------------------------------------------------------------

def _fmt_end_time(dt: datetime | None) -> str:
    if dt is None:
        return "[dim]n/a[/dim]"
    now = datetime.now(UTC)
    hours = (dt - now).total_seconds() / 3600
    if hours <= 0:
        return "[red]EXPIRED[/red]"
    if hours < 24:
        return f"[yellow]{hours:.1f}h[/yellow]"
    days = hours / 24
    if days < 7:
        return f"[cyan]{days:.1f}d[/cyan]"
    return dt.strftime("%Y-%m-%d")


def _fmt_hours(h: float | None) -> str:
    if h is None:
        return "[dim]n/a[/dim]"
    if h < 24:
        return f"[yellow]{h:.1f}h[/yellow]"
    return f"[cyan]{h / 24:.1f}d[/cyan]"


def _fmt_number(value: float | None) -> str:
    if value is None:
        return "[dim]n/a[/dim]"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.0f}"


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "[dim]n/a[/dim]"
    return f"{value:.3f}"


def _fmt_bucket(bucket: str) -> str:
    return {"whale": "[bold cyan]whale[/bold cyan]", "high": "[green]high[/green]"}.get(
        bucket, "[dim]safe[/dim]"
    )


def render_results(scored: list[ScoredMarket], top_n: int, label: str = "") -> None:
    title = f"[bold cyan]POLYBOT — Top {top_n} Polymarket Opportunities[/bold cyan]"
    if label:
        title += f"  [dim]{label}[/dim]"

    table = Table(title=title, show_lines=True, header_style="bold magenta", border_style="dim")
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Question", overflow="fold", max_width=44)
    table.add_column("YES", justify="right", width=6)
    table.add_column("NO", justify="right", width=6)
    table.add_column("Edge", justify="right", width=5)
    table.add_column("Hours", justify="right", width=7)
    table.add_column("24h Vol", justify="right", width=9)
    table.add_column("Bucket", justify="center", width=6)
    table.add_column("Score", justify="right", style="bold yellow", width=7)
    table.add_column("Signal", overflow="fold", max_width=28)

    for i, item in enumerate(scored[:top_n], start=1):
        m = item.market
        bucket = liquidity_bucket(m)
        table.add_row(
            str(i),
            m.question,
            _fmt_price(m.yes_price),
            _fmt_price(m.no_price),
            f"{edge_cents(m)}c" if edge_cents(m) is not None else "[dim]n/a[/dim]",
            _fmt_hours(hours_remaining(m)),
            _fmt_number(m.volume_24h),
            _fmt_bucket(bucket),
            f"{item.score:.2f}",
            item.reason,
        )

    console.print()
    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# JSON log saving
# ---------------------------------------------------------------------------

def _scored_to_dict(item: ScoredMarket) -> dict:
    m = item.market
    return {
        "market_id": m.market_id,
        "event_id": m.event_id,
        "question": m.question,
        "yes_price": m.yes_price,
        "no_price": m.no_price,
        "last_trade_price": m.last_trade_price,
        "best_bid": m.best_bid,
        "best_ask": m.best_ask,
        "spread": m.spread,
        "liquidity": m.liquidity,
        "volume": m.volume,
        "volume_24h": m.volume_24h,
        "open_interest": m.open_interest,
        "end_time": m.end_time.isoformat() if m.end_time else None,
        "hours_remaining": hours_remaining(m),
        "edge_cents": edge_cents(m),
        "bucket": liquidity_bucket(m),
        "score": item.score,
        "breakdown": {
            "price_attractiveness": item.breakdown.price_attractiveness,
            "time_to_close": item.breakdown.time_to_close,
            "liquidity_volume": item.breakdown.liquidity_volume,
            "market_activity": item.breakdown.market_activity,
        },
        "reason": item.reason,
        "computed_at": item.computed_at.isoformat(),
    }


def save_scan_log(
    scored: list[ScoredMarket],
    total_events: int,
    total_markets: int,
    duration_ms: int,
    top_n: int = 20,
) -> Path:
    """Persist the scan results to logs/scan_YYYY-MM-DD_HH-MM.json."""
    LOGS_DIR.mkdir(exist_ok=True)
    now = datetime.now(UTC)
    filename = LOGS_DIR / now.strftime("scan_%Y-%m-%d_%H-%M.json")

    payload = {
        "scanned_at": now.isoformat(),
        "duration_ms": duration_ms,
        "total_events": total_events,
        "total_markets": total_markets,
        "total_scored": len(scored),
        "top_markets": [_scored_to_dict(item) for item in scored[:top_n]],
    }

    filename.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return filename


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------

async def run_scan(pages: int) -> tuple[list[ScoredMarket], int, int, int]:
    """Fetch, normalize, and score all markets. Returns (scored, events, markets, ms)."""
    t0 = perf_counter()
    events = await fetch_events(pages=pages)
    markets, _ = normalize_all(events)
    scored = score_and_rank(markets)
    duration_ms = round((perf_counter() - t0) * 1000)
    return scored, len(events), len(markets), duration_ms


# ---------------------------------------------------------------------------
# Single scan mode
# ---------------------------------------------------------------------------

async def single_scan(top_n: int, pages: int) -> None:
    console.rule("[bold cyan]POLYBOT gamma_crawler[/bold cyan]", characters="-")
    console.print(
        f"  Fetching up to [bold]{pages * PAGE_LIMIT:,}[/bold] events "
        f"({pages} pages x {PAGE_LIMIT}) from {GAMMA_BASE}"
    )

    await check_geoblock()

    t0 = perf_counter()
    try:
        scored, n_events, n_markets, duration_ms = await run_scan(pages)
    except httpx.HTTPError as exc:
        console.print(f"[bold red]HTTP error:[/bold red] {exc}")
        raise SystemExit(1)

    total_ms = round((perf_counter() - t0) * 1000)
    console.print(f"  [green]+[/green] {n_events:,} events  |  {n_markets:,} markets  |  {len(scored):,} scored  |  {total_ms} ms")

    render_results(scored, top_n)

    log_path = save_scan_log(scored, n_events, n_markets, duration_ms, top_n=20)
    console.print(f"  [dim]Saved:[/dim] {log_path}")
    console.print(
        "[dim]Scoring: 35% price attractiveness - 25% time to close - "
        "20% liquidity/volume - 20% market activity[/dim]"
    )
    console.rule(characters="-")


# ---------------------------------------------------------------------------
# Watch mode
# ---------------------------------------------------------------------------

async def watch_mode(top_n: int, pages: int, interval: int) -> None:
    console.rule("[bold cyan]POLYBOT gamma_crawler -- WATCH MODE[/bold cyan]", characters="-")
    console.print(
        f"  Scanning every [bold]{interval}[/bold]s  |  pages={pages}  |  top={top_n}"
    )
    console.print("  Press Ctrl+C to stop.\n")

    await check_geoblock()

    seen_ids: set[str] = set()
    scan_number = 0

    while True:
        scan_number += 1
        ts = datetime.now(UTC).strftime("%H:%M:%S UTC")
        console.print(f"[dim]--- scan #{scan_number} at {ts} ---[/dim]")

        try:
            scored, n_events, n_markets, duration_ms = await run_scan(pages)
        except httpx.HTTPError as exc:
            console.print(f"  [red]Fetch error:[/red] {exc} — retrying next cycle")
            await asyncio.sleep(interval)
            continue

        console.print(
            f"  [green]+[/green] {n_events:,} events  |  {n_markets:,} markets  |  "
            f"{len(scored):,} scored  |  {duration_ms} ms"
        )

        current_ids = {item.market.market_id for item in scored[:top_n]}
        new_items = [item for item in scored[:top_n] if item.market.market_id not in seen_ids]

        if scan_number == 1:
            # First pass — show full top-N
            render_results(scored, top_n, label=f"scan #{scan_number}")
        elif new_items:
            render_results(new_items, len(new_items), label=f"scan #{scan_number} — {len(new_items)} NEW")
        else:
            console.print(f"  [dim]No new markets in top {top_n} — top unchanged.[/dim]\n")

        save_scan_log(scored, n_events, n_markets, duration_ms, top_n=20)
        seen_ids = current_ids

        console.print(f"  [dim]Next scan in {interval}s ...[/dim]\n")
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch and score live Polymarket markets.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--top", type=int, default=10, metavar="N", help="markets to display")
    parser.add_argument(
        "--pages", type=int, default=5, metavar="N", help="API pages to fetch (100 events/page)"
    )
    parser.add_argument(
        "--watch", action="store_true", help="repeat scan on an interval (default: 300s)"
    )
    parser.add_argument(
        "--interval", type=int, default=300, metavar="SEC",
        help="seconds between scans in --watch mode",
    )
    args = parser.parse_args()

    try:
        if args.watch:
            asyncio.run(watch_mode(top_n=args.top, pages=args.pages, interval=args.interval))
        else:
            asyncio.run(single_scan(top_n=args.top, pages=args.pages))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")

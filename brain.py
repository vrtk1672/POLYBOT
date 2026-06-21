"""
brain.py — POLYBOT Stage 2: Brain.

Three integrated subsystems:
  1. WebSocket listener  — real-time CLOB price changes on top-N markets
  2. Claude analyst      — batched market recommendations via claude-opus-4-6
  3. Alert engine        — fires when score > 70 AND Claude confidence > 0.8

Usage:
    .venv\\Scripts\\python brain.py                      # 10 min, top 10
    .venv\\Scripts\\python brain.py --minutes 5         # shorter session
    .venv\\Scripts\\python brain.py --top 15 --pages 5  # more markets
    .venv\\Scripts\\python brain.py --skip-ws           # skip WebSocket (Claude only)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import anthropic
import httpx
from rich.console import Console
from rich.table import Table

from app.models.score import ScoredMarket
from app.stage2.claude_analyst import MarketRecommendation, analyze_markets
from app.stage2.ws_listener import WSListener, extract_token_ids
from app.stage3 import PaperDashboard, PaperTrader
from app.stage4 import (
    LiveGuard,
    Stage4ExecutionClient,
    compute_bucket_targets,
    get_stage4_settings,
)
from app.services.recorders.phase1_cycle_persistence import (
    PersistedCycleHandle,
    Phase1CyclePersistenceService,
)
from app.services.recorders.execution_memory import ExecutionMemoryPersistenceService
from app.services.execution_aware_paper import ExecutionAwarePaperService
from app.services.live_execution_plan import build_live_execution_plan
from app.services.signal_paper import SignalPaperService
from app.services.shadow_live import ShadowLiveService
from app.db.config import get_database_settings
from app.db.migrate import run_migrations
from gamma_crawler import (
    GAMMA_BASE,
    GEOBLOCK_URL,
    USER_AGENT,
    normalize_all,
    fetch_events,
    score_and_rank,
    edge_cents,
    hours_remaining,
    _fmt_end_time,
    _fmt_number,
    _fmt_price,
    _fmt_bucket,
)

LOGS_DIR = Path("logs")
console = Console()

# Alert thresholds (task 3)
SCORE_THRESHOLD = 70.0
CONFIDENCE_THRESHOLD = 0.8
PAPER_CONFIDENCE_THRESHOLD = 0.60


@dataclass(slots=True)
class CycleResult:
    all_scored: list[ScoredMarket]
    top_scored: list[ScoredMarket]
    recommendations: list[MarketRecommendation]
    cycle_id: str | None = None


# ---------------------------------------------------------------------------
# Geoblock (re-used from gamma_crawler logic)
# ---------------------------------------------------------------------------

async def check_geoblock() -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as c:
            resp = await c.get(GEOBLOCK_URL)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        console.print(f"  [yellow]![/yellow] Geoblock check failed ({exc}) -- continuing")
        return

    if data.get("blocked") is True:
        country = data.get("countryCode", "?")
        console.print(f"\n[bold red]BLOCKED[/bold red] country={country}. Use a VPN.\n")
        raise SystemExit(1)

    console.print(f"  [green]+[/green] Geoblock OK (country: {data.get('countryCode', '?')})")


# ---------------------------------------------------------------------------
# Terminal rendering
# ---------------------------------------------------------------------------

def render_recommendations(
    scored: list[ScoredMarket],
    recs: list[MarketRecommendation],
    cycle: int,
) -> None:
    rec_by_rank = {r.rank: r for r in recs}

    table = Table(
        title=f"[bold cyan]POLYBOT Brain -- Cycle {cycle} | {datetime.now(UTC).strftime('%H:%M:%S UTC')}[/bold cyan]",
        show_lines=True,
        header_style="bold magenta",
        border_style="dim",
    )
    table.add_column("#", justify="right", width=3)
    table.add_column("Question", overflow="fold", max_width=40)
    table.add_column("YES", justify="right", width=6)
    table.add_column("Edge", justify="right", width=5)
    table.add_column("Closes", justify="right", width=9)
    table.add_column("Score", justify="right", width=6)
    table.add_column("AI Action", justify="center", width=9)
    table.add_column("Conf.", justify="right", width=5)
    table.add_column("Reason", overflow="fold", max_width=30)

    for i, item in enumerate(scored, 1):
        m = item.market
        rec = rec_by_rank.get(i)

        if rec is None:
            action_str = "[dim]--[/dim]"
            conf_str = "[dim]--[/dim]"
            reason_str = ""
        else:
            action_color = {
                "BUY_YES": "bold green",
                "BUY_NO": "bold red",
                "SKIP": "dim",
            }.get(rec.action, "white")
            action_str = f"[{action_color}]{rec.action}[/{action_color}]"
            conf_val = rec.confidence
            conf_color = "bold yellow" if conf_val >= 0.8 else ("yellow" if conf_val >= 0.6 else "dim")
            conf_str = f"[{conf_color}]{conf_val:.2f}[/{conf_color}]"
            reason_str = rec.reason

        table.add_row(
            str(i),
            m.question,
            _fmt_price(m.yes_price),
            f"{edge_cents(m)}c" if edge_cents(m) is not None else "[dim]n/a[/dim]",
            _fmt_end_time(m.end_time),
            f"{item.score:.1f}",
            action_str,
            conf_str,
            reason_str,
        )

    console.print()
    console.print(table)
    console.print()


def print_alert(item: ScoredMarket, rec: MarketRecommendation) -> None:
    m = item.market
    console.print(
        f"[bold yellow]OPPORTUNITY:[/bold yellow] "
        f"[bold]{m.question[:60]}[/bold]\n"
        f"  Score: [bold yellow]{item.score:.2f}[/bold yellow]  |  "
        f"AI: [bold green]{rec.action}[/bold green]  |  "
        f"Confidence: [bold cyan]{rec.confidence:.2f}[/bold cyan]  |  "
        f"YES={_fmt_price(m.yes_price)}  Edge={edge_cents(m)}c\n"
        f"  Reason: {rec.reason}"
    )
    console.print()


def print_final_summary(all_recs: list[list[MarketRecommendation]]) -> None:
    console.rule("[bold cyan]FINAL REPORT -- All Claude Recommendations[/bold cyan]", characters="-")

    # Flatten and deduplicate by question (keep highest-confidence per question)
    best: dict[str, MarketRecommendation] = {}
    for cycle_recs in all_recs:
        for rec in cycle_recs:
            key = rec.question[:80]
            if key not in best or rec.confidence > best[key].confidence:
                best[key] = rec

    table = Table(
        title=f"[bold]All Recommendations ({len(best)} unique markets)[/bold]",
        show_lines=True,
        header_style="bold magenta",
        border_style="dim",
    )
    table.add_column("#", justify="right", width=3)
    table.add_column("Question", overflow="fold", max_width=48)
    table.add_column("YES", justify="right", width=6)
    table.add_column("Score", justify="right", width=6)
    table.add_column("Action", justify="center", width=9)
    table.add_column("Conf.", justify="right", width=5)
    table.add_column("Reason", overflow="fold", max_width=35)

    sorted_recs = sorted(best.values(), key=lambda r: (-r.confidence, -r.score))
    for i, rec in enumerate(sorted_recs, 1):
        action_color = {
            "BUY_YES": "bold green",
            "BUY_NO": "bold red",
            "SKIP": "dim",
        }.get(rec.action, "white")
        conf_color = "bold yellow" if rec.confidence >= 0.8 else ("yellow" if rec.confidence >= 0.6 else "dim")
        table.add_row(
            str(i),
            rec.question,
            _fmt_price(rec.yes_price),
            f"{rec.score:.1f}",
            f"[{action_color}]{rec.action}[/{action_color}]",
            f"[{conf_color}]{rec.confidence:.2f}[/{conf_color}]",
            rec.reason,
        )

    console.print()
    console.print(table)
    console.print()

    # Highlight high-conviction trades
    alerts = [r for r in sorted_recs if r.score >= SCORE_THRESHOLD and r.confidence >= CONFIDENCE_THRESHOLD and r.action != "SKIP"]
    if alerts:
        console.print(f"[bold yellow]HIGH-CONVICTION OPPORTUNITIES ({len(alerts)} markets):[/bold yellow]")
        for r in alerts:
            action_color = "bold green" if r.action == "BUY_YES" else "bold red"
            console.print(
                f"  [{action_color}]{r.action}[/{action_color}] "
                f"[bold]{r.question[:60]}[/bold]\n"
                f"    Score={r.score:.1f}  Confidence={r.confidence:.2f}  YES={_fmt_price(r.yes_price)}\n"
                f"    {r.reason}"
            )
            console.print()
    else:
        console.print("[dim]No high-conviction opportunities found in this session.[/dim]\n")

    console.rule(characters="-")


def print_paper_cycle_update(result) -> None:
    if result.opened_trades:
        console.print(f"[bold green]PAPER OPENED {len(result.opened_trades)} trade(s)[/bold green]")
        for trade in result.opened_trades:
            console.print(
                f"  {trade.side} | {trade.question[:70]}\n"
                f"    entry={trade.entry_price:.3f} size=${trade.size_usd:.2f} bucket={trade.bucket}"
            )
    if result.closed_trades:
        console.print(f"[bold yellow]PAPER CLOSED {len(result.closed_trades)} trade(s)[/bold yellow]")
        for trade in result.closed_trades:
            console.print(
                f"  {trade.side} | {trade.question[:70]}\n"
                f"    exit={trade.exit_price:.3f} pnl=${trade.realized_pnl:+.2f} reason={trade.reason}"
            )
    if result.opened_trades or result.closed_trades:
        console.print(
            f"  [dim]Portfolio: balance=${result.portfolio.total_balance:.2f} "
            f"pnl=${result.portfolio.total_pnl:+.2f} open={result.portfolio.open_positions}[/dim]\n"
        )


async def run_stage4_auth_check() -> bool:
    settings = get_stage4_settings()
    client = Stage4ExecutionClient(settings)
    console.rule("[bold cyan]STAGE 4 AUTH CHECK[/bold cyan]", characters="-")
    try:
        result = await asyncio.to_thread(client.auth_self_check)
    except Exception as exc:
        console.print(f"  [red]Auth self-check failed:[/red] {exc}")
        return False

    status = "[green]PASS[/green]" if result.ok else "[yellow]BLOCKED[/yellow]"
    console.print(f"  Result: {status} {result.summary}")
    for key, value in result.details.items():
        console.print(f"  {key}: {value}")
    console.print()
    return result.ok


async def handle_live_order_path(
    cycle_result: CycleResult,
    *,
    live: bool,
    armed: bool,
) -> None:
    settings = get_stage4_settings()
    execution_client = Stage4ExecutionClient(settings)
    execution_memory = ExecutionMemoryPersistenceService()
    guard = LiveGuard(settings)
    auth_context = execution_client.auth_context()

    console.rule("[bold cyan]STAGE 4 EXECUTION PATH[/bold cyan]", characters="-")
    console.print(
        f"  Mode: [bold]{'LIVE SUBMIT' if live and armed else 'DRY RUN'}[/bold]  |  "
        f"Live enabled env: [bold]{settings.live_trading_enabled}[/bold]  |  "
        f"Max order: [bold]${settings.live_max_order_usd:.2f}[/bold]"
    )

    plan = await asyncio.to_thread(
        build_live_execution_plan,
        cycle_result,
        settings=settings,
        execution_client=execution_client,
        guard=guard,
        live=live,
        armed=armed,
    )

    console.print(
        f"  Selector: [bold]{'adaptive' if settings.live_use_adaptive_selector else 'legacy_top_1'}[/bold]\n"
        f"  Universe: scanned={len(plan.source_markets)} allowed={len(plan.allowed_universe)} "
        f"ranked={len(plan.ranked_candidates)} skipped={len(plan.skipped)}"
    )
    if plan.skipped:
        preview = ", ".join(plan.skipped[:3])
        suffix = " ..." if len(plan.skipped) > 3 else ""
        console.print(f"  [dim]Skipped sample: {preview}{suffix}[/dim]")

    if not plan.ranked_candidates:
        console.print("  [yellow]![/yellow] No eligible live candidate found from the adaptive universe.")
        console.print()
        return

    for evaluation in plan.evaluations:
        if evaluation.status != "BLOCKED":
            continue
        console.print(
            f"  [yellow]![/yellow] Candidate {evaluation.market_id} rejected during {evaluation.decision_stage}: "
            f"{evaluation.reason_text}"
        )

    selected = plan.selected
    if selected is None or selected.intent is None:
        console.print("  [yellow]![/yellow] No executable live candidate remains after sizing and safety checks.")
        console.print()
        return

    ranked = selected.ranked
    intent = selected.intent
    balance_info = selected.balance_info
    collateral_balance = float(selected.collateral_balance or settings.live_max_order_usd)
    open_orders = plan.open_orders
    open_orders_error = plan.open_orders_error

    bucket_targets = compute_bucket_targets(collateral_balance)
    console.print(
        f"  Bucket targets (reference): safe=${bucket_targets.safe:.2f} high=${bucket_targets.high:.2f} "
        f"whale=${bucket_targets.whale:.2f} reserve=${bucket_targets.reserve:.2f}"
    )

    console.print(
        f"  Candidate: [bold]{intent.question[:90]}[/bold]\n"
        f"  Market={intent.market_id} Token={intent.token_id} Action={intent.action} Side={intent.side}\n"
        f"  Adaptive rank={ranked.total_rank:.2f} ({ranked.reason})\n"
        f"  Price={intent.price:.4f} Size={intent.size:.3f} Notional=${intent.notional_usd:.4f} "
        f"Bucket={intent.bucket} Tick={intent.tick_size} NegRisk={intent.neg_risk}\n"
        f"  Auth context: {auth_context}\n"
        f"  Balance/allowance: {balance_info}\n"
        f"  Open orders inspected: {len(open_orders)}"
    )
    if open_orders_error:
        console.print(f"  [yellow]![/yellow] Open order inspection error: {open_orders_error}")

    if not live:
        console.print("  [cyan]+[/cyan] Dry-run preview only; submission is disabled in this mode.")
        try:
            signed_order = await asyncio.to_thread(execution_client.create_signed_order, intent)
            console.print(f"  Dry-run signed order preview: {signed_order}")
        except Exception as exc:
            console.print(f"  Dry-run signing unavailable: {exc}")
        console.print()
        return

    order_handle = None
    if cycle_result.cycle_id:
        order_handle = execution_memory.record_submission_requested(
            cycle_id=cycle_result.cycle_id,
            intent=intent,
            raw_request={
                "intent": {
                    "market_id": intent.market_id,
                    "token_id": intent.token_id,
                    "side": intent.side,
                    "action": intent.action,
                    "price": intent.price,
                    "size": intent.size,
                    "notional_usd": intent.notional_usd,
                    "bucket": intent.bucket,
                    "tick_size": intent.tick_size,
                    "neg_risk": intent.neg_risk,
                }
            },
        )

    try:
        response = await asyncio.to_thread(execution_client.submit_order, intent)
    except Exception as exc:
        if order_handle:
            execution_memory.record_submission_error(
                handle=order_handle,
                error=exc,
                raw_payload={
                    "error": str(exc),
                    "details": getattr(exc, "details", None),
                },
            )
        console.print(f"  [red]Live order submission failed:[/red] {exc}")
        details = getattr(exc, "details", None)
        if details:
            console.print(f"  [dim]Submission debug: {details}[/dim]")
        console.print()
        return

    if order_handle:
        execution_memory.record_submission_response(
            handle=order_handle,
            response=response,
        )

    console.print(f"  [green]+[/green] Live order submitted: {response}")
    response_payload = response.get("response", {})
    order_id = None
    if isinstance(response_payload, dict):
        order_id = (
            response_payload.get("orderID")
            or response_payload.get("id")
            or response_payload.get("order_id")
        )
    if order_id:
        try:
            order_status = await asyncio.to_thread(execution_client.get_order_status, order_id)
            if order_handle:
                execution_memory.record_status_lookup(
                    handle=order_handle,
                    status_payload=order_status,
                )
            console.print(f"  [green]+[/green] Live order status: {order_status}")
        except Exception as exc:
            console.print(f"  [yellow]![/yellow] Order submitted but status lookup failed: {exc}")
    console.print()


async def handle_signal_paper_path(cycle_result: CycleResult) -> None:
    console.rule("[bold cyan]PHASE 2A SIGNAL PAPER[/bold cyan]", characters="-")
    service = SignalPaperService()
    result = await asyncio.to_thread(service.record_cycle, cycle_result)
    if result is None:
        console.print("  [yellow]![/yellow] Signal Paper persistence is unavailable or failed.")
        console.print()
        return

    console.print(
        f"  [green]+[/green] Paper run recorded: {result.paper_run_id}\n"
        f"  Signals emitted: [bold]{result.signals_emitted_count}[/bold]  |  "
        f"Would-enter count: [bold]{result.candidates_selected_count}[/bold]  |  "
        f"Selected market: [bold]{result.selected_market_id or '--'}[/bold]"
    )
    console.print()


async def handle_execution_aware_paper_path(cycle_result: CycleResult) -> None:
    console.rule("[bold cyan]PHASE 2B EXECUTION-AWARE PAPER[/bold cyan]", characters="-")
    service = ExecutionAwarePaperService()
    result = await asyncio.to_thread(service.record_cycle, cycle_result)
    if result is None:
        console.print("  [yellow]![/yellow] Execution-aware paper persistence is unavailable or failed.")
        console.print()
        return

    console.print(
        f"  [green]+[/green] Execution-aware paper run recorded: {result.paper_run_id}\n"
        f"  Paper orders: [bold]{result.paper_orders_count}[/bold]  |  "
        f"Open paper orders: [bold]{result.open_orders_count}[/bold]  |  "
        f"Open paper positions: [bold]{result.open_positions_count}[/bold]"
    )
    console.print()


async def handle_shadow_live_path(cycle_result: CycleResult) -> None:
    console.rule("[bold cyan]PHASE 2C SHADOW LIVE[/bold cyan]", characters="-")
    service = ShadowLiveService()
    result = await asyncio.to_thread(service.record_cycle, cycle_result)
    if result is None:
        console.print("  [yellow]![/yellow] Shadow Live persistence is unavailable or failed.")
        console.print()
        return

    console.print(
        f"  [green]+[/green] Shadow run recorded: {result.shadow_run_id}\n"
        f"  Shadow orders: [bold]{result.shadow_orders_count}[/bold]  |  "
        f"Would-submit count: [bold]{result.candidates_selected_count}[/bold]  |  "
        f"Selected market: [bold]{result.selected_market_id or '--'}[/bold]"
    )
    console.print()


# ---------------------------------------------------------------------------
# One scan + analysis cycle
# ---------------------------------------------------------------------------

async def run_cycle(
    pages: int,
    top_n: int,
    claude_client: anthropic.AsyncAnthropic,
    ws_listener: WSListener | None,
    cycle: int,
    phase1_persistence: Phase1CyclePersistenceService | None = None,
    mode: str = "SCAN_ONLY",
) -> CycleResult:
    """Fetch markets, inject live prices from WS, run Claude analysis."""
    t0 = perf_counter()
    console.print(f"[dim]--- Scan cycle #{cycle} at {datetime.now(UTC).strftime('%H:%M:%S UTC')} ---[/dim]")
    cycle_handle = (
        phase1_persistence.open_cycle(
            mode=mode,
            trigger_source="brain.py",
            top_n=top_n,
            pages_requested=pages,
            metadata={"cycle_number": cycle},
        )
        if phase1_persistence
        else PersistedCycleHandle(cycle_id=None, started_perf=None)
    )

    # 1. Fetch + score markets
    try:
        events = await fetch_events(pages=pages)
    except httpx.HTTPError as exc:
        console.print(f"  [red]Fetch error:[/red] {exc}")
        if phase1_persistence:
            phase1_persistence.fail_cycle(
                handle=cycle_handle,
                markets_fetched_count=0,
                markets_scored_count=0,
                last_error=str(exc),
            )
        return CycleResult(
            all_scored=[],
            top_scored=[],
            recommendations=[],
            cycle_id=cycle_handle.cycle_id,
        )

    markets, skipped = normalize_all(events)
    scored = score_and_rank(markets)
    top = scored[:top_n]

    fetch_ms = round((perf_counter() - t0) * 1000)
    console.print(
        f"  [green]+[/green] {len(events):,} events | {len(markets):,} markets | "
        f"{len(scored):,} scored | {fetch_ms} ms"
    )

    # 2. Inject live WS prices (if available)
    if ws_listener and ws_listener.event_count > 0:
        live_prices = ws_listener.latest_prices
        injected = 0
        for item in top:
            for tid in extract_token_ids(item.market):
                if tid in live_prices:
                    # Update yes_price with live data (YES token = first clobTokenId)
                    tids = extract_token_ids(item.market)
                    if tids and tid == tids[0]:
                        item.market.yes_price = live_prices[tid]
                    injected += 1
        if injected:
            console.print(f"  [cyan]+[/cyan] {injected} live price(s) injected from WebSocket")

    # 3. Claude analysis
    console.print(f"  Sending {len(top)} markets to Claude (claude-opus-4-6)...")
    recs = await analyze_markets(top, claude_client, cycle=cycle)
    total_ms = round((perf_counter() - t0) * 1000)
    console.print(f"  [green]+[/green] Claude returned {len(recs)} recommendations in {total_ms} ms")

    # 4. Alert on high-score + high-confidence markets
    scored_by_rank = {i + 1: item for i, item in enumerate(top)}
    alerts = []
    for rec in recs:
        if rec.action == "SKIP":
            continue
        item = scored_by_rank.get(rec.rank)
        if item and item.score >= SCORE_THRESHOLD and rec.confidence >= CONFIDENCE_THRESHOLD:
            alerts.append((item, rec))

    if alerts:
        console.print(f"\n[bold yellow]*** {len(alerts)} OPPORTUNITY ALERT(S) ***[/bold yellow]")
        for item, rec in alerts:
            print_alert(item, rec)
    else:
        console.print(f"  [dim]No alerts (need score >= {SCORE_THRESHOLD} AND confidence >= {CONFIDENCE_THRESHOLD})[/dim]")

    # 5. Render combined table
    render_recommendations(top, recs, cycle)

    result = CycleResult(
        all_scored=scored,
        top_scored=top,
        recommendations=recs,
        cycle_id=cycle_handle.cycle_id,
    )
    if phase1_persistence:
        phase1_persistence.persist_cycle_snapshot(
            handle=cycle_handle,
            cycle_result=result,
        )

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def main(
    minutes: int,
    top_n: int,
    pages: int,
    interval: int,
    skip_ws: bool,
    paper: bool,
    signal_paper: bool,
    execution_aware_paper: bool,
    shadow_live: bool,
    live_dry_run: bool,
    live: bool,
    armed: bool,
    live_auth_check: bool,
) -> None:
    if shadow_live and (paper or signal_paper or execution_aware_paper or live or live_dry_run):
        console.print(
            "[bold red]ERROR:[/bold red] --shadow-live cannot be combined with --paper, --signal-paper, --execution-aware-paper, --live-dry-run, or --live"
        )
        raise SystemExit(1)
    if execution_aware_paper and (paper or signal_paper or shadow_live or live or live_dry_run):
        console.print(
            "[bold red]ERROR:[/bold red] --execution-aware-paper cannot be combined with --paper, --signal-paper, --shadow-live, --live-dry-run, or --live"
        )
        raise SystemExit(1)
    if signal_paper and (paper or live or live_dry_run):
        console.print(
            "[bold red]ERROR:[/bold red] --signal-paper cannot be combined with --paper, --live-dry-run, or --live"
        )
        raise SystemExit(1)

    if live_auth_check:
        ok = await run_stage4_auth_check()
        if not ok:
            raise SystemExit(1)
        return

    console.rule("[bold cyan]POLYBOT brain.py -- Stage 2: Brain[/bold cyan]", characters="-")
    console.print(
        f"  Runtime: [bold]{minutes}[/bold] min  |  "
        f"Markets: [bold]{top_n}[/bold]  |  "
        f"Pages: [bold]{pages}[/bold]  |  "
        f"Interval: [bold]{interval}[/bold]s  |  "
        f"Paper mode: [bold]{'ON' if paper else 'OFF'}[/bold]  |  "
        f"Signal Paper: [bold]{'ON' if signal_paper else 'OFF'}[/bold]  |  "
        f"Execution-Aware Paper: [bold]{'ON' if execution_aware_paper else 'OFF'}[/bold]  |  "
        f"Shadow Live: [bold]{'ON' if shadow_live else 'OFF'}[/bold]  |  "
        f"Live dry-run: [bold]{'ON' if live_dry_run else 'OFF'}[/bold]  |  "
        f"Live submit: [bold]{'ON' if live else 'OFF'}[/bold]"
    )

    # Check ANTHROPIC_API_KEY
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Try loading from .env file
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not api_key or api_key.startswith("sk-ant-..."):
        console.print(
            "\n[bold red]ERROR:[/bold red] ANTHROPIC_API_KEY not set.\n"
            "  1. Get your key at https://console.anthropic.com\n"
            "  2. Add to .env:  ANTHROPIC_API_KEY=sk-ant-...\n"
            "  3. Or export:    set ANTHROPIC_API_KEY=sk-ant-...\n"
        )
        raise SystemExit(1)

    console.print("  [green]+[/green] ANTHROPIC_API_KEY found")

    # Geoblock check
    await check_geoblock()

    # Build Claude client
    claude_client = anthropic.AsyncAnthropic(api_key=api_key)

    # Initial scan to get markets for WS subscription
    console.print("\n  Running initial scan for WebSocket subscription...")
    try:
        init_events = await fetch_events(pages=min(pages, 2))
        init_markets, _ = normalize_all(init_events)
        init_scored = score_and_rank(init_markets)[:top_n]
    except Exception as exc:
        console.print(f"  [red]Initial scan failed:[/red] {exc}")
        init_scored = []

    # Build token_id -> question map for WS
    token_id_to_name: dict[str, str] = {}
    for item in init_scored:
        tids = extract_token_ids(item.market)
        q_short = item.market.question[:50]
        for i, tid in enumerate(tids):
            suffix = " (YES)" if i == 0 else " (NO)"
            token_id_to_name[tid] = q_short + suffix

    # Launch WebSocket listener
    ws_listener: WSListener | None = None
    if not skip_ws and token_id_to_name:
        ws_listener = WSListener(token_id_to_name)
        await ws_listener.start()
        console.print(
            f"  [green]+[/green] WebSocket started — listening on "
            f"{len(token_id_to_name)} tokens ({len(init_scored)} markets)"
        )
        console.print(f"  [dim]Events logged to: {Path('logs/ws_events.jsonl')}[/dim]")
    elif skip_ws:
        console.print("  [dim]WebSocket skipped (--skip-ws)[/dim]")
    else:
        console.print("  [yellow]![/yellow] No markets for WS subscription")

    console.print()

    paper_trader: PaperTrader | None = None
    paper_dashboard: PaperDashboard | None = None
    paper_dashboard_task: asyncio.Task[None] | None = None
    phase1_persistence = Phase1CyclePersistenceService()
    db_settings = get_database_settings()
    if db_settings.enabled and db_settings.phase1_auto_migrate:
        applied = await asyncio.to_thread(run_migrations)
        if applied:
            console.print(f"  [green]+[/green] Applied Phase 1 migrations: {', '.join(applied)}")
    last_market_map = {}
    if paper:
        paper_trader = PaperTrader(console=console)
        paper_dashboard = PaperDashboard(
            console=console,
            session_id=paper_trader.session_id,
            interval_seconds=60,
        )
        paper_dashboard_task = asyncio.create_task(paper_dashboard.run())
        console.print(
            f"  [green]+[/green] Paper trading enabled "
            f"(thresholds: score > {SCORE_THRESHOLD}, confidence > {PAPER_CONFIDENCE_THRESHOLD:.2f})"
        )
        console.print(
            f"  [dim]Stage 3 uses temporary exits until real market resolution is wired in.[/dim]\n"
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    deadline = perf_counter() + minutes * 60
    cycle = 0
    all_recs: list[list[MarketRecommendation]] = []

    try:
        while perf_counter() < deadline:
            cycle += 1
            cycle_result = await run_cycle(
                pages=pages,
                top_n=top_n,
                claude_client=claude_client,
                ws_listener=ws_listener,
                cycle=cycle,
                phase1_persistence=phase1_persistence,
                mode="LIVE_SUBMIT" if live else "LIVE_DRY_RUN" if live_dry_run else "SHADOW_LIVE" if shadow_live else "PAPER_EXECUTION_AWARE" if execution_aware_paper else "PAPER_SIGNAL" if signal_paper else "PAPER" if paper else "SCAN_ONLY",
            )
            all_recs.append(cycle_result.recommendations)
            last_market_map = {item.market.market_id: item.market for item in cycle_result.all_scored}

            if shadow_live:
                await handle_shadow_live_path(cycle_result)
                break

            if execution_aware_paper:
                await handle_execution_aware_paper_path(cycle_result)
                break

            if signal_paper:
                await handle_signal_paper_path(cycle_result)
                break

            if paper_trader:
                paper_result = paper_trader.process_cycle(
                    all_scored_markets=cycle_result.all_scored,
                    analyzed_markets=cycle_result.top_scored,
                    recommendations=cycle_result.recommendations,
                )
                print_paper_cycle_update(paper_result)

            if live_dry_run or live:
                await handle_live_order_path(
                    cycle_result,
                    live=live,
                    armed=armed,
                )
                break

            # WS stats
            if ws_listener:
                console.print(
                    f"  [dim]WebSocket events received so far: {ws_listener.event_count}[/dim]"
                )

            # Wait for next cycle (or exit if deadline reached)
            remaining = deadline - perf_counter()
            if remaining <= 0:
                break

            wait_secs = min(interval, remaining)
            console.print(
                f"  [dim]Next cycle in {int(wait_secs)}s "
                f"({int(remaining)}s remaining in session)...[/dim]\n"
            )
            await asyncio.sleep(wait_secs)

    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
    finally:
        if paper_dashboard:
            paper_dashboard.stop()
        if paper_dashboard_task:
            await paper_dashboard_task
        if ws_listener:
            await ws_listener.stop()
            console.print(
                f"\n  WebSocket stopped | total events: {ws_listener.event_count} | "
                f"logged to logs/ws_events.jsonl"
            )

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    if paper_trader:
        paper_summary = paper_trader.finalize_session(last_market_map)
        if paper_dashboard:
            paper_dashboard.render_once(label="FINAL")
            paper_dashboard.print_final_summary(paper_summary)

    if all_recs:
        print_final_summary(all_recs)
    else:
        console.print("[dim]No recommendations collected.[/dim]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="POLYBOT Stage 2 Brain — WebSocket + Claude analysis",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--minutes", type=int, default=10, help="session duration in minutes")
    parser.add_argument("--top", type=int, default=10, help="markets to analyze per cycle")
    parser.add_argument("--pages", type=int, default=5, help="Gamma API pages per scan")
    parser.add_argument("--interval", type=int, default=300, help="seconds between cycles")
    parser.add_argument("--skip-ws", action="store_true", help="skip WebSocket (Claude only)")
    parser.add_argument("--paper", action="store_true", help="enable Stage 3 paper trading")
    parser.add_argument("--signal-paper", action="store_true", help="run Phase 2A signal paper only")
    parser.add_argument("--execution-aware-paper", action="store_true", help="run Phase 2B execution-aware paper only")
    parser.add_argument("--shadow-live", action="store_true", help="run Phase 2C shadow live only")
    parser.add_argument("--live-auth-check", action="store_true", help="run Stage 4 auth self-check and exit")
    parser.add_argument("--live-dry-run", action="store_true", help="build and validate one guarded live order without submission")
    parser.add_argument("--live", action="store_true", help="attempt one guarded live order")
    parser.add_argument("--armed", action="store_true", help="required alongside --live for actual order submission")
    args = parser.parse_args()

    try:
        asyncio.run(main(
            minutes=args.minutes,
            top_n=args.top,
            pages=args.pages,
            interval=args.interval,
            skip_ws=args.skip_ws,
            paper=args.paper,
            signal_paper=args.signal_paper,
            execution_aware_paper=args.execution_aware_paper,
            shadow_live=args.shadow_live,
            live_dry_run=args.live_dry_run,
            live=args.live,
            armed=args.armed,
            live_auth_check=args.live_auth_check,
        ))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")

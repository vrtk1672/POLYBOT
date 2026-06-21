from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


ENDPOINTS = (
    "/healthz",
    "/runtime/health",
    "/system/power",
    "/dashboard/api/v2/paper",
    "/dashboard/api/v2/paper/positions",
    "/dashboard/api/v2/paper/pnl",
    "/dashboard/api/v2/paper/soak-readiness",
    "/dashboard/api/v2/brain-dialogue",
    "/dashboard/api/v2/neuron-dialogue",
    "/dashboard/api/v2/system-life",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run POLYBOT 4h technical Paper soak.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--duration-minutes", type=float, default=240.0)
    parser.add_argument("--sample-minutes", type=float, default=5.0)
    parser.add_argument("--actor", default="codex")
    parser.add_argument("--reason", default="4h technical paper soak")
    args = parser.parse_args()

    started_at = datetime.now(UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    log_path = Path("logs/soak") / f"4h_paper_soak_{stamp}.log"
    report_path = Path("docs") / f"POLYBOT_4H_TECHNICAL_PAPER_SOAK_REPORT_{stamp}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    samples: list[dict[str, Any]] = []
    status = "RUNNING"
    stop_reason: str | None = None

    try:
        readiness = get_json(args.base_url, "/dashboard/api/v2/paper/soak-readiness")
        paper = get_json(args.base_url, "/dashboard/api/v2/paper")
    except Exception as exc:
        write_line(log_path, {"timestamp": now(), "event": "preflight_failed", "error": str(exc)})
        write_report(report_path, started_at, None, "RED", f"API preflight failed: {exc}", [], None, None)
        return 2

    if readiness.get("can_start_4h_soak") is not True:
        reason = f"readiness_not_green:{readiness.get('readiness_status')}:{readiness.get('blockers')}"
        write_line(log_path, {"timestamp": now(), "event": "readiness_blocked", "readiness": readiness})
        write_report(report_path, started_at, None, "RED", reason, [], paper, None)
        return 3

    baseline = safety_counts(paper)
    write_line(log_path, {"timestamp": now(), "event": "baseline", "baseline": baseline, "paper": paper})
    end_at = started_at + timedelta(minutes=args.duration_minutes)
    interval_seconds = max(1.0, args.sample_minutes * 60.0)
    write_report(report_path, started_at, None, "RUNNING", None, [], paper, None)

    try:
        while datetime.now(UTC) < end_at:
            sample = collect_sample(args.base_url, baseline)
            samples.append(sample)
            write_line(log_path, sample)
            stop_reason = evaluate_stop_condition(sample, baseline)
            if stop_reason:
                status = "RED"
                write_line(log_path, {"timestamp": now(), "event": "stop_condition", "reason": stop_reason})
                post_json(
                    args.base_url,
                    "/system/power/off",
                    {"actor": args.actor, "reason": f"technical paper soak stop condition: {stop_reason}", "correlation_id": stamp},
                )
                break
            if args.duration_minutes <= 0:
                break
            sleep_for = min(interval_seconds, max(0.0, (end_at - datetime.now(UTC)).total_seconds()))
            if sleep_for > 0:
                time.sleep(sleep_for)
        else:
            status = "GREEN"
    except KeyboardInterrupt:
        status = "YELLOW"
        stop_reason = "INTERRUPTED"
    except Exception as exc:
        status = "RED"
        stop_reason = f"RUNNER_ERROR:{type(exc).__name__}:{exc}"
        try:
            post_json(
                args.base_url,
                "/system/power/off",
                {"actor": args.actor, "reason": f"technical paper soak runner error: {stop_reason}", "correlation_id": stamp},
            )
        except Exception:
            pass

    final_paper = None
    try:
        final_paper = get_json(args.base_url, "/dashboard/api/v2/paper")
    except Exception:
        pass
    if status == "RUNNING":
        status = "GREEN"
    write_report(report_path, started_at, datetime.now(UTC), status, stop_reason, samples, paper, final_paper)
    write_line(log_path, {"timestamp": now(), "event": "final", "status": status, "stop_reason": stop_reason, "report_path": str(report_path)})
    print(json.dumps({"status": status, "log_path": str(log_path), "report_path": str(report_path), "samples": len(samples), "stop_reason": stop_reason}, indent=2))
    return 0 if status == "GREEN" else 4


def collect_sample(base_url: str, baseline: dict[str, int]) -> dict[str, Any]:
    endpoints: dict[str, Any] = {}
    errors: list[str] = []
    for endpoint in ENDPOINTS:
        try:
            endpoints[endpoint] = {"status": "OK", "payload": get_json(base_url, endpoint)}
        except Exception as exc:
            endpoints[endpoint] = {"status": "ERROR", "error": str(exc)}
            errors.append(f"{endpoint}:{type(exc).__name__}:{exc}")
    paper = endpoints.get("/dashboard/api/v2/paper", {}).get("payload") or {}
    system_life = endpoints.get("/dashboard/api/v2/system-life", {}).get("payload") or {}
    brain = endpoints.get("/dashboard/api/v2/brain-dialogue", {}).get("payload") or {}
    neuron = endpoints.get("/dashboard/api/v2/neuron-dialogue", {}).get("payload") or {}
    mock_data_endpoints = [
        endpoint
        for endpoint, result in endpoints.items()
        if isinstance(result.get("payload"), dict) and result["payload"].get("mock_data") is True
    ]
    sample = {
        "timestamp": now(),
        "system_power": paper.get("system_power"),
        "runtime_health": paper.get("runtime_health"),
        "scheduler_cycle_count": None,
        "latest_cycle_timestamp": (paper.get("latest_runtime") or {}).get("latest_cycle_at"),
        "brain_dialogue_events": paper.get("brain_dialogue_events"),
        "neuron_dialogue_events": paper.get("neuron_dialogue_events"),
        "components_speaking": system_life.get("active_components") or brain.get("components_speaking") or neuron.get("speaking_neurons"),
        "components_silent": system_life.get("silent_components") or brain.get("components_silent") or neuron.get("silent_neurons"),
        "paper_intents": paper.get("paper_intents_total"),
        "paper_orders": paper.get("paper_orders_total"),
        "paper_fills": paper.get("paper_fills_total"),
        "paper_positions": paper.get("paper_positions_total"),
        "open_paper_positions": paper.get("open_paper_positions"),
        "closed_paper_positions": paper.get("closed_paper_positions"),
        "paper_position_closes": paper.get("paper_position_closes"),
        "paper_trade_ledger": paper.get("paper_trade_ledger"),
        "paper_daily_pnl": paper.get("paper_daily_pnl"),
        "realized_pnl": paper.get("realized_pnl"),
        "unrealized_pnl": paper.get("unrealized_pnl"),
        "orphan_positions_count": paper.get("orphan_positions_count"),
        "duplicate_orders_count": paper.get("duplicate_orders_count"),
        "duplicate_fills_count": paper.get("duplicate_fills_count"),
        "duplicate_positions_count": paper.get("duplicate_positions_count"),
        "duplicate_intent_orders_count": paper.get("duplicate_intent_orders_count"),
        "duplicate_order_fills_count": paper.get("duplicate_order_fills_count"),
        "duplicate_fill_positions_count": paper.get("duplicate_fill_positions_count"),
        "positions_without_fills_count": paper.get("positions_without_fills_count"),
        "positions_without_open_ledger_count": paper.get("positions_without_open_ledger_count"),
        "closed_positions_without_close_count": paper.get("closed_positions_without_close_count"),
        "closed_positions_without_close_ledger_count": paper.get("closed_positions_without_close_ledger_count"),
        "executed_intents_reexecuted_count": paper.get("executed_intents_reexecuted_count"),
        "paper_lineage_consistency_status": paper.get("paper_lineage_consistency_status"),
        "paper_lineage_readiness_status": paper.get("paper_lineage_readiness_status"),
        "quarantined_paper_positions_count": paper.get("quarantined_paper_positions_count"),
        "raw_positions_without_fills_count": paper.get("raw_positions_without_fills_count"),
        "raw_positions_without_open_ledger_count": paper.get("raw_positions_without_open_ledger_count"),
        "stale_price_count": paper.get("stale_price_count"),
        "live_orders": paper.get("live_orders"),
        "real_orders": paper.get("real_orders_current"),
        "orders_v2": paper.get("orders_v2"),
        "fills_v2": paper.get("fills_v2"),
        "canonical_positions": paper.get("canonical_positions"),
        "top_blockers": paper.get("top_current_blockers"),
        "endpoint_health": {key: value.get("status") for key, value in endpoints.items()},
        "endpoint_errors": errors,
        "mock_data_endpoints": mock_data_endpoints,
        "safety_delta": {key: int(paper.get(key, 0) or 0) - baseline.get(key, 0) for key in baseline},
    }
    return sample


def evaluate_stop_condition(sample: dict[str, Any], baseline: dict[str, int]) -> str | None:
    if sample.get("endpoint_errors"):
        return "API_UNAVAILABLE"
    if sample.get("mock_data_endpoints"):
        return "MOCK_DASHBOARD_DATA_DETECTED"
    if int(sample.get("live_orders") or 0) > 0:
        return "LIVE_ORDERS_PRESENT"
    for key, reason in (
        ("real_orders_current", "REAL_ORDERS_DELTA"),
        ("orders_v2", "ORDERS_V2_DELTA"),
        ("fills_v2", "FILLS_V2_DELTA"),
        ("canonical_positions", "CANONICAL_POSITIONS_DELTA"),
    ):
        observed_key = "real_orders" if key == "real_orders_current" else key
        if int(sample.get(observed_key) or 0) > baseline.get(key, 0):
            return reason
    if int(sample.get("duplicate_fills_count") or 0) > 0:
        return "DUPLICATE_PAPER_FILLS"
    if int(sample.get("duplicate_positions_count") or 0) > 0:
        return "DUPLICATE_PAPER_POSITIONS"
    if int(sample.get("orphan_positions_count") or 0) > 0:
        return "ORPHAN_PAPER_POSITIONS"
    for key, reason in (
        ("duplicate_intent_orders_count", "DUPLICATE_INTENT_PAPER_ORDERS"),
        ("duplicate_order_fills_count", "DUPLICATE_ORDER_PAPER_FILLS"),
        ("duplicate_fill_positions_count", "DUPLICATE_FILL_PAPER_POSITIONS"),
        ("positions_without_fills_count", "PAPER_POSITIONS_WITHOUT_FILLS"),
        ("positions_without_open_ledger_count", "PAPER_POSITIONS_WITHOUT_OPEN_LEDGER"),
        ("closed_positions_without_close_count", "CLOSED_PAPER_POSITIONS_WITHOUT_CLOSE"),
        ("closed_positions_without_close_ledger_count", "CLOSED_PAPER_POSITIONS_WITHOUT_CLOSE_LEDGER"),
        ("executed_intents_reexecuted_count", "EXECUTED_INTENTS_REEXECUTED"),
    ):
        if int(sample.get(key) or 0) > 0:
            return reason
    if str(sample.get("paper_lineage_consistency_status") or "OK").upper() != "OK":
        return "PAPER_LINEAGE_CONSISTENCY_NOT_OK"
    if str(sample.get("paper_lineage_readiness_status") or "OK").upper() != "OK":
        return "PAPER_LINEAGE_READINESS_NOT_OK"
    if int(sample.get("quarantined_paper_positions_count") or 0) > int(baseline.get("quarantined_paper_positions_count") or 0):
        return "PAPER_QUARANTINE_COUNT_INCREASED"
    if int(sample.get("raw_positions_without_fills_count") or 0) > int(baseline.get("raw_positions_without_fills_count") or 0):
        return "RAW_PAPER_POSITIONS_WITHOUT_FILLS_INCREASED"
    if int(sample.get("raw_positions_without_open_ledger_count") or 0) > int(baseline.get("raw_positions_without_open_ledger_count") or 0):
        return "RAW_PAPER_POSITIONS_WITHOUT_OPEN_LEDGER_INCREASED"
    if int(sample.get("paper_positions") or 0) > int(baseline.get("paper_positions") or 0) and int(sample.get("paper_fills") or 0) <= int(baseline.get("paper_fills") or 0):
        return "PAPER_POSITIONS_INCREASED_WITHOUT_FILLS"
    if int(sample.get("paper_orders") or 0) > int(baseline.get("paper_orders") or 0) and int(sample.get("paper_intents") or 0) <= int(baseline.get("paper_intents") or 0):
        return "PAPER_ORDERS_INCREASED_WITHOUT_INTENTS"
    if int(sample.get("paper_positions") or 0) > int(baseline.get("paper_positions") or 0) and int(sample.get("paper_trade_ledger") or 0) <= int(baseline.get("paper_trade_ledger") or 0):
        return "PAPER_POSITIONS_INCREASED_WITHOUT_LEDGER"
    if str(sample.get("runtime_health") or "").upper() == "RED":
        return "RUNTIME_HEALTH_RED"
    return None


def safety_counts(paper: dict[str, Any]) -> dict[str, int]:
    return {
        "real_orders_current": int(paper.get("real_orders_current") or 0),
        "orders_v2": int(paper.get("orders_v2") or 0),
        "fills_v2": int(paper.get("fills_v2") or 0),
        "canonical_positions": int(paper.get("canonical_positions") or 0),
        "paper_intents": int(paper.get("paper_intents_total") or 0),
        "paper_orders": int(paper.get("paper_orders_total") or 0),
        "paper_fills": int(paper.get("paper_fills_total") or 0),
        "paper_positions": int(paper.get("paper_positions_total") or 0),
        "paper_trade_ledger": int(paper.get("paper_trade_ledger") or 0),
        "quarantined_paper_positions_count": int(paper.get("quarantined_paper_positions_count") or 0),
        "raw_positions_without_fills_count": int(paper.get("raw_positions_without_fills_count") or 0),
        "raw_positions_without_open_ledger_count": int(paper.get("raw_positions_without_open_ledger_count") or 0),
    }


def get_json(base_url: str, endpoint: str) -> dict[str, Any]:
    with urlopen(f"{base_url.rstrip('/')}{endpoint}", timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base_url: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


def write_line(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str, sort_keys=True) + "\n")


def write_report(
    path: Path,
    started_at: datetime,
    finished_at: datetime | None,
    status: str,
    stop_reason: str | None,
    samples: list[dict[str, Any]],
    baseline: dict[str, Any] | None,
    final: dict[str, Any] | None,
) -> None:
    finished_text = finished_at.isoformat() if finished_at else "NOT_COMPLETED"
    lines = [
        "# POLYBOT 4h Technical Paper Soak Report",
        "",
        f"- status: {status}",
        f"- started_at: {started_at.isoformat()}",
        f"- finished_at: {finished_text}",
        f"- samples: {len(samples)}",
        f"- stop_reason: {stop_reason or 'NONE'}",
        "",
        "## Baseline",
        "```json",
        json.dumps(baseline or {}, indent=2, default=str),
        "```",
        "",
        "## Final",
        "```json",
        json.dumps(final or {}, indent=2, default=str),
        "```",
        "",
        "## Samples",
        "```json",
        json.dumps(samples, indent=2, default=str),
        "```",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    sys.exit(main())

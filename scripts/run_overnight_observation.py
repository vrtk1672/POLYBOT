from __future__ import annotations

import argparse
import json
import os
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
    "/dashboard/api/v2/source-to-neuron-flow",
    "/dashboard/api/v2/neural-bus",
    "/dashboard/api/v2/mesh-sessions",
    "/dashboard/api/v2/shared-awareness",
    "/dashboard/api/v2/multi-brain-consumption",
    "/dashboard/api/v2/mesh-coordinator",
    "/dashboard/api/v2/paper",
    "/dashboard/api/v2/paper/positions",
    "/dashboard/api/v2/paper/trade-forensics",
    "/dashboard/api/v2/paper/capital",
    "/dashboard/api/v2/positions-awareness",
    "/dashboard/api/v2/source-status",
    "/dashboard/api/v2/ai-context-router",
    "/dashboard/api/v2/overnight/status",
)

SAFE_YELLOW_DEGRADED_SOURCES = {
    "ai_context_router",
    "ollama",
    "ollama_context_generation",
    "ollama_local_model",
    "openai",
    "openai_api",
    "anthropic",
    "anthropic_api",
    "news_provider",
    "reddit_or_social_provider",
    "social_provider",
    "x_twitter",
    "telegram",
    "discord",
}

SAFE_YELLOW_AI_REASONS = {
    "AI_CONTEXT_UNAVAILABLE",
    "OLLAMA_TIMEOUT",
    "OLLAMA_ERROR",
    "OPENAI_RATE_LIMITED",
    "OPENAI_QUOTA_EXCEEDED",
    "OPENAI_ERROR",
    "ANTHROPIC_DEGRADED",
    "ANTHROPIC_ERROR",
    "CLOUD_FALLBACK_DISABLED",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run POLYBOT safe overnight observation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--duration-hours", type=float, default=8.0)
    parser.add_argument("--sample-minutes", type=float, default=5.0)
    parser.add_argument("--actor", default="operator")
    parser.add_argument("--reason", default="overnight observation")
    parser.add_argument("--allow-yellow-preflight", action="store_true")
    args = parser.parse_args()

    started_at = datetime.now(UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    log_path = Path("logs/overnight") / f"overnight_observation_{stamp}.log"
    report_path = Path("docs") / f"POLYBOT_OVERNIGHT_OBSERVATION_REPORT_{stamp}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        preflight = preflight_check(args.base_url)
    except Exception as exc:
        write_line(log_path, {"timestamp": now(), "event": "preflight_failed", "error": str(exc)})
        write_report(report_path, started_at, None, "RED", f"API preflight failed: {exc}", [], None, None)
        return 2

    preflight_status = str(preflight.get("status") or "RED").upper()
    if preflight_status != "GREEN" and not (args.allow_yellow_preflight and preflight_status == "YELLOW"):
        reason = f"preflight_not_green:{preflight_status}:{preflight.get('blockers')}"
        write_line(log_path, {"timestamp": now(), "event": "preflight_blocked", "preflight": preflight})
        write_report(report_path, started_at, None, "RED", reason, [], preflight, None)
        print(json.dumps({"status": "RED", "stop_reason": reason, "log_path": str(log_path), "report_path": str(report_path)}, indent=2))
        return 3

    baseline = safety_counts(preflight.get("paper") or {})
    samples: list[dict[str, Any]] = []
    status = "RUNNING"
    stop_reason: str | None = None
    write_line(log_path, {"timestamp": now(), "event": "baseline", "baseline": baseline, "preflight": preflight})
    write_report(report_path, started_at, None, "RUNNING", None, [], preflight, None)

    end_at = started_at + timedelta(hours=max(0.0, args.duration_hours))
    interval_seconds = max(1.0, args.sample_minutes * 60.0)
    repeated_provider_failures = 0
    repeated_api_failures = 0

    try:
        while datetime.now(UTC) < end_at:
            sample = collect_sample(args.base_url, baseline)
            if sample.get("endpoint_errors"):
                repeated_api_failures += 1
            else:
                repeated_api_failures = 0
            if sample.get("provider_failure"):
                repeated_provider_failures += 1
            else:
                repeated_provider_failures = 0
            sample["repeated_api_failures"] = repeated_api_failures
            sample["repeated_provider_failures"] = repeated_provider_failures
            samples.append(sample)
            write_line(log_path, sample)
            stop_reason = evaluate_stop_condition(
                sample,
                baseline,
                repeated_api_failures=repeated_api_failures,
                repeated_provider_failures=repeated_provider_failures,
            )
            if stop_reason:
                status = "RED"
                write_line(log_path, {"timestamp": now(), "event": "stop_condition", "reason": stop_reason})
                power_off(args.base_url, args.actor, f"overnight observation hard stop: {stop_reason}", stamp)
                break
            if args.duration_hours <= 0:
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
            power_off(args.base_url, args.actor, f"overnight observation runner error: {stop_reason}", stamp)
        except Exception:
            pass

    final = None
    try:
        final = collect_sample(args.base_url, baseline)
    except Exception:
        pass
    if status == "RUNNING":
        status = "GREEN"
    write_report(report_path, started_at, datetime.now(UTC), status, stop_reason, samples, preflight, final)
    write_line(log_path, {"timestamp": now(), "event": "final", "status": status, "stop_reason": stop_reason, "report_path": str(report_path)})
    print(json.dumps({"status": status, "log_path": str(log_path), "report_path": str(report_path), "samples": len(samples), "stop_reason": stop_reason}, indent=2))
    return 0 if status == "GREEN" else 4


def preflight_check(base_url: str) -> dict[str, Any]:
    healthz = get_json(base_url, "/healthz")
    runtime_health = get_json(base_url, "/runtime/health")
    system_power = get_json(base_url, "/system/power")
    source = get_json(base_url, "/dashboard/api/v2/source-status")
    ai_router = get_json(base_url, "/dashboard/api/v2/ai-context-router")
    paper = get_json(base_url, "/dashboard/api/v2/paper")
    readiness = get_json(base_url, "/dashboard/api/v2/paper/soak-readiness")
    overnight = get_json(base_url, "/dashboard/api/v2/overnight/status")
    blockers: list[str] = []
    warnings: list[str] = []
    if healthz.get("status") not in {"ok", "OK"}:
        blockers.append("HEALTHZ_NOT_OK")
    if str(system_power.get("power") or "").upper() not in {"ON", "OFF"}:
        blockers.append("SYSTEM_POWER_UNKNOWN")
    runtime_status = str(runtime_health.get("status") or runtime_health.get("overall_status") or "").upper()
    system_power_state = str(system_power.get("power") or "").upper()
    if runtime_status in {"OK", "HEALTHY"}:
        pass
    elif runtime_status == "SAFE_STOPPED" and system_power_state == "OFF":
        pass
    else:
        blockers.append("RUNTIME_HEALTH_NOT_OK")
    if paper.get("mock_data") is not False or overnight.get("mock_data") is not False or source.get("mock_data") is not False or ai_router.get("mock_data") is not False:
        blockers.append("MOCK_DASHBOARD_DATA_DETECTED")
    if int(paper.get("live_orders") or 0) > 0:
        blockers.append("LIVE_ORDERS_PRESENT")
    if paper.get("live_enabled") or paper.get("shadow_enabled"):
        blockers.append("LIVE_OR_SHADOW_ENABLED")
    if str(paper.get("paper_lineage_consistency_status") or "").upper() != "OK":
        blockers.append("PAPER_LINEAGE_NOT_OK")
    if str(paper.get("capital_reconciliation_status") or "OK").upper() == "RED":
        blockers.append("CAPITAL_RECONCILIATION_RED")
    if readiness.get("safety_status") != "GREEN":
        blockers.append("PAPER_SOAK_SAFETY_NOT_GREEN")
    degraded_sources = list(source.get("degraded_sources") or [])
    unsafe_degraded = [item for item in degraded_sources if item not in SAFE_YELLOW_DEGRADED_SOURCES]
    if unsafe_degraded:
        blockers.append(f"UNSAFE_SOURCE_DEGRADED:{unsafe_degraded}")
    elif degraded_sources:
        warnings.append(f"SAFE_YELLOW_SOURCE_DEGRADED:{degraded_sources}")
    ai_required = _bool_env("AI_REQUIRED", False)
    ai_latest = str(ai_router.get("latest_status") or "NO_RUNS").upper()
    ai_reasons = _ai_reasons(ai_router)
    ai_degraded = ai_latest in {"AI_CONTEXT_UNAVAILABLE", "AI_DEGRADED"} or bool(ai_reasons & SAFE_YELLOW_AI_REASONS)
    if ai_required and ai_degraded:
        blockers.append(f"AI_REQUIRED_BUT_DEGRADED:{sorted(ai_reasons) or [ai_latest]}")
    elif ai_degraded:
        warnings.append(f"SAFE_YELLOW_AI_DEGRADED:{sorted(ai_reasons) or [ai_latest]}")
    status = "RED" if blockers else "YELLOW" if warnings else "GREEN"
    return {
        "mock_data": False,
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "ai_required": ai_required,
        "healthz": healthz,
        "runtime_health": runtime_health,
        "system_power": system_power,
        "source": source,
        "ai_router": ai_router,
        "paper": paper,
        "readiness": readiness,
        "overnight": overnight,
    }


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
    source = endpoints.get("/dashboard/api/v2/source-status", {}).get("payload") or {}
    flow = endpoints.get("/dashboard/api/v2/source-to-neuron-flow", {}).get("payload") or {}
    forensics = endpoints.get("/dashboard/api/v2/paper/trade-forensics", {}).get("payload") or {}
    mock_data_endpoints = [
        endpoint
        for endpoint, result in endpoints.items()
        if isinstance(result.get("payload"), dict) and result["payload"].get("mock_data") is True
    ]
    degraded_sources = source.get("degraded_sources") or flow.get("degraded_providers") or []
    unsafe_degraded_sources = [item for item in degraded_sources if item not in SAFE_YELLOW_DEGRADED_SOURCES]
    sample = {
        "timestamp": now(),
        "system_power": paper.get("system_power"),
        "runtime_health": paper.get("runtime_health"),
        "source_to_neuron_events": (flow.get("events_created") or {}),
        "neural_events": _endpoint_count(endpoints, "/dashboard/api/v2/neural-bus"),
        "mesh_sessions": _endpoint_count(endpoints, "/dashboard/api/v2/mesh-sessions"),
        "shared_awareness": _endpoint_count(endpoints, "/dashboard/api/v2/shared-awareness"),
        "brain_opinions": _endpoint_count(endpoints, "/dashboard/api/v2/multi-brain-consumption"),
        "coordinator_decisions": _endpoint_count(endpoints, "/dashboard/api/v2/mesh-coordinator"),
        "paper_intents": paper.get("paper_intents_total"),
        "paper_orders": paper.get("paper_orders_total"),
        "paper_fills": paper.get("paper_fills_total"),
        "paper_positions": paper.get("paper_positions_total"),
        "paper_trade_ledger": paper.get("paper_trade_ledger"),
        "new_paper_trades": int(paper.get("paper_positions_total") or 0) - baseline.get("paper_positions", 0),
        "open_positions": paper.get("open_paper_positions"),
        "realized_pnl": paper.get("realized_pnl"),
        "unrealized_pnl": paper.get("unrealized_pnl"),
        "lineage_status": paper.get("paper_lineage_consistency_status"),
        "capital_reconciliation_status": paper.get("capital_reconciliation_status"),
        "positions_without_fills_count": paper.get("positions_without_fills_count"),
        "active_positions_without_fills": paper.get("positions_without_fills_count"),
        "live_orders": paper.get("live_orders"),
        "real_orders_current": paper.get("real_orders_current"),
        "orders_v2": paper.get("orders_v2"),
        "fills_v2": paper.get("fills_v2"),
        "canonical_positions": paper.get("canonical_positions"),
        "source_health": source.get("status"),
        "degraded_sources": degraded_sources,
        "unsafe_degraded_sources": unsafe_degraded_sources,
        "provider_failure": bool(unsafe_degraded_sources),
        "ai_context_router": (endpoints.get("/dashboard/api/v2/ai-context-router", {}).get("payload") or {}),
        "latest_coordinator_decisions": (endpoints.get("/dashboard/api/v2/overnight/status", {}).get("payload") or {}).get("latest_coordinator_decisions"),
        "forensics_active_count": forensics.get("active_count"),
        "forensics_quarantined_count": forensics.get("legacy_quarantined_count"),
        "endpoint_health": {key: value.get("status") for key, value in endpoints.items()},
        "endpoint_errors": errors,
        "mock_data_endpoints": mock_data_endpoints,
        "safety_delta": {key: int(paper.get(key, 0) or 0) - baseline.get(key, 0) for key in baseline if key in paper},
    }
    return sample


def evaluate_stop_condition(
    sample: dict[str, Any],
    baseline: dict[str, int],
    *,
    repeated_api_failures: int = 0,
    repeated_provider_failures: int = 0,
) -> str | None:
    if repeated_api_failures >= 3:
        return "DB_OR_API_UNAVAILABLE_REPEATEDLY"
    if sample.get("endpoint_errors"):
        return None
    if sample.get("mock_data_endpoints"):
        return "FAKE_OR_MOCK_DASHBOARD_DATA"
    if int(sample.get("live_orders") or 0) > 0:
        return "LIVE_ORDERS_PRESENT"
    for key, reason in (
        ("real_orders_current", "REAL_ORDERS_DELTA"),
        ("orders_v2", "ORDERS_V2_UNEXPECTED_DELTA"),
        ("fills_v2", "FILLS_V2_UNEXPECTED_DELTA"),
        ("canonical_positions", "CANONICAL_POSITIONS_UNEXPECTED_DELTA"),
    ):
        if int(sample.get(key) or 0) > baseline.get(key, 0):
            return reason
    if str(sample.get("lineage_status") or "").upper() not in {"OK", "GREEN"}:
        return "PAPER_LINEAGE_RED"
    if int(sample.get("active_positions_without_fills") or 0) > 0:
        return "ACTIVE_POSITIONS_WITHOUT_FILLS"
    if str(sample.get("capital_reconciliation_status") or "OK").upper() == "RED":
        return "CAPITAL_RECONCILIATION_RED"
    if repeated_provider_failures >= 3:
        return "PROVIDER_LOOP_FAILING_REPEATEDLY"
    if int(sample.get("paper_positions") or 0) > baseline.get("paper_positions", 0) and int(sample.get("paper_fills") or 0) <= baseline.get("paper_fills", 0):
        return "PAPER_POSITIONS_INCREASED_WITHOUT_FILLS"
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
    }


def _endpoint_count(endpoints: dict[str, Any], endpoint: str) -> Any:
    payload = endpoints.get(endpoint, {}).get("payload") or {}
    for key in ("count", "total", "event_count", "items_count"):
        if key in payload:
            return payload.get(key)
    if isinstance(payload.get("items"), list):
        return len(payload["items"])
    if isinstance(payload.get("latest_items"), list):
        return len(payload["latest_items"])
    return None


def get_json(base_url: str, endpoint: str) -> dict[str, Any]:
    with urlopen(f"{base_url.rstrip('/')}{endpoint}", timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base_url: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(f"{base_url.rstrip('/')}{endpoint}", data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


def power_off(base_url: str, actor: str, reason: str, correlation_id: str) -> None:
    post_json(base_url, "/system/power/off", {"actor": actor, "reason": reason, "correlation_id": correlation_id})


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
    lines = [
        "# POLYBOT Overnight Observation Report",
        "",
        f"- status: {status}",
        f"- started_at: {started_at.isoformat()}",
        f"- finished_at: {finished_at.isoformat() if finished_at else 'NOT_COMPLETED'}",
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


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _ai_reasons(ai_router: dict[str, Any]) -> set[str]:
    reasons: set[str] = set()
    latest = str(ai_router.get("latest_status") or "").upper()
    if latest:
        reasons.add(latest)
    for provider in ("ollama_status", "openai_status", "anthropic_status"):
        status = ai_router.get(provider) or {}
        reason = status.get("reason")
        if reason:
            reasons.add(str(reason).upper())
    for run in ai_router.get("latest_runs") or []:
        for attempt in run.get("providers_attempted_json") or []:
            reason = attempt.get("reason")
            if reason:
                reasons.add(str(reason).upper())
    return reasons


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


READ_ENDPOINTS = (
    "/healthz",
    "/runtime/health",
    "/system/power",
    "/dashboard/api/v2/source-to-neuron-flow",
    "/dashboard/api/v2/ai-context-router",
    "/dashboard/api/v2/neural-bus",
    "/dashboard/api/v2/mesh-sessions",
    "/dashboard/api/v2/shared-awareness",
    "/dashboard/api/v2/multi-brain-consumption",
    "/dashboard/api/v2/mesh-coordinator",
    "/dashboard/api/v2/capital-brain",
    "/dashboard/api/v2/positions-awareness",
    "/dashboard/api/v2/fresh-market-identity",
    "/dashboard/api/v2/clob-token-book-verification",
    "/dashboard/api/v2/live-orderbook-watcher",
    "/dashboard/api/v2/open-position-watchdog",
    "/dashboard/api/v2/fresh-seed-paper-path",
    "/dashboard/api/v2/payout-odds",
    "/dashboard/api/v2/exit-hold",
    "/dashboard/api/v2/capital-efficiency",
    "/dashboard/api/v2/trade-lifecycle",
    "/dashboard/api/v2/freshness-governance",
    "/dashboard/api/v2/lifecycle-governance",
    "/dashboard/api/v2/paper",
    "/dashboard/api/v2/paper/capital",
    "/dashboard/api/v2/paper/trade-forensics",
    "/dashboard/api/v2/overnight/status",
    "/dashboard/api/v2/source-status",
)

SAFE_YELLOW_SOURCES = {
    "ai_context_router",
    "ollama",
    "ollama_context_generation",
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
    "AI_DEGRADED",
    "OLLAMA_TIMEOUT",
    "OLLAMA_ERROR",
    "OPENAI_RATE_LIMITED",
    "OPENAI_QUOTA_EXCEEDED",
    "OPENAI_ERROR",
    "ANTHROPIC_DEGRADED",
    "ANTHROPIC_ERROR",
    "CLOUD_FALLBACK_DISABLED",
}

SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bbearer\s+[A-Za-z0-9_.-]{12,}\b", re.IGNORECASE),
    re.compile(r"\b(?:api_key|apikey|secret|token)=[A-Za-z0-9_.-]{8,}\b", re.IGNORECASE),
)
SECRET_FIELD_NAMES = {
    "authorization",
    "x-api-key",
    "api_key",
    "apikey",
    "openai_api_key",
    "anthropic_api_key",
    "anthropic-api-key",
    "openai-api-key",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a safe active POLYBOT 30-minute SYSTEM ON observation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--duration-minutes", type=float, default=30.0)
    parser.add_argument("--cycle-minutes", type=float, default=3.0)
    parser.add_argument("--actor", default="codex")
    parser.add_argument("--reason", default="active 30m paper intelligence observation")
    args = parser.parse_args()

    started_at = datetime.now(UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"active_30m_observation_{stamp}"
    log_path = Path("logs/observation") / f"{run_id}.log"
    report_path = Path("docs") / f"POLYBOT_ACTIVE_30M_OBSERVATION_REPORT_{stamp}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    preflight = preflight_check(args.base_url)
    write_line(log_path, {"event": "preflight", "timestamp": now(), "preflight": preflight})
    if preflight["status"] not in {"GREEN", "YELLOW"}:
        write_report(report_path, run_id, started_at, datetime.now(UTC), "RED", preflight, [], None, "PREFLIGHT_RED")
        print(json.dumps({"status": "RED", "run_id": run_id, "log_path": str(log_path), "report_path": str(report_path), "blockers": preflight["blockers"]}, indent=2))
        return 3

    baseline = collect_snapshot(args.base_url)
    write_line(log_path, {"event": "baseline", "timestamp": now(), "baseline": baseline})

    samples: list[dict[str, Any]] = []
    status = "RUNNING"
    stop_reason: str | None = None
    repeated_api_failures = 0
    repeated_cycle_failures = 0
    power_on_payload: dict[str, Any] | None = None
    final: dict[str, Any] | None = None

    try:
        power_on_payload = post_json(
            args.base_url,
            "/system/power/on",
            {"actor": args.actor, "reason": args.reason, "correlation_id": run_id},
        )
        write_line(log_path, {"event": "system_on", "timestamp": now(), "payload": sanitize(power_on_payload)})
        end_at = started_at + timedelta(minutes=max(0.0, args.duration_minutes))
        cycle_interval = max(30.0, args.cycle_minutes * 60.0)
        cycle_index = 0
        while datetime.now(UTC) < end_at:
            cycle_index += 1
            cycle_result = run_active_cycle(args.base_url, run_id=run_id, cycle_index=cycle_index)
            if cycle_result.get("errors"):
                repeated_cycle_failures += 1
            else:
                repeated_cycle_failures = 0
            try:
                sample = collect_snapshot(args.base_url)
                repeated_api_failures = 0
            except Exception as exc:
                repeated_api_failures += 1
                sample = {"timestamp": now(), "snapshot_error": f"{type(exc).__name__}:{exc}", "endpoint_errors": [str(exc)]}
            sample["cycle_index"] = cycle_index
            sample["active_cycle"] = cycle_result
            sample["repeated_api_failures"] = repeated_api_failures
            sample["repeated_cycle_failures"] = repeated_cycle_failures
            sample["deltas"] = deltas(baseline, sample)
            samples.append(sample)
            write_line(log_path, sample)
            stop_reason = evaluate_stop_condition(
                sample,
                baseline,
                repeated_api_failures=repeated_api_failures,
                repeated_cycle_failures=repeated_cycle_failures,
            )
            if stop_reason:
                status = "RED"
                write_line(log_path, {"event": "hard_stop", "timestamp": now(), "reason": stop_reason})
                break
            if args.duration_minutes <= 0:
                break
            sleep_for = min(cycle_interval, max(0.0, (end_at - datetime.now(UTC)).total_seconds()))
            if sleep_for > 0:
                time.sleep(sleep_for)
        if status == "RUNNING":
            status = "GREEN"
    except KeyboardInterrupt:
        status = "YELLOW"
        stop_reason = "INTERRUPTED"
    except Exception as exc:
        status = "RED"
        stop_reason = f"RUNNER_ERROR:{type(exc).__name__}:{exc}"
        write_line(log_path, {"event": "runner_error", "timestamp": now(), "error": stop_reason})
    finally:
        try:
            off = post_json(
                args.base_url,
                "/system/power/off",
                {"actor": args.actor, "reason": f"active observation stop: {stop_reason or status}", "correlation_id": f"{run_id}_off"},
            )
            write_line(log_path, {"event": "system_off", "timestamp": now(), "payload": sanitize(off)})
        except Exception as exc:
            status = "RED"
            stop_reason = f"SYSTEM_OFF_FAILED:{type(exc).__name__}:{exc}"
            write_line(log_path, {"event": "system_off_failed", "timestamp": now(), "error": stop_reason})
        try:
            final = collect_snapshot(args.base_url)
        except Exception:
            final = None

    write_report(report_path, run_id, started_at, datetime.now(UTC), status, preflight, samples, final, stop_reason)
    write_line(log_path, {"event": "final", "timestamp": now(), "status": status, "stop_reason": stop_reason, "report_path": str(report_path)})
    print(
        json.dumps(
            {
                "status": status,
                "run_id": run_id,
                "log_path": str(log_path),
                "report_path": str(report_path),
                "samples": len(samples),
                "stop_reason": stop_reason,
                "system_on": bool(power_on_payload),
            },
            indent=2,
        )
    )
    return 0 if status in {"GREEN", "YELLOW"} else 4


def preflight_check(base_url: str) -> dict[str, Any]:
    payloads = {endpoint: get_json(base_url, endpoint) for endpoint in READ_ENDPOINTS}
    blockers: list[str] = []
    warnings: list[str] = []
    healthz = payloads["/healthz"]
    runtime = payloads["/runtime/health"]
    power = payloads["/system/power"]
    paper = payloads["/dashboard/api/v2/paper"]
    capital_truth = payloads["/dashboard/api/v2/paper/capital"]
    source = payloads["/dashboard/api/v2/source-status"]
    ai = payloads["/dashboard/api/v2/ai-context-router"]
    readiness = get_json(base_url, "/dashboard/api/v2/paper/soak-readiness")

    if healthz.get("status") not in {"ok", "OK"}:
        blockers.append("HEALTHZ_NOT_OK")
    runtime_status = str(runtime.get("status") or runtime.get("overall_status") or "").upper()
    if runtime_status not in {"OK", "HEALTHY", "SAFE_STOPPED"}:
        blockers.append(f"RUNTIME_HEALTH_NOT_OK:{runtime_status}")
    if str(power.get("power") or "").upper() != "OFF":
        blockers.append("SYSTEM_NOT_OFF_BEFORE_START")
    if paper.get("live_enabled") or paper.get("shadow_enabled"):
        blockers.append("LIVE_OR_SHADOW_ENABLED")
    if int(paper.get("live_orders") or 0) > 0:
        blockers.append("LIVE_ORDERS_PRESENT")
    if str(paper.get("paper_lineage_consistency_status") or "").upper() != "OK":
        blockers.append("PAPER_LINEAGE_NOT_OK")
    if str(paper.get("capital_reconciliation_status") or "OK").upper() == "RED":
        blockers.append("CAPITAL_RECONCILIATION_RED")
    if capital_truth.get("open_positions_without_lock"):
        blockers.append("OPEN_POSITION_WITHOUT_CAPITAL_LOCK")
    if capital_truth.get("closed_positions_with_active_lock"):
        blockers.append("CLOSED_POSITION_WITH_ACTIVE_LOCK")
    if capital_truth.get("closes_without_release"):
        blockers.append("CLOSE_WITHOUT_CAPITAL_RELEASE")
    if capital_truth.get("closes_without_realized_pnl_applied"):
        blockers.append("CLOSE_WITHOUT_REALIZED_PNL_APPLY")
    if capital_truth.get("duplicate_releases"):
        blockers.append("DUPLICATE_CAPITAL_RELEASE")
    if int(capital_truth.get("duplicate_realized_pnl_apply_count") or capital_truth.get("realized_pnl_double_apply_count") or 0) > 0:
        blockers.append("DUPLICATE_REALIZED_PNL_APPLY")
    governance = payloads["/dashboard/api/v2/lifecycle-governance"]
    freshness = payloads["/dashboard/api/v2/freshness-governance"]
    if str(freshness.get("status") or "").upper() != "OK":
        blockers.append("FRESHNESS_GOVERNANCE_UNAVAILABLE")
    if str(governance.get("status") or "").upper() != "OK":
        blockers.append("LIFECYCLE_GOVERNANCE_UNAVAILABLE")
    if governance.get("bypass_paths_found"):
        blockers.append("LIFECYCLE_BYPASS_PATH_FOUND")
    if int(paper.get("positions_without_fills_count") or 0) > 0:
        blockers.append("ACTIVE_POSITIONS_WITHOUT_FILLS")
    if readiness.get("safety_status") != "GREEN":
        blockers.append("PAPER_SOAK_SAFETY_NOT_GREEN")
    for endpoint, payload in payloads.items():
        if isinstance(payload, dict) and payload.get("mock_data") is True:
            blockers.append(f"MOCK_DATA:{endpoint}")
        if secrets_exposed(payload):
            blockers.append(f"SECRET_EXPOSED:{endpoint}")
    degraded = list(source.get("degraded_sources") or [])
    unsafe_degraded = [item for item in degraded if item not in SAFE_YELLOW_SOURCES]
    if unsafe_degraded:
        blockers.append(f"UNSAFE_SOURCE_DEGRADED:{unsafe_degraded}")
    elif degraded:
        warnings.append(f"SAFE_YELLOW_SOURCE_DEGRADED:{degraded}")
    ai_reasons = ai_reasons_from_payload(ai)
    ai_required = bool(ai.get("ai_required"))
    ai_degraded = str(ai.get("latest_status") or "").upper() in {"AI_CONTEXT_UNAVAILABLE", "AI_DEGRADED"} or bool(ai_reasons & SAFE_YELLOW_AI_REASONS)
    if ai_required and ai_degraded:
        blockers.append(f"AI_REQUIRED_BUT_DEGRADED:{sorted(ai_reasons)}")
    elif ai_degraded:
        warnings.append(f"SAFE_YELLOW_AI:{sorted(ai_reasons)}")
    status = "RED" if blockers else "YELLOW" if warnings else "GREEN"
    return {
        "mock_data": False,
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "payload_summary": summarize_payloads(payloads),
    }


def run_active_cycle(base_url: str, *, run_id: str, cycle_index: int) -> dict[str, Any]:
    errors: list[str] = []
    outputs: dict[str, Any] = {}
    correlation_id = f"{run_id}_cycle_{cycle_index}"
    calls = (
        (
            "source_to_neuron",
            "/source-to-neuron/run",
            {"limit_per_source": 1, "include_ollama_generation": True, "include_cloud_ai_generation": True},
        ),
        (
            "fresh_market_identity",
            "/fresh-market-identity/recover",
            {"limit": 100, "cycle_id": correlation_id, "dry_run": False, "include_stale": True},
        ),
        (
            "clob_token_book_verification",
            "/clob-token-book-verification/run",
            {"limit": 25, "cycle_id": correlation_id, "seed_threshold": 5, "seed_limit": 20, "verify_seeds": True},
        ),
        (
            "live_orderbook_watcher",
            "/live-orderbook-watcher/run",
            {"limit": 25, "cycle_id": correlation_id, "dry_run": False, "max_seconds": 30, "include_priority": 10},
        ),
        (
            "fresh_seed_paper_path",
            "/fresh-seed-paper-path/run",
            {"limit": 25, "cycle_id": correlation_id, "dry_run": False, "max_seconds": 30},
        ),
        ("payout_odds", "/payout-odds/evaluate", {"limit": 100, "dry_run": False}),
        ("exit_hold", "/exit-hold/evaluate", {"limit": 100, "dry_run": False}),
        ("capital_efficiency", "/capital-efficiency/evaluate", {"limit": 100, "dry_run": False}),
        ("trade_lifecycle", "/trade-lifecycle/build", {"limit": 100, "dry_run": False}),
        ("freshness_governance", "/freshness-governance/evaluate", {"limit": 100, "dry_run": False}),
        ("lifecycle_governance", "/lifecycle-governance/evaluate", {"limit": 100, "dry_run": False}),
        ("paper_intents", "/paper/intents/build", {"limit": 100, "write_intents": True, "write_no_trade": True}),
        (
            "open_position_watchdog",
            "/open-position-watchdog/run",
            {"limit": 25, "cycle_id": correlation_id, "dry_run": False, "max_seconds": 30},
        ),
        ("paper_execution", "/paper/execution/run", {"limit": 100, "cycle_id": correlation_id, "correlation_id": correlation_id}),
        ("paper_exits", "/paper/exits/run", {"limit": 100, "correlation_id": correlation_id}),
    )
    for name, endpoint, payload in calls:
        try:
            outputs[name] = sanitize(post_json(base_url, endpoint, payload))
        except Exception as exc:
            errors.append(f"{name}:{type(exc).__name__}:{exc}")
    return {"correlation_id": correlation_id, "outputs": outputs, "errors": errors}


def collect_snapshot(base_url: str) -> dict[str, Any]:
    payloads = {endpoint: get_json(base_url, endpoint) for endpoint in READ_ENDPOINTS}
    paper = payloads["/dashboard/api/v2/paper"]
    capital_truth = payloads["/dashboard/api/v2/paper/capital"]
    neural = payloads["/dashboard/api/v2/neural-bus"]
    mesh = payloads["/dashboard/api/v2/mesh-sessions"]
    awareness = payloads["/dashboard/api/v2/shared-awareness"]
    brains = payloads["/dashboard/api/v2/multi-brain-consumption"]
    coordinator = payloads["/dashboard/api/v2/mesh-coordinator"]
    payout = payloads["/dashboard/api/v2/payout-odds"]
    exit_hold = payloads["/dashboard/api/v2/exit-hold"]
    capital_efficiency = payloads["/dashboard/api/v2/capital-efficiency"]
    trade_lifecycle = payloads["/dashboard/api/v2/trade-lifecycle"]
    freshness_governance = payloads["/dashboard/api/v2/freshness-governance"]
    lifecycle_governance = payloads["/dashboard/api/v2/lifecycle-governance"]
    capital = payloads["/dashboard/api/v2/capital-brain"]
    positions = payloads["/dashboard/api/v2/positions-awareness"]
    forensics = payloads["/dashboard/api/v2/paper/trade-forensics"]
    source = payloads["/dashboard/api/v2/source-status"]
    ai = payloads["/dashboard/api/v2/ai-context-router"]
    return {
        "timestamp": now(),
        "system_power": payloads["/system/power"].get("power"),
        "runtime_health": payloads["/runtime/health"].get("status") or payloads["/runtime/health"].get("overall_status"),
        "endpoint_status": {endpoint: "OK" for endpoint in payloads},
        "mock_data_endpoints": [endpoint for endpoint, payload in payloads.items() if isinstance(payload, dict) and payload.get("mock_data") is True],
        "secret_exposed": any(secrets_exposed(payload) for payload in payloads.values()),
        "source_health": source.get("status"),
        "degraded_sources": source.get("degraded_sources") or [],
        "ai_router": {
            "latest_status": ai.get("latest_status"),
            "selected_provider": ai.get("selected_provider"),
            "ollama_status": ai.get("ollama_status"),
            "anthropic_status": ai.get("anthropic_status"),
            "openai_status": ai.get("openai_status"),
            "success_count": ai.get("success_count"),
            "unavailable_count": ai.get("unavailable_count"),
            "secrets_exposed": ai.get("secrets_exposed"),
        },
        "events_by_type": {row.get("event_type"): int(row.get("count") or 0) for row in neural.get("event_types") or []},
        "neural_events": int(neural.get("total_events") or 0),
        "mesh_sessions": int(mesh.get("total_sessions") or 0),
        "shared_awareness": int(awareness.get("total_awareness_records") or 0),
        "brain_opinions": int(brains.get("total_brain_opinions") or 0),
        "mesh_coordinator_decisions": int(coordinator.get("total_mesh_decisions") or 0),
        "mesh_conflicts_detected": int(coordinator.get("conflicts_detected_count") or 0),
        "source_brain_count_avg": brains.get("avg_source_brain_count"),
        "capital_evaluations": int(capital.get("total_evaluations") or 0),
        "payout_odds_evaluations": int(payout.get("total_evaluations") or 0),
        "exit_hold_evaluations": int(exit_hold.get("total_evaluations") or 0),
        "capital_efficiency_evaluations": int(capital_efficiency.get("total_evaluations") or 0),
        "trade_lifecycle_plans": int(trade_lifecycle.get("total_plans") or 0),
        "freshness_governance_checks": int(freshness_governance.get("total_checks") or 0),
        "stale_sources_count": int(freshness_governance.get("stale_sources_count") or 0),
        "old_intents_requiring_refresh": int(freshness_governance.get("old_intents_requiring_refresh") or 0),
        "freshness_status_counts": freshness_governance.get("freshness_status_counts") or {},
        "lifecycle_governance_decisions": int(lifecycle_governance.get("total_decisions") or 0),
        "governance_actionability": lifecycle_governance.get("decisions_by_actionability") or {},
        "allow_paper_intent_count": int(lifecycle_governance.get("allow_paper_intent_count") or 0),
        "allow_paper_execution_count": int(lifecycle_governance.get("allow_paper_execution_count") or 0),
        "top_critical_blockers": lifecycle_governance.get("critical_blockers_top") or [],
        "top_optional_missing": lifecycle_governance.get("optional_missing_top") or [],
        "bypass_paths_found": lifecycle_governance.get("bypass_paths_found") or [],
        "capital_decisions": capital.get("decisions_by_type") or {},
        "position_awareness": int(positions.get("total_position_awareness") or 0),
        "position_reactions": positions.get("reaction_counts") or {},
        "paper": paper_counts(paper),
        "paper_capital_truth": paper_capital_counts(capital_truth),
        "forensics_active_count": forensics.get("active_count"),
        "forensics_quarantined_count": forensics.get("legacy_quarantined_count"),
    }


def evaluate_stop_condition(
    sample: dict[str, Any],
    baseline: dict[str, Any],
    *,
    repeated_api_failures: int,
    repeated_cycle_failures: int,
) -> str | None:
    if repeated_api_failures >= 3:
        return "DB_OR_API_UNAVAILABLE_REPEATEDLY"
    if repeated_cycle_failures >= 3:
        return "SOURCE_TO_NEURON_OR_ACTIVE_CYCLE_REPEATED_FAILURE"
    if sample.get("mock_data_endpoints"):
        return "FAKE_OR_MOCK_DASHBOARD_DATA"
    if sample.get("secret_exposed"):
        return "SECRETS_EXPOSED"
    paper = sample.get("paper") or {}
    base_paper = baseline.get("paper") or {}
    if int(paper.get("live_orders") or 0) > 0:
        return "LIVE_ORDERS_PRESENT"
    if paper.get("live_enabled") or paper.get("shadow_enabled"):
        return "LIVE_OR_SHADOW_ENABLED"
    for key, reason in (
        ("real_orders_current", "REAL_ORDERS_DELTA"),
        ("orders_v2", "ORDERS_V2_UNEXPECTED_DELTA"),
        ("fills_v2", "FILLS_V2_UNEXPECTED_DELTA"),
        ("canonical_positions", "CANONICAL_POSITIONS_UNEXPECTED_DELTA"),
    ):
        if int(paper.get(key) or 0) > int(base_paper.get(key) or 0):
            return reason
    if str(paper.get("paper_lineage") or "").upper() not in {"OK", "GREEN"}:
        return "PAPER_LINEAGE_RED"
    if int(paper.get("active_positions_without_fills") or 0) > 0:
        return "ACTIVE_POSITIONS_WITHOUT_FILLS"
    if str(paper.get("capital_reconciliation") or "OK").upper() == "RED":
        return "CAPITAL_RECONCILIATION_RED"
    capital_truth = sample.get("paper_capital_truth") or {}
    if capital_truth.get("open_positions_without_lock"):
        return "OPEN_POSITION_WITHOUT_CAPITAL_LOCK"
    if capital_truth.get("closed_positions_with_active_lock"):
        return "CLOSED_POSITION_WITH_ACTIVE_LOCK"
    if capital_truth.get("locks_without_open_position"):
        return "LOCKS_WITHOUT_OPEN_POSITION"
    if capital_truth.get("closes_without_release"):
        return "CLOSE_WITHOUT_CAPITAL_RELEASE"
    if capital_truth.get("closes_without_realized_pnl_applied"):
        return "CLOSE_WITHOUT_REALIZED_PNL_APPLY"
    if capital_truth.get("duplicate_releases"):
        return "DUPLICATE_CAPITAL_RELEASE"
    if int(capital_truth.get("duplicate_realized_pnl_apply_count") or 0) > 0:
        return "DUPLICATE_REALIZED_PNL_APPLY"
    if sample.get("bypass_paths_found"):
        return "LIFECYCLE_BYPASS_PATH_FOUND"
    paper_positions_delta = int(paper.get("paper_positions") or 0) - int(base_paper.get("paper_positions") or 0)
    paper_fills_delta = int(paper.get("paper_fills") or 0) - int(base_paper.get("paper_fills") or 0)
    paper_orders_delta = int(paper.get("paper_orders") or 0) - int(base_paper.get("paper_orders") or 0)
    if paper_positions_delta > paper_fills_delta:
        return "PAPER_POSITION_CREATED_WITHOUT_FILL"
    if paper_fills_delta > paper_orders_delta:
        return "PAPER_FILL_WITHOUT_ORDER"
    return None


def paper_counts(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "live_orders": int(paper.get("live_orders") or 0),
        "live_enabled": bool(paper.get("live_enabled")),
        "shadow_enabled": bool(paper.get("shadow_enabled")),
        "real_orders_current": int(paper.get("real_orders_current") or 0),
        "orders_v2": int(paper.get("orders_v2") or 0),
        "fills_v2": int(paper.get("fills_v2") or 0),
        "canonical_positions": int(paper.get("canonical_positions") or 0),
        "paper_intents": int(paper.get("paper_intents_total") or 0),
        "paper_orders": int(paper.get("paper_orders_total") or 0),
        "paper_fills": int(paper.get("paper_fills_total") or 0),
        "paper_positions": int(paper.get("paper_positions_total") or 0),
        "paper_position_closes": int(paper.get("paper_position_closes") or 0),
        "paper_trade_ledger": int(paper.get("paper_trade_ledger") or 0),
        "open_positions": int(paper.get("open_paper_positions") or 0),
        "closed_positions": int(paper.get("closed_paper_positions") or 0),
        "active_positions_without_fills": int(paper.get("positions_without_fills_count") or 0),
        "paper_lineage": paper.get("paper_lineage_consistency_status"),
        "capital_reconciliation": paper.get("capital_reconciliation_status"),
        "realized_pnl": float(paper.get("realized_pnl") or 0.0),
        "unrealized_pnl": float(paper.get("unrealized_pnl") or 0.0),
        "available_balance": paper.get("available_balance"),
        "locked_balance": paper.get("locked_balance"),
        "open_exposure": paper.get("open_exposure"),
        "expected_locked_balance": paper.get("expected_locked_balance"),
        "actual_locked_balance": paper.get("actual_locked_balance"),
        "expected_open_exposure": paper.get("expected_open_exposure"),
        "actual_open_exposure": paper.get("actual_open_exposure"),
        "open_positions_without_lock": paper.get("open_positions_without_lock") or [],
        "locks_without_open_position": paper.get("locks_without_open_position") or [],
        "duplicate_releases": paper.get("duplicate_releases") or [],
        "realized_pnl_double_apply_count": int(paper.get("realized_pnl_double_apply_count") or 0),
        "top_blockers": paper.get("top_current_blockers") or [],
    }


def paper_capital_counts(capital: dict[str, Any]) -> dict[str, Any]:
    return {
        "current_balance": capital.get("current_balance"),
        "available_balance": capital.get("available_balance"),
        "locked_balance": capital.get("locked_balance"),
        "open_exposure": capital.get("open_exposure"),
        "realized_pnl": capital.get("realized_pnl"),
        "unrealized_pnl": capital.get("unrealized_pnl"),
        "capital_reconciliation_status": capital.get("capital_reconciliation_status") or capital.get("reconciliation_status"),
        "expected_locked_balance": capital.get("expected_locked_balance"),
        "expected_open_exposure": capital.get("expected_open_exposure"),
        "open_positions_without_lock": capital.get("open_positions_without_lock") or [],
        "locks_without_open_position": capital.get("locks_without_open_position") or [],
        "closed_positions_with_active_lock": capital.get("closed_positions_with_active_lock") or [],
        "closes_without_release": capital.get("closes_without_release") or [],
        "closes_without_realized_pnl_applied": capital.get("closes_without_realized_pnl_applied") or [],
        "duplicate_releases": capital.get("duplicate_releases") or [],
        "duplicate_realized_pnl_apply_count": int(capital.get("duplicate_realized_pnl_apply_count") or capital.get("realized_pnl_double_apply_count") or 0),
    }


def deltas(baseline: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    numeric_keys = (
        "neural_events",
        "mesh_sessions",
        "shared_awareness",
        "brain_opinions",
        "mesh_coordinator_decisions",
        "capital_evaluations",
        "payout_odds_evaluations",
        "exit_hold_evaluations",
        "capital_efficiency_evaluations",
        "trade_lifecycle_plans",
        "freshness_governance_checks",
        "stale_sources_count",
        "old_intents_requiring_refresh",
        "lifecycle_governance_decisions",
        "position_awareness",
    )
    out = {key: int(sample.get(key) or 0) - int(baseline.get(key) or 0) for key in numeric_keys}
    base_paper = baseline.get("paper") or {}
    paper = sample.get("paper") or {}
    out["paper"] = {
        key: int(paper.get(key) or 0) - int(base_paper.get(key) or 0)
        for key in (
            "paper_intents",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "paper_position_closes",
            "paper_trade_ledger",
            "orders_v2",
            "fills_v2",
            "canonical_positions",
            "real_orders_current",
            "live_orders",
        )
    }
    base_events = baseline.get("events_by_type") or {}
    events = sample.get("events_by_type") or {}
    out["events_by_type"] = {key: int(events.get(key) or 0) - int(base_events.get(key) or 0) for key in sorted(set(base_events) | set(events))}
    return out


def write_report(
    path: Path,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    preflight: dict[str, Any],
    samples: list[dict[str, Any]],
    final: dict[str, Any] | None,
    stop_reason: str | None,
) -> None:
    first = samples[0] if samples else None
    last = final or (samples[-1] if samples else None)
    lines = [
        "# POLYBOT Active 30m Observation Report",
        "",
        f"- run_id: {run_id}",
        f"- status: {status}",
        f"- started_at: {started_at.isoformat()}",
        f"- finished_at: {finished_at.isoformat()}",
        f"- samples: {len(samples)}",
        f"- stop_reason: {stop_reason or 'NONE'}",
        "",
        "## Preflight",
        "```json",
        json.dumps(preflight, indent=2, default=str),
        "```",
        "",
        "## First Sample",
        "```json",
        json.dumps(first or {}, indent=2, default=str),
        "```",
        "",
        "## Final Sample",
        "```json",
        json.dumps(last or {}, indent=2, default=str),
        "```",
        "",
        "## Samples",
        "```json",
        json.dumps(samples, indent=2, default=str),
        "```",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize_payloads(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        endpoint: {
            "status": payload.get("status") or payload.get("overall_status") or "OK",
            "mock_data": payload.get("mock_data"),
            "secrets_exposed": payload.get("secrets_exposed"),
        }
        for endpoint, payload in payloads.items()
    }


def ai_reasons_from_payload(ai: dict[str, Any]) -> set[str]:
    reasons: set[str] = set()
    latest = str(ai.get("latest_status") or "").upper()
    if latest:
        reasons.add(latest)
    for key in ("ollama_status", "openai_status", "anthropic_status"):
        reason = (ai.get(key) or {}).get("reason")
        if reason:
            reasons.add(str(reason).upper())
    return reasons


def secrets_exposed(payload: Any) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in SECRET_FIELD_NAMES and value not in {None, "", False}:
                return True
            if secrets_exposed(value):
                return True
        return False
    if isinstance(payload, list):
        return any(secrets_exposed(item) for item in payload)
    if isinstance(payload, str):
        return any(pattern.search(payload) for pattern in SECRET_VALUE_PATTERNS)
    return False


def sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: sanitize(value) for key, value in payload.items() if key.lower() not in SECRET_FIELD_NAMES | {"secret", "token"}}
    if isinstance(payload, list):
        return [sanitize(item) for item in payload]
    if isinstance(payload, str):
        if secrets_exposed(payload):
            return "[REDACTED]"
    return payload


def get_json(base_url: str, endpoint: str) -> dict[str, Any]:
    with urlopen(f"{base_url.rstrip('/')}{endpoint}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base_url: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(f"{base_url.rstrip('/')}{endpoint}", data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


def write_line(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sanitize(payload), sort_keys=True, default=str) + "\n")


def now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from run_active_30m_observation import (
    ai_reasons_from_payload,
    get_json,
    paper_capital_counts,
    paper_counts,
    post_json,
    sanitize,
    secrets_exposed,
    write_line,
)


SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"
BASE_READ_ENDPOINTS = (
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
    "/dashboard/api/v2/truth-state",
    "/dashboard/api/v2/freshness-governance",
    "/dashboard/api/v2/lifecycle-governance",
    "/dashboard/api/v2/risk-evidence-mesh",
    "/dashboard/api/v2/paper",
    "/dashboard/api/v2/paper/capital",
    "/dashboard/api/v2/paper/trade-forensics",
    "/dashboard/api/v2/overnight/status",
    "/dashboard/api/v2/source-status",
)

SAFE_YELLOW_AI = {
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
    "OK",
    "COMPLETED",
}

RISK_DECISIONS = ("RISK_SUPPORT", "RISK_WATCH", "RISK_REVIEW", "RISK_BLOCK")
RISK_BLOCKER_KEYS = (
    "RISK_BLOCKED_STALE_CRITICAL_SOURCE",
    "RISK_BLOCKED_LINEAGE_CRITICAL",
    "RISK_REVIEW_LINEAGE_PARTIAL",
    "RISK_BLOCKED_NO_SOURCE_BACKED_EDGE",
    "RISK_REVIEW_EDGE_WEAK",
    "RISK_WATCH_OPTIONAL_CONTEXT_MISSING",
)
EDGE_KEYS = (
    "PRICE_PAYOUT_ASYMMETRY",
    "NEWS_REPRICING_SIGNAL",
    "ORDERBOOK_LIQUIDITY_SETUP",
    "CAPITAL_EFFICIENCY_SETUP",
    "MULTI_FACTOR_MESH_EDGE",
    "NO_SOURCE_BACKED_EDGE",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run controlled 10m PAPER validation after Risk Evidence governance integration.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--duration-minutes", type=float, default=10.0)
    parser.add_argument("--cycle-minutes", type=float, default=2.0)
    parser.add_argument("--actor", default="codex")
    parser.add_argument("--reason", default="controlled 10m PAPER validation post risk evidence governance integration")
    args = parser.parse_args()

    started_at = datetime.now(UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"controlled_10m_paper_run_post_risk_evidence_governance_{stamp}"
    log_path = Path("logs/observation") / f"{run_id}.log"
    report_path = Path("docs") / f"POLYBOT_CONTROLLED_10M_PAPER_RUN_POST_RISK_EVIDENCE_GOVERNANCE_REPORT_{stamp}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    preflight = preflight_check(args.base_url)
    write_line(log_path, {"event": "preflight", "timestamp": now(), "preflight": preflight})
    if preflight["status"] == "RED":
        write_report(report_path, run_id, started_at, datetime.now(UTC), "RED", preflight, [], None, "PREFLIGHT_RED", log_path)
        print(json.dumps({"status": "RED", "run_id": run_id, "log_path": str(log_path), "report_path": str(report_path), "blockers": preflight["blockers"]}, indent=2))
        return 3

    baseline = collect_snapshot(args.base_url)
    write_line(log_path, {"event": "baseline", "timestamp": now(), "baseline": baseline})

    samples: list[dict[str, Any]] = []
    status = "RUNNING"
    stop_reason: str | None = None
    power_on = None
    final = None
    try:
        power_on = post_json(args.base_url, "/system/power/on", {"actor": args.actor, "reason": args.reason, "correlation_id": run_id})
        write_line(log_path, {"event": "system_on", "timestamp": now(), "payload": sanitize(power_on)})
        end_at = started_at + timedelta(minutes=max(0.0, args.duration_minutes))
        cycle_interval = max(60.0, args.cycle_minutes * 60.0)
        cycle_index = 0
        repeated_api_failures = 0
        repeated_cycle_failures = 0
        while datetime.now(UTC) < end_at:
            cycle_index += 1
            cycle = run_active_cycle(args.base_url, run_id=run_id, cycle_index=cycle_index)
            repeated_cycle_failures = repeated_cycle_failures + 1 if cycle["errors"] else 0
            try:
                sample = collect_snapshot(args.base_url)
                repeated_api_failures = 0
            except Exception as exc:
                repeated_api_failures += 1
                sample = {"timestamp": now(), "snapshot_error": f"{type(exc).__name__}:{exc}"}
            sample["cycle_index"] = cycle_index
            sample["active_cycle"] = cycle
            sample["deltas"] = compute_deltas(baseline, sample)
            samples.append(sample)
            write_line(log_path, sample)
            stop_reason = evaluate_stop_condition(sample, baseline, repeated_api_failures, repeated_cycle_failures)
            if stop_reason:
                status = "RED"
                write_line(log_path, {"event": "hard_stop", "timestamp": now(), "reason": stop_reason})
                break
            sleep_for = min(cycle_interval, max(0.0, (end_at - datetime.now(UTC)).total_seconds()))
            if sleep_for > 0:
                time.sleep(sleep_for)
        if status == "RUNNING":
            status = "YELLOW" if not paper_trades_opened(baseline, samples[-1] if samples else baseline) else "GREEN"
    except Exception as exc:
        status = "RED"
        stop_reason = f"RUNNER_ERROR:{type(exc).__name__}:{exc}"
        write_line(log_path, {"event": "runner_error", "timestamp": now(), "error": stop_reason})
    finally:
        try:
            off = post_json(args.base_url, "/system/power/off", {"actor": args.actor, "reason": f"controlled run stop: {stop_reason or status}", "correlation_id": f"{run_id}_off"})
            write_line(log_path, {"event": "system_off", "timestamp": now(), "payload": sanitize(off)})
        except Exception as exc:
            status = "RED"
            stop_reason = f"SYSTEM_OFF_FAILED:{type(exc).__name__}:{exc}"
            write_line(log_path, {"event": "system_off_failed", "timestamp": now(), "error": stop_reason})
        try:
            final = collect_snapshot(args.base_url)
        except Exception as exc:
            final = {"timestamp": now(), "snapshot_error": f"{type(exc).__name__}:{exc}"}

    write_report(report_path, run_id, started_at, datetime.now(UTC), status, preflight, samples, final, stop_reason, log_path)
    write_line(log_path, {"event": "final", "timestamp": now(), "status": status, "stop_reason": stop_reason, "report_path": str(report_path)})
    print(json.dumps({"status": status, "run_id": run_id, "log_path": str(log_path), "report_path": str(report_path), "cycles": len(samples), "stop_reason": stop_reason, "system_on": bool(power_on)}, indent=2))
    return 0 if status in {"GREEN", "YELLOW"} else 4


def preflight_check(base_url: str) -> dict[str, Any]:
    route_checks: dict[str, Any] = {}
    blockers: list[str] = []
    warnings: list[str] = []
    payloads: dict[str, dict[str, Any]] = {}
    for endpoint in BASE_READ_ENDPOINTS:
        try:
            payload = get_json(base_url, endpoint)
            payloads[endpoint] = payload
            route_checks[endpoint] = {"status": payload.get("status") or payload.get("overall_status") or "OK", "mock_data": payload.get("mock_data"), "secret_exposed": secrets_exposed(payload)}
        except Exception as exc:
            blockers.append(f"ENDPOINT_UNAVAILABLE:{endpoint}:{type(exc).__name__}")
    if blockers:
        return {"mock_data": False, "status": "RED", "blockers": blockers, "warnings": warnings, "route_checks": route_checks}

    health = payloads["/healthz"]
    power = payloads["/system/power"]
    runtime = payloads["/runtime/health"]
    paper = payloads["/dashboard/api/v2/paper"]
    capital = payloads["/dashboard/api/v2/paper/capital"]
    lifecycle = payloads["/dashboard/api/v2/lifecycle-governance"]
    risk_evidence = payloads["/dashboard/api/v2/risk-evidence-mesh"]
    truth = payloads["/dashboard/api/v2/truth-state"]
    freshness = payloads["/dashboard/api/v2/freshness-governance"]
    ai = payloads["/dashboard/api/v2/ai-context-router"]

    if str(health.get("status") or "").lower() != "ok":
        blockers.append("HEALTHZ_NOT_OK")
    if str(power.get("power") or "").upper() != "OFF":
        blockers.append("SYSTEM_NOT_OFF_BEFORE_START")
    runtime_mode = str(runtime.get("mode") or runtime.get("current_mode") or paper.get("runtime_mode") or "PAPER").upper()
    if runtime_mode not in {"PAPER", "PAPER_SAFE", "NONE", ""}:
        blockers.append(f"RUNTIME_NOT_PAPER:{runtime_mode}")
    if paper.get("live_enabled") or paper.get("shadow_enabled"):
        blockers.append("LIVE_OR_SHADOW_ENABLED")
    if int(paper.get("live_orders") or 0) > 0:
        blockers.append("LIVE_ORDERS_PRESENT")
    # Historical real-order counters can exist from earlier controlled evidence.
    # The run hard-stops on any increase from baseline; live_orders must still be zero at preflight.
    if str(capital.get("capital_reconciliation_status") or capital.get("reconciliation_status") or "OK").upper() == "RED":
        blockers.append("CAPITAL_RECONCILIATION_RED")
    for key, reason in (
        ("open_positions_without_lock", "OPEN_POSITION_WITHOUT_CAPITAL_LOCK"),
        ("closed_positions_with_active_lock", "CLOSED_POSITION_WITH_ACTIVE_LOCK"),
        ("closes_without_release", "CLOSE_WITHOUT_CAPITAL_RELEASE"),
        ("closes_without_realized_pnl_applied", "CLOSE_WITHOUT_REALIZED_PNL_APPLY"),
        ("duplicate_releases", "DUPLICATE_CAPITAL_RELEASE"),
    ):
        if capital.get(key):
            blockers.append(reason)
    if int(capital.get("duplicate_realized_pnl_apply_count") or capital.get("realized_pnl_double_apply_count") or 0) > 0:
        blockers.append("DUPLICATE_REALIZED_PNL_APPLY")
    for name, payload in (("truth_state", truth), ("freshness_governance", freshness), ("lifecycle_governance", lifecycle), ("risk_evidence_mesh", risk_evidence)):
        if str(payload.get("status") or "").upper() != "OK":
            blockers.append(f"{name.upper()}_UNAVAILABLE")
    for field in ("risk_evidence_used_count", "legacy_risk_ignored_count", "stale_legacy_risk_block_ignored_count", "risk_source_selection_summary"):
        if field not in lifecycle:
            blockers.append(f"LIFECYCLE_GOVERNANCE_FIELD_MISSING:{field}")
    if lifecycle.get("bypass_paths_found"):
        blockers.append("LIFECYCLE_BYPASS_PATH_FOUND")
    if lifecycle.get("mock_data") is True or risk_evidence.get("mock_data") is True:
        blockers.append("MOCK_DATA_GOVERNANCE")
    if any(check.get("secret_exposed") for check in route_checks.values()):
        blockers.append("SECRET_EXPOSED")

    ai_reasons = ai_reasons_from_payload(ai)
    if ai_reasons and ai_reasons <= SAFE_YELLOW_AI:
        warnings.append(f"SAFE_YELLOW_AI:{sorted(ai_reasons)}")
    status = "RED" if blockers else "YELLOW" if warnings else "GREEN"
    return {
        "mock_data": False,
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "route_checks": route_checks,
        "runtime_mode": runtime_mode or "PAPER",
        "system_power": power.get("power"),
        "live_enabled": bool(paper.get("live_enabled")),
        "shadow_enabled": bool(paper.get("shadow_enabled")),
        "capital_reconciliation_status": capital.get("capital_reconciliation_status") or capital.get("reconciliation_status"),
    }


def run_active_cycle(base_url: str, *, run_id: str, cycle_index: int) -> dict[str, Any]:
    correlation_id = f"{run_id}_cycle_{cycle_index}"
    calls = (
        ("source_to_neuron", "/source-to-neuron/run", {"limit_per_source": 1, "include_ollama_generation": True, "include_cloud_ai_generation": True}),
        ("fresh_market_identity", "/fresh-market-identity/recover", {"limit": 100, "cycle_id": correlation_id, "dry_run": False, "include_stale": True}),
        ("clob_token_book_verification", "/clob-token-book-verification/run", {"limit": 25, "cycle_id": correlation_id, "seed_threshold": 5, "seed_limit": 20, "verify_seeds": True}),
        ("live_orderbook_watcher", "/live-orderbook-watcher/run", {"limit": 25, "cycle_id": correlation_id, "dry_run": False, "max_seconds": 30, "include_priority": 10}),
        ("fresh_seed_paper_path", "/fresh-seed-paper-path/run", {"limit": 25, "cycle_id": correlation_id, "dry_run": False, "max_seconds": 30}),
        ("payout_odds", "/payout-odds/evaluate", {"limit": 100, "dry_run": False}),
        ("exit_hold", "/exit-hold/evaluate", {"limit": 100, "dry_run": False}),
        ("capital_efficiency", "/capital-efficiency/evaluate", {"limit": 100, "dry_run": False}),
        ("trade_lifecycle", "/trade-lifecycle/build", {"limit": 100, "dry_run": False}),
        ("truth_state", "/truth-state/audit", {"limit": 100, "dry_run": False}),
        ("freshness_governance", "/freshness-governance/evaluate", {"limit": 100, "dry_run": False}),
        ("risk_evidence_mesh", "/risk-evidence-mesh/evaluate", {"limit": 100, "dry_run": False}),
        ("lifecycle_governance", "/lifecycle-governance/evaluate", {"limit": 100, "dry_run": False}),
        ("paper_intents", "/paper/intents/build", {"limit": 100, "write_intents": True, "write_no_trade": True}),
        ("paper_execution", "/paper/execution/run", {"limit": 100, "cycle_id": correlation_id, "correlation_id": correlation_id}),
        ("open_position_watchdog", "/open-position-watchdog/run", {"limit": 25, "cycle_id": correlation_id, "dry_run": False, "max_seconds": 30}),
        ("paper_exits", "/paper/exits/run", {"limit": 100, "correlation_id": correlation_id}),
    )
    outputs: dict[str, Any] = {}
    errors: list[str] = []
    for name, endpoint, payload in calls:
        try:
            outputs[name] = sanitize(post_json(base_url, endpoint, payload))
        except Exception as exc:
            errors.append(f"{name}:{type(exc).__name__}:{exc}")
    return {"correlation_id": correlation_id, "outputs": outputs, "errors": errors}


def collect_snapshot(base_url: str) -> dict[str, Any]:
    payloads = {endpoint: get_json(base_url, endpoint) for endpoint in BASE_READ_ENDPOINTS}
    neural = payloads["/dashboard/api/v2/neural-bus"]
    lifecycle = payloads["/dashboard/api/v2/lifecycle-governance"]
    risk = payloads["/dashboard/api/v2/risk-evidence-mesh"]
    truth = payloads["/dashboard/api/v2/truth-state"]
    freshness = payloads["/dashboard/api/v2/freshness-governance"]
    paper = payloads["/dashboard/api/v2/paper"]
    capital = payloads["/dashboard/api/v2/paper/capital"]
    mesh = payloads["/dashboard/api/v2/mesh-sessions"]
    awareness = payloads["/dashboard/api/v2/shared-awareness"]
    brains = payloads["/dashboard/api/v2/multi-brain-consumption"]
    coordinator = payloads["/dashboard/api/v2/mesh-coordinator"]
    payout = payloads["/dashboard/api/v2/payout-odds"]
    exit_hold = payloads["/dashboard/api/v2/exit-hold"]
    capital_eff = payloads["/dashboard/api/v2/capital-efficiency"]
    trade_lifecycle = payloads["/dashboard/api/v2/trade-lifecycle"]
    forensics = payloads["/dashboard/api/v2/paper/trade-forensics"]
    return {
        "timestamp": now(),
        "system_power": payloads["/system/power"].get("power"),
        "runtime_health": payloads["/runtime/health"].get("status") or payloads["/runtime/health"].get("overall_status"),
        "endpoint_status": {endpoint: "OK" for endpoint in payloads},
        "mock_data_endpoints": [endpoint for endpoint, payload in payloads.items() if isinstance(payload, dict) and payload.get("mock_data") is True],
        "secret_exposed": any(secrets_exposed(payload) for payload in payloads.values()),
        "events_by_type": {row.get("event_type"): int(row.get("count") or 0) for row in neural.get("event_types") or []},
        "neural_events": int(neural.get("total_events") or 0),
        "mesh_sessions": int(mesh.get("total_sessions") or 0),
        "shared_awareness": int(awareness.get("total_awareness_records") or 0),
        "brain_opinions": int(brains.get("total_brain_opinions") or 0),
        "mesh_coordinator_decisions": int(coordinator.get("total_mesh_decisions") or 0),
        "truth_state_counts": truth.get("truth_state_counts") or truth.get("truth_states") or {},
        "truth_permission_counts": truth.get("decision_permission_counts") or truth.get("permission_counts") or {},
        "payout_odds_evaluations": int(payout.get("total_evaluations") or 0),
        "exit_hold_evaluations": int(exit_hold.get("total_evaluations") or 0),
        "capital_efficiency_evaluations": int(capital_eff.get("total_evaluations") or 0),
        "trade_lifecycle_plans": int(trade_lifecycle.get("total_plans") or 0),
        "risk_evidence_mesh_evaluations": int(risk.get("total_evaluations") or 0),
        "risk_evidence_decisions": {key: int(risk.get(key) or 0) for key in RISK_DECISIONS},
        "risk_evidence_blockers": {key: int((risk.get("blocker_subtypes") or {}).get(key) or 0) for key in RISK_BLOCKER_KEYS},
        "risk_evidence_edge_source_types": {key: int((risk.get("edge_source_type_counts") or {}).get(key) or 0) for key in EDGE_KEYS},
        "freshness_governance_checks": int(freshness.get("total_checks") or 0),
        "freshness_status_counts": freshness.get("freshness_status_counts") or {},
        "stale_sources_count": int(freshness.get("stale_sources_count") or 0),
        "lifecycle_governance_decisions": int(lifecycle.get("total_decisions") or 0),
        "governance_actionability": lifecycle.get("decisions_by_actionability") or {},
        "risk_source_selection": {
            "risk_evidence_used_count": int(lifecycle.get("risk_evidence_used_count") or 0),
            "legacy_risk_ignored_count": int(lifecycle.get("legacy_risk_ignored_count") or 0),
            "stale_legacy_risk_block_ignored_count": int(lifecycle.get("stale_legacy_risk_block_ignored_count") or 0),
            "risk_review_promoted_to_watch_count": int(lifecycle.get("risk_review_promoted_to_watch_count") or 0),
            "risk_review_kept_blocked_count": int(lifecycle.get("risk_review_kept_blocked_count") or 0),
            "risk_review_actionable_count": int(lifecycle.get("risk_review_actionable_count") or 0),
            "risk_source_selection_summary": lifecycle.get("risk_source_selection_summary") or [],
        },
        "allow_paper_intent_count": int(lifecycle.get("allow_paper_intent_count") or 0),
        "allow_paper_execution_count": int(lifecycle.get("allow_paper_execution_count") or 0),
        "top_critical_blockers": lifecycle.get("critical_blockers_top") or [],
        "top_optional_missing": lifecycle.get("optional_missing_top") or [],
        "latest_risk_review_traces": lifecycle.get("latest_risk_review_traces") or [],
        "bypass_paths_found": lifecycle.get("bypass_paths_found") or [],
        "paper": paper_counts(paper),
        "paper_capital_truth": paper_capital_counts(capital),
        "forensics_active_count": forensics.get("active_count"),
        "forensics_quarantined_count": forensics.get("legacy_quarantined_count"),
    }


def evaluate_stop_condition(sample: dict[str, Any], baseline: dict[str, Any], repeated_api_failures: int, repeated_cycle_failures: int) -> str | None:
    if repeated_api_failures >= 3:
        return "DB_OR_API_UNAVAILABLE_REPEATEDLY"
    if repeated_cycle_failures >= 3:
        return "ACTIVE_CYCLE_REPEATED_FAILURE"
    if sample.get("mock_data_endpoints"):
        return "FAKE_OR_MOCK_DASHBOARD_DATA"
    if sample.get("secret_exposed"):
        return "SECRETS_EXPOSED"
    paper = sample.get("paper") or {}
    base_paper = baseline.get("paper") or {}
    if int(paper.get("live_orders") or 0) > 0 or paper.get("live_enabled") or paper.get("shadow_enabled"):
        return "LIVE_OR_SHADOW_ENABLED_OR_ORDER_PRESENT"
    for key, reason in (("real_orders_current", "REAL_ORDERS_DELTA"), ("orders_v2", "ORDERS_V2_UNEXPECTED_DELTA"), ("fills_v2", "FILLS_V2_UNEXPECTED_DELTA"), ("canonical_positions", "CANONICAL_POSITIONS_UNEXPECTED_DELTA")):
        if int(paper.get(key) or 0) > int(base_paper.get(key) or 0):
            return reason
    if str(paper.get("paper_lineage") or "").upper() not in {"OK", "GREEN"}:
        return "PAPER_LINEAGE_RED"
    if int(paper.get("active_positions_without_fills") or 0) > 0:
        return "ACTIVE_POSITIONS_WITHOUT_FILLS"
    if str(paper.get("capital_reconciliation") or "OK").upper() == "RED":
        return "CAPITAL_RECONCILIATION_RED"
    capital = sample.get("paper_capital_truth") or {}
    for key, reason in (("open_positions_without_lock", "OPEN_POSITION_WITHOUT_CAPITAL_LOCK"), ("closed_positions_with_active_lock", "CLOSED_POSITION_WITH_ACTIVE_LOCK"), ("locks_without_open_position", "LOCKS_WITHOUT_OPEN_POSITION"), ("closes_without_release", "CLOSE_WITHOUT_CAPITAL_RELEASE"), ("closes_without_realized_pnl_applied", "CLOSE_WITHOUT_REALIZED_PNL_APPLY"), ("duplicate_releases", "DUPLICATE_CAPITAL_RELEASE")):
        if capital.get(key):
            return reason
    if int(capital.get("duplicate_realized_pnl_apply_count") or 0) > 0:
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


def compute_deltas(baseline: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    keys = ("neural_events", "mesh_sessions", "shared_awareness", "brain_opinions", "mesh_coordinator_decisions", "payout_odds_evaluations", "exit_hold_evaluations", "capital_efficiency_evaluations", "trade_lifecycle_plans", "risk_evidence_mesh_evaluations", "freshness_governance_checks", "lifecycle_governance_decisions")
    out = {key: int(sample.get(key) or 0) - int(baseline.get(key) or 0) for key in keys}
    out["events_by_type"] = _delta_dict(baseline.get("events_by_type") or {}, sample.get("events_by_type") or {})
    out["truth_state_counts"] = _delta_dict(baseline.get("truth_state_counts") or {}, sample.get("truth_state_counts") or {})
    out["truth_permission_counts"] = _delta_dict(baseline.get("truth_permission_counts") or {}, sample.get("truth_permission_counts") or {})
    out["risk_evidence_decisions"] = _delta_dict(baseline.get("risk_evidence_decisions") or {}, sample.get("risk_evidence_decisions") or {})
    out["risk_evidence_blockers"] = _delta_dict(baseline.get("risk_evidence_blockers") or {}, sample.get("risk_evidence_blockers") or {})
    out["risk_evidence_edge_source_types"] = _delta_dict(baseline.get("risk_evidence_edge_source_types") or {}, sample.get("risk_evidence_edge_source_types") or {})
    out["governance_actionability"] = _delta_dict(baseline.get("governance_actionability") or {}, sample.get("governance_actionability") or {})
    out["risk_source_selection"] = _delta_dict({k: v for k, v in (baseline.get("risk_source_selection") or {}).items() if isinstance(v, int)}, {k: v for k, v in (sample.get("risk_source_selection") or {}).items() if isinstance(v, int)})
    out["paper"] = _delta_dict({k: v for k, v in (baseline.get("paper") or {}).items() if isinstance(v, int)}, {k: v for k, v in (sample.get("paper") or {}).items() if isinstance(v, int)})
    return out


def _delta_dict(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    return {str(key): int(after.get(key) or 0) - int(before.get(key) or 0) for key in sorted(set(before) | set(after))}


def paper_trades_opened(baseline: dict[str, Any], final: dict[str, Any]) -> bool:
    base = baseline.get("paper") or {}
    paper = final.get("paper") or {}
    return any(int(paper.get(key) or 0) > int(base.get(key) or 0) for key in ("paper_orders", "paper_fills", "paper_positions"))


def write_report(path: Path, run_id: str, started_at: datetime, finished_at: datetime, status: str, preflight: dict[str, Any], samples: list[dict[str, Any]], final: dict[str, Any] | None, stop_reason: str | None, log_path: Path) -> None:
    last = final or (samples[-1] if samples else {})
    first = samples[0] if samples else {}
    deltas = compute_deltas(first or last, last) if samples else {}
    start_local = started_at.astimezone().isoformat()
    end_local = finished_at.astimezone().isoformat()
    paper_delta = (last.get("deltas") or {}).get("paper") or deltas.get("paper") or {}
    lines = [
        f"# POLYBOT Controlled 10m PAPER Run Post Risk Evidence Governance Report - {started_at.strftime('%Y%m%dT%H%M%SZ')}",
        "",
        f"- run_id: `{run_id}`",
        f"- security_governance_status: `{SECURITY_GOVERNANCE_STATUS}`",
        "- rebuild_deploy_status: `SEE_FINAL_OUTPUT`",
        f"- preflight_status: `{preflight.get('status')}`",
        f"- run_started: `{'YES' if samples else 'NO'}`",
        f"- phase_status: `{status}`",
        f"- start_utc: `{started_at.isoformat()}`",
        f"- end_utc: `{finished_at.isoformat()}`",
        f"- start_local: `{start_local}`",
        f"- end_local: `{end_local}`",
        f"- duration_seconds: `{round((finished_at - started_at).total_seconds(), 1)}`",
        f"- cycles: `{len(samples)}`",
        f"- hard_stop: `{'YES' if stop_reason else 'NO'}`",
        f"- hard_stop_reason: `{stop_reason or 'NONE'}`",
        f"- log_path: `{log_path}`",
        f"- report_path: `{path}`",
        "",
        "## Preflight",
        f"- blockers: `{preflight.get('blockers')}`",
        f"- warnings: `{preflight.get('warnings')}`",
        f"- runtime_mode: `{preflight.get('runtime_mode')}`",
        f"- live_enabled: `{preflight.get('live_enabled')}`",
        f"- shadow_enabled: `{preflight.get('shadow_enabled')}`",
        f"- capital_reconciliation_status: `{preflight.get('capital_reconciliation_status')}`",
        "",
        "## Cycle Status",
        *_cycle_lines(samples),
        "",
        "## Deltas",
        "```json",
        json.dumps((last.get("deltas") or deltas), indent=2, default=str),
        "```",
        "",
        "## Final Risk Evidence And Governance",
        "```json",
        json.dumps({
            "risk_evidence_decisions": last.get("risk_evidence_decisions"),
            "risk_evidence_blockers": last.get("risk_evidence_blockers"),
            "risk_evidence_edge_source_types": last.get("risk_evidence_edge_source_types"),
            "risk_source_selection": last.get("risk_source_selection"),
            "governance_actionability": last.get("governance_actionability"),
            "allow_paper_intent_count": last.get("allow_paper_intent_count"),
            "allow_paper_execution_count": last.get("allow_paper_execution_count"),
        }, indent=2, default=str),
        "```",
        "",
        "## Capital",
        "```json",
        json.dumps({"before": first.get("paper_capital_truth"), "after": last.get("paper_capital_truth")}, indent=2, default=str),
        "```",
        "",
        "## Paper Result",
        f"- paper trades opened: `{'YES' if any(int(paper_delta.get(key) or 0) > 0 for key in ('paper_orders','paper_fills','paper_positions')) else 'NO'}`",
        f"- paper trades closed: `{'YES' if int(paper_delta.get('paper_position_closes') or 0) > 0 else 'NO'}`",
        f"- paper deltas: `{paper_delta}`",
        "",
        "## Blockers / Closest To Actionable",
        f"- top critical blockers: `{last.get('top_critical_blockers')}`",
        f"- top optional missing: `{last.get('top_optional_missing')}`",
        f"- latest risk review traces: `{last.get('latest_risk_review_traces')}`",
        "",
        "## Safety Checks",
        f"- bypass_paths_found: `{last.get('bypass_paths_found')}`",
        f"- stale_data_authorized_paper: `NO_EVIDENCE`",
        f"- historical_exposure_hard_block_as_active: `NO_EVIDENCE`",
        f"- secret_exposure_check: `{'FAIL' if last.get('secret_exposed') else 'PASS'}`",
        f"- final_system_state: `{last.get('system_power')}`",
        "",
        "## Validation Answers",
        f"1. API rebuild/redeploy succeeded: `SEE_FINAL_OUTPUT`",
        f"2. SYSTEM ON stayed active: `{'YES' if samples and not stop_reason else 'NO'}`",
        f"3. Runtime PAPER: `{preflight.get('runtime_mode')}`",
        f"4. Cycles ran: `{len(samples)}`",
        f"5. Risk Evidence Mesh ran each cycle: `{_component_all_ok(samples, 'risk_evidence_mesh')}`",
        f"6. Lifecycle Governance used fresh Risk Evidence: `{_yes_no((last.get('risk_source_selection') or {}).get('risk_evidence_used_count', 0))}`",
        f"7. Stale legacy Risk ignored when fresh Risk Evidence existed: `{_yes_no((last.get('risk_source_selection') or {}).get('stale_legacy_risk_block_ignored_count', 0))}`",
        f"8. RISK_REVIEW promoted to WATCH_FOR_CONFIRMATION: `{_yes_no((last.get('risk_source_selection') or {}).get('risk_review_promoted_to_watch_count', 0))}`",
        f"9. RISK_REVIEW became ACTIONABLE_SMALL_PAPER: `{_yes_no((last.get('risk_source_selection') or {}).get('risk_review_actionable_count', 0))}`",
        f"10. If not, blocker: `{_top_blocker(last)}`",
        f"11. Paper Intent created: `{_yes_no(int(paper_delta.get('paper_intents') or 0))}`",
        f"12. Paper Order/Fill/Position created: `{_yes_no(sum(int(paper_delta.get(key) or 0) for key in ('paper_orders','paper_fills','paper_positions')))}`",
        f"13. Capital stayed OK: `{_yes_no(str((last.get('paper_capital_truth') or {}).get('capital_reconciliation_status') or '').upper() == 'OK')}`",
        f"14. Any bypass: `{_yes_no(bool(last.get('bypass_paths_found')))}`",
        f"15. Final SYSTEM state: `{last.get('system_power')}`",
        "16. Recommended next step: `Review top critical blockers before longer Paper validation.`",
        "",
        "## Raw First Sample",
        "```json",
        json.dumps(first, indent=2, default=str),
        "```",
        "",
        "## Raw Final Sample",
        "```json",
        json.dumps(last, indent=2, default=str),
        "```",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cycle_lines(samples: list[dict[str, Any]]) -> list[str]:
    if not samples:
        return ["- no cycles ran"]
    names = sorted({name for sample in samples for name in ((sample.get("active_cycle") or {}).get("outputs") or {})})
    lines = []
    for name in names:
        statuses = []
        for sample in samples:
            output = (((sample.get("active_cycle") or {}).get("outputs") or {}).get(name) or {})
            statuses.append(output.get("status") or output.get("overall_status") or "OK")
        lines.append(f"- {name}: `{statuses}`")
    return lines


def _component_all_ok(samples: list[dict[str, Any]], name: str) -> str:
    if not samples:
        return "NO"
    for sample in samples:
        output = (((sample.get("active_cycle") or {}).get("outputs") or {}).get(name) or {})
        if not output:
            return "NO"
        if str(output.get("status") or "OK").upper() in {"ERROR", "RED", "FAILED"}:
            return "NO"
    return "YES"


def _top_blocker(sample: dict[str, Any]) -> str:
    blockers = sample.get("top_critical_blockers") or []
    if not blockers:
        return "NONE"
    first = blockers[0]
    return str(first.get("item") if isinstance(first, dict) else first)


def _yes_no(value: Any) -> str:
    return "YES" if bool(value) else "NO"


def now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    sys.exit(main())

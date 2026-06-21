from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.services.query.full_system_run_query_service import json_default


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
DOCS = ROOT / "docs"
MIGRATIONS = APP / "db" / "migrations"


@dataclass(frozen=True)
class NodeSpec:
    name: str
    code_paths: tuple[str, ...]
    tables: tuple[str, ...]
    api_markers: tuple[str, ...]
    event_prefixes: tuple[str, ...]
    dashboard_endpoint: str | None
    test_globs: tuple[str, ...]
    runtime_endpoint: str | None = None


NODES: tuple[NodeSpec, ...] = (
    NodeSpec("Runtime / State Governor", ("app/runtime",), ("system_state", "system_state_history"), ("/runtime",), ("runtime.",), "/dashboard/api/v2/overview", ("tests/test_runtime_*.py",), "/runtime/state"),
    NodeSpec("Event Bus", ("app/events",), ("event_log", "event_consumers", "event_dlq"), ("/events",), ("event.",), "/dashboard/api/v2/events", ("tests/test_v2_1_*.py",), "/events/lag"),
    NodeSpec("Market Data", ("app/data_foundation", "app/ingestion"), ("markets_v2", "market_snapshots_v2", "orderbook_snapshots"), ("/data",), ("data.", "market."), "/dashboard/api/v2/market", ("tests/test_v2_2_*.py",), "/data/coverage"),
    NodeSpec("News Neuron", ("app/news_neuron",), ("news_sources", "news_raw_events", "news_market_links"), ("/news",), ("news.",), "/dashboard/api/v2/news", ("tests/test_v2_4_*.py",), "/news/health"),
    NodeSpec("Social Neuron", ("app/social_neuron",), ("social_sources", "social_raw_events", "social_market_links"), ("/social",), ("social.",), "/dashboard/api/v2/social", ("tests/test_v2_6_*.py",), "/social/health"),
    NodeSpec("Whale Neuron", ("app/whale_neuron",), ("whale_profiles", "whale_events", "whale_market_scores"), ("/whales",), ("whale.",), "/dashboard/api/v2/whales", ("tests/test_v2_7_whale_*.py",), "/whales/health"),
    NodeSpec("Rules / Wording Neuron", ("app/rules_neuron",), ("rules_analysis", "wording_risk_scores", "compliance_blocks"), ("/rules",), ("rules.",), "/dashboard/api/v2/market", ("tests/test_v2_5_*.py",), "/rules/health"),
    NodeSpec("Market Technical Neurons", ("app/market_neuron",), ("market_technical_signals", "orderbook_signals", "liquidity_signals"), ("/market-neuron",), ("market.technical_", "orderbook.signal.", "liquidity.signal."), "/dashboard/api/v2/market", ("tests/test_v2_8_*.py",), "/market-neuron/health"),
    NodeSpec("Market Memory", ("app/market_memory",), ("market_memory_v2", "market_family_memory", "engine_performance_memory"), ("/market-memory",), ("memory.",), "/dashboard/api/v2/memory", ("tests/test_v2_9_*.py",), "/market-memory/health"),
    NodeSpec("Context Brain", ("app/brains",), ("context_brain_outputs",), ("/brains",), ("brain.",), "/dashboard/api/v2/ai", ("tests/test_v2_10_*.py",), "/brains/health"),
    NodeSpec("Capital Brain", ("app/brains",), ("capital_brain_outputs",), ("/brains",), ("brain.",), "/dashboard/api/v2/capital", ("tests/test_v2_10_*.py",), "/brains/health"),
    NodeSpec("Opportunity Cortex", ("app/opportunity",), ("opportunity_scores_v2",), ("/opportunities",), ("opportunity.",), "/dashboard/api/v2/opportunities", ("tests/test_v2_11_*.py",), "/opportunities/health"),
    NodeSpec("Strategy Router", ("app/strategy",), ("strategy_routes_v2", "engine_decisions", "engine_rejections"), ("/strategy",), ("strategy.",), "/dashboard/api/v2/engines", ("tests/test_v2_12_*.py",), "/strategy/health"),
    NodeSpec("Capital Allocator", ("app/capital",), ("capital_state_v2", "engine_budgets", "capital_allocations_v2"), ("/capital",), ("capital.", "reinvest."), "/dashboard/api/v2/capital", ("tests/test_v2_13_*.py",), "/capital/health"),
    NodeSpec("Risk Gate", ("app/risk",), ("risk_gate_runs", "risk_gate_decisions"), ("/risk",), ("risk.gate.",), "/dashboard/api/v2/risk", ("tests/test_v2_14_*.py",), "/risk/health"),
    NodeSpec("Risk Governor", ("app/risk",), ("risk_governor_state", "risk_limits", "risk_breaches"), ("/risk",), ("risk.governor.", "risk.breach."), "/dashboard/api/v2/risk", ("tests/test_v2_14_*.py",), "/risk/governor"),
    NodeSpec("Execution Cortex", ("app/execution_v2",), ("orders_v2", "fills_v2", "execution_quality"), ("/execution",), ("execution.",), "/dashboard/api/v2/execution", ("tests/test_v2_15_*.py",), "/execution/health"),
    NodeSpec("Exit Cortex", ("app/exit_cortex",), ("exit_plans", "exit_intents", "exit_failures"), ("/exits",), ("exit.",), "/dashboard/api/v2/exits", ("tests/test_v2_16_*.py",), "/exits/health"),
    NodeSpec("No-Trade Intelligence", ("app/no_trade",), ("no_trade_log", "no_trade_reasons", "no_trade_regret_score"), ("/no-trade",), ("no_trade.",), "/dashboard/api/v2/no-trade", ("tests/test_v2_17_*.py",), "/no-trade/health"),
    NodeSpec("Feedback / Learning Loop", ("app/learning",), ("trade_reviews", "engine_learning", "model_adjustments"), ("/learning",), ("learning.",), "/dashboard/api/v2/learning", ("tests/test_v2_19_*.py",), "/learning/health"),
    NodeSpec("Dashboard V2", ("app/services/query/dashboard_v2_query_service.py", "app/api/routes.py"), tuple(), ("/dashboard/api/v2",), tuple(), "/dashboard/api/v2/overview", ("tests/test_v2_18_*.py",), "/dashboard/api/v2/overview"),
    NodeSpec("AI / Local Models / Model Runtime", ("app/ai_brain",), ("ai_requests", "ai_cache", "ai_cost_ledger"), ("/ai",), ("ai.",), "/dashboard/api/v2/ai", ("tests/test_v2_3_*.py",), "/ai/health"),
    NodeSpec("Scheduler / Orchestrator / Runner", ("app/runtime/cycle_orchestrator.py", "scripts/start_runtime.ps1"), ("runtime_cycles_v2", "service_health"), ("/runtime",), ("runtime.",), "/dashboard/api/v2/live-flow", ("tests/test_runtime_*.py",), "/runtime/health"),
    NodeSpec("Tests / Run Scripts / Long-Run Reports", ("tests", "scripts"), tuple(), tuple(), tuple(), None, ("tests/test_v2_20*.py",), None),
)


EDGES: tuple[tuple[str, str, str, str], ...] = (
    ("Market Data", "Market Technical Neurons", "DB/SERVICE", "market/orderbook snapshots feed technical truth"),
    ("Market Technical Neurons", "Market Memory", "DB/SERVICE", "technical snapshots available to memory services"),
    ("News Neuron", "Context Brain", "DB/EVENT", "news links and events are context inputs"),
    ("Social Neuron", "Context Brain", "DB/EVENT", "social signals are context inputs"),
    ("Whale Neuron", "Context Brain", "DB/EVENT", "whale scores are context inputs"),
    ("Rules / Wording Neuron", "Context Brain", "DB/EVENT", "wording risk is context/risk input"),
    ("Context Brain", "Opportunity Cortex", "DB/SERVICE", "context outputs feed opportunity scoring"),
    ("Capital Brain", "Opportunity Cortex", "DB/SERVICE", "capital brain outputs feed opportunity scoring"),
    ("Opportunity Cortex", "Strategy Router", "DB/SERVICE", "opportunity scores feed routing"),
    ("Strategy Router", "Capital Allocator", "DB/SERVICE", "strategy route records feed allocation"),
    ("Capital Allocator", "Risk Gate", "DB/SERVICE", "capital allocation feeds risk decision"),
    ("Risk Gate", "Execution Cortex", "DB/SERVICE", "risk decision required before execution"),
    ("Execution Cortex", "Exit Cortex", "DB/SERVICE", "orders_v2/fills_v2 feed exit planning/monitoring"),
    ("Exit Cortex", "Feedback / Learning Loop", "DB/SERVICE", "exit quality/failures feed learning"),
    ("Execution Cortex", "Feedback / Learning Loop", "DB/SERVICE", "execution quality/fills feed learning"),
    ("No-Trade Intelligence", "Feedback / Learning Loop", "DB/SERVICE", "no-trade regret feeds learning"),
    ("Feedback / Learning Loop", "Market Memory", "DB/MANUAL", "memory updates are confidence-gated"),
    ("All Nodes", "Dashboard V2", "API/QUERY", "dashboard query service aggregates module truth"),
    ("Safety-Sensitive Paths", "Runtime / State Governor", "SERVICE", "mode permissions gate execution actions"),
    ("Safety-Sensitive Paths", "Risk Governor", "SERVICE/DB", "risk governor blocks unsafe action"),
)


def _read_repo_text(paths: tuple[Path, ...]) -> str:
    chunks: list[str] = []
    for path in paths:
        if path.exists() and path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        elif path.exists() and path.is_dir():
            for child in list(path.rglob("*.py")) + list(path.rglob("*.sql")) + list(path.rglob("*.ps1")):
                chunks.append(child.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def migration_text() -> str:
    return _read_repo_text((MIGRATIONS,))


def event_text() -> str:
    return (APP / "events" / "types.py").read_text(encoding="utf-8", errors="ignore")


def router_text() -> str:
    return _read_repo_text((APP / "api", APP / "main.py"))


def dashboard_text() -> str:
    return _read_repo_text((APP / "services" / "query" / "dashboard_v2_query_service.py", APP / "api" / "routes.py"))


def _exists(path: str) -> bool:
    return (ROOT / path).exists()


def _glob_exists(pattern: str) -> bool:
    return bool(list(ROOT.glob(pattern)))


def node_matrix() -> list[dict[str, Any]]:
    migrations = migration_text()
    events = event_text()
    routers = router_text()
    dashboard = dashboard_text()
    matrix: list[dict[str, Any]] = []
    for spec in NODES:
        code_exists = all(_exists(path) for path in spec.code_paths)
        db_truth = True if not spec.tables else all(table in migrations for table in spec.tables)
        api_truth = True if not spec.api_markers else all(marker in routers for marker in spec.api_markers)
        event_truth = True if not spec.event_prefixes else any(prefix in events for prefix in spec.event_prefixes)
        dashboard_truth = True if spec.dashboard_endpoint is None else spec.dashboard_endpoint in dashboard
        tests = any(_glob_exists(pattern) for pattern in spec.test_globs)
        missing = []
        if not code_exists:
            missing.append("code_path")
        if not db_truth:
            missing.append("db_truth")
        if not api_truth:
            missing.append("api_truth")
        if not event_truth:
            missing.append("event_truth")
        if not dashboard_truth:
            missing.append("dashboard_truth")
        if not tests:
            missing.append("tests")
        status = "GREEN" if not missing else "YELLOW"
        blocker = "NONE" if not missing else "MEDIUM"
        if "code_path" in missing or "api_truth" in missing:
            blocker = "HIGH"
        matrix.append(
            {
                "node_name": spec.name,
                "status": status,
                "code_exists": code_exists,
                "db_truth": db_truth,
                "api_truth": api_truth,
                "event_truth": event_truth,
                "dashboard_truth": dashboard_truth,
                "tests": tests,
                "runtime_health": "CHECK_BY_RUNTIME_SCRIPT" if spec.runtime_endpoint else "N/A",
                "handles_missing_data_safely": "REQUIRES_RUNTIME_CONFIRMATION",
                "produces_useful_output": "REQUIRES_RUNTIME_CONFIRMATION",
                "consumes_required_upstream_truth": "STATIC_EVIDENCE_PRESENT",
                "emits_downstream_consumable_truth": "STATIC_EVIDENCE_PRESENT",
                "respects_state_governor": "SAFETY_REGRESSION_REQUIRED",
                "respects_risk_governor": "RELEVANT_FOR_SAFETY_PATHS",
                "does_not_create_live_orders": "SAFETY_REGRESSION_REQUIRED",
                "stale_no_data_behavior": "DASHBOARD_OR_MODULE_HEALTH_REQUIRED",
                "missing_items": missing,
                "blocker_level": blocker,
                "notes": "; ".join(missing) if missing else "static surface present",
            }
        )
    return matrix


def edge_matrix(nodes: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    nodes = nodes or node_matrix()
    node_status = {node["node_name"]: node["status"] for node in nodes}
    rows: list[dict[str, Any]] = []
    for from_node, to_node, connection_type, evidence in EDGES:
        from_ok = from_node in {"All Nodes", "Safety-Sensitive Paths"} or node_status.get(from_node) == "GREEN"
        to_ok = node_status.get(to_node) == "GREEN"
        status = "CONNECTED" if from_ok and to_ok else "PARTIAL"
        missing = []
        if not from_ok:
            missing.append(f"{from_node}_not_green")
        if not to_ok:
            missing.append(f"{to_node}_not_green")
        rows.append(
            {
                "from_node": from_node,
                "to_node": to_node,
                "connection_type": connection_type,
                "status": status,
                "evidence": evidence,
                "missing_items": missing,
                "blocker_level": "NONE" if not missing else "MEDIUM",
            }
        )
    return rows


def ai_model_readiness() -> dict[str, Any]:
    expected_models = ["qwen3:8b", "qwen3:14b", "deepseek-r1:14b", "cloud-critical-reasoner", "claude-opus-4-6"]
    ollama_path = shutil.which("ollama")
    installed_models: list[str] = []
    ollama_error = None
    if ollama_path:
        try:
            proc = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
            if proc.returncode == 0:
                for line in proc.stdout.splitlines()[1:]:
                    parts = line.split()
                    if parts:
                        installed_models.append(parts[0])
            else:
                ollama_error = proc.stderr.strip() or "ollama list failed"
        except Exception as exc:
            ollama_error = str(exc)
    missing_local = [model for model in expected_models[:3] if model not in installed_models]
    return {
        "expected_runtime": "LocalAIWorker transport plus optional Ollama-compatible local models; legacy/lite services use Anthropic when enabled.",
        "expected_models": expected_models,
        "ollama_binary": ollama_path or None,
        "installed_models": installed_models,
        "missing_models": missing_local if ollama_path else expected_models[:3],
        "anthropic_api_key_present": bool(os.getenv("ANTHROPIC_API_KEY")),
        "cloud_model_names": ["cloud-critical-reasoner", "claude-opus-4-6"],
        "fallback_behavior": "Hybrid AI returns UNAVAILABLE/BUDGET_BLOCKED/AI_UNAVAILABLE style responses; dashboard exposes AI cost/cache truth.",
        "crash_risk": "MEDIUM if legacy lite services are invoked without ANTHROPIC_API_KEY; LOW for HybridAIBrainService unavailable local models.",
        "ollama_error": ollama_error,
        "remediation": [
            "Install Ollama only if local model runtime is required for the run.",
            "ollama pull qwen3:8b",
            "ollama pull qwen3:14b",
            "ollama pull deepseek-r1:14b",
            "Set ANTHROPIC_API_KEY only for explicitly approved cloud/lite analysis paths; do not require it for safety smoke.",
        ],
    }


def runtime_readiness() -> dict[str, Any]:
    docker = _command_status(["docker", "info"])
    postgres = _postgres_status()
    migrations = _migration_status()
    return {
        "docker": docker,
        "postgres": postgres,
        "migrations": migrations,
        "redis": {"status": "NOT_DETECTED", "required": False},
        "startup_scripts": {
            "canonical": "scripts/start_runtime.ps1",
            "v2_20_smoke": ["scripts/run_v2_20_data_only_smoke.ps1", "scripts/run_v2_20_paper_smoke.ps1"],
            "long_run": ["scripts/run_v2_20_24h_data_only.ps1", "scripts/run_v2_20_24h_paper.ps1", "scripts/run_v2_20_72h_paper.ps1", "scripts/run_v2_20_7d_paper.ps1"],
        },
        "ports": {"runtime": "127.0.0.1:8000", "postgres": "127.0.0.1:55432"},
        "env_vars": {
            "POLYBOT_DATABASE_URL_present": bool(os.getenv("POLYBOT_DATABASE_URL")),
            "LIVE_TRADING_ENABLED": os.getenv("LIVE_TRADING_ENABLED", "<unset>"),
            "LIVE_EXECUTION_ENABLED": os.getenv("LIVE_EXECUTION_ENABLED", "<unset>"),
        },
        "known_windows_issue": "Canonical script can remain attached; use hidden direct python fallback in V2.20 smoke scripts when needed.",
    }


def data_source_readiness() -> list[dict[str, Any]]:
    return [
        {"source": "market", "required_for": "Market Data / Technical / Opportunity", "status": "UNKNOWN_UNTIL_RUNTIME", "fallback": "NO_DATA/STALE", "blocker_level": "HIGH"},
        {"source": "orderbook", "required_for": "Liquidity / Execution / Exit", "status": "UNKNOWN_UNTIL_RUNTIME", "fallback": "block execution or record insufficient_data", "blocker_level": "HIGH"},
        {"source": "news", "required_for": "News / Context / Exit invalidation", "status": "UNKNOWN_UNTIL_RUNTIME", "fallback": "stale/no-data news truth", "blocker_level": "MEDIUM"},
        {"source": "social", "required_for": "Social / Context", "status": "UNKNOWN_UNTIL_RUNTIME", "fallback": "stale/no-data social truth", "blocker_level": "MEDIUM"},
        {"source": "whales", "required_for": "Whale / Context / Learning", "status": "UNKNOWN_UNTIL_RUNTIME", "fallback": "stale/no-data whale truth", "blocker_level": "MEDIUM"},
        {"source": "rules", "required_for": "Rules / Opportunity / Risk", "status": "STATIC_CODE_PRESENT", "fallback": "bad/missing rules penalize or no-trade", "blocker_level": "MEDIUM"},
        {"source": "AI", "required_for": "Optional interpretation", "status": "PARTIAL", "fallback": "UNAVAILABLE/BUDGET_BLOCKED", "blocker_level": "MEDIUM"},
    ]


def runtime_endpoint_check(base_url: str) -> dict[str, Any]:
    endpoints = [
        "/healthz",
        "/runtime/state",
        "/runtime/health",
        "/dashboard/api/v2/overview",
        "/dashboard/api/v2/learning",
        "/ai/health",
        "/events/lag",
        "/risk/health",
        "/execution/health",
        "/exits/health",
        "/no-trade/health",
        "/learning/health",
    ]
    results: dict[str, Any] = {}
    for endpoint in endpoints:
        try:
            with urllib.request.urlopen(base_url.rstrip("/") + endpoint, timeout=8) as response:
                results[endpoint] = {"ok": True, "status_code": response.status}
        except Exception as exc:
            results[endpoint] = {"ok": False, "error": str(exc)}
    return results


def build_audit(base_url: str | None = None) -> dict[str, Any]:
    nodes = node_matrix()
    edges = edge_matrix(nodes)
    blockers = classify_blockers(nodes, edges)
    return {
        "audit_id": "v2_20a_neural_mesh_readiness",
        "node_matrix": nodes,
        "edge_matrix": edges,
        "ai_model_readiness": ai_model_readiness(),
        "data_source_readiness": data_source_readiness(),
        "runtime_readiness": runtime_readiness(),
        "runtime_endpoint_check": runtime_endpoint_check(base_url) if base_url else {"status": "NOT_RUN"},
        "blockers": blockers,
        "fix_plan": [
            "V2.20A: Readiness Audit only.",
            "V2.20B: Fix critical mesh blockers.",
            "V2.20C: DATA_ONLY 30m smoke.",
            "V2.20D: PAPER 30m smoke.",
            "V2.20E: 24h DATA_ONLY.",
            "V2.20F: 24h PAPER.",
            "V2.20G: 72h PAPER.",
            "V2.20H: 7d PAPER.",
        ],
    }


def classify_blockers(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}
    for node in nodes:
        if node["blocker_level"] in {"HIGH", "MEDIUM"}:
            result[node["blocker_level"]].append(
                {
                    "title": f"{node['node_name']} has incomplete static readiness",
                    "affected_node": node["node_name"],
                    "evidence": node["missing_items"],
                    "why_it_matters": "Long-run readiness requires code, DB/API/event/dashboard/test truth to be visible.",
                    "suggested_fix": "Inspect missing surface and either wire it or document why the node is intentionally read-only/partial.",
                    "estimated_scope": "small" if len(node["missing_items"]) <= 2 else "medium",
                    "can_safely_defer": "YES" if node["blocker_level"] == "MEDIUM" else "NO",
                }
            )
    for edge in edges:
        if edge["status"] != "CONNECTED":
            result["MEDIUM"].append(
                {
                    "title": f"{edge['from_node']} -> {edge['to_node']} is partial",
                    "affected_edge": f"{edge['from_node']} -> {edge['to_node']}",
                    "evidence": edge["missing_items"],
                    "why_it_matters": "Neural mesh long runs need consumable downstream truth, not isolated services.",
                    "suggested_fix": "Run runtime smoke and inspect source/target rows/events for real flow.",
                    "estimated_scope": "medium",
                    "can_safely_defer": "NO" if "Risk" in edge["to_node"] or "Execution" in edge["to_node"] else "YES",
                }
            )
    return result


def _command_status(command: list[str]) -> dict[str, Any]:
    if shutil.which(command[0]) is None:
        return {"status": "MISSING_BINARY", "command": command[0]}
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=10)
        return {"status": "OK" if proc.returncode == 0 else "FAILED", "returncode": proc.returncode}
    except Exception as exc:
        return {"status": "FAILED", "error": str(exc)}


def _postgres_status() -> dict[str, Any]:
    try:
        factory = DatabaseConnectionFactory()
        with factory.connect() as conn:
            row = conn.execute("SELECT 1 AS ok").fetchone()
        return {"status": "OK" if row and row["ok"] == 1 else "FAILED"}
    except Exception as exc:
        return {"status": "FAILED", "error": str(exc)}


def _migration_status() -> dict[str, Any]:
    try:
        factory = DatabaseConnectionFactory()
        with factory.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM schema_migrations").fetchone()
        return {"status": "OK", "applied_count": int(row["count"] or 0)}
    except Exception as exc:
        return {"status": "UNKNOWN", "error": str(exc)}


def write_audit(args: argparse.Namespace) -> int:
    payload = build_audit(args.base_url if args.with_runtime else None)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=json_default), encoding="utf-8")
    print(json.dumps({"audit_path": str(path), "node_count": len(payload["node_matrix"]), "edge_count": len(payload["edge_matrix"])}, indent=2))
    return 0


def print_ai(args: argparse.Namespace) -> int:
    print(json.dumps(ai_model_readiness(), indent=2, default=json_default))
    return 0


def print_runtime(args: argparse.Namespace) -> int:
    print(json.dumps(runtime_readiness(), indent=2, default=json_default))
    return 0


def print_edges(args: argparse.Namespace) -> int:
    print(json.dumps(edge_matrix(), indent=2, default=json_default))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="POLYBOT V2.20A neural mesh readiness audit")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--out", default="run_reports/v2_20a/neural_mesh_readiness_audit.json")
    audit.add_argument("--base-url", default="http://127.0.0.1:8000")
    audit.add_argument("--with-runtime", action="store_true")
    audit.set_defaults(func=write_audit)
    ai = sub.add_parser("ai-models")
    ai.set_defaults(func=print_ai)
    runtime = sub.add_parser("runtime")
    runtime.set_defaults(func=print_runtime)
    edges = sub.add_parser("edges")
    edges.set_defaults(func=print_edges)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

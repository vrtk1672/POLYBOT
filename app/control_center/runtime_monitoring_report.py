from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.utils.json_safety import json_safe


MONITORING_SNAPSHOT_KEYS = (
    "minute",
    "captured_at",
    "runtime_state",
    "supervisor_state",
    "degraded_reason",
    "current_active_cycle",
    "latest_completed_cycle",
    "events_count",
    "linked_events_count",
    "triggers_count",
    "candidates_generated",
    "mesh_reviewed",
    "paper_observation_count",
    "policy_eligible_count",
    "paper_runtime_decisions",
    "unique_decision_markets",
    "unique_decision_sides",
    "duplicate_suppression",
    "top_blockers",
    "paper_intents",
    "paper_orders",
    "paper_fills",
    "paper_positions",
    "open_paper_positions",
    "pnl",
    "live_orders",
    "shadow_orders",
    "real_orders",
    "latest_errors",
)


def build_monitoring_snapshot(*, minute: int, overview: dict[str, Any], health: dict[str, Any] | None = None) -> dict[str, Any]:
    decisions = overview.get("decisions") if isinstance(overview.get("decisions"), dict) else {}
    execution = overview.get("execution") if isinstance(overview.get("execution"), dict) else {}
    sources = overview.get("sources_events") if isinstance(overview.get("sources_events"), dict) else {}
    triggers = overview.get("triggers") if isinstance(overview.get("triggers"), dict) else {}
    candidates = overview.get("candidates") if isinstance(overview.get("candidates"), dict) else {}
    runtime_truth = overview.get("runtime_truth") if isinstance(overview.get("runtime_truth"), dict) else {}
    supervisor = overview.get("supervisor") if isinstance(overview.get("supervisor"), dict) else {}
    return json_safe(
        {
            "minute": int(minute),
            "captured_at": datetime.now(UTC).isoformat(),
            "runtime_state": overview.get("runtime_state"),
            "supervisor_state": overview.get("supervisor_state"),
            "degraded_reason": _first_reason(supervisor.get("errors"), overview.get("errors"), supervisor.get("warnings")),
            "current_active_cycle": runtime_truth.get("current_active_cycle_id") or (health or {}).get("active_cycle_id"),
            "latest_completed_cycle": runtime_truth.get("latest_completed_cycle_id"),
            "events_count": sources.get("recent_events"),
            "linked_events_count": sources.get("linked_events"),
            "triggers_count": triggers.get("total"),
            "candidates_generated": candidates.get("seeds_generated"),
            "mesh_reviewed": candidates.get("mesh_reviewed"),
            "paper_observation_count": decisions.get("paper_ready_decisions"),
            "policy_eligible_count": decisions.get("paper_ready_decisions"),
            "paper_runtime_decisions": decisions.get("runtime_decisions_total"),
            "unique_decision_markets": decisions.get("unique_market_count"),
            "unique_decision_sides": decisions.get("unique_side_count"),
            "duplicate_suppression": decisions.get("duplicate_suppression_count"),
            "top_blockers": decisions.get("top_blockers") or [],
            "paper_intents": execution.get("paper_intents"),
            "paper_orders": execution.get("paper_orders"),
            "paper_fills": execution.get("paper_fills"),
            "paper_positions": execution.get("paper_positions"),
            "open_paper_positions": execution.get("open_paper_positions"),
            "pnl": overview.get("pnl") or {},
            "live_orders": execution.get("live_orders"),
            "shadow_orders": execution.get("shadow_orders"),
            "real_orders": execution.get("real_orders"),
            "latest_errors": overview.get("errors") or [],
        }
    )


def missing_monitoring_snapshot_keys(snapshot: dict[str, Any]) -> list[str]:
    return [key for key in MONITORING_SNAPSHOT_KEYS if key not in snapshot]


def _first_reason(*groups: Any) -> str | None:
    for group in groups:
        if isinstance(group, list) and group:
            return str(group[0])
        if isinstance(group, str) and group:
            return group
    return None

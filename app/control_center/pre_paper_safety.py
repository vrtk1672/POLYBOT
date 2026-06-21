from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.control_center.candidate_scoped_events import CandidateScopedEventsService
from app.control_center.paper_actionability import PaperActionabilityService
from app.control_center.pre_paper_active_truth import pre_paper_active_counts
from app.control_center.paper_readiness import PaperReadinessService
from app.control_center.paper_simulation import PaperSimulationControlService
from app.control_center.runtime_readiness import RuntimeReadinessService
from app.control_center.supervisor_life_path import SupervisorLifePathService
from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    truth_envelope,
)
from app.control_center.unified_blockers import unified_blocker, unified_blockers
from app.db.connection import DatabaseConnectionFactory
from app.services.paper_observation_policy import PaperObservationPolicyReviewService


class PrePaperSafetyService:
    """Read-only pre-paper certification safety checklist."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def get_safety(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        runtime = RuntimeReadinessService(connection_factory=self._factory).get_readiness()
        supervisor = SupervisorLifePathService(connection_factory=self._factory).get_life_path()
        paper = PaperReadinessService(connection_factory=self._factory).get_readiness()
        paper_sim = PaperSimulationControlService(connection_factory=self._factory).status()
        scoped = CandidateScopedEventsService(connection_factory=self._factory).list_events(limit=50)
        actionability = PaperActionabilityService(connection_factory=self._factory).list_actionability(limit=50)
        observation_policy = PaperObservationPolicyReviewService(connection_factory=self._factory).summary(limit=5)
        counts = self._counts()
        actionability_counts = (actionability.get("data") or actionability).get("counts", {})
        observation_policy_counts = observation_policy.get("counts") or {}
        candidate_actionability_exists = (
            actionability_counts.get("actionable_small_paper", 0)
            + actionability_counts.get("actionable_if_paper_enabled", 0)
            + actionability_counts.get("watch_for_confirmation", 0)
        ) > 0
        invariant_results = [
            self._check("live_disabled", counts.get("live_orders", 0) == 0 and counts.get("positions", 0) == 0, "No live orders or live positions exist."),
            self._check("shadow_disabled", True, "No shadow activation endpoint was called in this bundle."),
            self._check("paper_simulation_currently_off", not bool((paper_sim.get("data") or paper_sim).get("enabled")), "Paper Simulation must be OFF before Phase 10."),
            self._check("system_can_turn_on_off_cleanly", (paper.get("system_power_state") in {"ON", "OFF"}), "System power state is readable after controlled smoke."),
            self._check("supervisor_life_path_visible", bool((supervisor.get("data") or supervisor).get("supervisor_life_state")), "Supervisor life path endpoint returns truth."),
            self._check("runtime_readiness_visible", bool((runtime.get("data") or runtime).get("runtime_life_state")), "Runtime readiness endpoint returns truth."),
            self._check("candidate_scoped_event_exists", (scoped.get("data") or scoped).get("counts", {}).get("candidate_event_scoped", 0) > 0, "At least one candidate-scoped event exists."),
            self._check("paper_actionability_exists", candidate_actionability_exists, "At least one candidate maps to candidate-level paper actionability or watch state."),
            self._check("no_duplicate_same_market_active_intent_risk", counts.get("duplicate_active_intent_risk", 0) == 0, "No duplicate active paper intent market/side risk was found."),
            self._check("no_open_paper_position_conflict", counts.get("open_paper_positions", 0) == 0, "No open paper position conflict exists."),
            self._check("no_forbidden_live_artifacts", counts.get("live_orders", 0) == 0 and counts.get("positions", 0) == 0, "No live artifacts exist."),
        ]
        blockers = self._blockers(invariant_results, scoped, actionability, paper_sim)
        readiness = "PRE_PAPER_NOT_READY" if any(b["blocker_code"] == "PAPER_SIMULATION_OFF" for b in blockers) else "PRE_PAPER_READY" if not blockers else "PRE_PAPER_BLOCKED"
        payload = {
            "status": "PARTIAL" if blockers else "REAL",
            "readiness_state": readiness,
            "source": {
                "runtime_readiness": "runtime_readiness",
                "supervisor_life_path": "supervisor_life_path",
                "paper_readiness": "paper_readiness",
                "candidate_scoped_events": "candidate_scoped_events",
                "paper_actionability": "paper_actionability",
            },
            "last_updated": now.isoformat(),
            "freshness_state": "FRESH",
            "truth_state": "ACTIVE_FRESH",
            "invariant_results": invariant_results,
            "counts": counts,
            "opportunity_score_status": {
                "full_paper_certification_ready": int(actionability_counts.get("full_paper_certification_ready") or 0),
                "paper_observation_eligible": int(actionability_counts.get("paper_observation_eligible") or 0),
                "watch_only": int(actionability_counts.get("watch_only") or 0),
                "hard_blocked": int(actionability_counts.get("opportunity_hard_blocked") or 0),
                "paper_observation_execution_enabled": False,
            },
            "paper_observation_policy_status": {
                "reviewed_count": int(observation_policy_counts.get("total_paper_observation_classifications_reviewed") or 0),
                "observation_policy_ready_count": int(observation_policy_counts.get("observation_policy_eligible_count") or 0),
                "observation_policy_watch_count": int(observation_policy_counts.get("observation_policy_watch_count") or 0),
                "observation_policy_blocked_count": int(observation_policy_counts.get("observation_policy_blocked_count") or 0),
                "observation_execution_mode_implemented": False,
                "observation_paper_intent_creation_allowed": False,
                "execution_allowed": False,
                "paper_allowed": False,
            },
            "blockers": [item["blocker_code"] for item in blockers],
            "unified_blockers": blockers,
            "required_to_pass": [req for blocker in blockers for req in blocker["required_to_pass"]],
            "warnings": ["Pre-paper safety is not Paper Simulation ON; Phase 10 must explicitly enable paper only after accepted pre-checks."],
            "errors": [],
            "generated_at": now.isoformat(),
        }
        return _envelope(payload)

    def _check(self, name: str, passed: bool, detail: str) -> dict[str, Any]:
        return {"name": name, "status": "PASS" if passed else "FAIL", "detail": detail}

    def _blockers(self, invariants: list[dict[str, Any]], scoped: dict[str, Any], actionability: dict[str, Any], paper_sim: dict[str, Any]) -> list[dict[str, Any]]:
        blockers: list[dict[str, Any]] = []
        if not bool((paper_sim.get("data") or paper_sim).get("enabled")):
            blockers.append(unified_blocker("PAPER_SIMULATION_OFF", source="pre_paper_safety"))
        failed = {item["name"] for item in invariants if item["status"] != "PASS"}
        if "candidate_scoped_event_exists" in failed:
            blockers.append(unified_blocker("NO_CANDIDATE_SCOPED_EVENT", source="pre_paper_safety"))
        action_payload = actionability.get("data") or actionability
        action_counts = action_payload.get("counts", {})
        if "paper_actionability_exists" in failed:
            specific_actionability_blockers = [
                code
                for code in (action_payload.get("blockers") or [])
                if code not in {"NO_PAPER_ACTIONABILITY"}
            ]
            if action_counts.get("candidate_scoped_bundles", 0) > 0 and specific_actionability_blockers:
                blockers.extend(unified_blockers(specific_actionability_blockers, source="pre_paper_safety"))
            else:
                blockers.append(
                    unified_blocker(
                        "NO_PAPER_ACTIONABILITY",
                        source="pre_paper_safety",
                        required_to_pass="No usable candidate-scoped bundle mapped to a candidate paper actionability state; refresh candidate-scoped mesh evidence and inspect paper-actionability blockers.",
                    )
                )
        if "no_duplicate_same_market_active_intent_risk" in failed:
            blockers.append(unified_blocker("DUPLICATE_ACTIVE_INTENT_RISK", source="pre_paper_safety"))
        if "no_open_paper_position_conflict" in failed:
            blockers.append(unified_blocker("OPEN_PAPER_POSITION_CONFLICT", source="pre_paper_safety"))
        for source_payload, source_name in ((scoped, "candidate_scoped_events"), (actionability, "paper_actionability")):
            for code in (source_payload.get("data") or source_payload).get("blockers") or []:
                blockers.extend(unified_blockers([code], source=source_name))
        return _dedupe_blockers(blockers)

    def _counts(self) -> dict[str, int]:
        out = {
            "paper_intents": 0,
            "paper_orders": 0,
            "paper_fills": 0,
            "paper_positions": 0,
            "open_paper_positions": 0,
            "live_orders": 0,
            "positions": 0,
            "duplicate_active_intent_risk": 0,
        }
        if not self._factory.enabled:
            return out
        with self._factory.connect() as conn:
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "positions"):
                if _table_exists(conn, table):
                    out[table] = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
            out.update(pre_paper_active_counts(conn))
        return out


def _dedupe_blockers(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for blocker in blockers:
        seen.setdefault(blocker["blocker_code"], blocker)
    return list(seen.values())


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return bool(row)


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    status = ControlCenterStatus(payload.get("status") if payload.get("status") in {item.value for item in ControlCenterStatus} else "PARTIAL")
    readiness = "BLOCKED" if payload.get("readiness_state") in {"PRE_PAPER_NOT_READY", "PRE_PAPER_BLOCKED"} else "READY" if payload.get("readiness_state") == "PRE_PAPER_READY" else "PARTIAL"
    envelope = truth_envelope(
        status=status,
        source="pre-paper safety invariants",
        truth_state=ControlCenterTruthState.ACTIVE_FRESH,
        data=payload,
        last_updated=payload.get("last_updated"),
        stale_after_seconds=300,
        freshness_state=ControlCenterFreshnessState.FRESH,
        runtime_state=ControlCenterRuntimeState.RUNNING,
        readiness_state=ControlCenterReadinessState(readiness),
        warnings=payload.get("warnings") or [],
        errors=payload.get("errors") or [],
    ).to_dict()
    return {**envelope, **payload, "data": payload}

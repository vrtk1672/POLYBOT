from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.coordinator import CoordinatorDecision, CoordinatorDecisionInput
from app.neural_mesh.runtime_coordinator import RuntimeCoordinatorInput, RuntimeCoordinatorRun
from app.repositories.runtime_coordinator_repository import RuntimeCoordinatorRepository
from app.services.brain_coordinator import BrainCoordinatorService
from app.services.dry_run_provenance import DryRunProvenanceService
from app.services.mesh_blockers import MeshBlockersService
from app.services.producer_health import ProducerHealthService


class RuntimeCoordinatorDecisionService:
    """Deterministic non-executing Coordinator decision producer for runtime Brain Outputs."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: RuntimeCoordinatorRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or RuntimeCoordinatorRepository()

    def run_runtime_coordinator(
        self,
        *,
        limit: int = 100,
        min_brain_confidence: float = 0.0,
        write_decisions: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"runtime_coord_{uuid4().hex}"
        safety_before = self._safety_counts()
        runtime_before = self._count_runtime_coordinator_decisions()
        dry_run_coord = self._count_dry_run_coordinator_decisions()
        runtime_brain = self._count_runtime_brain_outputs()
        dry_brain = self._count_dry_run_brain_outputs()
        candidates = self._candidate_rows(limit=limit, min_brain_confidence=min_brain_confidence)

        created = 0
        updated = 0
        inputs: list[RuntimeCoordinatorInput] = []
        decision_ids: dict[str, str] = {}
        errors: list[str] = []

        for row in candidates:
            if bool(row.get("already_has_runtime_coordinator_decision")):
                updated += 0
                continue
            try:
                item = _classify_runtime_brain_output(row)
                inputs.append(item)
                if write_decisions:
                    decision = _coordinator_decision_for_input(row, item, run_id=run_id)
                    coordinator_input = CoordinatorDecisionInput(
                        brain_output_id=item.brain_output_id,
                        brain=str(row.get("brain") or "runtime_brain_adapter"),
                        input_role=str(row.get("output_type") or ""),
                        input_recommendation=str(row.get("recommendation") or ""),
                        input_confidence=item.brain_confidence,
                    )
                    created_decision = BrainCoordinatorService(connection_factory=self._factory).create_coordinator_decision(
                        decision,
                        inputs=[coordinator_input],
                    )
                    decision_ids[item.brain_output_id] = str(created_decision["coordinator_decision_id"])
                    created += 1
            except Exception as exc:
                errors.append(f"{row.get('brain_output_id') or 'unknown'}:{type(exc).__name__}:{exc}")

        provenance_updated = 0
        if write_decisions and created:
            provenance = DryRunProvenanceService(connection_factory=self._factory).analyze_recent(limit=max(limit, created + 120))
            provenance_updated = int(provenance.get("created_or_updated") or 0)
        ProducerHealthService(connection_factory=self._factory).get_producer_health_summary(limit=50)
        blockers_after = MeshBlockersService(connection_factory=self._factory).get_mesh_blockers(limit=50)
        safety_after = self._safety_counts()
        runtime_after = self._count_runtime_coordinator_decisions()

        run = RuntimeCoordinatorRun(
            run_id=run_id,
            status="DRY_RUN" if not write_decisions else "DEGRADED" if errors else "OK",
            input_runtime_brain_outputs=len(candidates),
            eligible_brain_outputs=len(inputs),
            coordinator_decisions_created=created,
            coordinator_decisions_updated=updated,
            dry_run_decisions_touched=0,
            runtime_coordinator_decisions_before=runtime_before,
            runtime_coordinator_decisions_after=runtime_after,
            dry_run_coordinator_decisions=dry_run_coord,
            runtime_brain_outputs=runtime_brain,
            dry_run_brain_outputs=dry_brain,
            provenance_updated=provenance_updated,
            producer_health_updated=True,
            mesh_blockers_updated=True,
            paper_ready_before=False,
            paper_ready_after=False,
            orders_created=max(0, safety_after["orders"] - safety_before["orders"]),
            order_intents_created=max(0, safety_after["order_intents"] - safety_before["order_intents"]),
            fills_created=max(0, safety_after["fills"] - safety_before["fills"]),
            positions_created=max(0, safety_after["positions"] - safety_before["positions"]),
            live_actions_created=max(0, safety_after["live_actions"] - safety_before["live_actions"]),
            remaining_blockers=list(blockers_after.get("blocked_by") or []),
            inputs=inputs,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error_summary="; ".join(errors) if errors else None,
        )
        if write_decisions and self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.record_run(conn, run)
                for item in inputs:
                    self._repository.record_input(
                        conn,
                        run_id=run.run_id,
                        coordinator_decision_id=decision_ids.get(item.brain_output_id),
                        item=item,
                    )
        return run.to_api_dict()

    def get_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        latest_run = None
        latest_inputs: list[dict[str, Any]] = []
        if self._factory.enabled:
            with self._factory.connect() as conn:
                row = self._repository.latest_run(conn)
                if row:
                    latest_run = _json_safe(dict(row))
                    latest_inputs = [_json_safe(item) for item in self._repository.latest_inputs(conn, str(row["run_id"]), limit=limit)]
        provenance = DryRunProvenanceService(connection_factory=self._factory).get_summary(limit=limit)
        blockers = MeshBlockersService(connection_factory=self._factory).get_mesh_blockers(limit=limit)
        decision_counts = _decision_counts(latest_inputs)
        return {
            "status": "OK" if latest_run else "EMPTY",
            "mock_data": False,
            "latest_run": latest_run,
            "latest_inputs": latest_inputs,
            "runtime_coordinator_decisions": int(provenance.get("coordinator_decisions_runtime") or 0),
            "dry_run_coordinator_decisions": int(provenance.get("coordinator_decisions_dry_run") or 0),
            "runtime_coordinator_decisions_created_last_run": int(latest_run.get("coordinator_decisions_created") or 0) if latest_run else 0,
            "eligible_runtime_brain_outputs": int(latest_run.get("eligible_brain_outputs") or 0) if latest_run else 0,
            "no_trade_decisions": decision_counts.get("NO_TRADE", 0),
            "blocked_decisions": decision_counts.get("BLOCKED", 0),
            "hold_for_more_evidence_decisions": decision_counts.get("HOLD_FOR_MORE_EVIDENCE", 0),
            "input_brain_output_count": int(latest_run.get("input_runtime_brain_outputs") or 0) if latest_run else 0,
            "blocked_from_paper_count": int(latest_run.get("eligible_brain_outputs") or 0) if latest_run else 0,
            "paper_ready": False,
            "orders_created": int(latest_run.get("orders_created") or 0) if latest_run else 0,
            "order_intents_created": int(latest_run.get("order_intents_created") or 0) if latest_run else 0,
            "fills_created": int(latest_run.get("fills_created") or 0) if latest_run else 0,
            "positions_created": int(latest_run.get("positions_created") or 0) if latest_run else 0,
            "live_actions_created": int(latest_run.get("live_actions_created") or 0) if latest_run else 0,
            "remaining_blockers": blockers.get("blocked_by", []),
            "analysis_status": "OK" if latest_run else "EMPTY",
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _candidate_rows(self, *, limit: int, min_brain_confidence: float) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return self._repository.list_runtime_brain_output_candidates(conn, limit=limit, min_brain_confidence=min_brain_confidence)

    def _count_runtime_coordinator_decisions(self) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            return self._repository.count_runtime_coordinator_decisions(conn)

    def _count_dry_run_coordinator_decisions(self) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            return self._repository.count_dry_run_coordinator_decisions(conn)

    def _count_runtime_brain_outputs(self) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            return self._repository.count_runtime_brain_outputs(conn)

    def _count_dry_run_brain_outputs(self) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            return self._repository.count_dry_run_brain_outputs(conn)

    def _safety_counts(self) -> dict[str, int]:
        return {
            "orders": self._count_table("paper_orders") + self._count_table("shadow_orders") + self._count_table("live_orders"),
            "order_intents": self._count_table("order_intents"),
            "fills": self._count_table("paper_fills") + self._count_table("fills_v2"),
            "positions": self._count_table("positions"),
            "live_actions": self._count_table("live_orders"),
        }

    def _count_table(self, table: str) -> int:
        if not self._factory.enabled:
            return 0
        try:
            with self._factory.connect() as conn:
                if not _table_exists(conn, table):
                    return 0
                row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
                return int(row["count"] or 0)
        except Exception:
            return 0


def _classify_runtime_brain_output(row: dict[str, Any]) -> RuntimeCoordinatorInput:
    metadata = row.get("metadata_json") or {}
    flags = [str(flag).upper() for flag in row.get("risk_flags_json") or []]
    confidence = float(row.get("confidence") or 0.0)
    recommendation = str(row.get("recommendation") or "").upper()
    output_type = str(row.get("output_type") or "").upper()
    source_signal_ids = [str(item) for item in row.get("source_signal_ids") or [] if item]
    blockers = set(flags)
    missing = [str(item).upper() for item in metadata.get("missing_requirements") or []]
    blockers.update(missing)

    if "MISSING_MARKET_LINK" in blockers or not row.get("market_id"):
        blockers.add("MISSING_MARKET_LINK")
    blockers.update({"NO_RISK_CORE", "NO_EXIT_FOUNDATION", "ORDERBOOK_SNAPSHOTS_MISSING"})

    if "WEAK_SIGNAL" in recommendation or output_type == "CAUTION":
        decision_type = "NO_TRADE"
        blockers.add("WEAK_SIGNAL")
    elif "NO_TRADE" in recommendation or output_type == "NO_TRADE_HINT":
        decision_type = "NO_TRADE"
    elif "MISSING_MARKET_LINK" in blockers:
        decision_type = "BLOCKED"
    elif confidence >= 0.70:
        decision_type = "HOLD_FOR_MORE_EVIDENCE"
    else:
        decision_type = "NO_TRADE"

    return RuntimeCoordinatorInput(
        brain_output_id=str(row["brain_output_id"]),
        source_signal_ids=source_signal_ids,
        brain_confidence=confidence,
        brain_decision_type=recommendation or output_type or None,
        coordinator_decision_type=decision_type,
        blockers=sorted(blockers),
        paper_allowed=False,
        execution_allowed=False,
        order_intent_allowed=False,
        evidence={
            "brain": row.get("brain"),
            "output_type": row.get("output_type"),
            "recommendation": row.get("recommendation"),
            "confidence": row.get("confidence"),
            "runtime_brain_run_id": metadata.get("runtime_brain_run_id"),
        },
    )


def _coordinator_decision_for_input(row: dict[str, Any], item: RuntimeCoordinatorInput, *, run_id: str) -> CoordinatorDecision:
    if item.coordinator_decision_type == "HOLD_FOR_MORE_EVIDENCE":
        final_state = "REVIEW_REQUIRED"
        approved_actions = ["REQUEST_MORE_DATA", "WATCH"]
        primary_reason = "Runtime Coordinator holds for orderbook, risk, and exit evidence before any Paper consideration."
    elif item.coordinator_decision_type == "BLOCKED":
        final_state = "PAPER_CANDIDATE_BLOCKED"
        approved_actions = ["REQUEST_MORE_DATA", "WATCH"]
        primary_reason = "Runtime Coordinator blocks this Brain Output from Paper because required evidence is missing."
    else:
        final_state = "NO_TRADE"
        approved_actions = ["MARK_NO_TRADE", "WATCH"]
        primary_reason = "Runtime Coordinator preserves a non-executing no-trade decision from runtime Brain evidence."

    metadata = row.get("metadata_json") or {}
    source_signal_ids = item.source_signal_ids or [str(item) for item in metadata.get("source_signal_ids") or [] if item]
    return CoordinatorDecision(
        market_id=row.get("market_id"),
        position_id=row.get("position_id"),
        final_state=final_state,
        primary_reason=primary_reason,
        confidence=item.brain_confidence,
        urgency=0.0,
        conflicts_detected=False,
        governor_required=True,
        execution_allowed=False,
        approved_actions=approved_actions,
        blocked_actions=["EXECUTION", "LIVE_ENTRY", "ORDER_CREATION", "PAPER_ENTRY", "POSITION_OPEN"],
        required_reviews=["SEND_TO_HUMAN_REVIEW"],
        risk_flags=item.blockers,
        source_brain_count=1,
        input_output_count=1,
        conflict_count=0,
        correlation_id=row.get("correlation_id") or f"{run_id}:{row.get('brain_output_id')}",
        status="ACTIVE",
        metadata={
            "generated_by": "runtime",
            "producer_name": "runtime_coordinator_adapter",
            "generated_from": "runtime_brain_output",
            "is_runtime_generated": True,
            "is_dry_run_generated": False,
            "runtime_coordinator_run_id": run_id,
            "source_brain_output_ids": [item.brain_output_id],
            "source_signal_ids": source_signal_ids,
            "coordinator_decision_type": item.coordinator_decision_type,
            "brain_decision_type": item.brain_decision_type,
            "raw_payload_ref": f"runtime_coordinator:{run_id}:{item.brain_output_id}",
            "paper_allowed": False,
            "execution_allowed": False,
            "order_intent_allowed": False,
            "paper_ready": False,
            "missing_requirements": sorted(set(item.blockers)),
        },
    )


def _decision_counts(inputs: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in inputs:
        decision = str(item.get("coordinator_decision_type") or "").upper()
        if not decision:
            continue
        counts[decision] = counts.get(decision, 0) + 1
    return counts


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])

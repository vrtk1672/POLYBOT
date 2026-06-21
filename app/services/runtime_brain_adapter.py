from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.brain_outputs import BrainOutput, BrainOutputDependency
from app.neural_mesh.runtime_brain_adapter import RuntimeBrainInput, RuntimeBrainProducerRun
from app.repositories.runtime_brain_adapter_repository import RuntimeBrainAdapterRepository
from app.services.brain_outputs import BrainOutputService
from app.services.dry_run_provenance import DryRunProvenanceService
from app.services.mesh_blockers import MeshBlockersService
from app.services.producer_health import ProducerHealthService


class RuntimeBrainAdapterService:
    """Deterministic non-executing Brain Output producer for runtime Signals."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: RuntimeBrainAdapterRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or RuntimeBrainAdapterRepository()

    def run_runtime_brain(
        self,
        *,
        limit: int = 100,
        min_quality_score: float = 0.0,
        write_outputs: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"runtime_brain_{uuid4().hex}"
        blockers_before = MeshBlockersService(connection_factory=self._factory).get_mesh_blockers(limit=50)
        safety_before = self._safety_counts()
        runtime_before = self._count_runtime_brain_outputs()
        dry_run_outputs = self._count_dry_run_brain_outputs()
        coordinator_runtime = self._count_runtime_coordinator_decisions()
        candidates = self._candidate_rows(limit=limit, min_quality_score=min_quality_score)

        created = 0
        updated = 0
        inputs: list[RuntimeBrainInput] = []
        brain_output_ids: dict[str, str] = {}
        errors: list[str] = []

        for row in candidates:
            if bool(row.get("already_has_runtime_brain_output")):
                updated += 0
                continue
            try:
                item = _classify_runtime_signal(row)
                inputs.append(item)
                if write_outputs:
                    output = _brain_output_for_input(row, item, run_id=run_id)
                    dependency = BrainOutputDependency(
                        dependency_type="signal",
                        dependency_id=item.signal_id,
                        dependency_role="runtime_signal",
                        confidence=item.signal_quality_score,
                    )
                    created_output = BrainOutputService(connection_factory=self._factory).create_brain_output_with_dependencies(
                        output,
                        dependencies=[dependency],
                    )
                    brain_output_ids[item.signal_id] = str(created_output["brain_output_id"])
                    created += 1
            except Exception as exc:
                errors.append(f"{row.get('signal_id') or 'unknown'}:{type(exc).__name__}:{exc}")

        provenance_updated = 0
        if write_outputs and created:
            provenance = DryRunProvenanceService(connection_factory=self._factory).analyze_recent(limit=max(limit, created + 120))
            provenance_updated = int(provenance.get("created_or_updated") or 0)
        ProducerHealthService(connection_factory=self._factory).get_producer_health_summary(limit=50)
        blockers_after = MeshBlockersService(connection_factory=self._factory).get_mesh_blockers(limit=50)
        safety_after = self._safety_counts()
        runtime_after = self._count_runtime_brain_outputs()

        run = RuntimeBrainProducerRun(
            run_id=run_id,
            status="DRY_RUN" if not write_outputs else "DEGRADED" if errors else "OK",
            input_runtime_signals=len(candidates),
            eligible_signals=len(inputs),
            brain_outputs_created=created,
            brain_outputs_updated=updated,
            dry_run_outputs_touched=0,
            runtime_brain_outputs_before=runtime_before,
            runtime_brain_outputs_after=runtime_after,
            dry_run_brain_outputs=dry_run_outputs,
            # This run must not create coordinator decisions. Existing runtime
            # coordinator totals are observed separately for dashboard context,
            # but the contract field represents mutations caused by this run.
            coordinator_runtime_decisions=0,
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
        if write_outputs and self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.record_run(conn, run)
                for item in inputs:
                    self._repository.record_input(
                        conn,
                        run_id=run.run_id,
                        brain_output_id=brain_output_ids.get(item.signal_id),
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
        runtime_brain = int(provenance.get("brain_outputs_runtime") or 0)
        dry_brain = int(provenance.get("brain_outputs_dry_run") or 0)
        decision_counts = _decision_counts(latest_inputs)
        return {
            "status": "OK" if latest_run else "EMPTY",
            "mock_data": False,
            "latest_run": latest_run,
            "latest_inputs": latest_inputs,
            "runtime_brain_outputs": runtime_brain,
            "dry_run_brain_outputs": dry_brain,
            "runtime_brain_outputs_created_last_run": int(latest_run.get("brain_outputs_created") or 0) if latest_run else 0,
            "eligible_runtime_signals": int(latest_run.get("eligible_signals") or 0) if latest_run else 0,
            "weak_runtime_signals": decision_counts.get("WEAK_SIGNAL", 0),
            "no_trade_candidates": decision_counts.get("NO_TRADE_CANDIDATE", 0),
            "input_signal_count": int(latest_run.get("input_runtime_signals") or 0) if latest_run else 0,
            "blocked_from_paper_count": int(latest_run.get("eligible_signals") or 0) if latest_run else 0,
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

    def _candidate_rows(self, *, limit: int, min_quality_score: float) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return self._repository.list_runtime_signal_candidates(conn, limit=limit, min_quality_score=min_quality_score)

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

    def _count_runtime_coordinator_decisions(self) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            return self._repository.count_runtime_coordinator_decisions(conn)

    def _safety_counts(self) -> dict[str, int]:
        return {
            "orders": self._count_table("paper_orders") + self._count_table("shadow_orders") + self._count_table("live_orders"),
            "order_intents": self._count_table("order_intents"),
            "fills": self._count_table("paper_fills"),
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


def _classify_runtime_signal(row: dict[str, Any]) -> RuntimeBrainInput:
    blockers: list[str] = []
    quality = float(row.get("quality_score") or 0.0)
    if bool(row.get("quality_is_stale")) or str(row.get("quality_status") or "").upper() == "STALE":
        blockers.append("STALE_SIGNAL")
    if not bool(row.get("is_linked_to_market")):
        blockers.append("MISSING_MARKET_LINK")
    if str(row.get("lineage_status") or "").upper() not in {"RUNTIME_VERIFIED", "COMPLETE"}:
        blockers.append("LINEAGE_NOT_TRUSTED")
    if str(row.get("quality_status") or "").upper() in {"ERROR", "BLOCKED"}:
        blockers.append("QUALITY_BLOCKED")
    if not bool(row.get("processing_can_feed_brain")) and not bool(row.get("can_feed_brain")):
        blockers.append("BRAIN_GATE_BLOCKED")

    if not blockers and quality >= 0.70:
        decision = "OBSERVE"
    elif "STALE_SIGNAL" in blockers or quality < 0.50:
        decision = "WEAK_SIGNAL"
    else:
        decision = "NO_TRADE_CANDIDATE"
    return RuntimeBrainInput(
        signal_id=str(row["signal_id"]),
        signal_quality_score=quality,
        signal_processing_state=row.get("processing_state"),
        lineage_status=row.get("lineage_status"),
        link_status=row.get("linkability_status"),
        decision_type=decision,
        blockers=sorted(set(blockers)),
        paper_allowed=False,
        execution_allowed=False,
        evidence={
            "quality_status": row.get("quality_status"),
            "gate_status": row.get("gate_status"),
            "lineage_trust_score": row.get("lineage_trust_score"),
            "provenance_status": row.get("provenance_status"),
            "primary_unlinked_reason": row.get("primary_unlinked_reason"),
        },
    )


def _brain_output_for_input(row: dict[str, Any], item: RuntimeBrainInput, *, run_id: str) -> BrainOutput:
    output_type = "WATCH" if item.decision_type == "OBSERVE" else "CAUTION" if item.decision_type == "WEAK_SIGNAL" else "NO_TRADE_HINT"
    recommendation = item.decision_type
    reason = _reasoning(item)
    return BrainOutput(
        brain="runtime_brain_adapter",
        output_type=output_type,
        market_id=row.get("market_id"),
        recommendation=recommendation,
        confidence=item.signal_quality_score,
        urgency=0.0,
        risk_flags=item.blockers,
        reasoning_summary=reason,
        status="ACTIVE",
        correlation_id=row.get("correlation_id"),
        generated_by="runtime",
        model_name="deterministic_runtime_brain_adapter",
        model_version="v2_part4c_j",
        prompt_version=None,
        raw_payload_ref=f"runtime_brain:{run_id}:{item.signal_id}",
        metadata={
            "producer_name": "runtime_brain_adapter",
            "generated_from": "runtime_signal",
            "generated_by": "runtime",
            "is_runtime_generated": True,
            "is_dry_run_generated": False,
            "runtime_brain_run_id": run_id,
            "source_signal_ids": [item.signal_id],
            "decision_type": item.decision_type,
            "missing_requirements": item.blockers,
            "paper_allowed": False,
            "execution_allowed": False,
            "paper_ready": False,
            "source_signal": {
                "signal_id": item.signal_id,
                "source_name": row.get("source_name"),
                "producer_name": row.get("producer_name"),
                "quality_score": item.signal_quality_score,
                "lineage_status": item.lineage_status,
                "link_status": item.link_status,
            },
        },
    )


def _reasoning(item: RuntimeBrainInput) -> str:
    if item.decision_type == "OBSERVE":
        return "Runtime Signal is observable by the brain adapter; no execution permission is granted."
    if item.decision_type == "WEAK_SIGNAL":
        return f"Runtime Signal is weak or stale; blocked by: {', '.join(item.blockers) or 'quality gate'}."
    return f"Runtime Signal remains a no-trade candidate; missing: {', '.join(item.blockers) or 'paper evidence'}."


def _decision_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        decision = str(row.get("decision_type") or "")
        counts[decision] = counts.get(decision, 0) + 1
    return counts


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value

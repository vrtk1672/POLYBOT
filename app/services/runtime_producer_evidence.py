from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.events.correlation import new_correlation_id
from app.neural_mesh.runtime_producer_evidence import RuntimeProducerEvidenceItem, RuntimeProducerEvidenceRun
from app.repositories.runtime_producer_evidence_repository import RuntimeProducerEvidenceRepository
from app.services.dry_run_provenance import DryRunProvenanceService
from app.services.link_coverage import LinkCoverageService
from app.services.lineage_coverage import LineageCoverageService
from app.services.mesh_blockers import MeshBlockersService
from app.services.neuron_signals import NeuronSignalService, source_status_to_signal
from app.services.producer_health import ProducerHealthService
from app.services.signal_processing import SignalProcessingService
from app.services.signal_quality import SignalQualityService


class RuntimeProducerEvidenceService:
    """Create non-executing runtime Signal evidence from existing local DB observations."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: RuntimeProducerEvidenceRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or RuntimeProducerEvidenceRepository()

    def run_runtime_evidence_loop(
        self,
        *,
        limit: int = 100,
        producer_names: list[str] | None = None,
        dry_run: bool = False,
        apply_evaluations: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"runtime_evidence_{uuid4().hex}"
        before_health = ProducerHealthService(connection_factory=self._factory).get_producer_health_summary(limit=50)
        before_blockers = MeshBlockersService(connection_factory=self._factory).get_mesh_blockers(limit=50)
        safety_before = self._safety_counts()

        candidates = self._source_status_candidates(limit=limit, producer_names=producer_names)
        items: list[RuntimeProducerEvidenceItem] = []
        signal_ids: list[str] = []
        errors: list[str] = []

        for source in candidates:
            try:
                signal_payload, lineage, item = self._candidate_to_signal(source, run_id=run_id)
                if dry_run:
                    item.status = "PLANNED"
                    items.append(item)
                    continue
                created = NeuronSignalService(connection_factory=self._factory).create_signal_with_lineage(signal_payload, lineage)
                item.signal_id = str(created["signal_id"])
                items.append(item)
                signal_ids.append(item.signal_id)
            except Exception as exc:
                errors.append(f"{source.get('source_name') or 'unknown'}:{type(exc).__name__}:{exc}")

        quality_updated = processing_updated = lineage_updated = link_updated = 0
        provenance_updated = 0
        if apply_evaluations and not dry_run:
            quality_updated, processing_updated, lineage_updated, link_updated = self._evaluate_signals(signal_ids)
            provenance = DryRunProvenanceService(connection_factory=self._factory).analyze_recent(limit=max(limit, len(signal_ids) + 20))
            provenance_updated = int(provenance.get("created_or_updated") or 0)

        after_health = ProducerHealthService(connection_factory=self._factory).get_producer_health_summary(limit=50)
        after_blockers = MeshBlockersService(connection_factory=self._factory).get_mesh_blockers(limit=50)
        safety_after = self._safety_counts()

        run = RuntimeProducerEvidenceRun(
            run_id=run_id,
            status="DRY_RUN" if dry_run else "DEGRADED" if errors else "OK",
            producers_checked=len(candidates),
            runtime_producers_active_before=int(before_health.get("runtime_active_producers") or 0),
            runtime_producers_active_after=int(after_health.get("runtime_active_producers") or 0),
            dry_run_only_producers_before=int(before_health.get("dry_run_only_producers") or 0),
            dry_run_only_producers_after=int(after_health.get("dry_run_only_producers") or 0),
            signals_created=0 if dry_run else len(signal_ids),
            signals_updated=0,
            quality_updated=quality_updated,
            processing_updated=processing_updated,
            lineage_updated=lineage_updated,
            link_coverage_updated=link_updated,
            provenance_updated=provenance_updated,
            producer_health_updated=True,
            mesh_blockers_updated=True,
            paper_ready_before=False,
            paper_ready_after=False,
            orders_created=max(0, safety_after["orders"] - safety_before["orders"]),
            order_intents_created=max(0, safety_after["order_intents"] - safety_before["order_intents"]),
            live_actions_created=max(0, safety_after["live_actions"] - safety_before["live_actions"]),
            blocked_by=list(before_blockers.get("blocked_by") or []),
            remaining_blockers=list(after_blockers.get("blocked_by") or []),
            items=items,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error_summary="; ".join(errors) if errors else None,
        )

        if not dry_run and self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.record_run(conn, run)
                for item in items:
                    self._repository.record_item(conn, run_id=run.run_id, item=item)
        return run.to_api_dict()

    def get_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        latest_run = None
        latest_items: list[dict[str, Any]] = []
        if self._factory.enabled:
            with self._factory.connect() as conn:
                row = self._repository.latest_run(conn)
                if row:
                    latest_run = _json_safe(dict(row))
                    latest_items = [_json_safe(item) for item in self._repository.list_run_items(conn, str(row["run_id"]), limit=limit)]
        health = ProducerHealthService(connection_factory=self._factory).get_producer_health_summary(limit=limit)
        blockers = MeshBlockersService(connection_factory=self._factory).get_mesh_blockers(limit=limit)
        return {
            "status": "OK" if latest_run else "EMPTY",
            "mock_data": False,
            "latest_run": latest_run,
            "latest_items": latest_items,
            "runtime_producers_active_after": health.get("runtime_active_producers", 0),
            "dry_run_only_producers_after": health.get("dry_run_only_producers", 0),
            "signals_created": int(latest_run.get("signals_created") or 0) if latest_run else 0,
            "signals_updated": int(latest_run.get("signals_updated") or 0) if latest_run else 0,
            "quality_updated": int(latest_run.get("quality_updated") or 0) if latest_run else 0,
            "processing_updated": int(latest_run.get("processing_updated") or 0) if latest_run else 0,
            "lineage_updated": int(latest_run.get("lineage_updated") or 0) if latest_run else 0,
            "link_coverage_updated": int(latest_run.get("link_coverage_updated") or 0) if latest_run else 0,
            "provenance_updated": int(latest_run.get("provenance_updated") or 0) if latest_run else 0,
            "producer_health_updated": bool(latest_run.get("producer_health_updated")) if latest_run else False,
            "mesh_blockers_updated": bool(latest_run.get("mesh_blockers_updated")) if latest_run else False,
            "paper_ready": False,
            "orders_created": int(latest_run.get("orders_created") or 0) if latest_run else 0,
            "order_intents_created": int(latest_run.get("order_intents_created") or 0) if latest_run else 0,
            "live_actions_created": int(latest_run.get("live_actions_created") or 0) if latest_run else 0,
            "remaining_blockers": blockers.get("blocked_by", []),
            "analysis_status": "OK" if latest_run else "EMPTY",
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _source_status_candidates(self, *, limit: int, producer_names: list[str] | None) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return self._repository.list_source_status_candidates(conn, limit=limit, producer_names=producer_names)

    def _candidate_to_signal(self, source: dict[str, Any], *, run_id: str) -> tuple[dict[str, Any], dict[str, Any], RuntimeProducerEvidenceItem]:
        signal = source_status_to_signal(source)
        source_name = str(source.get("source_name") or signal.source_name or "unknown")
        source_id = source.get("id")
        correlation_id = signal.correlation_id or new_correlation_id()
        raw_payload_ref = f"source_status:{source_id}:{source_name}" if source_id is not None else signal.raw_payload_ref or f"source_status:{source_name}"
        producer = "clob_source_status_adapter" if source_name.startswith("polymarket_clob") else "source_status_adapter"
        signal.correlation_id = correlation_id
        signal.raw_payload_ref = raw_payload_ref
        signal.evidence.update(
            {
                "generated_by": "runtime",
                "is_runtime_generated": True,
                "is_dry_run_generated": False,
                "runtime_evidence_run_id": run_id,
                "runtime_evidence_source": "source_status",
                "source_status_id": source_id,
                "producer_name": producer,
            }
        )
        signal.evidence_count = max(signal.evidence_count, len(signal.evidence))
        lineage = {
            "producer_name": producer,
            "producer_component": "app.services.runtime_producer_evidence",
            "producer_version": "v2_part4c_i",
            "source_name": source_name,
            "source_status_id": source_id,
            "source_event_id": f"runtime_evidence:{run_id}:{source_name}",
            "market_id": signal.market_id,
            "correlation_id": correlation_id,
            "raw_payload_ref": raw_payload_ref,
            "generated_from": "source_status",
            "lineage": {
                "generated_by": "runtime",
                "is_runtime_generated": True,
                "is_dry_run_generated": False,
                "runtime_evidence_run_id": run_id,
                "raw_payload_policy": "local_reference_only",
                "source_type": source.get("source_type"),
                "runtime_status": source.get("runtime_status"),
                "freshness_status": source.get("freshness_status"),
            },
        }
        item = RuntimeProducerEvidenceItem(
            producer_name=producer,
            source=source_name,
            correlation_id=correlation_id,
            raw_payload_ref=raw_payload_ref,
            generated_from="source_status",
            evidence={
                "source_status_id": source_id,
                "source_type": source.get("source_type"),
                "runtime_status": source.get("runtime_status"),
                "freshness_status": source.get("freshness_status"),
            },
        )
        return signal.to_api_dict(), lineage, item

    def _evaluate_signals(self, signal_ids: list[str]) -> tuple[int, int, int, int]:
        quality = processing = lineage = link = 0
        quality_service = SignalQualityService(connection_factory=self._factory)
        processing_service = SignalProcessingService(connection_factory=self._factory)
        lineage_service = LineageCoverageService(connection_factory=self._factory)
        link_service = LinkCoverageService(connection_factory=self._factory)
        for signal_id in signal_ids:
            if quality_service.evaluate_signal_quality(signal_id):
                quality += 1
            if processing_service.evaluate_signal_processing(signal_id):
                processing += 1
            if lineage_service.analyze_signal(signal_id):
                lineage += 1
            if link_service.analyze_signal(signal_id, create_suggestions=True, apply_safe_links=False):
                link += 1
        return quality, processing, lineage, link

    def _safety_counts(self) -> dict[str, int]:
        return {
            "orders": self._count_table("paper_orders") + self._count_table("shadow_orders") + self._count_table("live_orders"),
            "order_intents": self._count_table("order_intents"),
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

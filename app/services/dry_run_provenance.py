from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.dry_run_provenance import DryRunProvenanceAnalysis, dry_run_provenance_from_row
from app.repositories.dry_run_provenance_repository import DryRunProvenanceRepository


class DryRunProvenanceService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: DryRunProvenanceRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or DryRunProvenanceRepository()

    def analyze_recent(self, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "OK", "mock_data": False, "analyzed": 0, "created_or_updated": 0, "summary": _empty_summary()}
        with self._factory.connect() as conn, conn.transaction():
            rows = self._repository.list_recent_objects(conn, limit=limit)
            updated = 0
            for row in rows:
                analysis = classify_provenance(row)
                self._repository.upsert_analysis(conn, analysis)
                updated += 1
            summary = self._repository.summary(conn, limit=20)
            status = "OK" if updated == len(rows) else "PARTIAL"
            self._repository.record_run(conn, requested_limit=limit, summary={**summary, "analyzed_count": updated}, status=status)
        return {"status": status, "mock_data": False, "analyzed": len(rows), "created_or_updated": updated, "summary": _summary_response(summary)}

    def get_provenance(self, object_type: str, object_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_analysis(conn, object_type=object_type, object_id=object_id)
        return _analysis_response(row) if row else None

    def list_provenance(
        self,
        *,
        limit: int = 50,
        object_type: str | None = None,
        generated_by: str | None = None,
        provenance_status: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_analyses(
                conn,
                limit=limit,
                object_type=object_type,
                generated_by=generated_by,
                provenance_status=provenance_status,
            )
        return [_analysis_response(row) for row in rows]

    def get_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        return _summary_response(summary)


def classify_provenance(row: dict[str, Any]) -> DryRunProvenanceAnalysis:
    object_type = str(row.get("object_type") or "").upper()
    object_id = str(row.get("object_id") or "")
    metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
    raw_generated_by = _normalize_token(row.get("generated_by") or metadata.get("generated_by"))
    dry_run_id = _blank_none(row.get("dry_run_id") or metadata.get("dry_run_id"))
    producer = _blank_none(row.get("producer_name"))
    source_table = _source_table(object_type)
    source_created_at = row.get("source_created_at")

    tokens = {
        raw_generated_by,
        _normalize_token(row.get("source_name")),
        _normalize_token(metadata.get("dry_run_phase")),
        _normalize_token(metadata.get("source")),
        _normalize_token(metadata.get("producer")),
        _normalize_token(metadata.get("generated_by")),
    }
    input_generated_by = [_normalize_token(item) for item in row.get("input_generated_by") or []]
    input_producers = [str(item) for item in row.get("input_producers") or [] if item]

    explicit_runtime = raw_generated_by == "runtime"
    explicit_adapter = raw_generated_by == "adapter"
    explicit_manual = raw_generated_by == "manual"
    explicit_dry_run = raw_generated_by in {"dry_run", "mesh_dry_run"} or bool(dry_run_id)
    inferred_dry_run = "mesh_dry_run" in tokens or "dry_run" in tokens or "v2_part4b" in tokens
    input_dry_run = bool(input_generated_by) and all(item in {"mesh_dry_run", "dry_run"} for item in input_generated_by)
    input_runtime = bool(input_generated_by) and all(item == "runtime" for item in input_generated_by)
    quality_dry_run = bool(row.get("quality_is_dry_run_generated"))
    quality_runtime = bool(row.get("quality_is_runtime_generated"))

    mixed = (explicit_runtime or input_runtime or quality_runtime) and (explicit_dry_run or inferred_dry_run or input_dry_run or quality_dry_run)
    if mixed:
        generated_by = "unknown"
        status = "MIXED"
        confidence = 0.40
        reason = "Conflicting runtime and dry-run provenance markers were present."
    elif explicit_dry_run or input_dry_run or quality_dry_run:
        generated_by = "dry_run"
        status = "DRY_RUN_ONLY"
        confidence = 0.95 if (explicit_dry_run or dry_run_id or quality_dry_run) else 0.80
        reason = "Object carries explicit dry-run provenance." if confidence >= 0.95 else "Object inferred as dry-run from linked dry-run inputs."
    elif inferred_dry_run:
        generated_by = "dry_run"
        status = "DRY_RUN_ONLY"
        confidence = 0.80
        reason = "Object inferred as dry-run from local metadata."
    elif explicit_runtime or input_runtime or quality_runtime:
        generated_by = "runtime"
        status = "RUNTIME_VERIFIED"
        confidence = 0.95 if explicit_runtime else 0.80
        reason = "Object carries runtime provenance."
    elif explicit_adapter:
        generated_by = "adapter"
        status = "ADAPTER_GENERATED"
        confidence = 0.95
        reason = "Object carries adapter provenance."
    elif explicit_manual:
        generated_by = "manual"
        status = "MANUAL_GENERATED"
        confidence = 0.95
        reason = "Object carries manual provenance."
    elif object_type == "SIGNAL" and producer:
        generated_by = "adapter"
        status = "ADAPTER_GENERATED"
        confidence = 0.80
        reason = "Signal has producer/source metadata but no explicit runtime marker."
    else:
        generated_by = "unknown"
        status = "UNKNOWN"
        confidence = 0.20
        reason = "No explicit or inferable provenance metadata was found."

    if producer and confidence < 0.98 and status not in {"UNKNOWN", "MIXED"}:
        confidence = min(1.0, confidence + 0.03)
    confidence = round(max(0.0, min(1.0, confidence)), 4)
    dry_run = status == "DRY_RUN_ONLY"
    runtime = status == "RUNTIME_VERIFIED"
    adapter = status == "ADAPTER_GENERATED"
    manual = status == "MANUAL_GENERATED"
    can_feed_brain = status in {"RUNTIME_VERIFIED", "ADAPTER_GENERATED", "MANUAL_GENERATED"} and confidence >= 0.80
    can_feed_paper = status == "RUNTIME_VERIFIED" and confidence >= 0.95 and object_type == "SIGNAL"

    if object_type == "COORDINATOR_DECISION" and not producer and input_producers:
        producer = "coordinator:" + ",".join(sorted(set(input_producers)))

    return DryRunProvenanceAnalysis(
        object_type=object_type,
        object_id=object_id,
        generated_by=generated_by,
        dry_run_id=dry_run_id,
        producer_name=producer,
        is_dry_run_generated=dry_run,
        is_runtime_generated=runtime,
        is_adapter_generated=adapter,
        is_manual_generated=manual,
        provenance_status=status,
        provenance_confidence=confidence,
        provenance_reason=reason,
        can_feed_brain_by_provenance=can_feed_brain,
        can_feed_paper_by_provenance=can_feed_paper and not dry_run,
        source_table=source_table,
        source_created_at=source_created_at,
        analyzed_at=datetime.now(UTC),
    )


def _summary_response(summary: dict[str, Any]) -> dict[str, Any]:
    total = int(summary.get("total_analyzed") or 0)
    status = "EMPTY"
    if total:
        status = "DEGRADED" if int(summary.get("unknown_provenance_count") or 0) or int(summary.get("brain_outputs_dry_run") or 0) or int(summary.get("coordinator_decisions_dry_run") or 0) else "OK"
    return {
        "status": status,
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "total_analyzed": total,
        "brain_outputs_total": int(summary.get("brain_outputs_total") or 0),
        "brain_outputs_runtime": int(summary.get("brain_outputs_runtime") or 0),
        "brain_outputs_dry_run": int(summary.get("brain_outputs_dry_run") or 0),
        "coordinator_decisions_total": int(summary.get("coordinator_decisions_total") or 0),
        "coordinator_decisions_runtime": int(summary.get("coordinator_decisions_runtime") or 0),
        "coordinator_decisions_dry_run": int(summary.get("coordinator_decisions_dry_run") or 0),
        "signals_total": int(summary.get("signals_total") or 0),
        "signals_runtime": int(summary.get("signals_runtime") or 0),
        "signals_dry_run": int(summary.get("signals_dry_run") or 0),
        "generated_by_counts": [_json_safe(row) for row in summary.get("generated_by_counts", [])],
        "provenance_status_counts": [_json_safe(row) for row in summary.get("provenance_status_counts", [])],
        "dry_run_by_id": [_json_safe(row) for row in summary.get("dry_run_by_id", [])],
        "producer_name_coverage": [_json_safe(row) for row in summary.get("producer_name_coverage", [])],
        "unknown_provenance_count": int(summary.get("unknown_provenance_count") or 0),
        "can_feed_paper_by_provenance_count": int(summary.get("can_feed_paper_by_provenance_count") or 0),
        "blocked_from_paper_count": int(summary.get("blocked_from_paper_count") or 0),
        "last_analysis_at": _json_safe(summary.get("last_analysis_at")),
        "analysis_status": "ERROR" if int(summary.get("error_count") or 0) else status,
        "latest_analyses": [_json_safe(dry_run_provenance_from_row(row).to_api_dict()) for row in summary.get("latest_analyses", [])],
        "paper_ready": False,
    }


def _analysis_response(row: dict[str, Any]) -> dict[str, Any]:
    return _json_safe(dry_run_provenance_from_row(dict(row)).to_api_dict())


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "OK",
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "total_analyzed": 0,
        "brain_outputs_total": 0,
        "brain_outputs_runtime": 0,
        "brain_outputs_dry_run": 0,
        "coordinator_decisions_total": 0,
        "coordinator_decisions_runtime": 0,
        "coordinator_decisions_dry_run": 0,
        "signals_total": 0,
        "signals_runtime": 0,
        "signals_dry_run": 0,
        "generated_by_counts": [],
        "provenance_status_counts": [],
        "dry_run_by_id": [],
        "producer_name_coverage": [],
        "unknown_provenance_count": 0,
        "can_feed_paper_by_provenance_count": 0,
        "blocked_from_paper_count": 0,
        "last_analysis_at": None,
        "analysis_status": "OK",
        "latest_analyses": [],
        "paper_ready": False,
    }


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().lower()


def _blank_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _source_table(object_type: str) -> str:
    return {
        "SIGNAL": "neuron_signals",
        "BRAIN_OUTPUT": "brain_outputs",
        "COORDINATOR_DECISION": "coordinator_decisions",
        "QUALITY_EVALUATION": "signal_quality_evaluations",
        "PROCESSING_STATE": "signal_processing_states",
        "LINK_COVERAGE": "signal_link_coverage_analysis",
        "LINEAGE_COVERAGE": "signal_lineage_coverage_analysis",
    }.get(object_type, "unknown")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value

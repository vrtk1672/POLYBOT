from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.lineage_coverage import SignalLineageCoverageAnalysis, lineage_coverage_from_row
from app.repositories.lineage_coverage_repository import LineageCoverageRepository


class LineageCoverageService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: LineageCoverageRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or LineageCoverageRepository()

    def analyze_signal(self, signal_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn, conn.transaction():
            context = self._repository.get_signal_context(conn, signal_id)
            if not context:
                return None
            analysis = analyze_lineage_context(context)
            row = self._repository.upsert_analysis(conn, analysis)
        return _analysis_response(row)

    def analyze_recent_signals(self, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "OK", "mock_data": False, "analyzed": 0, "created_or_updated": 0, "summary": _empty_summary()}
        with self._factory.connect() as conn, conn.transaction():
            signal_ids = self._repository.list_recent_signal_ids(conn, limit=limit)
            updated = 0
            for signal_id in signal_ids:
                context = self._repository.get_signal_context(conn, signal_id)
                if not context:
                    continue
                analysis = analyze_lineage_context(context)
                self._repository.upsert_analysis(conn, analysis)
                updated += 1
            summary = self._repository.summary(conn, limit=20)
            status = "OK" if updated == len(signal_ids) else "PARTIAL"
            self._repository.record_run(conn, requested_limit=limit, summary={**summary, "analyzed_count": updated}, status=status)
        return {
            "status": status,
            "mock_data": False,
            "analyzed": len(signal_ids),
            "created_or_updated": updated,
            "summary": _summary_response(summary),
        }

    def get_lineage_coverage(self, signal_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_analysis(conn, signal_id)
        return _analysis_response(row) if row else None

    def list_lineage_coverage(
        self,
        *,
        limit: int = 50,
        lineage_status: str | None = None,
        reason: str | None = None,
        producer: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_analyses(
                conn,
                limit=limit,
                lineage_status=lineage_status,
                reason=reason,
                producer=producer,
                source=source,
            )
        return [_analysis_response(row) for row in rows]

    def get_lineage_coverage_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        return _summary_response(summary)


def analyze_lineage_context(row: dict[str, Any]) -> SignalLineageCoverageAnalysis:
    try:
        evidence = row.get("evidence_json") if isinstance(row.get("evidence_json"), dict) else {}
        lineage = row.get("lineage_json") if isinstance(row.get("lineage_json"), dict) else {}
        producer = _blank_none(row.get("producer_name"))
        source = _blank_none(row.get("binding_source_name") or row.get("source_name"))
        correlation_id = _blank_none(row.get("binding_correlation_id") or row.get("correlation_id"))
        raw_payload_ref = _blank_none(row.get("binding_raw_payload_ref") or row.get("raw_payload_ref"))
        generated_from = _blank_none(row.get("generated_from"))
        generated_by = _blank_none(lineage.get("generated_by") or evidence.get("generated_by") or producer)
        generated_at = row.get("binding_created_at") or row.get("signal_created_at")
        signal_created_at = row.get("signal_created_at")

        has_producer = bool(producer)
        has_source = bool(source)
        has_correlation_id = bool(correlation_id)
        has_raw_payload_ref = bool(raw_payload_ref)
        has_generated_from = bool(generated_from)
        has_generated_at = isinstance(generated_at, datetime)

        lower_tokens = {
            str(value or "").strip().lower()
            for value in (
                producer,
                source,
                generated_from,
                generated_by,
                evidence.get("source"),
                evidence.get("producer"),
                evidence.get("generated_by"),
                lineage.get("source"),
                lineage.get("producer"),
                lineage.get("generated_by"),
            )
        }
        is_dry_run = bool(row.get("quality_is_dry_run_generated")) or "mesh_dry_run" in lower_tokens or "dry_run" in lower_tokens
        is_manual = str(generated_from or "").lower() in {"manual", "dashboard"}
        is_adapter = bool(producer) and str(generated_from or "").lower() in {"source_status", "rules_resolution", "event_log", "future_connector"}
        is_runtime = bool(row.get("quality_is_runtime_generated")) or (bool(signal_created_at) and not is_dry_run and not is_manual)

        can_trace_to_event = bool(row.get("event_log_id") or row.get("source_event_id") or row.get("source_status_id"))
        can_trace_to_payload = has_raw_payload_ref
        can_trace_to_producer = has_producer
        has_explainable_origin = has_producer or has_source or has_generated_from or can_trace_to_event or can_trace_to_payload

        missing = _missing_fields(
            has_producer=has_producer,
            has_source=has_source,
            has_correlation_id=has_correlation_id,
            has_raw_payload_ref=has_raw_payload_ref,
            has_generated_from=has_generated_from,
            has_generated_at=has_generated_at,
        )
        reasons = list(missing)
        if not can_trace_to_event:
            reasons = _append_unique(reasons, "NO_EVENT_TRACE")
        if not can_trace_to_payload:
            reasons = _append_unique(reasons, "NO_PAYLOAD_TRACE")
        if not can_trace_to_producer:
            reasons = _append_unique(reasons, "NO_PRODUCER_TRACE")
        if is_dry_run:
            reasons = _prepend_reason(reasons, "DRY_RUN_ONLY")
        if not has_explainable_origin:
            reasons = _prepend_reason(reasons, "UNKNOWN_ORIGIN")

        score = _lineage_trust_score(
            has_producer=has_producer,
            has_source=has_source,
            has_correlation_id=has_correlation_id,
            has_raw_payload_ref=has_raw_payload_ref,
            has_generated_from=has_generated_from,
            has_generated_at=has_generated_at,
            is_runtime_generated=is_runtime,
            is_dry_run_generated=is_dry_run,
            unknown_origin=not has_explainable_origin,
        )

        complete = has_producer and has_source and has_correlation_id and has_raw_payload_ref and has_generated_from and has_generated_at
        if is_dry_run:
            lineage_status = "DRY_RUN_ONLY"
        elif complete and is_runtime and can_trace_to_payload and can_trace_to_producer:
            lineage_status = "RUNTIME_VERIFIED"
        elif complete:
            lineage_status = "COMPLETE"
        elif is_manual:
            lineage_status = "MANUAL"
        elif is_adapter and score >= 0.50:
            lineage_status = "ADAPTER"
        elif score >= 0.50 and (has_producer or has_source):
            lineage_status = "PARTIAL"
        elif not has_explainable_origin:
            lineage_status = "STALE_OR_UNKNOWN"
        else:
            lineage_status = "UNBOUND"

        if lineage_status in {"COMPLETE", "RUNTIME_VERIFIED"}:
            primary = "ALREADY_BOUND"
            reasons = ["ALREADY_BOUND"]
        elif is_dry_run:
            primary = "DRY_RUN_ONLY"
        else:
            primary = _primary_reason(reasons)

        can_feed_brain = score >= 0.50 and has_source and has_producer and lineage_status != "ERROR"
        can_feed_paper = (
            score >= 0.85
            and complete
            and is_runtime
            and not is_dry_run
            and can_trace_to_payload
            and can_trace_to_producer
        )
        is_bound = lineage_status in {"COMPLETE", "RUNTIME_VERIFIED"} or bool(row.get("binding_id"))
        is_unbound = lineage_status not in {"COMPLETE", "RUNTIME_VERIFIED"}

        return SignalLineageCoverageAnalysis(
            signal_id=str(row["signal_id"]),
            lineage_status=lineage_status,
            lineage_trust_score=score,
            is_bound=is_bound,
            is_unbound=is_unbound,
            primary_unbound_reason=primary,
            unbound_reasons=reasons or ["UNKNOWN"],
            missing_lineage_fields=missing,
            producer=producer,
            source=source,
            correlation_id=correlation_id,
            raw_payload_ref=raw_payload_ref,
            generated_from=generated_from,
            generated_by=generated_by,
            generated_at=generated_at,
            signal_created_at=signal_created_at,
            is_dry_run_generated=is_dry_run,
            is_runtime_generated=is_runtime,
            is_manual_generated=is_manual,
            is_adapter_generated=is_adapter,
            has_producer=has_producer,
            has_source=has_source,
            has_correlation_id=has_correlation_id,
            has_raw_payload_ref=has_raw_payload_ref,
            has_generated_from=has_generated_from,
            has_generated_at=has_generated_at,
            has_explainable_origin=has_explainable_origin,
            can_trace_to_event=can_trace_to_event,
            can_trace_to_payload=can_trace_to_payload,
            can_trace_to_producer=can_trace_to_producer,
            can_feed_brain_by_lineage=can_feed_brain,
            can_feed_paper_by_lineage=can_feed_paper,
            analysis_status="OK" if lineage_status not in {"PARTIAL", "UNBOUND", "STALE_OR_UNKNOWN", "DRY_RUN_ONLY"} else "PARTIAL",
            analyzed_at=datetime.now(UTC),
        )
    except Exception as exc:
        return SignalLineageCoverageAnalysis(
            signal_id=str(row.get("signal_id") or "unknown"),
            lineage_status="ERROR",
            lineage_trust_score=0.0,
            is_bound=False,
            is_unbound=True,
            primary_unbound_reason="UNKNOWN",
            unbound_reasons=["UNKNOWN"],
            missing_lineage_fields=[],
            analysis_status="ERROR",
            analysis_error=f"{type(exc).__name__}: {exc}",
            analyzed_at=datetime.now(UTC),
        )


def _summary_response(summary: dict[str, Any]) -> dict[str, Any]:
    total = int(summary.get("total_analyzed") or 0)
    bound = int(summary.get("bound_signals") or 0)
    unbound = int(summary.get("unbound_signals") or 0)
    status = "EMPTY"
    if total:
        status = "DEGRADED" if unbound or int(summary.get("error_count") or 0) else "OK"
    return {
        "status": status,
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "total_signals": int(summary.get("total_signals") or 0),
        "total_analyzed": total,
        "bound_signals": bound,
        "unbound_signals": unbound,
        "complete_lineage": int(summary.get("complete_lineage") or 0),
        "partial_lineage": int(summary.get("partial_lineage") or 0),
        "lineage_coverage_ratio": round(bound / total, 4) if total else 0.0,
        "dry_run_only_signals": int(summary.get("dry_run_only_signals") or 0),
        "runtime_verified_signals": int(summary.get("runtime_verified_signals") or 0),
        "missing_producer_count": int(summary.get("missing_producer_count") or 0),
        "missing_source_count": int(summary.get("missing_source_count") or 0),
        "missing_correlation_id_count": int(summary.get("missing_correlation_id_count") or 0),
        "missing_raw_payload_ref_count": int(summary.get("missing_raw_payload_ref_count") or 0),
        "missing_generated_from_count": int(summary.get("missing_generated_from_count") or 0),
        "unbound_by_reason": [_json_safe(row) for row in summary.get("unbound_by_reason", [])],
        "missing_lineage_fields": [_json_safe(row) for row in summary.get("missing_lineage_fields", [])],
        "producer_coverage": [_json_safe(row) for row in summary.get("producer_coverage", [])],
        "source_coverage": [_json_safe(row) for row in summary.get("source_coverage", [])],
        "raw_payload_coverage": _json_safe(summary.get("raw_payload_coverage", {})),
        "correlation_coverage": _json_safe(summary.get("correlation_coverage", {})),
        "producer_coverage_ratio": summary.get("producer_coverage_ratio", 0.0),
        "source_coverage_ratio": summary.get("source_coverage_ratio", 0.0),
        "avg_lineage_trust_score": summary.get("avg_lineage_trust_score", 0.0),
        "last_analysis_at": _json_safe(summary.get("last_analysis_at")),
        "analysis_status": "ERROR" if int(summary.get("error_count") or 0) else status,
        "latest_analyses": [_json_safe(lineage_coverage_from_row(row).to_api_dict()) for row in summary.get("latest_analyses", [])],
        "paper_ready": False,
    }


def _analysis_response(row: dict[str, Any]) -> dict[str, Any]:
    return _json_safe(lineage_coverage_from_row(dict(row)).to_api_dict())


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "OK",
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "total_signals": 0,
        "total_analyzed": 0,
        "bound_signals": 0,
        "unbound_signals": 0,
        "complete_lineage": 0,
        "partial_lineage": 0,
        "lineage_coverage_ratio": 0.0,
        "dry_run_only_signals": 0,
        "runtime_verified_signals": 0,
        "missing_producer_count": 0,
        "missing_source_count": 0,
        "missing_correlation_id_count": 0,
        "missing_raw_payload_ref_count": 0,
        "missing_generated_from_count": 0,
        "unbound_by_reason": [],
        "missing_lineage_fields": [],
        "producer_coverage": [],
        "source_coverage": [],
        "raw_payload_coverage": {"present": 0, "missing": 0, "ratio": 0.0},
        "correlation_coverage": {"present": 0, "missing": 0, "ratio": 0.0},
        "producer_coverage_ratio": 0.0,
        "source_coverage_ratio": 0.0,
        "avg_lineage_trust_score": 0.0,
        "last_analysis_at": None,
        "analysis_status": "OK",
        "latest_analyses": [],
        "paper_ready": False,
    }


def _lineage_trust_score(
    *,
    has_producer: bool,
    has_source: bool,
    has_correlation_id: bool,
    has_raw_payload_ref: bool,
    has_generated_from: bool,
    has_generated_at: bool,
    is_runtime_generated: bool,
    is_dry_run_generated: bool,
    unknown_origin: bool,
) -> float:
    score = 0.0
    score += 0.20 if has_producer else 0.0
    score += 0.20 if has_source else 0.0
    score += 0.15 if has_correlation_id else 0.0
    score += 0.20 if has_raw_payload_ref else 0.0
    score += 0.10 if has_generated_from else 0.0
    score += 0.05 if has_generated_at else 0.0
    score += 0.10 if is_runtime_generated else 0.0
    score -= 0.25 if is_dry_run_generated else 0.0
    score -= 0.30 if unknown_origin else 0.0
    return round(max(0.0, min(1.0, score)), 4)


def _missing_fields(
    *,
    has_producer: bool,
    has_source: bool,
    has_correlation_id: bool,
    has_raw_payload_ref: bool,
    has_generated_from: bool,
    has_generated_at: bool,
) -> list[str]:
    mapping = {
        "has_producer": "MISSING_PRODUCER",
        "has_source": "MISSING_SOURCE",
        "has_correlation_id": "MISSING_CORRELATION_ID",
        "has_raw_payload_ref": "MISSING_RAW_PAYLOAD_REF",
        "has_generated_from": "MISSING_GENERATED_FROM",
        "has_generated_at": "MISSING_GENERATED_AT",
    }
    flags = locals()
    return [reason for field, reason in mapping.items() if not flags.get(field)]


def _primary_reason(reasons: list[str]) -> str:
    priority = [
        "MISSING_PRODUCER",
        "MISSING_SOURCE",
        "MISSING_CORRELATION_ID",
        "MISSING_RAW_PAYLOAD_REF",
        "MISSING_GENERATED_FROM",
        "MISSING_GENERATED_AT",
        "UNKNOWN_ORIGIN",
        "NO_EVENT_TRACE",
        "NO_PAYLOAD_TRACE",
        "NO_PRODUCER_TRACE",
    ]
    for reason in priority:
        if reason in reasons:
            return reason
    return reasons[0] if reasons else "UNKNOWN"


def _blank_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _prepend_reason(reasons: list[str], reason: str) -> list[str]:
    return [reason, *[item for item in reasons if item != reason]]


def _append_unique(reasons: list[str], reason: str) -> list[str]:
    return reasons if reason in reasons else [*reasons, reason]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value

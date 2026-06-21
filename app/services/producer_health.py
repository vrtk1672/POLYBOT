from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.producer_health import ProducerHealth, ProducerHealthSummary
from app.services.neuron_registry import NeuronRegistryService


class ProducerHealthService:
    """Read-only producer/neuron runtime truth from registry, Signals, and provenance."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def get_producer_health_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return build_producer_health_summary([], [], [], [], limit=limit).to_api_dict()
        try:
            NeuronRegistryService(connection_factory=self._factory).refresh_neuron_health_from_signals()
            with self._factory.connect() as conn:
                registered = _registered_producers(conn)
                observed = _observed_signal_producers(conn)
                output_stats = _output_producer_stats(conn)
                registry_neurons = _registry_neurons(conn)
            return build_producer_health_summary(
                registered,
                observed,
                output_stats,
                registry_neurons,
                limit=limit,
            ).to_api_dict()
        except Exception as exc:
            now = datetime.now(UTC)
            error = ProducerHealth(
                producer_name="unknown",
                health_status="ERROR",
                health_reason="Producer health analysis failed.",
                evidence={"error_type": type(exc).__name__, "error": str(exc)},
                analyzed_at=now,
            )
            return ProducerHealthSummary(
                mock_data=False,
                overall_status="ERROR",
                paper_ready=False,
                total_producers=1,
                registered_producers=0,
                observed_producers=0,
                runtime_active_producers=0,
                dry_run_only_producers=0,
                producer_health=[error],
                neuron_runtime_truth=_runtime_truth([error]),
                last_updated=now,
                analysis_status="ERROR",
            ).to_api_dict()


def build_producer_health_summary(
    registered: list[dict[str, Any]],
    observed: list[dict[str, Any]],
    output_stats: list[dict[str, Any]],
    registry_neurons: list[dict[str, Any]],
    *,
    limit: int = 50,
) -> ProducerHealthSummary:
    now = datetime.now(UTC)
    producers: dict[str, dict[str, Any]] = {}

    for row in registered:
        name = _producer_name(row.get("producer_name") or row.get("neuron_name"))
        producers[name] = {
            "producer_name": name,
            "neuron_name": _blank_none(row.get("neuron_name")),
            "registered": True,
            "expected": bool(row.get("enabled", True)),
            "observed": False,
            "registry": row,
        }

    for row in observed:
        name = _producer_name(row.get("producer_name"))
        current = producers.setdefault(name, {"producer_name": name, "registered": False, "expected": False, "observed": False})
        current.update(
            {
                "neuron_name": current.get("neuron_name") or _blank_none(row.get("neuron_name")),
                "observed": True,
                "signal_count": _int(row.get("signal_count")),
                "runtime_signal_count": _int(row.get("runtime_signal_count")),
                "dry_run_signal_count": _int(row.get("dry_run_signal_count")),
                "recent_signal_count": _int(row.get("recent_signal_count")),
                "stale_signal_count": _int(row.get("stale_signal_count")),
                "lineage_complete_count": _int(row.get("lineage_complete_count")),
                "lineage_unbound_count": _int(row.get("lineage_unbound_count")),
                "avg_quality_score": _none_float(row.get("avg_quality_score")),
                "paper_signal_count": _int(row.get("paper_signal_count")),
                "brain_signal_count": _int(row.get("brain_signal_count")),
                "first_seen_at": row.get("first_seen_at"),
                "last_seen_at": row.get("last_seen_at"),
                "signal_evidence": row,
            }
        )

    for row in output_stats:
        name = _producer_name(row.get("producer_name"))
        current = producers.setdefault(name, {"producer_name": name, "registered": False, "expected": False, "observed": True})
        current["brain_output_count"] = current.get("brain_output_count", 0) + _int(row.get("brain_output_count"))
        current["coordinator_decision_count"] = current.get("coordinator_decision_count", 0) + _int(row.get("coordinator_decision_count"))
        current["dry_run_signal_count"] = current.get("dry_run_signal_count", 0) + _int(row.get("dry_run_output_count"))
        current["runtime_signal_count"] = current.get("runtime_signal_count", 0) + _int(row.get("runtime_output_count"))
        current["last_seen_at"] = _max_time(current.get("last_seen_at"), row.get("last_seen_at"))
        current["observed"] = True

    registry_by_neuron = {str(row.get("neuron_name") or ""): row for row in registry_neurons}
    health_items = [_classify_producer(item, registry_by_neuron, now) for item in producers.values()]

    registered_neurons = {str(row.get("neuron_name") or "") for row in registry_neurons if row.get("enabled", True)}
    observed_neurons = {str(item.neuron_name or "") for item in health_items if item.observed and item.neuron_name}
    health_items.extend(
        _missing_neuron_item(row, now)
        for name, row in registry_by_neuron.items()
        if name and name not in observed_neurons and name not in {item.neuron_name for item in health_items if item.registered}
    )

    all_items = sorted(health_items, key=lambda item: (_status_rank(item.health_status), item.producer_name))
    response_items = all_items[:limit]
    overall_status = _overall_status(all_items)
    return ProducerHealthSummary(
        mock_data=False,
        overall_status=overall_status,
        paper_ready=False,
        total_producers=len(all_items),
        registered_producers=sum(1 for item in all_items if item.registered),
        observed_producers=sum(1 for item in all_items if item.observed),
        runtime_active_producers=sum(1 for item in all_items if item.runtime_active),
        dry_run_only_producers=sum(1 for item in all_items if item.dry_run_only),
        silent_expected_neurons=sorted({str(item.neuron_name or item.producer_name) for item in all_items if item.silent_expected}),
        missing_neurons=sorted({str(item.neuron_name or item.producer_name) for item in all_items if item.missing}),
        degraded_neurons=sorted({str(item.neuron_name or item.producer_name) for item in all_items if item.degraded}),
        dry_run_only_neurons=sorted({str(item.neuron_name or item.producer_name) for item in all_items if item.dry_run_only}),
        producer_health=response_items,
        neuron_runtime_truth=_runtime_truth(all_items),
        last_updated=now,
        analysis_status="OK",
    )


def _classify_producer(item: dict[str, Any], registry_by_neuron: dict[str, dict[str, Any]], now: datetime) -> ProducerHealth:
    signal_count = _int(item.get("signal_count"))
    runtime_count = _int(item.get("runtime_signal_count"))
    dry_count = _int(item.get("dry_run_signal_count"))
    stale_count = _int(item.get("stale_signal_count"))
    lineage_unbound = _int(item.get("lineage_unbound_count"))
    lineage_complete = _int(item.get("lineage_complete_count"))
    brain_outputs = _int(item.get("brain_output_count"))
    coordinator_decisions = _int(item.get("coordinator_decision_count"))
    avg_quality = _none_float(item.get("avg_quality_score"))
    neuron_name = _blank_none(item.get("neuron_name"))
    registry_row = registry_by_neuron.get(str(neuron_name or ""))
    expected = bool(item.get("expected")) or bool(registry_row and registry_row.get("enabled") and registry_row.get("expected_signal_types"))
    observed = bool(item.get("observed")) or signal_count > 0 or brain_outputs > 0 or coordinator_decisions > 0
    registered = bool(item.get("registered"))
    recent_count = _int(item.get("recent_signal_count"))
    paper_signal_count = _int(item.get("paper_signal_count"))
    brain_signal_count = _int(item.get("brain_signal_count"))

    dry_run_only = observed and runtime_count == 0 and (dry_count > 0 or brain_outputs > 0 or coordinator_decisions > 0)
    runtime_active = runtime_count > 0 and recent_count > 0 and not dry_run_only
    stale_ratio = stale_count / signal_count if signal_count else 0.0
    lineage_unbound_ratio = lineage_unbound / signal_count if signal_count else 0.0

    health_status = "UNKNOWN"
    health_reason = "No clear producer evidence was available."
    silent_expected = False
    degraded = False
    missing = False

    if registered and expected and not observed:
        health_status = "SILENT"
        health_reason = "Registered expected producer has no observed Signals."
        silent_expected = True
    elif expected and not observed:
        health_status = "MISSING"
        health_reason = "Expected neuron has no observed producer evidence."
        missing = True
    elif _producer_name(item.get("producer_name")) == "unknown":
        health_status = "UNKNOWN"
        health_reason = "Observed producer evidence has no producer name."
    elif dry_run_only:
        health_status = "DRY_RUN_ONLY"
        health_reason = "Only dry-run or dry-run-derived evidence observed."
    elif signal_count and stale_ratio >= 0.50:
        health_status = "DEGRADED"
        health_reason = "STALE_OUTPUT_HIGH"
        degraded = True
    elif signal_count and lineage_unbound_ratio > 0:
        health_status = "DEGRADED"
        health_reason = "LINEAGE_INCOMPLETE"
        degraded = True
    elif avg_quality is not None and avg_quality < 0.60:
        health_status = "DEGRADED"
        health_reason = "QUALITY_LOW"
        degraded = True
    elif runtime_active and (brain_signal_count > 0 or avg_quality is None or avg_quality >= 0.60):
        health_status = "HEALTHY"
        health_reason = "Runtime Signals are recent and usable for observability."
    elif runtime_count > 0:
        health_status = "ACTIVE"
        health_reason = "Runtime producer evidence exists but is not fully recent."
    elif registered and not observed:
        health_status = "REGISTERED_ONLY"
        health_reason = "Producer is registered but has no runtime evidence."
    elif observed:
        health_status = "ACTIVE"
        health_reason = "Observed producer evidence exists."

    can_feed_brain = bool(brain_signal_count > 0 or (runtime_count > 0 and not missing and health_status in {"HEALTHY", "ACTIVE", "DEGRADED"}))
    can_feed_paper = bool(paper_signal_count > 0 and runtime_count > 0 and not dry_run_only and not missing and health_status in {"HEALTHY", "ACTIVE"})

    return ProducerHealth(
        producer_name=_producer_name(item.get("producer_name")),
        neuron_name=neuron_name,
        registered=registered,
        expected=expected,
        observed=observed,
        signal_count=signal_count,
        runtime_signal_count=runtime_count,
        dry_run_signal_count=dry_count,
        recent_signal_count=recent_count,
        stale_signal_count=stale_count,
        brain_output_count=brain_outputs,
        coordinator_decision_count=coordinator_decisions,
        lineage_complete_count=lineage_complete,
        lineage_unbound_count=lineage_unbound,
        avg_quality_score=avg_quality,
        health_status=health_status,
        health_reason=health_reason,
        dry_run_only=dry_run_only,
        runtime_active=runtime_active,
        silent_expected=silent_expected,
        degraded=degraded,
        missing=missing,
        can_feed_brain=can_feed_brain,
        can_feed_paper=can_feed_paper,
        evidence=_json_safe(
            {
                "signal_count": signal_count,
                "runtime_signal_count": runtime_count,
                "dry_run_signal_count": dry_count,
                "recent_signal_count": recent_count,
                "stale_signal_count": stale_count,
                "lineage_unbound_count": lineage_unbound,
                "avg_quality_score": avg_quality,
                "registered": registered,
                "expected": expected,
            }
        ),
        first_seen_at=item.get("first_seen_at"),
        last_seen_at=item.get("last_seen_at"),
        analyzed_at=now,
    )


def _missing_neuron_item(row: dict[str, Any], now: datetime) -> ProducerHealth:
    enabled = bool(row.get("enabled", True))
    expected = enabled and bool(row.get("expected_signal_types") or row.get("is_required_for_paper"))
    status = "MISSING" if expected else "REGISTERED_ONLY"
    return ProducerHealth(
        producer_name=_producer_name(row.get("neuron_name")),
        neuron_name=_blank_none(row.get("neuron_name")),
        registered=True,
        expected=expected,
        observed=False,
        health_status=status,
        health_reason="Expected registered neuron has no observed producer evidence." if expected else "Registered neuron has no observed runtime evidence.",
        silent_expected=expected,
        missing=expected,
        evidence={"registry": _json_safe(row)},
        analyzed_at=now,
    )


def _runtime_truth(items: list[ProducerHealth]) -> dict[str, list[str]]:
    return {
        "runtime_active": sorted({str(item.neuron_name or item.producer_name) for item in items if item.runtime_active}),
        "dry_run_only": sorted({str(item.neuron_name or item.producer_name) for item in items if item.dry_run_only}),
        "silent_expected": sorted({str(item.neuron_name or item.producer_name) for item in items if item.silent_expected}),
        "degraded": sorted({str(item.neuron_name or item.producer_name) for item in items if item.degraded}),
        "missing": sorted({str(item.neuron_name or item.producer_name) for item in items if item.missing}),
        "unknown": sorted({str(item.neuron_name or item.producer_name) for item in items if item.health_status == "UNKNOWN"}),
    }


def _registered_producers(conn: Any) -> list[dict[str, Any]]:
    if not _table_exists(conn, "neuron_producers"):
        if not _table_exists(conn, "neuron_registry"):
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT neuron_name AS producer_name, neuron_name, enabled, expected_signal_types,
                       is_required_for_paper, default_status, owner_component AS source_name
                FROM neuron_registry
                """
            ).fetchall()
        ]
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT p.producer_name, p.neuron_name, p.enabled, p.expected_signal_types,
                   p.source_name, r.is_required_for_paper, r.default_status, r.owner_component
            FROM neuron_producers p
            LEFT JOIN neuron_registry r ON r.neuron_name = p.neuron_name
            ORDER BY p.producer_name
            """
        ).fetchall()
    ]


def _registry_neurons(conn: Any) -> list[dict[str, Any]]:
    if not _table_exists(conn, "neuron_registry"):
        return []
    return [dict(row) for row in conn.execute("SELECT * FROM neuron_registry ORDER BY neuron_name").fetchall()]


def _observed_signal_producers(conn: Any) -> list[dict[str, Any]]:
    if not _table_exists(conn, "neuron_signals"):
        return []
    binding_expr = "b.producer_name" if _table_exists(conn, "neuron_signal_bindings") else "NULL"
    binding_neuron_expr = "b.neuron_name" if _table_exists(conn, "neuron_signal_bindings") else "NULL"
    binding_join = "LEFT JOIN neuron_signal_bindings b ON b.signal_id = s.signal_id" if _table_exists(conn, "neuron_signal_bindings") else ""
    quality_join = "LEFT JOIN signal_quality_evaluations q ON q.signal_id = s.signal_id" if _table_exists(conn, "signal_quality_evaluations") else ""
    lineage_join = "LEFT JOIN signal_lineage_coverage_analysis l ON l.signal_id = s.signal_id" if _table_exists(conn, "signal_lineage_coverage_analysis") else ""
    provenance_join = "LEFT JOIN dry_run_provenance_analysis dp ON dp.object_type = 'SIGNAL' AND dp.object_id = s.signal_id" if _table_exists(conn, "dry_run_provenance_analysis") else ""
    processing_join = "LEFT JOIN signal_processing_states ps ON ps.signal_id = s.signal_id" if _table_exists(conn, "signal_processing_states") else ""
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT
                COALESCE({binding_expr}, NULLIF(s.source_name, ''), 'unknown') AS producer_name,
                COALESCE({binding_neuron_expr}, s.neuron) AS neuron_name,
                COUNT(*) AS signal_count,
                COUNT(*) FILTER (
                    WHERE COALESCE(dp.is_dry_run_generated, q.is_dry_run_generated, l.is_dry_run_generated, false) = true
                ) AS dry_run_signal_count,
                COUNT(*) FILTER (
                    WHERE COALESCE(dp.is_dry_run_generated, q.is_dry_run_generated, l.is_dry_run_generated, false) = false
                      AND (
                          COALESCE(dp.is_runtime_generated, q.is_runtime_generated, l.is_runtime_generated, false) = true
                          OR {binding_expr} IS NOT NULL
                      )
                ) AS runtime_signal_count,
                COUNT(*) FILTER (WHERE s.created_at >= now() - interval '60 minutes') AS recent_signal_count,
                COUNT(*) FILTER (
                    WHERE s.status = 'STALE'
                       OR COALESCE(ps.is_stale, q.is_stale, false) = true
                       OR (s.expires_at IS NOT NULL AND s.expires_at <= now())
                       OR (
                           s.stale_after_seconds IS NOT NULL
                           AND s.created_at + (s.stale_after_seconds::text || ' seconds')::interval <= now()
                       )
                ) AS stale_signal_count,
                COUNT(*) FILTER (WHERE COALESCE(l.lineage_status, '') IN ('COMPLETE', 'RUNTIME_VERIFIED')) AS lineage_complete_count,
                COUNT(*) FILTER (WHERE COALESCE(l.is_unbound, false) = true) AS lineage_unbound_count,
                AVG(q.quality_score) AS avg_quality_score,
                COUNT(*) FILTER (WHERE COALESCE(q.can_feed_brain, ps.can_feed_brain, false) = true) AS brain_signal_count,
                COUNT(*) FILTER (WHERE COALESCE(q.can_feed_paper, ps.can_feed_paper, false) = true) AS paper_signal_count,
                MIN(s.created_at) AS first_seen_at,
                MAX(s.created_at) AS last_seen_at
            FROM neuron_signals s
            {binding_join}
            {quality_join}
            {lineage_join}
            {provenance_join}
            {processing_join}
            GROUP BY COALESCE({binding_expr}, NULLIF(s.source_name, ''), 'unknown'), COALESCE({binding_neuron_expr}, s.neuron)
            ORDER BY signal_count DESC
            """
        ).fetchall()
    ]


def _output_producer_stats(conn: Any) -> list[dict[str, Any]]:
    if not _table_exists(conn, "dry_run_provenance_analysis"):
        return []
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                COALESCE(NULLIF(producer_name, ''), 'unknown') AS producer_name,
                COUNT(*) FILTER (WHERE object_type = 'BRAIN_OUTPUT') AS brain_output_count,
                COUNT(*) FILTER (WHERE object_type = 'COORDINATOR_DECISION') AS coordinator_decision_count,
                COUNT(*) FILTER (WHERE is_dry_run_generated = true) AS dry_run_output_count,
                COUNT(*) FILTER (WHERE is_runtime_generated = true) AS runtime_output_count,
                MAX(source_created_at) AS last_seen_at
            FROM dry_run_provenance_analysis
            WHERE object_type IN ('BRAIN_OUTPUT', 'COORDINATOR_DECISION')
            GROUP BY COALESCE(NULLIF(producer_name, ''), 'unknown')
            """
        ).fetchall()
    ]


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _overall_status(items: list[ProducerHealth]) -> str:
    if any(item.health_status == "ERROR" for item in items):
        return "ERROR"
    if any(item.degraded or item.silent_expected or item.missing or item.dry_run_only or item.health_status in {"UNKNOWN", "REGISTERED_ONLY"} for item in items):
        return "DEGRADED"
    return "OK"


def _status_rank(status: str) -> int:
    return {"ERROR": 0, "MISSING": 1, "SILENT": 2, "DEGRADED": 3, "DRY_RUN_ONLY": 4, "UNKNOWN": 5, "REGISTERED_ONLY": 6, "ACTIVE": 7, "HEALTHY": 8}.get(str(status).upper(), 9)


def _producer_name(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    return text or "unknown"


def _blank_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _none_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _max_time(left: Any, right: Any) -> Any:
    values = [item for item in (left, right) if item is not None]
    if not values:
        return None
    return max(values)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.signal_quality import SignalQualityEvaluation, signal_quality_from_row
from app.repositories.signal_quality_repository import SignalQualityRepository


class SignalQualityService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: SignalQualityRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or SignalQualityRepository()

    def evaluate_signal_quality(self, signal_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn, conn.transaction():
            context = self._repository.get_signal_context(conn, signal_id)
            if not context:
                return None
            evaluation = evaluate_signal_context(context)
            row = self._repository.upsert_evaluation(conn, evaluation)
        return signal_quality_from_row(row).to_api_dict()

    def evaluate_recent_signals(self, *, limit: int = 100) -> dict[str, Any]:
        return self._evaluate_signal_ids(limit=limit, unevaluated_only=False)

    def evaluate_all_unevaluated_signals(self, *, limit: int = 100) -> dict[str, Any]:
        return self._evaluate_signal_ids(limit=limit, unevaluated_only=True)

    def get_signal_quality(self, signal_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_evaluation(conn, signal_id)
        return signal_quality_from_row(row).to_api_dict() if row else None

    def list_signal_quality(
        self,
        *,
        limit: int = 50,
        quality_status: str | None = None,
        can_feed_brain: bool | None = None,
        can_feed_paper: bool | None = None,
    ) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_evaluations(
                conn,
                limit=limit,
                quality_status=quality_status,
                can_feed_brain=can_feed_brain,
                can_feed_paper=can_feed_paper,
            )
        return [signal_quality_from_row(row).to_api_dict() for row in rows]

    def get_signal_quality_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        status = "EMPTY"
        if summary["total_evaluated"] > 0:
            status = "DEGRADED" if summary["low_quality_count"] > 0 or summary["can_feed_paper"] == 0 else "OK"
        return {
            "status": status,
            "mock_data": False,
            "updated_at": datetime.now(UTC).isoformat(),
            "total_evaluated": summary["total_evaluated"],
            "avg_quality_score": summary["avg_quality_score"],
            "can_feed_brain": summary["can_feed_brain"],
            "can_feed_paper": summary["can_feed_paper"],
            "quality_by_status": [_json_safe(row) for row in summary["quality_by_status"]],
            "missing_fields_summary": [_json_safe(row) for row in summary["missing_fields_summary"]],
            "dry_run_generated": summary["dry_run_generated"],
            "runtime_generated": summary["runtime_generated"],
            "low_quality_count": summary["low_quality_count"],
            "low_quality_signals": [_json_safe(signal_quality_from_row(row).to_api_dict()) for row in summary["low_quality_signals"]],
            "paper_blocking_reasons": [_json_safe(row) for row in summary["paper_blocking_reasons"]],
            "latest_evaluated_at": _json_safe(summary["latest_evaluated_at"]),
        }

    def get_missing_field_summary(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return self.get_signal_quality_summary(limit=limit)["missing_fields_summary"]

    def get_quality_distribution(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return self.get_signal_quality_summary(limit=limit)["quality_by_status"]

    def get_low_quality_signals(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return self.get_signal_quality_summary(limit=limit)["low_quality_signals"]

    def _evaluate_signal_ids(self, *, limit: int, unevaluated_only: bool) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "OK", "mock_data": False, "evaluated": 0, "created_or_updated": 0, "summary": _empty_summary()}
        with self._factory.connect() as conn, conn.transaction():
            signal_ids = (
                self._repository.list_unevaluated_signal_ids(conn, limit=limit)
                if unevaluated_only
                else self._repository.list_recent_signal_ids(conn, limit=limit)
            )
            updated = 0
            for signal_id in signal_ids:
                context = self._repository.get_signal_context(conn, signal_id)
                if not context:
                    continue
                evaluation = evaluate_signal_context(context)
                self._repository.upsert_evaluation(conn, evaluation)
                updated += 1
            summary = self._repository.summary(conn, limit=20)
        response_summary = {
            "total_evaluated": summary["total_evaluated"],
            "avg_quality_score": summary["avg_quality_score"],
            "can_feed_brain": summary["can_feed_brain"],
            "can_feed_paper": summary["can_feed_paper"],
            "quality_by_status": [_json_safe(row) for row in summary["quality_by_status"]],
            "missing_fields_summary": [_json_safe(row) for row in summary["missing_fields_summary"]],
            "paper_blocking_reasons": [_json_safe(row) for row in summary["paper_blocking_reasons"]],
        }
        return {
            "status": "OK" if updated == len(signal_ids) else "DEGRADED",
            "mock_data": False,
            "evaluated": len(signal_ids),
            "created_or_updated": updated,
            "summary": response_summary,
        }


def evaluate_signal_context(row: dict[str, Any]) -> SignalQualityEvaluation:
    evidence = row.get("evidence_json") if isinstance(row.get("evidence_json"), dict) else {}
    source_name = row.get("binding_source_name") or row.get("source_name")
    correlation_id = row.get("binding_correlation_id") or row.get("correlation_id")
    raw_payload_ref = row.get("binding_raw_payload_ref") or row.get("raw_payload_ref")
    generated_from = str(row.get("generated_from") or "").lower()
    producer_name = str(row.get("producer_name") or "").lower()
    evidence_generated_by = str(evidence.get("generated_by") or "").lower()

    has_market_id = bool(row.get("market_id"))
    has_source = bool(source_name)
    has_lineage = bool(row.get("has_binding"))
    has_correlation_id = bool(correlation_id)
    has_raw_payload_ref = bool(raw_payload_ref)
    has_confidence = row.get("confidence") is not None
    has_strength = row.get("strength") is not None
    has_freshness = row.get("freshness_seconds") is not None or row.get("stale_after_seconds") is not None or row.get("expires_at") is not None
    has_evidence = bool(evidence) or int(row.get("evidence_count") or 0) > 0 or bool(row.get("has_evidence_rows"))
    linked_to_market = bool(row.get("linked_to_market"))
    linked_to_position = bool(row.get("linked_to_position"))
    used_by_brain_output = bool(row.get("used_by_brain_output"))
    used_by_coordinator = bool(row.get("used_by_coordinator"))
    is_dry_run_generated = (
        generated_from == "mesh_dry_run"
        or producer_name == "mesh_dry_run"
        or str(row.get("source_name") or "").lower() == "mesh_dry_run"
        or evidence_generated_by == "mesh_dry_run"
    )
    is_runtime_generated = bool(row.get("created_at")) and not is_dry_run_generated
    is_stale = _is_stale(row)

    score = 0.0
    score += 0.10 if has_source else 0.0
    score += 0.12 if has_lineage else 0.0
    score += 0.08 if has_correlation_id else 0.0
    score += 0.08 if has_raw_payload_ref else 0.0
    score += 0.08 if has_confidence else 0.0
    score += 0.08 if has_strength else 0.0
    score += 0.08 if has_freshness else 0.0
    score += 0.10 if has_evidence else 0.0
    score += 0.10 if has_market_id else 0.0
    score += 0.12 if linked_to_market else 0.0
    score += 0.08 if used_by_brain_output else 0.0
    score += 0.08 if used_by_coordinator else 0.0
    if is_stale:
        score -= 0.20

    caps: list[float] = []
    if is_dry_run_generated and not is_runtime_generated:
        caps.append(0.70)
    if not has_lineage:
        caps.append(0.60)
    if not linked_to_market:
        caps.append(0.65)
    if not has_evidence:
        caps.append(0.75)
    if not has_source:
        caps.append(0.55)
    if caps:
        score = min(score, min(caps))
    score = round(max(0.0, min(1.0, score)), 4)

    missing_fields = _missing_fields(
        has_market_id=has_market_id,
        has_source=has_source,
        has_lineage=has_lineage,
        has_correlation_id=has_correlation_id,
        has_raw_payload_ref=has_raw_payload_ref,
        has_confidence=has_confidence,
        has_strength=has_strength,
        has_freshness=has_freshness,
        has_evidence=has_evidence,
        linked_to_market=linked_to_market,
        linked_to_position=linked_to_position,
        used_by_brain_output=used_by_brain_output,
        used_by_coordinator=used_by_coordinator,
        is_stale=is_stale,
        has_non_dry_run_market_link=bool(row.get("has_non_dry_run_market_link")),
    )
    can_feed_brain = score >= 0.50 and (has_lineage or has_source) and not is_stale
    can_feed_paper = (
        score >= 0.80
        and has_market_id
        and linked_to_market
        and bool(row.get("has_non_dry_run_market_link"))
        and has_lineage
        and has_source
        and has_evidence
        and not is_stale
        and is_runtime_generated
        and not is_dry_run_generated
    )
    status = _quality_status(
        source_status=str(row.get("status") or ""),
        score=score,
        is_stale=is_stale,
        is_dry_run_generated=is_dry_run_generated,
        is_runtime_generated=is_runtime_generated,
        has_lineage=has_lineage,
        linked_to_market=linked_to_market,
        has_market_id=has_market_id,
        can_feed_brain=can_feed_brain,
    )
    readiness_reason = _readiness_reason(score, status, missing_fields, can_feed_brain, can_feed_paper)
    return SignalQualityEvaluation(
        signal_id=str(row["signal_id"]),
        quality_score=score,
        quality_status=status,
        missing_fields=missing_fields,
        readiness_reason=readiness_reason,
        can_feed_brain=can_feed_brain,
        can_feed_paper=can_feed_paper,
        has_market_id=has_market_id,
        has_source=has_source,
        has_lineage=has_lineage,
        has_correlation_id=has_correlation_id,
        has_raw_payload_ref=has_raw_payload_ref,
        has_confidence=has_confidence,
        has_strength=has_strength,
        has_freshness=has_freshness,
        has_evidence=has_evidence,
        linked_to_market=linked_to_market,
        linked_to_position=linked_to_position,
        used_by_brain_output=used_by_brain_output,
        used_by_coordinator=used_by_coordinator,
        is_dry_run_generated=is_dry_run_generated,
        is_runtime_generated=is_runtime_generated,
        is_stale=is_stale,
        evaluated_at=datetime.now(UTC),
    )


def _is_stale(row: dict[str, Any]) -> bool:
    now = datetime.now(UTC)
    status = str(row.get("status") or "").upper()
    if status == "STALE":
        return True
    expires_at = row.get("expires_at")
    if isinstance(expires_at, datetime):
        expires = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        if expires <= now:
            return True
    created_at = row.get("created_at")
    stale_after = row.get("stale_after_seconds")
    if isinstance(created_at, datetime) and stale_after is not None:
        created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
        return (now - created).total_seconds() >= int(stale_after)
    return False


def _missing_fields(**flags: Any) -> list[str]:
    fields = []
    for name in (
        "has_market_id",
        "has_source",
        "has_lineage",
        "has_correlation_id",
        "has_raw_payload_ref",
        "has_confidence",
        "has_strength",
        "has_freshness",
        "has_evidence",
        "linked_to_market",
        "used_by_brain_output",
        "used_by_coordinator",
    ):
        if not flags.get(name):
            fields.append(name.removeprefix("has_"))
    if not flags.get("linked_to_position"):
        fields.append("position_link")
    if flags.get("is_stale"):
        fields.append("fresh_signal")
    if flags.get("linked_to_market") and not flags.get("has_non_dry_run_market_link"):
        fields.append("production_market_link")
    return fields


def _quality_status(
    *,
    source_status: str,
    score: float,
    is_stale: bool,
    is_dry_run_generated: bool,
    is_runtime_generated: bool,
    has_lineage: bool,
    linked_to_market: bool,
    has_market_id: bool,
    can_feed_brain: bool,
) -> str:
    if source_status.upper() == "ERROR":
        return "ERROR"
    if is_stale:
        return "STALE"
    if is_dry_run_generated and not is_runtime_generated:
        return "DRY_RUN_ONLY"
    if not has_lineage:
        return "UNBOUND"
    if has_market_id and not linked_to_market:
        return "UNLINKED"
    if score >= 0.80:
        return "GOOD"
    if can_feed_brain:
        return "PARTIAL"
    if score < 0.25:
        return "BLOCKED"
    return "WEAK"


def _readiness_reason(score: float, status: str, missing_fields: list[str], can_feed_brain: bool, can_feed_paper: bool) -> str:
    if can_feed_paper:
        return "Signal meets strict informational paper-feed quality gates; this does not make global paper_ready true."
    if can_feed_brain:
        return f"Signal can feed brain outputs but is not paper-feed ready; missing: {', '.join(missing_fields) or 'none'}."
    return f"Signal quality is {status} at {score:.2f}; blocked by: {', '.join(missing_fields) or 'quality gate'}."


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "OK",
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "total_evaluated": 0,
        "avg_quality_score": 0.0,
        "can_feed_brain": 0,
        "can_feed_paper": 0,
        "quality_by_status": [],
        "missing_fields_summary": [],
        "dry_run_generated": 0,
        "runtime_generated": 0,
        "low_quality_count": 0,
        "low_quality_signals": [],
        "paper_blocking_reasons": [],
        "latest_evaluated_at": None,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value

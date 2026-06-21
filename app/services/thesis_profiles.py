from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.thesis_profiles import ThesisProfile, ThesisProfileRun
from app.repositories.thesis_profile_repository import ThesisProfileRepository, thesis_profile_from_row


class ThesisProfileService:
    """Runtime Coordinator-derived thesis profile foundation."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: ThesisProfileRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or ThesisProfileRepository()

    def build_profiles(
        self,
        *,
        limit: int = 100,
        include_incomplete: bool = True,
        include_blocked: bool = True,
        write_profiles: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"thesis_{uuid4().hex}"
        safety_before = _safety_counts(self._factory)
        rows: list[dict[str, Any]] = []
        if self._factory.enabled:
            with self._factory.connect() as conn:
                rows = self._repository.list_runtime_coordinator_decisions(conn, limit=limit)

        profiles: list[ThesisProfile] = []
        errors: list[str] = []
        for row in rows:
            try:
                profile = _profile_from_coordinator(row, run_id=run_id)
                if profile.status == "INCOMPLETE" and not include_incomplete:
                    continue
                if profile.status == "BLOCKED" and not include_blocked:
                    continue
                profiles.append(profile)
            except Exception as exc:
                errors.append(f"{row.get('coordinator_decision_id') or 'unknown'}:{type(exc).__name__}:{exc}")

        created = 0
        updated = 0
        if write_profiles and self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                for profile in profiles:
                    _, was_created = self._repository.upsert_profile(conn, profile)
                    self._repository.record_evidence_items(conn, profile)
                    created += 1 if was_created else 0
                    updated += 0 if was_created else 1

        safety_after = _safety_counts(self._factory)
        run = ThesisProfileRun(
            run_id=run_id,
            status="ERROR" if errors and not profiles else "PARTIAL" if errors else "OK",
            coordinator_decisions_checked=len(rows),
            eligible_decisions=len(profiles),
            thesis_profiles_created=created,
            thesis_profiles_updated=updated,
            complete_thesis_count=len([item for item in profiles if item.status == "COMPLETE"]),
            incomplete_thesis_count=len([item for item in profiles if item.status == "INCOMPLETE"]),
            blocked_thesis_count=len([item for item in profiles if item.status == "BLOCKED"]),
            weak_thesis_count=len([item for item in profiles if item.status == "WEAK"]),
            missing_market_count=len([item for item in profiles if "MISSING_MARKET_ID" in item.missing_evidence]),
            missing_orderbook_count=len([item for item in profiles if "MISSING_FRESH_ORDERBOOK" in item.missing_evidence]),
            missing_binding_count=len([item for item in profiles if "MISSING_SIGNAL_MARKET_BINDING" in item.missing_evidence]),
            missing_evidence_count=sum(len(item.missing_evidence) for item in profiles),
            paper_ready_before=False,
            paper_ready_after=False,
            orders_created=max(0, safety_after["orders"] - safety_before["orders"]),
            order_intents_created=max(0, safety_after["order_intents"] - safety_before["order_intents"]),
            fills_created=max(0, safety_after["fills"] - safety_before["fills"]),
            positions_created=max(0, safety_after["positions"] - safety_before["positions"]),
            live_actions_created=max(0, safety_after["live_actions"] - safety_before["live_actions"]),
            profiles=profiles,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error_summary="; ".join(errors) if errors else None,
        )
        if write_profiles and self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.record_run(conn, run)
        return run.to_api_dict()

    def list_recent(self, *, limit: int = 50, status: str | None = None, market_id: str | None = None) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "OK", "count": 0, "profiles": []}
        with self._factory.connect() as conn:
            rows = self._repository.list_profiles(conn, limit=limit, status=status, market_id=market_id)
        profiles = [thesis_profile_from_row(row).to_api_dict() for row in rows]
        return {"mock_data": False, "status": "OK", "count": len(profiles), "profiles": profiles}

    def get_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            if not _table_exists(conn, "thesis_profiles"):
                return _empty_summary()
            summary = self._repository.summary(conn, limit=limit)
        latest_run = summary.get("latest_run") or {}
        return {
            "mock_data": False,
            "status": "OK",
            "latest_run": _json_safe(latest_run) if latest_run else None,
            "total_thesis_profiles": int(summary.get("total_thesis_profiles") or 0),
            "complete_thesis_profiles": int(summary.get("complete_thesis_profiles") or 0),
            "incomplete_thesis_profiles": int(summary.get("incomplete_thesis_profiles") or 0),
            "blocked_thesis_profiles": int(summary.get("blocked_thesis_profiles") or 0),
            "weak_thesis_profiles": int(summary.get("weak_thesis_profiles") or 0),
            "runtime_thesis_profiles": int(summary.get("runtime_thesis_profiles") or 0),
            "dry_run_thesis_profiles": int(summary.get("dry_run_thesis_profiles") or 0),
            "paper_candidate_allowed_count": int(summary.get("paper_candidate_allowed_count") or 0),
            "missing_market_count": _missing_count(summary, "MISSING_MARKET_ID"),
            "missing_orderbook_count": _missing_count(summary, "MISSING_FRESH_ORDERBOOK"),
            "missing_binding_count": _missing_count(summary, "MISSING_SIGNAL_MARKET_BINDING"),
            "missing_evidence_summary": [_json_safe(row) for row in summary.get("missing_evidence_summary", [])],
            "invalidation_rule_summary": [_json_safe(row) for row in summary.get("invalidation_rule_summary", [])],
            "risk_notes_summary": [_json_safe(row) for row in summary.get("risk_notes_summary", [])],
            "latest_thesis_profiles": [_json_safe(thesis_profile_from_row(row).to_api_dict()) for row in summary.get("latest_thesis_profiles", [])],
            "paper_ready": False,
            "orders_created": int(latest_run.get("orders_created") or 0) if latest_run else 0,
            "order_intents_created": int(latest_run.get("order_intents_created") or 0) if latest_run else 0,
            "fills_created": int(latest_run.get("fills_created") or 0) if latest_run else 0,
            "positions_created": int(latest_run.get("positions_created") or 0) if latest_run else 0,
            "live_actions_created": int(latest_run.get("live_actions_created") or 0) if latest_run else 0,
            "remaining_blockers": [],
            "analysis_status": "OK",
            "last_updated": datetime.now(UTC).isoformat(),
        }


def _profile_from_coordinator(row: dict[str, Any], *, run_id: str) -> ThesisProfile:
    metadata = row.get("metadata_json") or {}
    source_brain_output_ids = [str(item) for item in row.get("source_brain_output_ids") or metadata.get("source_brain_output_ids") or [] if item]
    source_signal_ids = [str(item) for item in metadata.get("source_signal_ids") or row.get("dependency_signal_ids") or [] if item]
    blockers = {str(item).upper() for item in row.get("risk_flags_json") or [] if item}
    blockers.update(str(item).upper() for item in metadata.get("missing_requirements") or [] if item)
    market_id = row.get("market_id")
    orderbook_snapshot_id = row.get("orderbook_snapshot_id")
    has_binding = bool(row.get("has_signal_market_binding"))
    final_state = str(row.get("final_state") or "").upper()
    missing: list[str] = []
    if not market_id:
        missing.append("MISSING_MARKET_ID")
    if market_id and orderbook_snapshot_id is None:
        missing.append("MISSING_FRESH_ORDERBOOK")
    if source_signal_ids and not has_binding:
        missing.append("MISSING_SIGNAL_MARKET_BINDING")
    if not source_signal_ids and not source_brain_output_ids:
        missing.append("MISSING_SOURCE_TRACE")
    if blockers & {"WEAK_LINEAGE_OR_PROVENANCE", "MISSING_LINEAGE", "UNKNOWN_PROVENANCE"}:
        missing.append("WEAK_LINEAGE_OR_PROVENANCE")
    missing.extend(item for item in sorted(blockers) if item.startswith("MISSING_") and item not in missing)

    if final_state == "NO_TRADE":
        status = "BLOCKED"
        thesis_type = "BLOCKED_NO_TRADE_THESIS"
    elif final_state == "PAPER_CANDIDATE_BLOCKED":
        status = "BLOCKED"
        thesis_type = "HOLD_FOR_MORE_EVIDENCE"
    elif "WEAK_SIGNAL" in blockers:
        status = "WEAK"
        thesis_type = "WEAK_SIGNAL_THESIS"
    elif missing:
        status = "INCOMPLETE"
        thesis_type = "HOLD_FOR_MORE_EVIDENCE"
    else:
        status = "COMPLETE"
        thesis_type = "RUNTIME_COORDINATOR_THESIS"

    if status == "COMPLETE" and (not market_id or missing):
        status = "INCOMPLETE"
        thesis_type = "HOLD_FOR_MORE_EVIDENCE"

    confidence = _clamp(row.get("confidence"))
    why_now = _why_now(status, market_id=market_id)
    expected_move = _expected_move(row.get("side"), metadata)
    risk_notes = [
        "NO_RISK_CORE",
        "NO_EXIT_FOUNDATION",
        "paper_candidate_allowed=false_until_paper_eligibility_gate",
    ]
    if "MISSING_FRESH_ORDERBOOK" in missing:
        risk_notes.append("fresh_orderbook_required_before_paper")
    if "MISSING_SIGNAL_MARKET_BINDING" in missing:
        risk_notes.append("signal_market_binding_required_before_paper")
    invalidation_rules = [
        "invalidate_if_orderbook_becomes_stale",
        "invalidate_if_signal_market_binding_is_missing",
        "invalidate_if_runtime_coordinator_decision_is_superseded",
    ]
    if final_state == "NO_TRADE":
        invalidation_rules.append("blocked_by_no_trade_coordinator_state")

    return ThesisProfile(
        thesis_id=f"thesis_{row['coordinator_decision_id']}",
        market_id=str(market_id) if market_id else None,
        side=expected_move if expected_move in {"YES", "NO"} else None,
        status=status,
        thesis_type=thesis_type,
        why_now=why_now,
        expected_move=expected_move,
        confidence=confidence,
        evidence={
            "runtime_thesis_run_id": run_id,
            "coordinator_decision_id": row.get("coordinator_decision_id"),
            "final_state": row.get("final_state"),
            "primary_reason": row.get("primary_reason"),
            "risk_flags": row.get("risk_flags_json") or [],
            "source_brain_output_ids": source_brain_output_ids,
            "source_signal_ids": source_signal_ids,
            "orderbook_snapshot_id": orderbook_snapshot_id,
            "has_signal_market_binding": has_binding,
        },
        missing_evidence=sorted(set(missing)),
        invalidation_rules=invalidation_rules,
        risk_notes=sorted(set(risk_notes)),
        source_coordinator_decision_id=str(row.get("coordinator_decision_id")),
        source_brain_output_ids=source_brain_output_ids,
        source_signal_ids=source_signal_ids,
        orderbook_snapshot_id=int(orderbook_snapshot_id) if orderbook_snapshot_id is not None else None,
        generated_by="runtime",
        producer_name="thesis_profile_builder",
        is_runtime_generated=True,
        is_dry_run_generated=False,
        paper_candidate_allowed=False,
        risk_required=True,
        exit_required=True,
    )


def _why_now(status: str, *, market_id: Any) -> str:
    if status == "COMPLETE":
        return "Runtime coordinator produced a traceable market thesis with fresh orderbook evidence; Risk and Exit remain required."
    if market_id:
        return "Runtime coordinator observed market-linked evidence, but missing requirements prevent Paper eligibility."
    return "Runtime coordinator produced non-executing evidence, but missing market binding prevents a complete Paper thesis."


def _expected_move(side: Any, metadata: dict[str, Any]) -> str:
    explicit = str(side or metadata.get("side") or metadata.get("expected_move") or "").upper()
    if explicit in {"YES", "NO", "YES_UP", "NO_UP"}:
        return explicit
    return "UNKNOWN"


def _clamp(value: Any) -> float:
    try:
        numeric = float(value or 0.0)
    except (TypeError, ValueError):
        numeric = 0.0
    return round(max(0.0, min(1.0, numeric)), 6)


def _missing_count(summary: dict[str, Any], field: str) -> int:
    for row in summary.get("missing_evidence_summary", []):
        if str(row.get("field")) == field:
            return int(row.get("count") or 0)
    return 0


def _safety_counts(factory: DatabaseConnectionFactory) -> dict[str, int]:
    return {
        "orders": _count_table(factory, "paper_orders") + _count_table(factory, "shadow_orders") + _count_table(factory, "live_orders"),
        "order_intents": _count_table(factory, "order_intents"),
        "fills": _count_table(factory, "paper_fills") + _count_table(factory, "fills_v2"),
        "positions": _count_table(factory, "positions"),
        "live_actions": _count_table(factory, "live_orders"),
    }


def _count_table(factory: DatabaseConnectionFactory, table: str) -> int:
    if not factory.enabled:
        return 0
    try:
        with factory.connect() as conn:
            if not _table_exists(conn, table):
                return 0
            return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
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
    if value.__class__.__name__ == "Decimal":
        return float(value)
    return value


def _empty_summary() -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": "OK",
        "latest_run": None,
        "total_thesis_profiles": 0,
        "complete_thesis_profiles": 0,
        "incomplete_thesis_profiles": 0,
        "blocked_thesis_profiles": 0,
        "weak_thesis_profiles": 0,
        "runtime_thesis_profiles": 0,
        "dry_run_thesis_profiles": 0,
        "paper_candidate_allowed_count": 0,
        "missing_market_count": 0,
        "missing_orderbook_count": 0,
        "missing_binding_count": 0,
        "missing_evidence_summary": [],
        "invalidation_rule_summary": [],
        "risk_notes_summary": [],
        "latest_thesis_profiles": [],
        "paper_ready": False,
        "orders_created": 0,
        "order_intents_created": 0,
        "fills_created": 0,
        "positions_created": 0,
        "live_actions_created": 0,
        "remaining_blockers": [],
        "analysis_status": "OK",
        "last_updated": datetime.now(UTC).isoformat(),
    }

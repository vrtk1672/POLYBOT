from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.brain_outputs import BrainOutput, BrainOutputDependency
from app.repositories.mesh_dry_run_repository import MeshDryRunRepository
from app.runtime.health_truth import HealthTruthService
from app.services.brain_coordinator import BrainCoordinatorService
from app.services.brain_outputs import BrainOutputService


class MeshDryRunService:
    """Controlled non-executing intelligence flow producer."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: MeshDryRunRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or MeshDryRunRepository()

    def run_first_intelligence_dry_run(
        self,
        *,
        limit: int = 20,
        market_id: str | None = None,
        dry_run_only: bool = True,
    ) -> dict[str, Any]:
        dry_run_id = f"dry_{uuid4().hex}"
        started_at = datetime.now(UTC)
        mode = self._current_mode()
        if not self._factory.enabled:
            return _empty_run(dry_run_id, mode=mode, started_at=started_at)

        safety_before = self._order_counts()
        signal_market_links_created = 0
        event_entities_created = 0
        impact_links_created = 0
        brain_outputs_created = 0
        coordinator_decisions_created = 0
        no_trade_explanations_created = 0
        sample_results: list[dict[str, Any]] = []

        with self._factory.connect() as conn, conn.transaction():
            signals = self._repository.list_candidate_signals(conn, limit=limit, market_id=market_id)
            signal_ids = [str(signal["signal_id"]) for signal in signals]
            entities = self._repository.list_signal_entities(conn, signal_ids)
            entity_rows_by_signal: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for entity in entities:
                entity_rows_by_signal[str(entity["signal_id"])].append(entity)

            signals_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
            impact_ids_by_market: dict[str, list[str]] = defaultdict(list)
            signal_status_by_market: dict[str, dict[str, str]] = defaultdict(dict)

            for signal in signals:
                explicit_market_id = signal.get("market_id")
                if not explicit_market_id:
                    continue
                explicit_market_id = str(explicit_market_id)
                signals_by_market[explicit_market_id].append(signal)
                signal_status_by_market[explicit_market_id][str(signal.get("neuron") or "unknown")] = str(signal.get("status") or "MISSING")
                _, created = self._repository.ensure_signal_market_link(
                    conn,
                    signal_id=str(signal["signal_id"]),
                    market_id=explicit_market_id,
                    reason="Signal carried an explicit market_id; linked by safe mesh dry run.",
                )
                signal_market_links_created += int(created)

                for entity in entity_rows_by_signal[str(signal["signal_id"])]:
                    _, entity_created = self._repository.ensure_event_entity(
                        conn,
                        signal_id=str(signal["signal_id"]),
                        entity_type=str(entity.get("entity_type") or "unknown"),
                        entity_name=str(entity.get("entity_name") or "unknown"),
                        entity_id=str(entity.get("entity_id") or f"entity_{uuid4().hex}"),
                        confidence=_float_or_none(entity.get("confidence")),
                    )
                    event_entities_created += int(entity_created)

                impact = self._impact_from_signal(signal)
                impact_row, impact_created = self._repository.ensure_impact_link(
                    conn,
                    signal_id=str(signal["signal_id"]),
                    market_id=explicit_market_id,
                    impact_direction=impact["impact_direction"],
                    cortex_action_hint=impact["cortex_action_hint"],
                    reasoning_summary=impact["reason"],
                    confidence=_float_or_none(signal.get("confidence")),
                    urgency=impact["urgency"],
                )
                impact_ids_by_market[explicit_market_id].append(str(impact_row["impact_link_id"]))
                impact_links_created += int(impact_created)

        for current_market_id, market_signals in signals_by_market.items():
            source_signal_ids = [str(signal["signal_id"]) for signal in market_signals]
            risk_flags = _risk_flags(market_signals)
            reasons = _reasons(market_signals, risk_flags)
            outputs, created_count, no_trade_count = self._create_market_brain_outputs(
                market_id=current_market_id,
                source_signal_ids=source_signal_ids,
                risk_flags=risk_flags,
                reasons=reasons,
            )
            brain_outputs_created += created_count
            no_trade_explanations_created += no_trade_count
            output_ids = [str(output["brain_output_id"]) for output in outputs]
            decision = self._find_existing_coordinator_decision(output_ids, market_id=current_market_id)
            if not decision:
                decision = BrainCoordinatorService(connection_factory=self._factory).coordinate_outputs(
                    output_ids,
                    market_id=current_market_id,
                )
                coordinator_decisions_created += 1
            sample_results.append(
                {
                    "market_id": current_market_id,
                    "signals": signal_status_by_market[current_market_id],
                    "signal_count": len(market_signals),
                    "impact_link_count": len(impact_ids_by_market[current_market_id]),
                    "brain_output_count": len(outputs),
                    "brain_outputs": [
                        {
                            "brain": output["brain"],
                            "recommendation": output["recommendation"],
                            "reason": output.get("reasoning_summary"),
                        }
                        for output in outputs
                    ],
                    "coordinator_decision_id": decision["coordinator_decision_id"],
                    "coordinator_final_state": decision["final_state"],
                    "reason": decision["primary_reason"],
                    "no_trade_explanation": _no_trade_explanation(outputs, decision),
                    "execution_allowed": decision["execution_allowed"],
                }
            )

        safety_after = self._order_counts()
        status = "OK" if signals_by_market else "DEGRADED"
        if safety_after != safety_before:
            status = "ERROR"
        completed_at = datetime.now(UTC)
        summary = {
            "dry_run_id": dry_run_id,
            "markets_processed": len(signals_by_market),
            "signals_processed": len(signals),
            "signal_market_links_created": signal_market_links_created,
            "event_entities_created": event_entities_created,
            "impact_links_created": impact_links_created,
            "brain_outputs_created": brain_outputs_created,
            "coordinator_decisions_created": coordinator_decisions_created,
            "no_trade_explanations_created": no_trade_explanations_created,
            "sample_results": sample_results,
            "dry_run_only": bool(dry_run_only),
        }
        with self._factory.connect() as conn, conn.transaction():
            self._repository.insert_dry_run(
                conn,
                dry_run_id=dry_run_id,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                mode=mode,
                summary=summary,
                safety_before=safety_before,
                safety_after=safety_after,
            )
            for item in sample_results:
                self._repository.insert_dry_run_item(conn, dry_run_id=dry_run_id, item=item)

        return _json_safe(
            {
                "status": status,
                "mock_data": False,
                "dry_run_id": dry_run_id,
                "created_at": completed_at.isoformat(),
                "mode": mode,
                "execution_allowed": False,
                "orders_created": _orders_created(safety_before, safety_after),
                **summary,
                "safety": {
                    **safety_after,
                    "execution_allowed_count": self._execution_allowed_count(),
                },
            }
        )

    def get_latest_dry_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "mesh_dry_runs"):
                return []
            return [_dry_run_row(row) for row in self._repository.list_recent_dry_runs(conn, limit=limit)]

    def get_dry_run(self, dry_run_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "mesh_dry_runs"):
                return None
            row = self._repository.get_dry_run(conn, dry_run_id)
            if not row:
                return None
            items = self._repository.list_dry_run_items(conn, dry_run_id)
        return {**_dry_run_row(row), "items": [_dry_run_item(row) for row in items]}

    def get_dry_run_summary(self, *, limit: int = 10) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            if not _table_exists(conn, "mesh_dry_runs"):
                return _empty_summary()
            summary = self._repository.summary(conn, limit=limit)
        safety = self._order_counts()
        safety["execution_allowed_count"] = self._execution_allowed_count()
        latest = _dry_run_row(summary["latest_dry_run"]) if summary["latest_dry_run"] else None
        recent = [_dry_run_row(row) for row in summary["recent_dry_runs"]]
        return _json_safe(
            {
                "status": "OK" if latest else "EMPTY",
                "mock_data": False,
                "updated_at": datetime.now(UTC).isoformat(),
                "latest_dry_run": latest,
                "recent_dry_runs": recent,
                "flow_counts": summary["flow_counts"],
                "safety": safety,
            }
        )

    def _create_market_brain_outputs(
        self,
        *,
        market_id: str,
        source_signal_ids: list[str],
        risk_flags: list[str],
        reasons: list[str],
    ) -> tuple[list[dict[str, Any]], int, int]:
        created_count = 0
        no_trade_count = 0
        outputs: list[dict[str, Any]] = []
        specs = [
            ("context", "CAUTION", "WATCH", 0.65, ["DATA_DEGRADED"] if risk_flags else [], "Context brain dry run: " + "; ".join(reasons)),
            ("risk", "RISK_WARNING", "CAUTION", 0.75, risk_flags or ["INSUFFICIENT_DATA"], "Risk brain dry run: " + "; ".join(reasons)),
            ("no_trade", "NO_TRADE_HINT", "NO_TRADE_HINT", 0.8, sorted(set(risk_flags + ["NO_TRADE"])), "No-Trade dry run: " + "; ".join(reasons)),
            ("opportunity", "WATCH", "INSUFFICIENT_DATA", 0.45, ["INSUFFICIENT_DATA"], "Opportunity dry run: insufficient verified edge for candidate action."),
        ]
        with self._factory.connect() as conn:
            existing_by_brain = {
                brain: self._repository.find_dry_run_brain_output(
                    conn,
                    market_id=market_id,
                    brain=brain,
                    source_signal_ids=source_signal_ids,
                )
                for brain, *_ in specs
            }
        for brain, output_type, recommendation, confidence, flags, reason in specs:
            existing = existing_by_brain.get(brain)
            if existing:
                outputs.append(_brain_row_to_api(existing))
                continue
            output = BrainOutput(
                brain=brain,
                output_type=output_type,
                market_id=market_id,
                recommendation=recommendation,
                confidence=confidence,
                urgency=0.35 if brain != "risk" else 0.55,
                risk_flags=flags,
                reasoning_summary=reason,
                status="ACTIVE",
                correlation_id=f"mesh_dry_run:{market_id}",
                generated_by="mesh_dry_run",
                metadata={
                    "non_executing": True,
                    "dry_run_phase": "v2_part4b",
                    "source_signal_ids": source_signal_ids,
                    "source_signal_key": ",".join(sorted(source_signal_ids)),
                },
            )
            dependencies = [
                BrainOutputDependency(
                    dependency_type="signal",
                    dependency_id=signal_id,
                    dependency_role="dry_run_evidence",
                    confidence=1.0,
                )
                for signal_id in source_signal_ids
            ]
            created = BrainOutputService(connection_factory=self._factory).create_brain_output_with_dependencies(
                output,
                dependencies=dependencies,
            )
            outputs.append(created)
            created_count += 1
            no_trade_count += int(brain == "no_trade")
        return outputs, created_count, no_trade_count

    def _impact_from_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        status = str(signal.get("status") or "").upper()
        neuron = str(signal.get("neuron") or "").lower()
        event_type = str(signal.get("event_type") or "").lower()
        if status in {"DEGRADED", "ERROR", "MISSING", "STALE"} or neuron in {"rules", "resolution"}:
            return {
                "impact_direction": "adverse" if status in {"DEGRADED", "ERROR", "MISSING", "STALE"} else "unknown",
                "cortex_action_hint": "NO_TRADE_REVIEW" if neuron in {"rules", "resolution"} else "REVIEW",
                "urgency": 0.5 if status in {"DEGRADED", "ERROR", "MISSING", "STALE"} else 0.3,
                "reason": f"Dry run linked {neuron or 'unknown'} signal with status {status or 'UNKNOWN'} and event_type {event_type or 'unknown'} for non-executing review.",
            }
        if status == "PARTIAL":
            return {
                "impact_direction": "unknown",
                "cortex_action_hint": "REVIEW",
                "urgency": 0.35,
                "reason": "Dry run linked partial signal for non-executing review.",
            }
        return {
            "impact_direction": "neutral",
            "cortex_action_hint": "WATCH",
            "urgency": 0.2,
            "reason": "Dry run linked active signal for watch-only mesh flow.",
        }

    def _current_mode(self) -> str | None:
        try:
            return str(HealthTruthService(connection_factory=self._factory).get_health_truth().get("current_mode") or "")
        except Exception:
            return None

    def _order_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {"paper_orders": 0, "shadow_orders": 0, "live_orders": 0}
        with self._factory.connect() as conn:
            return {
                "paper_orders": _table_count(conn, "paper_orders"),
                "shadow_orders": _table_count(conn, "shadow_orders"),
                "live_orders": _table_count(conn, "live_orders"),
            }

    def _execution_allowed_count(self) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            return _execution_allowed_count(conn)

    def _find_existing_coordinator_decision(self, output_ids: list[str], *, market_id: str) -> dict[str, Any] | None:
        if not output_ids or not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "coordinator_decisions"):
                return None
            row = conn.execute(
                """
                SELECT cd.*
                FROM coordinator_decisions cd
                JOIN coordinator_decision_inputs cdi
                    ON cdi.coordinator_decision_id = cd.coordinator_decision_id
                WHERE cd.market_id = %s
                GROUP BY cd.id
                HAVING array_agg(DISTINCT cdi.brain_output_id ORDER BY cdi.brain_output_id) = %s
                ORDER BY cd.created_at DESC, cd.id DESC
                LIMIT 1
                """,
                (market_id, sorted(output_ids)),
            ).fetchone()
        return _coordinator_row_to_api(dict(row)) if row else None


def _risk_flags(signals: list[dict[str, Any]]) -> list[str]:
    flags: set[str] = set()
    neurons = {str(signal.get("neuron") or "").lower() for signal in signals}
    statuses = {str(signal.get("status") or "").upper() for signal in signals}
    if neurons.intersection({"rules", "resolution"}):
        flags.add("RESOLUTION_AMBIGUOUS")
    if statuses.intersection({"DEGRADED", "ERROR", "MISSING", "STALE"}):
        flags.add("RISK_HIGH")
        flags.add("DATA_DEGRADED")
    if "orderbook" not in neurons:
        flags.add("INSUFFICIENT_ORDERBOOK_EVIDENCE")
    if not flags:
        flags.add("INSUFFICIENT_DATA")
    return sorted(flags)


def _reasons(signals: list[dict[str, Any]], risk_flags: list[str]) -> list[str]:
    reasons = []
    if "RESOLUTION_AMBIGUOUS" in risk_flags:
        reasons.append("rules/resolution signal requires review")
    if "INSUFFICIENT_ORDERBOOK_EVIDENCE" in risk_flags:
        reasons.append("no explicit orderbook signal in this market group")
    if "DATA_DEGRADED" in risk_flags:
        reasons.append("one or more source signals are degraded, stale, missing, or errored")
    if "INSUFFICIENT_DATA" in risk_flags:
        reasons.append("insufficient verified edge for a candidate action")
    if not reasons:
        reasons.append(f"{len(signals)} signals were linked for watch-only review")
    return reasons


def _no_trade_explanation(outputs: list[dict[str, Any]], decision: dict[str, Any]) -> str:
    for output in outputs:
        if output.get("brain") == "no_trade":
            return str(output.get("reasoning_summary") or decision.get("primary_reason") or "No-Trade dry run explanation.")
    return str(decision.get("primary_reason") or "Coordinator preserved a non-executing dry run state.")


def _table_count(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"] or 0)


def _execution_allowed_count(conn: Any) -> int:
    if not _table_exists(conn, "coordinator_decisions"):
        return 0
    row = conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed IS TRUE").fetchone()
    return int(row["count"] or 0)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _orders_created(before: dict[str, int], after: dict[str, int]) -> int:
    return sum(max(0, after.get(key, 0) - before.get(key, 0)) for key in ("paper_orders", "shadow_orders", "live_orders"))


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _brain_row_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return _json_safe(
        {
            "brain_output_id": row["brain_output_id"],
            "brain": row["brain"],
            "output_type": row["output_type"],
            "market_id": row.get("market_id"),
            "position_id": row.get("position_id"),
            "recommendation": row["recommendation"],
            "confidence": row.get("confidence"),
            "urgency": row.get("urgency"),
            "risk_flags": row.get("risk_flags_json") or [],
            "reasoning_summary": row.get("reasoning_summary"),
            "status": row["status"],
            "correlation_id": row.get("correlation_id"),
            "generated_by": row.get("generated_by"),
            "metadata": row.get("metadata_json") or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
    )


def _coordinator_row_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return _json_safe(
        {
            "coordinator_decision_id": row["coordinator_decision_id"],
            "market_id": row.get("market_id"),
            "position_id": row.get("position_id"),
            "final_state": row["final_state"],
            "primary_reason": row["primary_reason"],
            "confidence": row.get("confidence"),
            "urgency": row.get("urgency"),
            "conflicts_detected": row.get("conflicts_detected", False),
            "governor_required": row.get("governor_required", True),
            "execution_allowed": row.get("execution_allowed", False),
            "approved_actions": row.get("approved_actions_json") or [],
            "blocked_actions": row.get("blocked_actions_json") or [],
            "required_reviews": row.get("required_reviews_json") or [],
            "risk_flags": row.get("risk_flags_json") or [],
            "status": row.get("status"),
            "metadata": row.get("metadata_json") or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
    )


def _dry_run_row(row: dict[str, Any]) -> dict[str, Any]:
    return _json_safe(
        {
            "dry_run_id": row["dry_run_id"],
            "status": row["status"],
            "started_at": row.get("started_at"),
            "completed_at": row.get("completed_at"),
            "mode": row.get("mode"),
            "markets_processed": row.get("markets_processed", 0),
            "signals_processed": row.get("signals_processed", 0),
            "signal_market_links_created": row.get("signal_market_links_created", 0),
            "impact_links_created": row.get("impact_links_created", 0),
            "brain_outputs_created": row.get("brain_outputs_created", 0),
            "coordinator_decisions_created": row.get("coordinator_decisions_created", 0),
            "no_trade_explanations_created": row.get("no_trade_explanations_created", 0),
            "execution_allowed": row.get("execution_allowed", False),
            "summary": row.get("summary_json") or {},
            "created_at": row.get("created_at"),
        }
    )


def _dry_run_item(row: dict[str, Any]) -> dict[str, Any]:
    return _json_safe(
        {
            "dry_run_id": row["dry_run_id"],
            "market_id": row.get("market_id"),
            "position_id": row.get("position_id"),
            "final_state": row.get("final_state"),
            "primary_reason": row.get("primary_reason"),
            "signal_count": row.get("signal_count", 0),
            "impact_link_count": row.get("impact_link_count", 0),
            "brain_output_count": row.get("brain_output_count", 0),
            "coordinator_decision_id": row.get("coordinator_decision_id"),
            "no_trade_explanation": row.get("no_trade_explanation"),
            "details": row.get("details_json") or {},
            "created_at": row.get("created_at"),
        }
    )


def _empty_run(dry_run_id: str, *, mode: str | None, started_at: datetime) -> dict[str, Any]:
    return {
        "status": "DEGRADED",
        "mock_data": False,
        "dry_run_id": dry_run_id,
        "created_at": started_at.isoformat(),
        "mode": mode,
        "execution_allowed": False,
        "orders_created": 0,
        "markets_processed": 0,
        "signals_processed": 0,
        "signal_market_links_created": 0,
        "impact_links_created": 0,
        "brain_outputs_created": 0,
        "coordinator_decisions_created": 0,
        "no_trade_explanations_created": 0,
        "sample_results": [],
        "safety": {"paper_orders": 0, "shadow_orders": 0, "live_orders": 0, "execution_allowed_count": 0},
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "EMPTY",
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "latest_dry_run": None,
        "recent_dry_runs": [],
        "flow_counts": {
            "signals": 0,
            "impact_links": 0,
            "brain_outputs": 0,
            "coordinator_decisions": 0,
            "no_trade_explanations": 0,
        },
        "safety": {"paper_orders": 0, "shadow_orders": 0, "live_orders": 0, "execution_allowed_count": 0},
    }


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

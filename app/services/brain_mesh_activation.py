from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.logging import get_logger
from app.neural_mesh.position_thesis import PositionThesisProfile
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.position_thesis import PositionThesisService
from app.services.runtime_brain_adapter import RuntimeBrainAdapterService
from app.services.runtime_coordinator import RuntimeCoordinatorDecisionService
from app.services.runtime_producer_evidence import RuntimeProducerEvidenceService
from app.services.system_power import SystemPowerService
from app.services.thesis_profiles import ThesisProfileService

logger = get_logger(__name__)


class BrainMeshActivationService:
    """Autonomous, non-executing Brain Mesh cycle for SYSTEM ON runtime."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        evidence_service: RuntimeProducerEvidenceService | None = None,
        brain_service: RuntimeBrainAdapterService | None = None,
        coordinator_service: RuntimeCoordinatorDecisionService | None = None,
        thesis_service: ThesisProfileService | None = None,
        position_thesis_service: PositionThesisService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._evidence = evidence_service or RuntimeProducerEvidenceService(connection_factory=self._factory)
        self._brain = brain_service or RuntimeBrainAdapterService(connection_factory=self._factory)
        self._coordinator = coordinator_service or RuntimeCoordinatorDecisionService(connection_factory=self._factory)
        self._thesis = thesis_service or ThesisProfileService(connection_factory=self._factory)
        self._position_thesis = position_thesis_service or PositionThesisService(connection_factory=self._factory)

    def run_activation(
        self,
        *,
        cycle_id: str | None = None,
        phase1_cycle_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"brain_mesh_activation_{uuid4().hex}"
        power_state = self._system_power.get_power_state()
        system_power = str(power_state.get("power") or "OFF").upper()
        if system_power != "ON" or not bool(power_state.get("runtime_work_allowed")):
            return self._blocked_payload(
                run_id=run_id,
                cycle_id=cycle_id,
                phase1_cycle_id=phase1_cycle_id,
                system_power=system_power,
                started_at=started_at,
                blocked_reason="SYSTEM_POWER_OFF",
            )
        if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
            return self._blocked_payload(
                run_id=run_id,
                cycle_id=cycle_id,
                phase1_cycle_id=phase1_cycle_id,
                system_power=system_power,
                started_at=started_at,
                blocked_reason="STATE_GOVERNOR_BLOCKED_INTELLIGENCE",
            )
        existing = self._existing_for_cycle(cycle_id)
        if existing:
            payload = _json_safe(dict(existing))
            payload["mock_data"] = False
            payload["idempotent"] = True
            return payload

        safety_before = self._safety_counts()
        errors: list[str] = []
        evidence_result: dict[str, Any] = {}
        brain_result: dict[str, Any] = {}
        coordinator_result: dict[str, Any] = {}
        thesis_result: dict[str, Any] = {}
        position_result: dict[str, Any] = {"created": 0, "updated": 0, "checked": 0, "skipped": 0}

        try:
            evidence_result = self._evidence.run_runtime_evidence_loop(limit=limit, dry_run=False, apply_evaluations=True)
        except Exception as exc:
            errors.append(f"runtime_producer_evidence:{type(exc).__name__}:{exc}")
            logger.exception("brain_mesh_activation_evidence_failed cycle_id=%s", cycle_id)

        try:
            brain_result = self._brain.run_runtime_brain(limit=limit, min_quality_score=0.0, write_outputs=True)
        except Exception as exc:
            errors.append(f"runtime_brain_adapter:{type(exc).__name__}:{exc}")
            logger.exception("brain_mesh_activation_brain_failed cycle_id=%s", cycle_id)

        try:
            coordinator_result = self._coordinator.run_runtime_coordinator(limit=limit, min_brain_confidence=0.0, write_decisions=True)
        except Exception as exc:
            errors.append(f"runtime_coordinator:{type(exc).__name__}:{exc}")
            logger.exception("brain_mesh_activation_coordinator_failed cycle_id=%s", cycle_id)

        try:
            thesis_result = self._thesis.build_profiles(limit=limit, include_incomplete=True, include_blocked=True, write_profiles=True)
        except Exception as exc:
            errors.append(f"thesis_profiles:{type(exc).__name__}:{exc}")
            logger.exception("brain_mesh_activation_thesis_failed cycle_id=%s", cycle_id)

        try:
            position_result = self._build_position_thesis_profiles(limit=limit, activation_run_id=run_id)
        except Exception as exc:
            errors.append(f"position_thesis_profiles:{type(exc).__name__}:{exc}")
            logger.exception("brain_mesh_activation_position_thesis_failed cycle_id=%s", cycle_id)

        safety_after = self._safety_counts()
        finished_at = datetime.now(UTC)
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "phase1_cycle_id": phase1_cycle_id,
            "system_power": system_power,
            "status": "DEGRADED" if errors else "OK",
            "evidence_created": int(evidence_result.get("signals_created") or 0),
            "brain_outputs_created": int(brain_result.get("brain_outputs_created") or 0),
            "coordinator_decisions_created": int(coordinator_result.get("coordinator_decisions_created") or 0),
            "thesis_profiles_created": int(thesis_result.get("thesis_profiles_created") or 0),
            "thesis_profiles_updated": int(thesis_result.get("thesis_profiles_updated") or 0),
            "position_thesis_profiles_created": int(position_result.get("created") or 0),
            "position_thesis_profiles_updated": int(position_result.get("updated") or 0),
            "blocked_reason": None,
            "error_message": "; ".join(errors) if errors else None,
            "orders_created": max(0, safety_after["orders"] - safety_before["orders"]),
            "order_intents_created": max(0, safety_after["order_intents"] - safety_before["order_intents"]),
            "fills_created": max(0, safety_after["fills"] - safety_before["fills"]),
            "positions_created": max(0, safety_after["positions"] - safety_before["positions"]),
            "live_actions_created": max(0, safety_after["live_actions"] - safety_before["live_actions"]),
            "started_at": started_at,
            "finished_at": finished_at,
            "metadata": {
                "evidence_run_id": evidence_result.get("run_id"),
                "brain_run_id": brain_result.get("run_id"),
                "coordinator_run_id": coordinator_result.get("run_id"),
                "thesis_run_id": thesis_result.get("run_id"),
                "position_thesis_checked": position_result.get("checked", 0),
                "position_thesis_skipped": position_result.get("skipped", 0),
                "non_executing_activation": True,
            },
        }
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._insert_run(conn, payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        power = self._system_power.get_power_state()
        latest_run = self._latest_run()
        latest_counts = self._latest_output_timestamps()
        return {
            "mock_data": False,
            "status": "OK" if latest_run else "EMPTY",
            "brain_mesh_activation_allowed": bool(power.get("runtime_work_allowed")),
            "brain_mesh_activation_active": False,
            "manual_only_status": False,
            "last_brain_mesh_activation_at": latest_run.get("finished_at") if latest_run else None,
            "last_brain_mesh_activation_status": latest_run.get("status") if latest_run else None,
            "latest_run": latest_run,
            "last_evidence_created_count": int(latest_run.get("evidence_created") or 0) if latest_run else 0,
            "last_brain_outputs_created_count": int(latest_run.get("brain_outputs_created") or 0) if latest_run else 0,
            "last_coordinator_decisions_created_count": int(latest_run.get("coordinator_decisions_created") or 0) if latest_run else 0,
            "last_thesis_profiles_created_count": int(latest_run.get("thesis_profiles_created") or 0) if latest_run else 0,
            "last_position_thesis_profiles_created_count": int(latest_run.get("position_thesis_profiles_created") or 0) if latest_run else 0,
            "latest_brain_output_at": latest_counts.get("latest_brain_output_at"),
            "latest_coordinator_decision_at": latest_counts.get("latest_coordinator_decision_at"),
            "latest_thesis_profile_at": latest_counts.get("latest_thesis_profile_at"),
            "latest_position_thesis_profile_at": latest_counts.get("latest_position_thesis_profile_at"),
            "orders_created": int(latest_run.get("orders_created") or 0) if latest_run else 0,
            "order_intents_created": int(latest_run.get("order_intents_created") or 0) if latest_run else 0,
            "fills_created": int(latest_run.get("fills_created") or 0) if latest_run else 0,
            "positions_created": int(latest_run.get("positions_created") or 0) if latest_run else 0,
            "live_actions_created": int(latest_run.get("live_actions_created") or 0) if latest_run else 0,
            "paper_ready": False,
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _build_position_thesis_profiles(self, *, limit: int, activation_run_id: str) -> dict[str, int]:
        rows = self._position_thesis_candidates(limit=limit)
        created = updated = skipped = 0
        for row in rows:
            market_id = str(row.get("market_id") or "").strip()
            if not market_id:
                skipped += 1
                continue
            profile = _position_profile_from_coordinator(row, activation_run_id=activation_run_id)
            existing = self._position_thesis.get_thesis_by_id(profile.thesis_id)
            if existing:
                self._position_thesis.update_position_thesis_profile(profile.thesis_id, profile.model_dump())
                updated += 1
            else:
                self._position_thesis.create_position_thesis_profile(profile)
                created += 1
        return {"checked": len(rows), "created": created, "updated": updated, "skipped": skipped}

    def _position_thesis_candidates(self, *, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "coordinator_decisions") or not _table_exists(conn, "position_thesis_profiles"):
                return []
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT
                        cd.coordinator_decision_id,
                        cd.market_id,
                        cd.final_state,
                        cd.primary_reason,
                        cd.confidence,
                        cd.risk_flags_json,
                        cd.metadata_json,
                        array_remove(array_agg(DISTINCT cdi.brain_output_id), NULL) AS source_brain_output_ids,
                        array_remove(array_agg(DISTINCT dep.dependency_id) FILTER (WHERE dep.dependency_type = 'signal'), NULL) AS source_signal_ids
                    FROM coordinator_decisions cd
                    LEFT JOIN coordinator_decision_inputs cdi
                        ON cdi.coordinator_decision_id = cd.coordinator_decision_id
                    LEFT JOIN brain_output_dependencies dep
                        ON dep.brain_output_id = cdi.brain_output_id
                    WHERE cd.metadata_json->>'generated_by' = 'runtime'
                      AND cd.metadata_json->>'producer_name' = 'runtime_coordinator_adapter'
                      AND COALESCE(cd.metadata_json->>'is_runtime_generated', 'false') = 'true'
                      AND COALESCE(cd.metadata_json->>'is_dry_run_generated', 'false') = 'false'
                      AND cd.market_id IS NOT NULL
                    GROUP BY cd.id
                    ORDER BY cd.created_at DESC, cd.id DESC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            ]

    def _blocked_payload(
        self,
        *,
        run_id: str,
        cycle_id: str | None,
        phase1_cycle_id: str | None,
        system_power: str,
        started_at: datetime,
        blocked_reason: str,
    ) -> dict[str, Any]:
        return _json_safe(
            {
                "mock_data": False,
                "run_id": run_id,
                "cycle_id": cycle_id,
                "phase1_cycle_id": phase1_cycle_id,
                "system_power": system_power,
                "status": "BLOCKED",
                "blocked_reason": blocked_reason,
                "evidence_created": 0,
                "brain_outputs_created": 0,
                "coordinator_decisions_created": 0,
                "thesis_profiles_created": 0,
                "position_thesis_profiles_created": 0,
                "orders_created": 0,
                "order_intents_created": 0,
                "fills_created": 0,
                "positions_created": 0,
                "live_actions_created": 0,
                "started_at": started_at,
                "finished_at": datetime.now(UTC),
            }
        )

    def _insert_run(self, conn: Any, payload: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO brain_mesh_activation_runs (
                run_id, cycle_id, phase1_cycle_id, system_power, status,
                evidence_created, brain_outputs_created, coordinator_decisions_created,
                thesis_profiles_created, thesis_profiles_updated,
                position_thesis_profiles_created, position_thesis_profiles_updated,
                blocked_reason, error_message, orders_created, order_intents_created,
                fills_created, positions_created, live_actions_created, started_at,
                finished_at, metadata_json
            )
            VALUES (
                %(run_id)s, %(cycle_id)s, %(phase1_cycle_id)s, %(system_power)s, %(status)s,
                %(evidence_created)s, %(brain_outputs_created)s, %(coordinator_decisions_created)s,
                %(thesis_profiles_created)s, %(thesis_profiles_updated)s,
                %(position_thesis_profiles_created)s, %(position_thesis_profiles_updated)s,
                %(blocked_reason)s, %(error_message)s, %(orders_created)s, %(order_intents_created)s,
                %(fills_created)s, %(positions_created)s, %(live_actions_created)s, %(started_at)s,
                %(finished_at)s, %(metadata_json)s
            )
            ON CONFLICT (run_id) DO NOTHING
            """,
            {**payload, "metadata_json": Jsonb(payload.get("metadata") or {})},
        )

    def _existing_for_cycle(self, cycle_id: str | None) -> dict[str, Any] | None:
        if not cycle_id or not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "brain_mesh_activation_runs"):
                return None
            row = conn.execute(
                "SELECT * FROM brain_mesh_activation_runs WHERE cycle_id = %s ORDER BY id DESC LIMIT 1",
                (cycle_id,),
            ).fetchone()
            return dict(row) if row else None

    def _latest_run(self) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "brain_mesh_activation_runs"):
                return None
            row = conn.execute("SELECT * FROM brain_mesh_activation_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _latest_output_timestamps(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {}
        with self._factory.connect() as conn:
            return {
                "latest_brain_output_at": _max_timestamp(conn, "brain_outputs"),
                "latest_coordinator_decision_at": _max_timestamp(conn, "coordinator_decisions"),
                "latest_thesis_profile_at": _max_timestamp(conn, "thesis_profiles"),
                "latest_position_thesis_profile_at": _max_timestamp(conn, "position_thesis_profiles"),
            }

    def _safety_counts(self) -> dict[str, int]:
        return {
            "orders": _count_table(self._factory, "paper_orders") + _count_table(self._factory, "shadow_orders") + _count_table(self._factory, "live_orders") + _count_table(self._factory, "orders_v2"),
            "order_intents": _count_table(self._factory, "order_intents"),
            "fills": _count_table(self._factory, "paper_fills") + _count_table(self._factory, "fills_v2"),
            "positions": _count_table(self._factory, "positions") + _count_table(self._factory, "paper_positions") + _count_table(self._factory, "shadow_positions"),
            "live_actions": _count_table(self._factory, "live_orders"),
        }


def _position_profile_from_coordinator(row: dict[str, Any], *, activation_run_id: str) -> PositionThesisProfile:
    coordinator_id = str(row["coordinator_decision_id"])
    market_id = str(row["market_id"])
    metadata = row.get("metadata_json") or {}
    risk_flags = [str(item).upper() for item in row.get("risk_flags_json") or [] if item]
    source_signal_ids = [str(item) for item in row.get("source_signal_ids") or metadata.get("source_signal_ids") or [] if item]
    side = str(metadata.get("side") or metadata.get("expected_move") or "UNKNOWN").upper()
    if side not in {"YES", "NO"}:
        side = "UNKNOWN"
    reason = str(row.get("primary_reason") or "Runtime coordinator produced a non-executing observation.")
    return PositionThesisProfile(
        thesis_id=f"position_thesis_{coordinator_id}",
        position_id=f"brain_mesh_candidate_{coordinator_id}",
        market_id=market_id,
        side=side,
        entry_thesis=f"Runtime coordinator observation for market {market_id}. {reason}",
        profit_drivers=["Additional verified evidence would be required before future paper consideration."],
        invalidation_drivers=["Coordinator decision superseded", "Market binding lost", "Orderbook stale"],
        watch_entities=[market_id],
        danger_signals=risk_flags or ["Missing downstream evidence"],
        take_profit_rules=[],
        partial_exit_rules=[],
        emergency_exit_rules=["Manual review required before any future action"],
        status="NEEDS_REVIEW",
        paper_ready=False,
        live_ready=False,
        coordinator_decision_id=coordinator_id,
        brain_output_id=(row.get("source_brain_output_ids") or [None])[0],
        source_signal_ids=source_signal_ids,
        risk_flags=risk_flags,
        created_by="brain_mesh_activation",
        metadata={
            "generated_by": "runtime",
            "producer_name": "brain_mesh_activation",
            "activation_run_id": activation_run_id,
            "source_layer": "runtime_coordinator",
            "non_executing_activation": True,
            "paper_ready": False,
            "execution_allowed": False,
        },
    )


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


def _max_timestamp(conn: Any, table: str) -> str | None:
    if not _table_exists(conn, table):
        return None
    row = conn.execute(f"SELECT MAX(created_at) AS latest_at FROM {table}").fetchone()
    value = row["latest_at"] if row else None
    return value.isoformat() if hasattr(value, "isoformat") else value


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

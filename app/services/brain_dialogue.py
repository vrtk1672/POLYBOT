from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.system_power import SystemPowerService


STALE_AFTER = timedelta(minutes=20)


class BrainDialogueService:
    """Materialize factual component dialogue from runtime source records.

    This service is deliberately observational. It only writes dialogue rows
    that cite an existing source record, and dashboard reads are read-only.
    """

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)

    def materialize_recent(self, *, limit_per_source: int = 25) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DB_UNAVAILABLE", "events_created": 0, "normal_dialogue_blocked": True}
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        runtime_allowed = bool(power.get("runtime_work_allowed"))
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "brain_dialogue_events"):
                return {"mock_data": False, "status": "MISSING_DIALOGUE_TABLE", "events_created": 0}
            created = self._materialize_system_power(conn, limit=limit_per_source)
            if system_power != "ON" or not runtime_allowed:
                return {
                    "mock_data": False,
                    "status": "SYSTEM_POWER_OFF",
                    "system_power": system_power,
                    "events_created": created,
                    "normal_dialogue_blocked": True,
                }
            for materializer in (
                self._materialize_market_service,
                self._materialize_data_foundation,
                self._materialize_brain_mesh_activation,
                self._materialize_evidence_refresh,
                self._materialize_side_evidence,
                self._materialize_downstream_recompute,
                self._materialize_post_side_readiness,
                self._materialize_risk_gate,
                self._materialize_risk_evidence_mesh,
                self._materialize_exit_cortex,
                self._materialize_eligibility_gate,
                self._materialize_same_market_side_guard,
                self._materialize_payout_odds,
                self._materialize_exit_hold_reasoning,
                self._materialize_capital_efficiency,
                self._materialize_trade_lifecycle,
                self._materialize_lifecycle_governance,
                self._materialize_truth_state,
                self._materialize_paper_intent_gate,
                self._materialize_paper_execution,
                self._materialize_paper_positions,
                self._materialize_paper_exit_loop,
                self._materialize_pnl_ledger,
                self._materialize_no_trade_ledger,
                self._materialize_neuron_intelligence,
                self._materialize_neural_events,
                self._materialize_mesh_sessions,
                self._materialize_shared_awareness,
                self._materialize_capital_brain,
                self._materialize_position_awareness,
                self._materialize_multi_brain_consumption,
                self._materialize_mesh_coordinator_decisions,
                self._materialize_fresh_market_identity,
                self._materialize_clob_token_book_verification,
                self._materialize_live_orderbook_watcher,
                self._materialize_open_position_watchdog,
                self._materialize_fresh_seed_paper_path,
                self._materialize_polymarket_binding,
                self._materialize_polymarket_token_truth,
                self._materialize_neuron_dialogue,
            ):
                created += materializer(conn, limit=limit_per_source)
        return {
            "mock_data": False,
            "status": "OK",
            "system_power": system_power,
            "events_created": created,
            "normal_dialogue_blocked": False,
        }

    def list_events(
        self,
        *,
        limit: int = 100,
        component: str | None = None,
        market_id: str | None = None,
        candidate_id: str | None = None,
        paper_position_id: str | None = None,
        severity: str | None = None,
        component_type: str | None = None,
        status: str | None = None,
        silent: bool | None = None,
        since: str | datetime | None = None,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_feed()
        with self._factory.connect() as conn:
            if not _table_exists(conn, "brain_dialogue_events"):
                return _empty_feed()
            events = _query_events(
                conn,
                limit=limit,
                component=component,
                market_id=market_id,
                candidate_id=candidate_id,
                paper_position_id=paper_position_id,
                severity=severity,
                component_type=component_type,
                status=status,
                silent=silent,
                since=_parse_since(since),
            )
            total_events = _count_table(conn, "brain_dialogue_events")
            components_speaking = _components_speaking(conn, window=timedelta(hours=1))
            component_states = self._component_states(conn)
            safety = _safety_counts(conn)
            latest_event_at = _max_timestamp(conn, "brain_dialogue_events", "timestamp")
            power = self._system_power.get_power_state()
        silent = [item for item in component_states if not item["active"]]
        return {
            "mock_data": False,
            "generated_at": datetime.now(UTC).isoformat(),
            "system_power": power.get("power"),
            "events": [_json_safe(dict(row)) for row in events],
            "total_events": total_events,
            "components_speaking": components_speaking,
            "components_silent": len(silent),
            "latest_event_at": latest_event_at.isoformat() if latest_event_at else None,
            "safety": safety,
        }

    def get_system_life(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_life()
        with self._factory.connect() as conn:
            if not _table_exists(conn, "brain_dialogue_events"):
                return _empty_life()
            components = self._component_states(conn)
            neuron_states = self._neuron_states(conn)
            safety = _safety_counts(conn)
            power = self._system_power.get_power_state()
            top_blockers = _top_current_blockers(conn)
            open_positions = _count_where(conn, "paper_positions", "current_status = 'OPEN'")
        active = [item for item in components if item["active"]]
        silent = [item for item in components if not item["active"]]
        stale = [item for item in components if item["stale"]]
        latest_by_type = {item["key"]: item.get("last_dialogue_at") for item in components}
        neuron_active = [item for item in neuron_states if item["active"]]
        neuron_silent = [item for item in neuron_states if not item["active"] and item["status"] not in {"MISSING_SOURCE", "DISABLED"}]
        neuron_missing = [item for item in neuron_states if item["status"] == "MISSING_SOURCE"]
        neuron_disabled = [item for item in neuron_states if item["status"] == "DISABLED"]
        last_neuron_dialogue_at = max((item.get("last_dialogue_at") for item in neuron_states if item.get("last_dialogue_at")), default=None)
        neuron_coverage = {
            "total_neurons": len(neuron_states),
            "neuron_components_speaking": len(neuron_active),
            "neuron_components_silent": len(neuron_silent),
            "neuron_components_missing": len(neuron_missing),
            "neuron_components_disabled": len(neuron_disabled),
            "last_neuron_dialogue_at": last_neuron_dialogue_at,
            "neurons": neuron_states,
        }
        return {
            "mock_data": False,
            "system_power": power.get("power"),
            "runtime_work_allowed": power.get("runtime_work_allowed"),
            "components": components,
            "neuron_coverage": neuron_coverage,
            "total_neurons": neuron_coverage["total_neurons"],
            "neuron_components_speaking": neuron_coverage["neuron_components_speaking"],
            "neuron_components_silent": neuron_coverage["neuron_components_silent"],
            "neuron_components_missing": neuron_coverage["neuron_components_missing"],
            "neuron_components_disabled": neuron_coverage["neuron_components_disabled"],
            "last_neuron_dialogue_at": last_neuron_dialogue_at,
            "active_components": len(active),
            "silent_components": len(silent),
            "stale_components": len(stale),
            "latest_market_event_at": latest_by_type.get("market_service"),
            "latest_brain_event_at": latest_by_type.get("brain_mesh_activation"),
            "latest_evidence_event_at": latest_by_type.get("evidence_refresh"),
            "latest_risk_event_at": latest_by_type.get("risk_gate"),
            "latest_exit_event_at": latest_by_type.get("exit_cortex"),
            "latest_eligibility_event_at": latest_by_type.get("eligibility_gate"),
            "latest_paper_event_at": latest_by_type.get("paper_execution") or latest_by_type.get("paper_intent_gate"),
            "latest_pnl_event_at": latest_by_type.get("pnl_ledger"),
            "top_current_blockers": top_blockers,
            "open_paper_positions": open_positions,
            "live_orders": safety["live_orders"],
            "real_orders": safety["real_orders"],
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def get_candidate_dialogue(self, candidate_id: str, *, limit: int = 100) -> dict[str, Any]:
        payload = self.list_events(limit=limit, candidate_id=candidate_id)
        payload["candidate_id"] = candidate_id
        return payload

    def get_neuron_dialogue(self, *, limit: int = 100, component: str | None = None, status: str | None = None) -> dict[str, Any]:
        payload = self.list_events(limit=limit, component=component, component_type="neuron", status=status)
        if not self._factory.enabled:
            payload.update(
                {
                    "total_neurons": 0,
                    "speaking_neurons": 0,
                    "silent_neurons": 0,
                    "missing_neurons": 0,
                    "disabled_neurons": 0,
                    "per_neuron_status": [],
                }
            )
            return payload
        with self._factory.connect() as conn:
            states = self._neuron_states(conn) if _table_exists(conn, "brain_dialogue_events") else []
        payload.update(
            {
                "total_neurons": len(states),
                "speaking_neurons": len([item for item in states if item["active"]]),
                "silent_neurons": len([item for item in states if not item["active"] and item["status"] not in {"MISSING_SOURCE", "DISABLED"}]),
                "missing_neurons": len([item for item in states if item["status"] == "MISSING_SOURCE"]),
                "disabled_neurons": len([item for item in states if item["status"] == "DISABLED"]),
                "per_neuron_status": states,
            }
        )
        return payload

    def _component_states(self, conn: Any) -> list[dict[str, Any]]:
        power = self._system_power.get_power_state()
        runtime_allowed = bool(power.get("runtime_work_allowed"))
        now = datetime.now(UTC)
        states: list[dict[str, Any]] = []
        for spec in _component_specs():
            last_source_at = _latest_source_at(conn, spec)
            latest_dialogue = _latest_dialogue_for_component(conn, spec["component"])
            events_1h = _dialogue_count_for_component(conn, spec["component"], since=now - timedelta(hours=1))
            events_24h = _dialogue_count_for_component(conn, spec["component"], since=now - timedelta(hours=24))
            last_dialogue_at = latest_dialogue.get("timestamp") if latest_dialogue else None
            last_status = latest_dialogue.get("status") if latest_dialogue else None
            latest_message = latest_dialogue.get("human_message") if latest_dialogue else None
            effective_at = last_source_at or last_dialogue_at
            stale = bool(effective_at and now - _as_aware(effective_at) > STALE_AFTER)
            active = bool(effective_at and not stale)
            allowed = True if spec["key"] == "dashboard_truth" else runtime_allowed
            states.append(
                _json_safe(
                    {
                        "key": spec["key"],
                        "component": spec["component"],
                        "active": active,
                        "allowed": allowed,
                        "wired": spec["wired"],
                        "last_dialogue_at": last_dialogue_at,
                        "last_source_record_at": last_source_at,
                        "last_status": last_status,
                        "stale": stale,
                        "stale_reason": "NO_RECENT_SOURCE_RECORD" if stale else None,
                        "latest_message": latest_message,
                        "events_1h": events_1h,
                        "events_24h": events_24h,
                    }
                )
            )
        return states

    def _neuron_states(self, conn: Any) -> list[dict[str, Any]]:
        power = self._system_power.get_power_state()
        runtime_allowed = bool(power.get("runtime_work_allowed"))
        now = datetime.now(UTC)
        states: list[dict[str, Any]] = []
        for spec in _neuron_specs():
            registry = _neuron_registry_row(conn, spec["neuron_name"])
            enabled = bool(registry.get("enabled", True)) if registry else True
            source_tables = [source for source in spec["sources"] if _table_exists(conn, source["table"])]
            latest_source_at = _latest_neuron_source_at(conn, spec)
            latest_dialogue = _latest_dialogue_for_component(conn, spec["component"])
            events_1h = _dialogue_count_for_component(conn, spec["component"], since=now - timedelta(hours=1))
            events_24h = _dialogue_count_for_component(conn, spec["component"], since=now - timedelta(hours=24))
            last_dialogue_at = latest_dialogue.get("timestamp") if latest_dialogue else None
            latest_message = latest_dialogue.get("human_message") if latest_dialogue else None
            effective_at = latest_source_at or last_dialogue_at
            stale = bool(effective_at and now - _as_aware(effective_at) > STALE_AFTER)
            if not enabled:
                status = "DISABLED"
                silent_reason = "DISABLED_IN_NEURON_REGISTRY"
            elif not source_tables:
                status = "MISSING_SOURCE"
                silent_reason = "SILENT_NO_SOURCE_TABLE"
            elif latest_source_at is None:
                status = "SILENT_NO_SOURCE_RECORD"
                silent_reason = "SILENT_NO_SOURCE_RECORD"
            elif stale:
                status = "SILENT_STALE"
                silent_reason = "SILENT_STALE_SOURCE_RECORD"
            else:
                status = "ACTIVE"
                silent_reason = None
            active = status == "ACTIVE"
            states.append(
                _json_safe(
                    {
                        "key": spec["key"],
                        "name": spec["component"],
                        "component": spec["component"],
                        "component_type": "neuron",
                        "active": active,
                        "allowed": runtime_allowed and enabled,
                        "wired": bool(source_tables),
                        "status": status,
                        "silent_reason": silent_reason,
                        "registry_enabled": enabled,
                        "source_tables": [source["table"] for source in source_tables],
                        "last_source_record_at": latest_source_at,
                        "last_dialogue_at": last_dialogue_at,
                        "last_status": latest_dialogue.get("status") if latest_dialogue else None,
                        "stale": stale,
                        "stale_reason": silent_reason if stale else None,
                        "events_1h": events_1h,
                        "events_24h": events_24h,
                        "latest_message": latest_message,
                    }
                )
            )
        return states

    def _materialize_system_power(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "system_power_transitions"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM system_power_transitions
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            power = row["new_power"]
            event_type = "brain_dialogue.system.on" if power == "ON" else "brain_dialogue.system.off"
            status = "ON" if power == "ON" else "OFF"
            message = (
                f"SystemPower: SYSTEM {power} is active. Runtime work is "
                f"{'allowed' if power == 'ON' else 'blocked'} by actor={row.get('actor')} reason={row.get('reason')}."
            )
            created += self._insert_event(
                conn,
                source_table="system_power_transitions",
                source_record_id=row["transition_id"],
                timestamp=row["created_at"],
                component="SystemPower",
                component_type="runtime_control",
                event_type=event_type,
                severity="INFO",
                status=status,
                decision=power,
                human_message=message,
                raw_payload=row,
                correlation_id=row.get("correlation_id"),
                what_i_saw=f"old_power={row.get('old_power')} new_power={power}",
                what_i_understand="Operator-facing power controls decide whether autonomous runtime work may run.",
            )
        return created

    def _materialize_neuron_intelligence(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "neuron_intelligence_evidence"):
            return 0
        rows = conn.execute(
            "SELECT * FROM neuron_intelligence_evidence ORDER BY created_at DESC, id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="neuron_intelligence_evidence",
                source_record_id=row.get("evidence_id") or str(row.get("id")),
                timestamp=row.get("created_at"),
                component=row.get("neuron_name"),
                event_type=f"brain_dialogue.neuron_intelligence.{_slug(row.get('neuron_name'))}",
                market_id=row.get("market_id"),
                status=str(row.get("decision") or row.get("status") or "OBSERVED"),
                severity="WARN" if row.get("status") == "BLOCKED" else "INFO",
                human_message=row.get("human_message"),
                evidence_used=row.get("evidence_json") or {},
                block_reason=", ".join(row.get("blockers_json") or []) if row.get("blockers_json") else None,
                what_i_saw=f"{row.get('neuron_name')} produced source-backed Pack 1 evidence.",
                what_i_understand="Neuron Intelligence Pack 1 evidence is observational and can be consumed by Risk, Exit, Eligibility, and Opportunity scoring.",
            )
        return created

    def _materialize_market_service(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "runtime_cycles_v2"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM runtime_cycles_v2
            ORDER BY started_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            status = str(row.get("status") or "UNKNOWN")
            message = (
                f"MarketService: I ran runtime cycle {row.get('cycle_id')} in mode={row.get('mode')} "
                f"with scanner_finished={row.get('scanner_finished')} intelligence_finished={row.get('intelligence_finished')} "
                f"paper_finished={row.get('paper_finished')}. Cycle status is {status}."
            )
            created += self._insert_event(
                conn,
                source_table="runtime_cycles_v2",
                source_record_id=row["cycle_id"],
                cycle_id=row["cycle_id"],
                timestamp=row["started_at"],
                component="MarketService",
                component_type="runtime_cycle",
                event_type="brain_dialogue.market.cycle",
                severity="INFO" if status in {"COMPLETED", "RUNNING"} else "WARN",
                status=status,
                decision=status,
                human_message=message,
                raw_payload=row,
                what_i_saw="A runtime cycle record exists with scanner, intelligence, and paper stage flags.",
                what_i_understand="This is the runtime spine that hands real work to the Brain Mesh and paper-safe stages.",
            )
        return created

    def _materialize_data_foundation(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "event_log"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM event_log
            WHERE source_service = 'data_foundation'
              AND event_type IN ('market.snapshot.created', 'liquidity.snapshot.created', 'fee.snapshot.created', 'data.completeness.updated')
            ORDER BY stored_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            payload = row.get("payload_json") or {}
            message = f"DataFoundation: I persisted {row.get('event_type')} for aggregate={row.get('aggregate_id')}. The payload is DB-backed."
            created += self._insert_event(
                conn,
                source_event_id=row["event_id"],
                source_table="event_log",
                source_record_id=row["event_id"],
                cycle_id=row.get("cycle_id"),
                correlation_id=row.get("correlation_id"),
                timestamp=row["stored_at"],
                component="DataFoundation",
                component_type="data_foundation",
                event_type="brain_dialogue.data.persisted",
                severity="INFO",
                market_id=str(payload.get("market_id")) if payload.get("market_id") else None,
                status="PERSISTED",
                human_message=message,
                raw_payload=row,
                evidence_used=payload,
                what_i_saw=str(row.get("event_type")),
                what_i_understand="Market, liquidity, fee, or completeness data was stored for downstream evidence consumers.",
            )
        return created

    def _materialize_brain_mesh_activation(self, conn: Any, *, limit: int) -> int:
        return self._materialize_run_table(
            conn,
            table="brain_mesh_activation_runs",
            id_col="run_id",
            ts_col="created_at",
            limit=limit,
            component="Brain Mesh Activation",
            component_type="brain_mesh",
            event_type="brain_dialogue.brain.activated",
            message_builder=lambda r: (
                f"Brain Mesh Activation: I created evidence={_int(r.get('evidence_created'))}, "
                f"brain_outputs={_int(r.get('brain_outputs_created'))}, coordinator_decisions={_int(r.get('coordinator_decisions_created'))}, "
                f"thesis_profiles={_int(r.get('thesis_profiles_created')) + _int(r.get('thesis_profiles_updated'))}, "
                f"position_thesis_profiles={_int(r.get('position_thesis_profiles_created')) + _int(r.get('position_thesis_profiles_updated'))}. "
                f"Status={r.get('status')}."
            ),
        )

    def _materialize_evidence_refresh(self, conn: Any, *, limit: int) -> int:
        return self._materialize_run_table(
            conn,
            table="evidence_refresh_runs",
            id_col="run_id",
            ts_col="created_at",
            limit=limit,
            component="Evidence Refresh",
            component_type="evidence",
            event_type="brain_dialogue.evidence.refreshed",
            message_builder=lambda r: (
                f"Evidence Refresh: I checked {r.get('markets_checked')} markets, created {r.get('orderbook_snapshots_created')} "
                f"orderbook snapshots, created/refreshed bindings={_int(r.get('bindings_created')) + _int(r.get('bindings_refreshed'))}, "
                f"rejected bindings={r.get('bindings_rejected')}, and recovered sides={r.get('sides_recovered')}. Status={r.get('status')}."
            ),
        )

    def _materialize_side_evidence(self, conn: Any, *, limit: int) -> int:
        return self._materialize_run_table(
            conn,
            table="side_evidence_recovery_runs",
            id_col="run_id",
            ts_col="created_at",
            limit=limit,
            component="Side Evidence",
            component_type="evidence",
            event_type="brain_dialogue.side.resolved",
            message_builder=lambda r: (
                f"Side Evidence: I checked {r.get('links_checked')} links and {r.get('candidates_checked')} candidates. "
                f"I recovered {r.get('sides_recovered')} sides, rejected {r.get('sides_rejected')}, "
                f"and found side_conflicts={r.get('side_conflict_count')}. Status={r.get('status')}."
            ),
        )

    def _materialize_downstream_recompute(self, conn: Any, *, limit: int) -> int:
        return self._materialize_run_table(
            conn,
            table="downstream_evidence_recompute_runs",
            id_col="run_id",
            ts_col="created_at",
            limit=limit,
            component="Downstream Evidence Recompute",
            component_type="decision_recompute",
            event_type="brain_dialogue.downstream.recomputed",
            message_builder=lambda r: (
                f"Downstream Evidence Recompute: I updated thesis={r.get('thesis_updated')}, risk={r.get('risk_updated')}, "
                f"exit={r.get('exit_updated')}, eligibility={r.get('eligibility_updated')}, no_trade={r.get('no_trade_updated')}. "
                f"Missing side moved {r.get('missing_side_before')}->{r.get('missing_side_after')}. Status={r.get('status')}."
            ),
        )

    def _materialize_post_side_readiness(self, conn: Any, *, limit: int) -> int:
        return self._materialize_run_table(
            conn,
            table="post_side_risk_exit_recovery_runs",
            id_col="run_id",
            ts_col="created_at",
            limit=limit,
            component="Risk Exit Readiness Recovery",
            component_type="decision_recompute",
            event_type="brain_dialogue.risk_exit.recovered",
            message_builder=lambda r: (
                f"Risk Exit Readiness Recovery: I checked {r.get('candidates_checked')} candidates with side={r.get('candidates_with_side')}. "
                f"Risk approved moved {r.get('risk_approved_before')}->{r.get('risk_approved_after')}, "
                f"exit ready moved {r.get('exit_ready_before')}->{r.get('exit_ready_after')}, "
                f"eligible moved {r.get('eligible_before')}->{r.get('eligible_after')}. Status={r.get('status')}."
            ),
        )

    def _materialize_risk_gate(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "risk_decisions"):
            return 0
        rows = conn.execute(
            "SELECT * FROM risk_decisions ORDER BY updated_at DESC, id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            approved = bool(row.get("risk_approved"))
            blockers = _listify(row.get("blockers"))
            status = "APPROVED" if approved else str(row.get("decision") or row.get("risk_status") or "BLOCKED")
            event_type = "brain_dialogue.risk.approved" if approved else "brain_dialogue.risk.blocked"
            missing = _listify(row.get("required_missing_evidence")) or blockers
            message = (
                f"Risk Gate: I consumed market_id={row.get('market_id')}, side evidence from the thesis chain, "
                f"orderbook_snapshot_id={row.get('orderbook_snapshot_id')}, and thesis={row.get('thesis_id')}. "
                f"Risk is {status}."
            )
            if not approved:
                message += f" Blockers={blockers or missing}."
            created += self._insert_event(
                conn,
                source_table="risk_decisions",
                source_record_id=row["risk_decision_id"],
                timestamp=row["updated_at"] or row["created_at"],
                component="Risk Gate",
                component_type="risk",
                event_type=event_type,
                severity="INFO" if approved else "WARN",
                market_id=row.get("market_id"),
                risk_decision_id=row.get("risk_decision_id"),
                status=status,
                decision=row.get("decision"),
                block_reason=", ".join(blockers) if blockers and not approved else None,
                next_required_evidence=missing,
                human_message=message,
                raw_payload=row,
                evidence_used={
                    "thesis_id": row.get("thesis_id"),
                    "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
                    "risk_score": row.get("risk_score"),
                    "confidence": row.get("confidence"),
                },
                what_i_saw=f"risk_approved={approved} blockers={blockers}",
                what_i_understand="Risk approval can only pass when the thesis, market binding, side, liquidity, and orderbook evidence satisfy risk policy.",
            )
        return created

    def _materialize_risk_evidence_mesh(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "risk_evidence_mesh_evaluations"):
            return 0
        rows = conn.execute(
            "SELECT * FROM risk_evidence_mesh_evaluations ORDER BY created_at DESC, id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            decision = str(row.get("risk_decision") or "RISK_BLOCK")
            subtype = str(row.get("risk_blocker_subtype") or "RISK_BLOCKED_UNKNOWN")
            critical = _listify(row.get("critical_evidence_missing_json"))
            optional = _listify(row.get("optional_context_missing_json"))
            blocking = _listify(row.get("blocking_evidence_json"))
            if decision == "RISK_BLOCK":
                message = f"Risk Evidence Mesh: {row.get('subject_type')} {row.get('subject_id')} blocked because {subtype}; critical missing={critical[:6]}."
            elif decision in {"RISK_WATCH", "RISK_REVIEW"}:
                message = f"Risk Evidence Mesh: {row.get('subject_type')} {row.get('subject_id')} is {decision}; optional missing={optional[:6]} and edge={row.get('edge_source_type')}."
            else:
                message = f"Risk Evidence Mesh: {row.get('subject_type')} {row.get('subject_id')} supports source-backed edge {row.get('edge_source_type')}."
            created += self._insert_event(
                conn,
                source_table="risk_evidence_mesh_evaluations",
                source_record_id=row["evaluation_id"],
                timestamp=row["created_at"],
                component="Risk Evidence Mesh",
                component_type="risk_evidence",
                event_type="brain_dialogue.risk_evidence_mesh.evaluation",
                severity="WARN" if decision == "RISK_BLOCK" else "INFO",
                market_id=row.get("market_id"),
                candidate_id=row.get("subject_id") if row.get("subject_type") in {"FRESH_SEED", "PAPER_CANDIDATE", "LIFECYCLE_PLAN"} else None,
                paper_intent_id=row.get("subject_id") if row.get("subject_type") == "PAPER_INTENT" else None,
                paper_position_id=row.get("subject_id") if row.get("subject_type") == "PAPER_POSITION" else None,
                status=decision,
                decision=decision,
                block_reason=subtype if decision == "RISK_BLOCK" else None,
                next_required_evidence=[*critical, *blocking],
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "edge_source_type": row.get("edge_source_type"),
                    "edge_status": row.get("edge_status"),
                    "critical_evidence_present": row.get("critical_evidence_present_json"),
                    "optional_context_missing": optional,
                },
                what_i_saw=f"risk_decision={decision} subtype={subtype} edge={row.get('edge_source_type')} optional={optional}",
                what_i_understand="Risk Evidence Mesh separates critical blockers from optional context and does not fabricate edge or probability.",
            )
        return created

    def _materialize_exit_cortex(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "exit_plans"):
            return 0
        rows = conn.execute("SELECT * FROM exit_plans ORDER BY updated_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            ready = bool(row.get("paper_exit_ready")) or str(row.get("status") or "").upper() == "COMPLETE"
            blockers = _listify(row.get("blockers")) or _listify(row.get("missing_exit_evidence"))
            event_type = "brain_dialogue.exit.complete" if ready else "brain_dialogue.exit.blocked"
            status = str(row.get("status") or ("COMPLETE" if ready else "BLOCKED"))
            message = (
                f"Exit Cortex: I consumed risk={row.get('risk_decision_ref') or row.get('risk_decision_id')}, "
                f"side={row.get('side')}, orderbook_snapshot_id={row.get('orderbook_snapshot_id')}, "
                f"target={row.get('target_exit')}, stop={row.get('stop_loss')}. Exit status is {status}."
            )
            if not ready:
                message += f" Blockers={blockers}."
            created += self._insert_event(
                conn,
                source_table="exit_plans",
                source_record_id=row["exit_plan_id"],
                timestamp=row["updated_at"] or row["created_at"],
                component="Exit Cortex",
                component_type="exit",
                event_type=event_type,
                severity="INFO" if ready else "WARN",
                market_id=row.get("market_id"),
                risk_decision_id=row.get("risk_decision_ref") or row.get("risk_decision_id"),
                exit_plan_id=row.get("exit_plan_id"),
                status=status,
                decision="COMPLETE" if ready else status,
                block_reason=", ".join(blockers) if blockers and not ready else None,
                next_required_evidence=blockers if not ready else [],
                human_message=message,
                raw_payload=row,
                evidence_used={
                    "side": row.get("side"),
                    "target_exit": row.get("target_exit"),
                    "stop_loss": row.get("stop_loss"),
                    "max_hold_seconds": row.get("max_hold_seconds"),
                },
                what_i_saw=f"paper_exit_ready={ready} status={status}",
                what_i_understand="Exit readiness requires side, fresh price evidence, risk state, target, stop, and emergency rules.",
            )
        return created

    def _materialize_eligibility_gate(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "paper_eligibility_candidates"):
            return 0
        rows = conn.execute(
            "SELECT * FROM paper_eligibility_candidates ORDER BY updated_at DESC, id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            eligible = str(row.get("status") or "").upper() == "ELIGIBLE"
            blockers = _listify(row.get("eligibility_blockers")) or _listify(row.get("missing_requirements"))
            event_type = "brain_dialogue.eligibility.eligible" if eligible else "brain_dialogue.eligibility.blocked"
            message = (
                f"Eligibility Gate: I consumed risk_approved={row.get('risk_approved')}, exit_ready={row.get('exit_ready')}, "
                f"side={row.get('side')}, orderbook_snapshot_id={row.get('orderbook_snapshot_id')}, "
                f"lineage_trusted={row.get('lineage_trusted')}. Candidate {row.get('eligibility_id')} is {row.get('status')}."
            )
            if not eligible:
                message += f" Blockers={blockers}."
            created += self._insert_event(
                conn,
                source_table="paper_eligibility_candidates",
                source_record_id=row["eligibility_id"],
                timestamp=row["updated_at"] or row["created_at"],
                component="Eligibility Gate",
                component_type="eligibility",
                event_type=event_type,
                severity="INFO" if eligible else "WARN",
                market_id=row.get("market_id"),
                candidate_id=row.get("eligibility_id"),
                risk_decision_id=row.get("risk_decision_id"),
                exit_plan_id=row.get("exit_plan_id"),
                eligibility_id=row.get("eligibility_id"),
                status=row.get("status"),
                decision=row.get("status"),
                block_reason=", ".join(blockers) if blockers and not eligible else None,
                next_required_evidence=blockers if not eligible else [],
                human_message=message,
                raw_payload=row,
                evidence_used={
                    "side": row.get("side"),
                    "risk_approved": row.get("risk_approved"),
                    "exit_ready": row.get("exit_ready"),
                    "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
                },
                what_i_saw=f"status={row.get('status')} blockers={blockers}",
                what_i_understand="Eligibility requires current risk, exit, thesis, trusted binding, fresh orderbook, side, and lineage.",
            )
        return created

    def _materialize_paper_intent_gate(self, conn: Any, *, limit: int) -> int:
        created = 0
        if _table_exists(conn, "paper_intents"):
            rows = conn.execute("SELECT * FROM paper_intents ORDER BY updated_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
            for row in rows:
                message = (
                    f"Paper Intent Gate: I created/updated paper_intent={row.get('paper_intent_id')} from eligible candidate={row.get('eligibility_id')}. "
                    f"paper_only={row.get('paper_only')} live={row.get('live')} execution_allowed={row.get('execution_allowed')}."
                )
                created += self._insert_event(
                    conn,
                    source_table="paper_intents",
                    source_record_id=row["paper_intent_id"],
                    timestamp=row["updated_at"] or row["created_at"],
                    component="Paper Intent Gate",
                    component_type="paper_intent",
                    event_type="brain_dialogue.paper_intent.created",
                    severity="INFO",
                    market_id=row.get("market_id"),
                    candidate_id=row.get("eligibility_id"),
                    risk_decision_id=row.get("risk_decision_id"),
                    exit_plan_id=row.get("exit_plan_id"),
                    eligibility_id=row.get("eligibility_id"),
                    paper_intent_id=row.get("paper_intent_id"),
                    status=row.get("intent_status"),
                    decision=row.get("intent_type"),
                    human_message=message,
                    raw_payload=row,
                    evidence_used={"intended_price": row.get("intended_price"), "price_basis": row.get("price_basis")},
                    what_i_saw=f"intent_status={row.get('intent_status')} paper_only={row.get('paper_only')}",
                    what_i_understand="Paper intents are non-live simulation requests and do not create real orders.",
                )
        if _table_exists(conn, "paper_intent_runs"):
            created += self._materialize_run_table(
                conn,
                table="paper_intent_runs",
                id_col="run_id",
                ts_col="created_at",
                limit=limit,
                component="Paper Intent Gate",
                component_type="paper_intent",
                event_type="brain_dialogue.paper_intent.run",
                message_builder=lambda r: (
                    f"Paper Intent Gate: I checked {r.get('candidates_checked')} candidates, found eligible={r.get('eligible_candidates')}, "
                    f"created intents={r.get('paper_intents_created')}, and recorded no_trade={r.get('no_trade_records_created')}. Status={r.get('status')}."
                ),
            )
        return created

    def _materialize_same_market_side_guard(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "same_market_side_guard_decisions"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM same_market_side_guard_decisions
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            decision = str(row.get("decision") or "UNKNOWN")
            blocker = row.get("blocker_reason")
            rationale = row.get("rationale_type")
            if decision == "ALLOW" and rationale:
                message = (
                    f"Same-Market Guard: Allowed {row.get('proposed_side')} on market {row.get('market_id')} "
                    f"because coordinator/source recorded {rationale}."
                )
            elif decision == "REVIEW":
                message = (
                    f"Same-Market Guard: Sent {row.get('proposed_side')} on market {row.get('market_id')} "
                    f"to REVIEW because {blocker}."
                )
            elif blocker in {
                "SAME_MARKET_OPPOSING_SIDE_BLOCK",
                "SAME_MARKET_OPPOSING_INTENT_BLOCK",
                "SAME_MARKET_OPEN_OPPOSITE_POSITION_BLOCK",
                "SAME_MARKET_ACTIVE_OPPOSITE_INTENT_BLOCK",
                "SAME_MARKET_BATCH_CONFLICT_BLOCK",
            }:
                message = (
                    f"Same-Market Guard: Blocked {row.get('proposed_side')} on market {row.get('market_id')} "
                    "because opposing same-market exposure exists and no hedge/arbitrage rationale was present."
                )
            else:
                message = (
                    f"Same-Market Guard: {decision} for {row.get('proposed_side')} on market {row.get('market_id')}; "
                    f"reason={blocker or 'NONE'}."
                )
            created += self._insert_event(
                conn,
                source_table="same_market_side_guard_decisions",
                source_record_id=row["decision_id"],
                timestamp=row["created_at"],
                component="Same-Market Guard",
                component_type="paper_risk_guard",
                event_type="brain_dialogue.same_market_guard.decision",
                severity="WARN" if decision in {"BLOCK", "REVIEW"} else "INFO",
                market_id=row.get("market_id"),
                candidate_id=row.get("proposed_candidate_id"),
                paper_intent_id=row.get("proposed_intent_id"),
                status=decision,
                decision=decision,
                block_reason=blocker,
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "existing_exposure": row.get("existing_exposure_json"),
                    "rationale_type": rationale,
                    "rationale_source": row.get("rationale_source"),
                    "source_backed": row.get("source_backed"),
                },
                next_required_evidence=[] if decision == "ALLOW" else ["SOURCE_BACKED_STRATEGIC_RATIONALE"],
                what_i_saw=f"decision={decision} blocker={blocker} rationale={rationale}",
                what_i_understand="Same-market opposing YES/NO exposure requires explicit source-backed strategic rationale before Paper can continue.",
            )
        return created

    def _materialize_payout_odds(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "payout_odds_evaluations"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM payout_odds_evaluations
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            status = str(row.get("settlement_value_status") or "UNKNOWN")
            subject = str(row.get("subject_type") or "UNKNOWN")
            if status == "MISSING_PRICE":
                message = f"Payout/Odds: Evaluation skipped for {subject} {row.get('subject_id')} because executable price is missing."
                severity = "WARN"
            elif row.get("price") is None:
                message = f"Payout/Odds: Evaluation for {subject} {row.get('subject_id')} is incomplete; status={status}."
                severity = "WARN"
            elif subject == "PAPER_POSITION":
                message = (
                    f"Payout/Odds: Position {row.get('subject_id')} entry {row.get('price')} has "
                    f"payout_if_win={row.get('payout_if_win')} and profit_if_win={row.get('profit_if_win')} from entry."
                )
                severity = "INFO"
            else:
                message = (
                    f"Payout/Odds: {subject} {row.get('subject_id')} at price {row.get('price')} implies "
                    f"{row.get('implied_probability')} probability; stake {row.get('stake_usd')} buys "
                    f"{row.get('shares_if_buy')} shares with {row.get('profit_if_win')} profit if win."
                )
                severity = "INFO"
            created += self._insert_event(
                conn,
                source_table="payout_odds_evaluations",
                source_record_id=row["evaluation_id"],
                timestamp=row["created_at"],
                component="Payout/Odds",
                component_type="economic_reasoning",
                event_type="brain_dialogue.payout_odds.evaluation",
                severity=severity,
                market_id=row.get("market_id"),
                candidate_id=row.get("subject_id") if subject in {"FRESH_SEED", "PAPER_CANDIDATE"} else None,
                paper_intent_id=row.get("subject_id") if subject == "PAPER_INTENT" else None,
                paper_position_id=row.get("subject_id") if subject == "PAPER_POSITION" else None,
                status=status,
                decision="OBSERVE",
                block_reason=None if status not in {"MISSING_PRICE", "INVALID_PRICE"} else status,
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "price": row.get("price"),
                    "price_source": row.get("price_source"),
                    "source_refs": row.get("source_refs_json"),
                    "fair_probability": row.get("fair_probability"),
                    "expected_value": row.get("expected_value"),
                },
                next_required_evidence=[] if row.get("fair_probability") is not None else ["SOURCE_BACKED_FAIR_PROBABILITY_FOR_EV"],
                what_i_saw=f"subject={subject} price={row.get('price')} stake={row.get('stake_usd')} status={status}",
                what_i_understand="Market price is implied probability; payout/EV uses only source-backed price and leaves fair probability/EV null without a real source.",
            )
        return created

    def _materialize_exit_hold_reasoning(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "exit_hold_evaluations"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM exit_hold_evaluations
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            decision = str(row.get("decision") or "INSUFFICIENT_DATA")
            missing = _listify(row.get("missing_inputs_json"))
            position_id = row.get("paper_position_id") or (row.get("subject_id") if row.get("subject_type") == "PAPER_POSITION" else None)
            severity = "WARN" if decision in {"EMERGENCY_EXIT_REVIEW", "INSUFFICIENT_DATA", "PARTIAL_EXIT_REVIEW", "HOLD_REVIEW"} else "INFO"
            if "EXIT_NOW_UNAVAILABLE" in missing and decision == "EMERGENCY_EXIT_REVIEW":
                message = f"Exit/Hold: Position {position_id} marked EMERGENCY_EXIT_REVIEW because current exit price is missing."
            elif "PAYOUT_ODDS_MISSING" in missing:
                message = f"Exit/Hold: Evaluation skipped for {row.get('subject_type')} {row.get('subject_id')} because payout/odds evidence is missing."
            elif decision == "HOLD_TO_RESOLUTION":
                message = (
                    f"Exit/Hold: Position {position_id or row.get('subject_id')} marked HOLD_TO_RESOLUTION because time to resolution is short "
                    f"and hold-to-resolution profit if win is {row.get('hold_to_resolution_profit_if_win')} versus exit-now PnL {row.get('exit_now_pnl')}."
                )
            else:
                message = (
                    f"Exit/Hold: {row.get('subject_type')} {row.get('subject_id')} can exit now for PnL {row.get('exit_now_pnl')}, "
                    f"while hold-to-resolution profit if win is {row.get('hold_to_resolution_profit_if_win')}. Decision={decision}."
                )
            created += self._insert_event(
                conn,
                source_table="exit_hold_evaluations",
                source_record_id=row["evaluation_id"],
                timestamp=row["created_at"],
                component="Exit/Hold",
                component_type="exit_reasoning",
                event_type="brain_dialogue.exit_hold.evaluation",
                severity=severity,
                market_id=row.get("market_id"),
                candidate_id=row.get("subject_id") if row.get("subject_type") == "PAPER_CANDIDATE" else None,
                paper_intent_id=row.get("subject_id") if row.get("subject_type") == "PAPER_INTENT" else None,
                paper_position_id=position_id,
                status=decision,
                decision=decision,
                block_reason=decision if decision in {"EMERGENCY_EXIT_REVIEW", "INSUFFICIENT_DATA"} else None,
                next_required_evidence=missing,
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "source_refs": row.get("source_refs_json"),
                    "current_exit_price": row.get("current_exit_price"),
                    "exit_now_value": row.get("exit_now_value"),
                    "hold_to_resolution_value": row.get("hold_to_resolution_value"),
                    "time_to_resolution_seconds": row.get("time_to_resolution_seconds"),
                    "rules_risk": row.get("rules_risk"),
                },
                what_i_saw=f"decision={decision} missing={missing}",
                what_i_understand="Exit/Hold reasoning is observational only; it compares exit value to hold-to-resolution value without closing positions.",
            )
        return created

    def _materialize_capital_efficiency(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "capital_efficiency_evaluations"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM capital_efficiency_evaluations
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            rec = str(row.get("recommendation") or "CAPITAL_INSUFFICIENT_DATA")
            missing = _listify(row.get("missing_inputs_json"))
            subject = str(row.get("subject_type") or "UNKNOWN")
            position_id = row.get("paper_position_id") or (row.get("subject_id") if subject == "PAPER_POSITION" else None)
            severity = "WARN" if rec in {"CAPITAL_BLOCK", "CAPITAL_RELEASE_REVIEW", "CAPITAL_REDUCE_REVIEW", "CAPITAL_INSUFFICIENT_DATA"} else "INFO"
            if "TIME_TO_RESOLUTION_MISSING" in missing:
                message = (
                    f"Capital Efficiency: {subject} {row.get('subject_id')} locks {row.get('capital_locked')}, "
                    f"potential reward {row.get('potential_reward')}, reward per dollar-hour unavailable because time to resolution is missing."
                )
            elif rec == "CAPITAL_RELEASE_REVIEW":
                message = (
                    f"Capital Efficiency: Position {position_id} marked CAPITAL_RELEASE_REVIEW because current exit PnL "
                    f"{row.get('current_exit_pnl')} can free capital and hold efficiency is weak."
                )
            else:
                message = (
                    f"Capital Efficiency: {subject} {row.get('subject_id')} recommendation={rec}; capital_locked={row.get('capital_locked')}, "
                    f"potential_reward={row.get('potential_reward')}, reward_per_dollar_hour={row.get('reward_per_dollar_hour')}."
                )
            created += self._insert_event(
                conn,
                source_table="capital_efficiency_evaluations",
                source_record_id=row["evaluation_id"],
                timestamp=row["created_at"],
                component="Capital Efficiency",
                component_type="capital_efficiency",
                event_type="brain_dialogue.capital_efficiency.evaluation",
                severity=severity,
                market_id=row.get("market_id"),
                candidate_id=row.get("subject_id") if subject in {"FRESH_SEED", "PAPER_CANDIDATE"} else None,
                paper_intent_id=row.get("subject_id") if subject == "PAPER_INTENT" else None,
                paper_position_id=position_id,
                status=rec,
                decision=rec,
                block_reason=rec if rec in {"CAPITAL_BLOCK", "CAPITAL_INSUFFICIENT_DATA"} else None,
                next_required_evidence=missing,
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "source_refs": row.get("source_refs_json"),
                    "capital_locked": row.get("capital_locked"),
                    "reward_per_dollar_hour": row.get("reward_per_dollar_hour"),
                    "capital_efficiency_score": row.get("capital_efficiency_score"),
                    "missing_inputs": missing,
                },
                what_i_saw=f"recommendation={rec} missing={missing}",
                what_i_understand="Capital Efficiency is observational only; it compares reward, time, liquidity, and locked capital without trading.",
            )
        return created

    def _materialize_trade_lifecycle(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "trade_lifecycle_plans"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM trade_lifecycle_plans
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            subject = str(row.get("subject_type") or "UNKNOWN")
            status = str(row.get("plan_status") or "INSUFFICIENT_DATA")
            strategy = str(row.get("strategy_type") or "UNKNOWN")
            decision = str(row.get("decision_class") or "INSUFFICIENT_DATA")
            missing = _listify(row.get("missing_inputs_json"))
            position_id = row.get("subject_id") if subject == "PAPER_POSITION" else None
            if status == "BLOCKED":
                message = f"Trade Lifecycle: {subject} {row.get('subject_id')} is BLOCKED with strategy={strategy}; missing/source notes={missing[:5]}."
            elif subject == "PAPER_POSITION" and decision in {"HOLD_REVIEW", "EXIT_REVIEW"}:
                message = f"Trade Lifecycle: Position {row.get('subject_id')} recommends {decision} with strategy={strategy}; {row.get('exit_thesis')}"
            elif status == "PARTIAL":
                message = f"Trade Lifecycle: {subject} {row.get('subject_id')} has PARTIAL lifecycle plan; missing {missing[:6]}."
            else:
                message = f"Trade Lifecycle: {subject} {row.get('subject_id')} plan_status={status}, strategy={strategy}, decision={decision}."
            severity = "WARN" if status in {"BLOCKED", "NO_TRADE", "INSUFFICIENT_DATA"} or decision in {"EXIT_REVIEW", "BLOCKED"} else "INFO"
            created += self._insert_event(
                conn,
                source_table="trade_lifecycle_plans",
                source_record_id=row["plan_id"],
                timestamp=row["created_at"],
                component="Trade Lifecycle",
                component_type="trade_lifecycle",
                event_type="brain_dialogue.trade_lifecycle.plan",
                severity=severity,
                market_id=row.get("market_id"),
                candidate_id=row.get("subject_id") if subject in {"FRESH_SEED", "PAPER_CANDIDATE"} else None,
                paper_intent_id=row.get("subject_id") if subject == "PAPER_INTENT" else None,
                paper_position_id=position_id,
                status=status,
                decision=decision,
                block_reason=str(row.get("strategy_type")) if status in {"BLOCKED", "NO_TRADE"} else None,
                next_required_evidence=missing,
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "source_refs": row.get("source_refs_json"),
                    "strategy_type": strategy,
                    "economic_thesis": row.get("economic_thesis"),
                    "entry_thesis": row.get("entry_thesis"),
                    "exit_thesis": row.get("exit_thesis"),
                    "capital_plan": row.get("capital_plan_json"),
                },
                what_i_saw=f"plan_status={status} strategy={strategy} decision={decision} missing={missing}",
                what_i_understand="Trade Lifecycle Mesh aggregates source-backed brain contributions into an observational plan; it does not execute trades.",
            )
        return created

    def _materialize_lifecycle_governance(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "lifecycle_governance_decisions"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM lifecycle_governance_decisions
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            subject = str(row.get("subject_type") or "UNKNOWN")
            actionability = str(row.get("actionability_class") or "HARD_BLOCK")
            critical = _listify(row.get("critical_blockers_json"))
            optional = _listify(row.get("optional_missing_json"))
            risk_trace = _dict(_dict(row.get("metadata_json")).get("risk_source_trace"))
            selected_risk = risk_trace.get("selected_risk_source")
            legacy_ignored = bool(risk_trace.get("legacy_ignored"))
            if actionability == "HARD_BLOCK":
                if selected_risk == "RISK_EVIDENCE_MESH" and legacy_ignored:
                    message = f"Lifecycle Governance: {subject} {row.get('subject_id')} used fresh Risk Evidence and ignored stale legacy risk, but stayed blocked by {critical[:6]}."
                else:
                    message = f"Lifecycle Governance: {subject} {row.get('subject_id')} blocked because critical blockers exist: {critical[:6]}."
            elif actionability == "WATCH_FOR_CONFIRMATION":
                if selected_risk == "RISK_EVIDENCE_MESH" and legacy_ignored:
                    message = f"Lifecycle Governance: {subject} {row.get('subject_id')} promoted to WATCH_FOR_CONFIRMATION after fresh Risk Evidence replaced stale legacy risk; optional/context missing={optional[:6]}."
                else:
                    message = f"Lifecycle Governance: {subject} {row.get('subject_id')} held for confirmation; optional/context missing={optional[:6]}."
            elif actionability.startswith("ACTIONABLE"):
                message = f"Lifecycle Governance: {subject} {row.get('subject_id')} allowed as {actionability}; critical blockers are clear."
            else:
                message = f"Lifecycle Governance: {subject} {row.get('subject_id')} classified as {actionability}."
            created += self._insert_event(
                conn,
                source_table="lifecycle_governance_decisions",
                source_record_id=row["decision_id"],
                timestamp=row["created_at"],
                component="Lifecycle Governance",
                component_type="lifecycle_governance",
                event_type="brain_dialogue.lifecycle_governance.decision",
                severity="WARN" if actionability in {"HARD_BLOCK", "NO_TRADE", "WATCH_FOR_CONFIRMATION"} else "INFO",
                market_id=row.get("market_id"),
                candidate_id=row.get("subject_id") if subject in {"FRESH_SEED", "PAPER_CANDIDATE"} else None,
                paper_intent_id=row.get("subject_id") if subject == "PAPER_INTENT" else None,
                paper_position_id=row.get("subject_id") if subject == "PAPER_POSITION" else None,
                status=actionability,
                decision=actionability,
                block_reason=critical[0] if actionability == "HARD_BLOCK" and critical else None,
                next_required_evidence=[*critical, *optional, *_listify(row.get("context_dependent_missing_json"))],
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "lifecycle_plan_id": row.get("lifecycle_plan_id"),
                    "critical_blockers": critical,
                    "optional_missing": optional,
                    "allow_paper_intent": row.get("allow_paper_intent"),
                    "allow_paper_execution": row.get("allow_paper_execution"),
                    "risk_source_trace": risk_trace,
                },
                what_i_saw=f"actionability={actionability} allow_intent={row.get('allow_paper_intent')} allow_execution={row.get('allow_paper_execution')}",
                what_i_understand="Lifecycle Governance converts source-backed lifecycle plans into Paper authorization decisions; it does not execute trades.",
            )
        return created

    def _materialize_truth_state(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "truth_state_registry"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM truth_state_registry
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            source_type = str(row.get("source_type") or "UNKNOWN")
            truth_state = str(row.get("truth_state") or "UNKNOWN")
            permission = str(row.get("decision_permission") or "UNKNOWN_PERMISSION")
            if permission == "CAN_AUTHORIZE":
                message = (
                    f"Truth State: {source_type} {row.get('source_record_id')} is ACTIVE_FRESH "
                    "and can authorize decisions while its source remains current."
                )
                severity = "INFO"
            elif permission == "MUST_REFRESH":
                message = (
                    f"Truth State: {source_type} {row.get('source_record_id')} is {truth_state}; "
                    "it must refresh before it can authorize Paper."
                )
                severity = "WARN"
            elif permission == "CAN_TEACH_ONLY":
                message = (
                    f"Truth State: {source_type} {row.get('source_record_id')} is historical memory; "
                    "it can explain prior behavior but cannot authorize new Paper action."
                )
                severity = "INFO"
            else:
                message = (
                    f"Truth State: {source_type} {row.get('source_record_id')} is {truth_state} "
                    f"with permission={permission}."
                )
                severity = "INFO" if permission == "CAN_INFORM_ONLY" else "WARN"
            created += self._insert_event(
                conn,
                source_table="truth_state_registry",
                source_record_id=row["truth_id"],
                timestamp=row.get("updated_at") or row.get("last_verified_at") or row.get("created_at"),
                component="Truth State",
                component_type="truth_state_governance",
                event_type="brain_dialogue.truth_state.classified",
                severity=severity,
                market_id=row.get("market_id"),
                candidate_id=row.get("subject_id") if row.get("subject_type") in {"FRESH_SEED", "PAPER_CANDIDATE"} else None,
                paper_intent_id=row.get("subject_id") if row.get("subject_type") == "PAPER_INTENT" else None,
                paper_position_id=row.get("subject_id") if row.get("subject_type") == "PAPER_POSITION" else None,
                status=truth_state,
                decision=permission,
                block_reason=truth_state if permission in {"MUST_REFRESH", "MUST_BLOCK"} else None,
                next_required_evidence=["REFRESH_SOURCE"] if permission == "MUST_REFRESH" else [],
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "source_table": row.get("source_table"),
                    "source_record_id": row.get("source_record_id"),
                    "source_type": source_type,
                    "age_seconds": row.get("age_seconds"),
                    "ttl_seconds": row.get("ttl_seconds"),
                    "freshness_reason": row.get("freshness_reason"),
                },
                what_i_saw=f"truth_state={truth_state} permission={permission} source_type={source_type}",
                what_i_understand="Fresh source truth may authorize; stale truth must refresh; historical memory can explain and teach only.",
            )
        return created

    def _materialize_paper_execution(self, conn: Any, *, limit: int) -> int:
        return self._materialize_run_table(
            conn,
            table="paper_execution_runs",
            id_col="run_id",
            ts_col="created_at",
            limit=limit,
            component="Paper Execution",
            component_type="paper_execution",
            event_type="brain_dialogue.paper_execution.run",
            message_builder=lambda r: (
                f"Paper Execution: I checked intents={r.get('intents_checked')}, executable={r.get('executable_intents')}, "
                f"created paper_orders={r.get('orders_created')}, paper_fills={r.get('fills_created')}, "
                f"paper_positions={r.get('positions_created')}. live_orders_delta={r.get('live_orders_delta')} real_orders_delta={r.get('real_orders_delta')}. "
                f"Status={r.get('status')}."
            ),
        )

    def _materialize_paper_positions(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "paper_positions"):
            return 0
        rows = conn.execute("SELECT * FROM paper_positions ORDER BY opened_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            payload = row.get("payload_json") or {}
            paper_position_id = str(row.get("id"))
            message = (
                f"Paper Execution: I opened paper_position={paper_position_id} from paper_intent={payload.get('source_intent_id')} "
                f"at entry={row.get('avg_entry')} side={row.get('intended_outcome')}. live_orders=0 and real_orders=0."
            )
            created += self._insert_event(
                conn,
                source_table="paper_positions",
                source_record_id=paper_position_id,
                timestamp=row.get("opened_at") or row.get("updated_at"),
                component="Paper Execution",
                component_type="paper_execution",
                event_type="brain_dialogue.paper_execution.position_opened",
                severity="INFO",
                market_id=row.get("market_id"),
                candidate_id=payload.get("eligibility_id"),
                risk_decision_id=payload.get("risk_decision_id"),
                exit_plan_id=payload.get("exit_plan_id"),
                eligibility_id=payload.get("eligibility_id"),
                paper_intent_id=payload.get("source_intent_id"),
                paper_order_id=str(payload.get("paper_order_id")) if payload.get("paper_order_id") else None,
                paper_fill_id=payload.get("paper_fill_id"),
                paper_position_id=paper_position_id,
                status=row.get("current_status"),
                decision="OPENED",
                human_message=message,
                raw_payload=row,
                evidence_used={"entry_price": row.get("avg_entry"), "quantity": row.get("size"), "price_basis": payload.get("price_basis")},
                what_i_saw="A paper position exists with paper-only lineage.",
                what_i_understand="Paper execution created simulated artifacts only; live and real execution remain off.",
            )
        return created

    def _materialize_paper_exit_loop(self, conn: Any, *, limit: int) -> int:
        return self._materialize_run_table(
            conn,
            table="paper_exit_loop_runs",
            id_col="run_id",
            ts_col="created_at",
            limit=limit,
            component="Paper Exit Loop",
            component_type="paper_exit",
            event_type="brain_dialogue.paper_exit.checked",
            message_builder=lambda r: (
                f"Paper Exit Loop: I checked open_positions={r.get('open_positions_checked')}, closed={r.get('closed_positions_count')}, "
                f"held_without_trigger={r.get('no_exit_condition_count')}, blocked_no_price={r.get('no_exit_price_count')}, "
                f"orphan_positions={r.get('orphan_positions_count')}. Status={r.get('status')}."
            ),
        )

    def _materialize_pnl_ledger(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "paper_daily_pnl"):
            return 0
        rows = conn.execute("SELECT * FROM paper_daily_pnl ORDER BY updated_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            message = (
                f"PnL Ledger: I calculated daily paper PnL for {row.get('pnl_date')}: realized={row.get('realized_pnl')}, "
                f"unrealized={row.get('unrealized_pnl')}, open_positions={row.get('open_positions_count')}, "
                f"closed_trades={row.get('closed_trades_count')}."
            )
            created += self._insert_event(
                conn,
                source_table="paper_daily_pnl",
                source_record_id=str(row["pnl_date"]),
                timestamp=row["updated_at"],
                component="PnL Ledger",
                component_type="paper_pnl",
                event_type="brain_dialogue.pnl.updated",
                severity="INFO",
                pnl_id=str(row.get("id")),
                status="UPDATED",
                decision="UPDATED",
                human_message=message,
                raw_payload=row,
                evidence_used={
                    "realized_pnl": row.get("realized_pnl"),
                    "unrealized_pnl": row.get("unrealized_pnl"),
                    "stale_price_count": row.get("stale_price_count"),
                },
                what_i_saw="A daily paper PnL ledger row exists.",
                what_i_understand="PnL is derived from paper ledger and open paper positions, not live trading.",
            )
        return created

    def _materialize_no_trade_ledger(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "no_trade_log"):
            return 0
        rows = conn.execute("SELECT * FROM no_trade_log ORDER BY updated_at DESC NULLS LAST, created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            blockers = _listify(row.get("blockers")) or _listify(row.get("missing_requirements")) or _listify(row.get("reasons_json"))
            message = (
                f"No-Trade Ledger: I recorded NO_TRADE for eligibility={row.get('eligibility_id')} market={row.get('market_id')} "
                f"category={row.get('no_trade_category') or row.get('primary_reason')}. Blockers={blockers}."
            )
            source_id = row.get("no_trade_id") or str(row.get("id"))
            created += self._insert_event(
                conn,
                source_table="no_trade_log",
                source_record_id=source_id,
                timestamp=row.get("updated_at") or row.get("created_at"),
                component="No-Trade Ledger",
                component_type="no_trade",
                event_type="brain_dialogue.no_trade.recorded",
                severity="WARN",
                market_id=row.get("market_id"),
                candidate_id=row.get("eligibility_id"),
                risk_decision_id=row.get("risk_decision_id"),
                exit_plan_id=row.get("exit_plan_id"),
                eligibility_id=row.get("eligibility_id"),
                status=row.get("no_trade_category") or row.get("decision_status") or "NO_TRADE",
                decision="NO_TRADE",
                block_reason=row.get("no_trade_reason") or row.get("primary_reason"),
                next_required_evidence=_listify(row.get("missing_requirements")),
                human_message=message,
                raw_payload=row,
                evidence_used=row.get("evidence") or {},
                what_i_saw=f"no_trade_category={row.get('no_trade_category') or row.get('primary_reason')}",
                what_i_understand="NO_TRADE is first-class and preserves exact reasons instead of disappearing blocked candidates.",
            )
        return created

    def _materialize_neuron_dialogue(self, conn: Any, *, limit: int) -> int:
        created = 0
        created += self._materialize_market_neuron(conn, limit=limit)
        created += self._materialize_orderbook_neuron(conn, limit=limit)
        created += self._materialize_trusted_orderbook_neuron(conn, limit=limit)
        created += self._materialize_liquidity_neuron(conn, limit=limit)
        created += self._materialize_time_neuron(conn, limit=limit)
        created += self._materialize_rules_neuron(conn, limit=limit)
        created += self._materialize_fees_neuron(conn, limit=limit)
        created += self._materialize_news_neuron(conn, limit=limit)
        created += self._materialize_social_neuron(conn, limit=limit)
        created += self._materialize_whale_neuron(conn, limit=limit)
        created += self._materialize_ai_context_neuron(conn, limit=limit)
        created += self._materialize_capital_neuron(conn, limit=limit)
        created += self._materialize_position_neuron(conn, limit=limit)
        return created

    def _materialize_market_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "market_snapshots"):
            return 0
        rows = conn.execute("SELECT * FROM market_snapshots ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            message = (
                f"Market Neuron: I observed market={row.get('market_id')} with yes_price={row.get('yes_price')}, "
                f"no_price={row.get('no_price')}, volume_24h={row.get('volume_24h')}, liquidity={row.get('liquidity')}, "
                f"and spread={row.get('spread')}."
            )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="market_snapshots",
                source_record_id=str(row["id"]),
                timestamp=row.get("created_at") or row.get("captured_at"),
                component="Market Neuron",
                event_type="brain_dialogue.neuron.market.observed",
                market_id=row.get("market_id"),
                status="OBSERVED",
                human_message=message,
                evidence_used={
                    "yes_price": row.get("yes_price"),
                    "no_price": row.get("no_price"),
                    "volume_24h": row.get("volume_24h"),
                    "liquidity": row.get("liquidity"),
                    "spread": row.get("spread"),
                },
                what_i_saw="A market snapshot row exists.",
                what_i_understand="Market price, volume, and liquidity context can be consumed by downstream brain and gate layers.",
            )
        return created

    def _materialize_orderbook_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "orderbook_snapshots"):
            return 0
        rows = conn.execute("SELECT * FROM orderbook_snapshots ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            stale = bool(row.get("is_stale"))
            status = "STALE" if stale else str(row.get("snapshot_status") or "FRESH")
            message = (
                f"Orderbook Neuron: I refreshed orderbook evidence for market={row.get('market_id')} token={row.get('token_id')}. "
                f"best_bid={row.get('best_bid')}, best_ask={row.get('best_ask')}, mid_price={row.get('mid_price')}, "
                f"spread={row.get('spread')}, stale={stale}. Risk Gate and Exit Cortex can consume this source-backed orderbook evidence."
            )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="orderbook_snapshots",
                source_record_id=row.get("orderbook_snapshot_id") or str(row.get("id")),
                timestamp=row.get("created_at") or row.get("collected_at"),
                component="Orderbook Neuron",
                event_type="brain_dialogue.neuron.orderbook.observed",
                market_id=row.get("market_id"),
                status=status,
                severity="WARN" if stale else "INFO",
                human_message=message,
                evidence_used={
                    "token_id": row.get("token_id"),
                    "side": row.get("side"),
                    "best_bid": row.get("best_bid"),
                    "best_ask": row.get("best_ask"),
                    "mid_price": row.get("mid_price"),
                    "spread": row.get("spread"),
                    "liquidity_score": row.get("liquidity_score"),
                    "stale_reason": row.get("stale_reason"),
                },
                block_reason=row.get("stale_reason") if stale else None,
                what_i_saw="An orderbook snapshot row exists.",
                what_i_understand="Fresh orderbook evidence is required by Risk, Exit, and Eligibility; stale snapshots remain blockers.",
            )
        return created

    def _materialize_trusted_orderbook_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "trusted_orderbook_evidence_links"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM trusted_orderbook_evidence_links
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            trusted = bool(row.get("trusted"))
            status = "TRUSTED" if trusted else str(row.get("trust_status") or "REJECTED")
            reason = row.get("trust_reason")
            message = (
                f"Orderbook Neuron: I linked trusted orderbook snapshot={row.get('orderbook_snapshot_id')} "
                f"to candidate={row.get('candidate_id')} for market={row.get('market_id')} side={row.get('side')} "
                f"expected_token={row.get('expected_token_id')}. best_bid={row.get('best_bid')}, "
                f"best_ask={row.get('best_ask')}, mid_price={row.get('mid_price')}, spread={row.get('spread')}. "
                "Risk Gate, Exit Cortex, and Eligibility Gate can consume this deterministic orderbook evidence."
                if trusted
                else
                f"Orderbook Neuron: I rejected orderbook evidence for candidate={row.get('candidate_id')} "
                f"market={row.get('market_id')} side={row.get('side')} because {reason}. "
                "Risk Gate, Exit Cortex, and Eligibility Gate must keep orderbook-dependent blockers active."
            )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="trusted_orderbook_evidence_links",
                source_record_id=row.get("link_id") or str(row.get("id")),
                timestamp=row.get("updated_at") or row.get("created_at"),
                component="Orderbook Neuron",
                event_type="brain_dialogue.neuron.orderbook.trusted" if trusted else "brain_dialogue.neuron.orderbook.rejected",
                market_id=row.get("market_id"),
                status=status,
                severity="INFO" if trusted else "WARN",
                human_message=message,
                evidence_used={
                    "candidate_id": row.get("candidate_id"),
                    "side": row.get("side"),
                    "expected_token_id": row.get("expected_token_id"),
                    "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
                    "orderbook_token_id": row.get("orderbook_token_id"),
                    "best_bid": row.get("best_bid"),
                    "best_ask": row.get("best_ask"),
                    "mid_price": row.get("mid_price"),
                    "spread": row.get("spread"),
                    "age_seconds": row.get("age_seconds"),
                    "freshness_threshold_seconds": row.get("freshness_threshold_seconds"),
                },
                block_reason=None if trusted else reason,
                next_required_evidence=[] if trusted else [reason or "TRUSTED_ORDERBOOK"],
                what_i_saw="A candidate-to-orderbook trust decision row exists.",
                what_i_understand=(
                    "This candidate has deterministic market, side, token, freshness, and price evidence."
                    if trusted
                    else "This candidate does not yet have deterministic trusted orderbook evidence."
                ),
            )
        return created

    def _materialize_polymarket_binding(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "polymarket_binding_candidate_traces"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM polymarket_binding_candidate_traces
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            category = str(row.get("exact_fix_category") or "UNKNOWN")
            trusted = bool(row.get("trust_link_id"))
            if trusted:
                message = (
                    f"Polymarket Binding: Candidate {row.get('candidate_id')} resolved {row.get('side')} "
                    f"token {row.get('expected_token_id')} from market {row.get('market_id')} "
                    f"condition {row.get('condition_id')}; trusted orderbook {row.get('snapshot_id')} was created."
                )
            elif category == "NO_SIDE":
                message = (
                    f"Polymarket Binding: Candidate {row.get('candidate_id')} cannot request CLOB book "
                    "because side is missing."
                )
            elif row.get("clob_token_book_check_attempted"):
                message = (
                    f"Polymarket Binding: Candidate {row.get('candidate_id')} requested CLOB book by token "
                    f"{row.get('expected_token_id')} for condition {row.get('condition_id')}; "
                    f"result={row.get('clob_book_status')}."
                )
            else:
                message = (
                    f"Polymarket Binding: Candidate {row.get('candidate_id')} remains blocked by {category}; "
                    "no CLOB orderbook was trusted."
                )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="polymarket_binding_candidate_traces",
                source_record_id=str(row.get("id")),
                timestamp=row.get("created_at"),
                component="Polymarket Binding",
                event_type="brain_dialogue.neuron.polymarket_binding.trusted" if trusted else "brain_dialogue.neuron.polymarket_binding.rejected",
                market_id=row.get("market_id"),
                status="TRUSTED" if trusted else "BLOCKED",
                severity="INFO" if trusted else "WARN",
                human_message=message,
                evidence_used={
                    "candidate_id": row.get("candidate_id"),
                    "source_signal_id": row.get("source_signal_id"),
                    "market_id": row.get("market_id"),
                    "condition_id": row.get("condition_id"),
                    "side": row.get("side"),
                    "expected_token_id": row.get("expected_token_id"),
                    "clob_book_status": row.get("clob_book_status"),
                    "snapshot_id": row.get("snapshot_id"),
                    "trust_link_id": row.get("trust_link_id"),
                },
                block_reason=None if trusted else category,
                next_required_evidence=[] if trusted else [category],
                what_i_saw="A Polymarket identity binding trace row exists.",
                what_i_understand="CLOB books must be requested by outcome token id and matched to the expected condition id.",
            )
        return created

    def _materialize_fresh_market_identity(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "fresh_market_identity_traces"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM fresh_market_identity_traces
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            status = str(row.get("identity_status") or "UNKNOWN")
            verified = status == "FRESH_VERIFIED"
            if verified:
                message = (
                    f"Fresh Market Identity: Candidate {row.get('candidate_id')} verified current market "
                    f"identity from Gamma for market {row.get('market_id')} and side {row.get('side')}."
                )
            elif status == "MISSING_SIDE":
                message = (
                    f"Fresh Market Identity: Candidate {row.get('candidate_id')} blocked because side is missing."
                )
            elif status == "STALE_MARKET":
                message = (
                    f"Fresh Market Identity: Candidate {row.get('candidate_id')} marked STALE_MARKET "
                    f"because current Gamma no longer returns market {row.get('market_id')}."
                )
            else:
                message = (
                    f"Fresh Market Identity: Candidate {row.get('candidate_id')} blocked by {status}; "
                    f"reason={row.get('reason')}."
                )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="fresh_market_identity_traces",
                source_record_id=str(row.get("id")),
                timestamp=row.get("created_at"),
                component="Fresh Market Identity",
                event_type="brain_dialogue.neuron.fresh_market_identity.verified" if verified else "brain_dialogue.neuron.fresh_market_identity.blocked",
                market_id=row.get("market_id"),
                status="VERIFIED" if verified else "BLOCKED",
                severity="INFO" if verified else "WARN",
                human_message=message,
                evidence_used={
                    "candidate_id": row.get("candidate_id"),
                    "market_id": row.get("market_id"),
                    "condition_id": row.get("condition_id"),
                    "side": row.get("side"),
                    "yes_token_id": row.get("yes_token_id"),
                    "no_token_id": row.get("no_token_id"),
                    "expected_token_id": row.get("expected_token_id"),
                    "gamma_lookup_status": row.get("gamma_lookup_status"),
                    "identity_source": row.get("identity_source"),
                },
                block_reason=None if verified else status,
                next_required_evidence=[] if verified else [status],
                what_i_saw="A fresh market identity gate trace row exists.",
                what_i_understand="Candidates need current Gamma-confirmed market identity before Paper can rely on side/token truth.",
            )
        return created

    def _materialize_polymarket_token_truth(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "polymarket_token_truth_traces"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM polymarket_token_truth_traces
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            classification = str(row.get("classification") or "UNKNOWN")
            verified = classification == "VERIFIED_BY_CLOB_BOOK"
            if verified:
                message = (
                    f"Polymarket Token Truth: Verified {row.get('side')} token "
                    f"{row.get('expected_token_id')} by CLOB book response asset_id match "
                    f"for market {row.get('market_id')}."
                )
            elif classification in {"TOKEN_NOT_FOUND", "CLOB_TOKEN_NOT_FOUND_DESPITE_GAMMA_TOKEN"}:
                message = (
                    f"Polymarket Token Truth: Rejected token {row.get('expected_token_id')} "
                    "because CLOB returned TOKEN_NOT_FOUND."
                )
            elif row.get("expected_token_id"):
                message = (
                    f"Polymarket Token Truth: Resolved {row.get('side')} token from Gamma field "
                    f"{row.get('gamma_field')} for market {row.get('market_id')}; "
                    f"classification={classification}."
                )
            else:
                message = (
                    f"Polymarket Token Truth: Candidate {row.get('candidate_id') or row.get('market_id')} "
                    f"blocked by {classification}; no token was trusted."
                )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="polymarket_token_truth_traces",
                source_record_id=str(row.get("id")),
                timestamp=row.get("created_at"),
                component="Polymarket Token Truth",
                event_type="brain_dialogue.neuron.polymarket_token_truth.verified" if verified else "brain_dialogue.neuron.polymarket_token_truth.rejected",
                market_id=row.get("market_id"),
                status="TRUSTED" if verified else "BLOCKED",
                severity="INFO" if verified else "WARN",
                human_message=message,
                evidence_used={
                    "candidate_id": row.get("candidate_id"),
                    "market_id": row.get("market_id"),
                    "condition_id": row.get("condition_id"),
                    "side": row.get("side"),
                    "expected_token_id": row.get("expected_token_id"),
                    "gamma_field": row.get("gamma_field"),
                    "clob_book_status": row.get("clob_book_status"),
                    "classification": classification,
                },
                block_reason=None if verified else classification,
                next_required_evidence=[] if verified else [classification],
                what_i_saw="A Polymarket token truth trace row exists.",
                what_i_understand="Outcome tokens must come from source-backed Gamma/CLOB identity and be verified by CLOB asset_id before trust.",
            )
        return created

    def _materialize_clob_token_book_verification(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "clob_token_book_verification_traces"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM clob_token_book_verification_traces
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            reason = str(row.get("rejection_reason") or "")
            verified = not reason and row.get("clob_book_status") == "OK"
            trace_type = str(row.get("trace_type") or "")
            if verified:
                message = (
                    f"CLOB Token Book Verification: Verified CLOB book for market {row.get('market_id')} "
                    f"side {row.get('side')} token {row.get('expected_token_id')}."
                )
            elif reason == "ASSET_ID_MISMATCH":
                message = (
                    f"CLOB Token Book Verification: Rejected token {row.get('expected_token_id')} "
                    "because CLOB response asset_id mismatch."
                )
            elif reason == "STALE_MARKET":
                message = (
                    f"CLOB Token Book Verification: Skipped candidate {row.get('candidate_id')} "
                    "because identity_status is STALE_MARKET."
                )
            elif trace_type == "fresh_seed":
                message = (
                    f"Fresh Candidate Seeder: Seeded current Gamma market {row.get('market_id')} "
                    f"side {row.get('side')} for future verification."
                )
            else:
                message = (
                    f"CLOB Token Book Verification: Rejected {row.get('seed_id') or row.get('candidate_id')} "
                    f"by {reason or row.get('clob_book_status')}."
                )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="clob_token_book_verification_traces",
                source_record_id=str(row.get("id")),
                timestamp=row.get("created_at"),
                component="CLOB Token Book Verification" if trace_type != "fresh_seed" else "Fresh Candidate Seeder",
                event_type="brain_dialogue.neuron.clob_token_book.verified" if verified else "brain_dialogue.neuron.clob_token_book.rejected",
                market_id=row.get("market_id"),
                status="TRUSTED" if verified else "BLOCKED",
                severity="INFO" if verified or trace_type == "fresh_seed" else "WARN",
                human_message=message,
                evidence_used={
                    "candidate_id": row.get("candidate_id"),
                    "seed_id": row.get("seed_id"),
                    "market_id": row.get("market_id"),
                    "condition_id": row.get("condition_id"),
                    "side": row.get("side"),
                    "expected_token_id": row.get("expected_token_id"),
                    "asset_id": row.get("asset_id"),
                    "response_market": row.get("response_market"),
                    "snapshot_id": row.get("snapshot_id"),
                    "trust_link_id": row.get("trust_link_id"),
                },
                block_reason=None if verified else reason or row.get("clob_book_status"),
                next_required_evidence=[] if verified else [reason or row.get("clob_book_status") or "CLOB_BOOK"],
                what_i_saw="A CLOB token book verification trace row exists.",
                what_i_understand="Only fresh identities or isolated fresh seeds can create trusted CLOB book evidence.",
            )
        return created

    def _materialize_live_orderbook_watcher(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "live_orderbook_watcher_traces"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM live_orderbook_watcher_traces
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            events = row.get("events_published_json") or []
            if isinstance(events, str):
                events = [events]
            spread = row.get("new_spread")
            liquidity = row.get("new_liquidity_score")
            reason = str(row.get("reason") or row.get("clob_status") or "OK")
            if "TOKEN_BOOK_UNAVAILABLE" in events:
                message = (
                    f"Live Orderbook Watcher: TOKEN_BOOK_UNAVAILABLE for token {row.get('token_id')} "
                    f"on market {row.get('market_id')}; reason={reason}."
                )
                event_type = "brain_dialogue.neuron.live_orderbook_watcher.token_unavailable"
                status = "DEGRADED"
                severity = "WARN"
                block_reason = reason
            elif "MARKET_RESOLVED" in events:
                message = (
                    f"Live Orderbook Watcher: MARKET_RESOLVED for market {row.get('market_id')} "
                    f"side {row.get('side')} token {row.get('token_id')}."
                )
                event_type = "brain_dialogue.neuron.live_orderbook_watcher.market_resolved"
                status = "RESOLVED"
                severity = "WARN"
                block_reason = reason
            elif "SPREAD_CHANGED" in events:
                message = (
                    f"Live Orderbook Watcher: SPREAD_CHANGED from {row.get('previous_spread')} "
                    f"to {row.get('new_spread')} for market {row.get('market_id')}."
                )
                event_type = "brain_dialogue.neuron.live_orderbook_watcher.spread_changed"
                status = "UPDATED"
                severity = "INFO"
                block_reason = None
            elif "LIQUIDITY_CHANGED" in events:
                message = (
                    f"Live Orderbook Watcher: LIQUIDITY_CHANGED from {row.get('previous_liquidity_score')} "
                    f"to {row.get('new_liquidity_score')} for market {row.get('market_id')}."
                )
                event_type = "brain_dialogue.neuron.live_orderbook_watcher.liquidity_changed"
                status = "UPDATED"
                severity = "INFO"
                block_reason = None
            elif "ORDERBOOK_REFRESHED" in events:
                message = (
                    f"Live Orderbook Watcher: ORDERBOOK_REFRESHED for market {row.get('market_id')} "
                    f"side {row.get('side')} token {row.get('token_id')}, spread {spread}."
                )
                event_type = "brain_dialogue.neuron.live_orderbook_watcher.refreshed"
                status = "UPDATED"
                severity = "INFO"
                block_reason = None
            else:
                message = (
                    f"Live Orderbook Watcher: Watching market {row.get('market_id')} side {row.get('side')} "
                    f"token {row.get('token_id')}; status={row.get('clob_status')}."
                )
                event_type = "brain_dialogue.neuron.live_orderbook_watcher.observed"
                status = "OBSERVED"
                severity = "INFO" if row.get("clob_status") == "OK" else "WARN"
                block_reason = None if row.get("clob_status") == "OK" else reason
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="live_orderbook_watcher_traces",
                source_record_id=str(row.get("id")),
                timestamp=row.get("created_at"),
                component="Live Orderbook Watcher",
                event_type=event_type,
                market_id=row.get("market_id"),
                status=status,
                severity=severity,
                human_message=message,
                evidence_used={
                    "run_id": row.get("run_id"),
                    "watch_id": row.get("watch_id"),
                    "market_id": row.get("market_id"),
                    "condition_id": row.get("condition_id"),
                    "side": row.get("side"),
                    "token_id": row.get("token_id"),
                    "new_snapshot_id": row.get("new_snapshot_id"),
                    "best_bid": row.get("new_best_bid"),
                    "best_ask": row.get("new_best_ask"),
                    "spread": spread,
                    "liquidity_score": liquidity,
                    "events": events,
                },
                block_reason=block_reason,
                next_required_evidence=[] if block_reason is None else [block_reason],
                what_i_saw="A live orderbook watcher trace row exists.",
                what_i_understand="The watcher is read-only: it refreshes verified CLOB token books and publishes source-backed events without trading authority.",
            )
        return created

    def _materialize_open_position_watchdog(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "open_position_watchdog_traces"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM open_position_watchdog_traces
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            reaction = str(row.get("reaction_type") or row.get("reason") or row.get("clob_status") or "OBSERVED")
            severity = row.get("severity") or ("INFO" if row.get("clob_status") == "OK" else "WARN")
            if reaction == "POSITION_TOKEN_LOCKED":
                message = f"Open Position Watchdog: Locked token {row.get('token_id')} for paper position {row.get('paper_position_id')}."
            elif reaction == "POSITION_ORDERBOOK_REFRESHED":
                message = f"Open Position Watchdog: POSITION_ORDERBOOK_REFRESHED for position {row.get('paper_position_id')} spread {row.get('current_spread')}."
            elif reaction == "POSITION_EXIT_RISK":
                message = f"Open Position Watchdog: POSITION_EXIT_RISK for position {row.get('paper_position_id')}; reason={row.get('reason') or 'watchdog risk evidence'}."
            elif reaction == "EXIT_REVIEW":
                message = f"Open Position Watchdog: EXIT_REVIEW for position {row.get('paper_position_id')}; no exit was executed."
            elif reaction == "HOLD_REVIEW":
                message = f"Open Position Watchdog: HOLD_REVIEW for position {row.get('paper_position_id')}."
            elif reaction == "TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION":
                message = f"Open Position Watchdog: TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION for token {row.get('token_id')}."
            else:
                message = f"Open Position Watchdog: Position {row.get('paper_position_id')} trace status={row.get('clob_status')}, reaction={reaction}."
            created += self._insert_event(
                conn,
                source_table="open_position_watchdog_traces",
                source_record_id=str(row.get("id")),
                timestamp=row.get("created_at"),
                component="Open Position Watchdog",
                component_type="open_position_watchdog",
                event_type="brain_dialogue.position.open_position_watchdog",
                severity=severity,
                market_id=row.get("market_id"),
                paper_position_id=row.get("paper_position_id"),
                status=reaction,
                decision="OBSERVE",
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "run_id": row.get("run_id"),
                    "lock_id": row.get("lock_id"),
                    "token_id": row.get("token_id"),
                    "snapshot_id": row.get("snapshot_id"),
                    "event_id": row.get("event_id"),
                },
                what_i_saw=f"Open position watchdog trace {row.get('id')} was recorded.",
                what_i_understand="The open position watchdog is observational: it locks entry tokens and publishes review signals without closing positions.",
            )
        return created

    def _materialize_fresh_seed_paper_path(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "fresh_seed_candidate_conversions"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM fresh_seed_candidate_conversions
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            status = str(row.get("status") or "UNKNOWN")
            if status == "PAPER_INTENT_CREATED":
                message = (
                    f"Fresh Seed Paper Path: Candidate {row.get('candidate_id')} created Paper Intent "
                    f"{row.get('paper_intent_id')} from seed {row.get('seed_id')}."
                )
                severity = "INFO"
                block_reason = None
            elif row.get("candidate_id"):
                message = (
                    f"Fresh Seed Paper Path: Seed {row.get('seed_id')} became candidate "
                    f"{row.get('candidate_id')} with status {status}."
                )
                severity = "INFO" if status in {"ELIGIBILITY_CREATED", "EXIT_CREATED", "RISK_CREATED", "THESIS_CREATED"} else "WARN"
                block_reason = row.get("blocker_reason")
            else:
                message = (
                    f"Fresh Seed Paper Path: Seed {row.get('seed_id')} blocked before candidate conversion; "
                    f"reason={row.get('blocker_reason') or status}."
                )
                severity = "WARN"
                block_reason = row.get("blocker_reason") or status
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="fresh_seed_candidate_conversions",
                source_record_id=str(row.get("conversion_id")),
                timestamp=row.get("updated_at") or row.get("created_at"),
                component="Fresh Seed Paper Path",
                event_type="brain_dialogue.neuron.fresh_seed_paper_path",
                market_id=row.get("market_id"),
                status=status,
                severity=severity,
                human_message=message,
                evidence_used={
                    "seed_id": row.get("seed_id"),
                    "candidate_id": row.get("candidate_id"),
                    "thesis_id": row.get("thesis_id"),
                    "risk_decision_id": row.get("risk_decision_id"),
                    "exit_plan_id": row.get("exit_plan_id"),
                    "eligibility_id": row.get("eligibility_id"),
                    "paper_intent_id": row.get("paper_intent_id"),
                    "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
                    "trusted_orderbook_link_id": row.get("trusted_orderbook_link_id"),
                },
                block_reason=block_reason,
                next_required_evidence=[] if status == "PAPER_INTENT_CREATED" else [block_reason or status],
                what_i_saw="A fresh seed Paper path conversion trace exists.",
                what_i_understand="Fresh verified seeds can enter Paper only through Risk, Exit, Eligibility, and Paper Intent gates.",
            )
        return created

    def _materialize_liquidity_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "liquidity_snapshots"):
            return 0
        rows = conn.execute("SELECT * FROM liquidity_snapshots ORDER BY snapshot_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            message = (
                f"Liquidity Neuron: I observed liquidity for market={row.get('market_id')} score={row.get('liquidity_score')}, "
                f"exit_quality={row.get('exit_quality')}, max_safe_size={row.get('max_safe_size')}, "
                f"and fill_probability={row.get('fill_probability')}."
            )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="liquidity_snapshots",
                source_record_id=row.get("liquidity_snapshot_id") or str(row.get("id")),
                timestamp=row.get("snapshot_at"),
                component="Liquidity Neuron",
                event_type="brain_dialogue.neuron.liquidity.observed",
                market_id=row.get("market_id"),
                status="OBSERVED",
                human_message=message,
                evidence_used={
                    "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
                    "liquidity_score": row.get("liquidity_score"),
                    "exit_quality": row.get("exit_quality"),
                    "max_safe_size": row.get("max_safe_size"),
                    "slippage_at_safe_size": row.get("slippage_at_safe_size"),
                    "fill_probability": row.get("fill_probability"),
                },
                what_i_saw="A liquidity snapshot row exists.",
                what_i_understand="Liquidity and exit-quality evidence constrain safe paper sizing and exit readiness.",
            )
        return created

    def _materialize_time_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "market_snapshots"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM market_snapshots
            WHERE time_to_close_seconds IS NOT NULL
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            seconds = row.get("time_to_close_seconds")
            status = "URGENT" if seconds is not None and int(seconds) <= 3600 else "OBSERVED"
            message = (
                f"Time Neuron: I observed market={row.get('market_id')} with time_to_close_seconds={seconds}. "
                f"Time risk status is {status}."
            )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="market_snapshots",
                source_record_id=str(row["id"]),
                timestamp=row.get("created_at") or row.get("captured_at"),
                component="Time Neuron",
                event_type="brain_dialogue.neuron.time.observed",
                market_id=row.get("market_id"),
                status=status,
                severity="WARN" if status == "URGENT" else "INFO",
                human_message=message,
                evidence_used={"time_to_close_seconds": seconds},
                what_i_saw="A market snapshot included time_to_close_seconds.",
                what_i_understand="Time-to-close evidence affects urgency, lockup risk, and max-hold constraints.",
            )
        return created

    def _materialize_rules_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "rules_analysis"):
            return 0
        rows = conn.execute("SELECT * FROM rules_analysis ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            blocked = bool(row.get("cannot_trade_reason"))
            message = (
                f"Rules / Wording Neuron: I analyzed rules for market={row.get('market_id')}. "
                f"wording_risk={row.get('wording_risk')}, dispute_risk={row.get('dispute_risk')}, "
                f"resolution_clarity={row.get('resolution_clarity')}, recommendation={row.get('recommendation')}."
            )
            if blocked:
                message += f" Cannot-trade reason={row.get('cannot_trade_reason')}."
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="rules_analysis",
                source_record_id=row.get("rules_analysis_id") or str(row.get("id")),
                timestamp=row.get("created_at"),
                component="Rules / Wording Neuron",
                event_type="brain_dialogue.neuron.rules.observed",
                market_id=row.get("market_id"),
                status="BLOCKED" if blocked else str(row.get("recommendation") or "OBSERVED"),
                severity="WARN" if blocked else "INFO",
                human_message=message,
                evidence_used={
                    "wording_risk": row.get("wording_risk"),
                    "dispute_risk": row.get("dispute_risk"),
                    "resolution_clarity": row.get("resolution_clarity"),
                    "compliance_status": row.get("compliance_status"),
                    "source_verification_status": row.get("source_verification_status"),
                },
                block_reason=row.get("cannot_trade_reason"),
                what_i_saw="A rules analysis row exists.",
                what_i_understand="Rules clarity, dispute risk, and compliance status are evidence for NO_TRADE and Risk blocks.",
            )
        return created

    def _materialize_fees_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "fee_snapshots"):
            return 0
        rows = conn.execute("SELECT * FROM fee_snapshots ORDER BY snapshot_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            message = (
                f"Fees / Rewards Neuron: I observed fee/reward evidence for market={row.get('market_id')}. "
                f"maker_fee={row.get('maker_fee')}, taker_fee={row.get('taker_fee')}, spread_cost={row.get('spread_cost')}, "
                f"slippage_cost={row.get('estimated_slippage_cost')}, net_edge_adjustment={row.get('net_edge_adjustment')}."
            )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="fee_snapshots",
                source_record_id=row.get("fee_snapshot_id") or str(row.get("id")),
                timestamp=row.get("snapshot_at"),
                component="Fees / Rewards Neuron",
                event_type="brain_dialogue.neuron.fees.observed",
                market_id=row.get("market_id"),
                status="OBSERVED",
                human_message=message,
                evidence_used={
                    "maker_fee": row.get("maker_fee"),
                    "taker_fee": row.get("taker_fee"),
                    "spread_cost": row.get("spread_cost"),
                    "estimated_slippage_cost": row.get("estimated_slippage_cost"),
                    "reward_pool": row.get("reward_pool"),
                    "net_edge_adjustment": row.get("net_edge_adjustment"),
                },
                what_i_saw="A fee snapshot row exists.",
                what_i_understand="Fees, rewards, spread cost, and slippage adjust net edge rather than create trade permission.",
            )
        return created

    def _materialize_news_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "news_normalized_events"):
            return 0
        rows = conn.execute("SELECT * FROM news_normalized_events ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            title = row.get("title") or row.get("normalized_title") or row.get("news_event_id")
            message = (
                f"News Neuron: I found a news event '{title}' from source={row.get('source_id')} "
                f"published_at={row.get('published_at')} with importance={row.get('importance_score')} and urgency={row.get('urgency_score')}."
            )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="news_normalized_events",
                source_record_id=row.get("news_event_id") or str(row.get("id")),
                timestamp=row.get("created_at") or row.get("collected_at") or row.get("published_at"),
                component="News Neuron",
                event_type="brain_dialogue.neuron.news.observed",
                status=str(row.get("status") or "OBSERVED"),
                human_message=message,
                evidence_used={
                    "source_id": row.get("source_id"),
                    "importance_score": row.get("importance_score"),
                    "urgency_score": row.get("urgency_score"),
                    "novelty_score": row.get("novelty_score"),
                    "source_reliability": row.get("source_reliability"),
                },
                what_i_saw="A normalized news event exists.",
                what_i_understand="News can affect market context only when source-backed and linked to markets.",
            )
        return created

    def _materialize_social_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "social_normalized_events"):
            return 0
        rows = conn.execute("SELECT * FROM social_normalized_events ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            message = (
                f"Social / Hype Neuron: I observed social activity on platform={row.get('platform')} from author={row.get('author_handle')}. "
                f"engagement_score={row.get('engagement_score')}, influence_score={row.get('influence_score')}, "
                f"spam_score={row.get('spam_score')}, bot_risk={row.get('bot_risk')}."
            )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="social_normalized_events",
                source_record_id=row.get("social_event_id") or str(row.get("id")),
                timestamp=row.get("created_at") or row.get("collected_at") or row.get("published_at"),
                component="Social / Hype Neuron",
                event_type="brain_dialogue.neuron.social.observed",
                status=str(row.get("status") or "OBSERVED"),
                human_message=message,
                evidence_used={
                    "platform": row.get("platform"),
                    "engagement_score": row.get("engagement_score"),
                    "influence_score": row.get("influence_score"),
                    "spam_score": row.get("spam_score"),
                    "bot_risk": row.get("bot_risk"),
                },
                what_i_saw="A normalized social event exists.",
                what_i_understand="Social evidence is useful only with noise and bot-risk context.",
            )
        return created

    def _materialize_whale_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "whale_events"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM whale_events
            ORDER BY COALESCE(event_time, event_timestamp, created_at) DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            message = (
                f"Whale Neuron: I observed whale activity for market={row.get('market_id')} wallet={row.get('wallet_address')}. "
                f"side={row.get('side') or row.get('side_or_outcome')}, action={row.get('action_type')}, "
                f"size={row.get('size')}, size_usd={row.get('size_usd')}, confidence={row.get('confidence')}."
            )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="whale_events",
                source_record_id=row.get("whale_event_id") or str(row.get("id")),
                timestamp=row.get("event_time") or row.get("event_timestamp") or row.get("created_at"),
                component="Whale Neuron",
                event_type="brain_dialogue.neuron.whale.observed",
                market_id=row.get("market_id"),
                status="OBSERVED",
                human_message=message,
                evidence_used={
                    "whale_id": row.get("whale_id"),
                    "side": row.get("side") or row.get("side_or_outcome"),
                    "action_type": row.get("action_type"),
                    "size": row.get("size"),
                    "size_usd": row.get("size_usd"),
                    "price": row.get("price"),
                    "confidence": row.get("confidence"),
                },
                what_i_saw="A whale event row exists.",
                what_i_understand="Whale activity is evidence, not permission; it must be weighed against noise and risk.",
            )
        return created

    def _materialize_ai_context_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "ai_decision_logs"):
            return 0
        rows = conn.execute("SELECT * FROM ai_decision_logs ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            message = (
                f"AI / Context Neuron: I observed AI decision log task={row.get('task_type')} decision={row.get('decision_type')} "
                f"for market={row.get('market_id')} with confidence={row.get('confidence')}. Secrets are not included."
            )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="ai_decision_logs",
                source_record_id=row.get("ai_decision_id") or str(row.get("id")),
                timestamp=row.get("created_at"),
                component="AI / Context Neuron",
                event_type="brain_dialogue.neuron.ai_context.observed",
                market_id=row.get("market_id"),
                status=str(row.get("decision_type") or "OBSERVED"),
                severity="WARN" if row.get("cannot_trade_reason") else "INFO",
                human_message=message,
                evidence_used={
                    "task_type": row.get("task_type"),
                    "decision_type": row.get("decision_type"),
                    "confidence": row.get("confidence"),
                    "risk_flags_json": row.get("risk_flags_json"),
                },
                block_reason=row.get("cannot_trade_reason"),
                what_i_saw="An AI decision log row exists.",
                what_i_understand="AI/context evidence can inform interpretation but cannot bypass deterministic gates.",
            )
        return created

    def _materialize_capital_neuron(self, conn: Any, *, limit: int) -> int:
        created = 0
        if _table_exists(conn, "paper_capital_ledger"):
            rows = conn.execute("SELECT * FROM paper_capital_ledger ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
            for row in rows:
                event_type = str(row.get("event_type") or "OBSERVED")
                if event_type == "CAPITAL_LOCKED_ON_FILL":
                    message = (
                        f"Capital Neuron: I locked paper capital amount={row.get('amount')} for paper_fill={row.get('paper_fill_id')} "
                        f"and paper_position={row.get('paper_position_id')}. available_after={row.get('available_after')} locked_after={row.get('locked_after')}."
                    )
                elif event_type in {"CAPITAL_RELEASED_ON_CLOSE", "CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE"}:
                    message = (
                        f"Capital Neuron: I released paper capital amount={row.get('amount')} for paper_close={row.get('paper_close_id')}. "
                        f"available_after={row.get('available_after')} locked_after={row.get('locked_after')}."
                    )
                elif event_type in {"REALIZED_PNL_APPLIED", "REALIZED_PNL_BACKFILLED_FROM_REAL_CLOSE"}:
                    message = (
                        f"Capital Neuron: I applied realized paper PnL delta={row.get('realized_pnl_delta')} "
                        f"from paper_close={row.get('paper_close_id')}. balance_after={row.get('balance_after')}."
                    )
                elif event_type.endswith("_BLOCK") or event_type == "DAILY_LOSS_GUARD_TRIGGERED":
                    message = (
                        f"Capital Neuron: I blocked paper execution reason={row.get('reason')} "
                        f"for paper_intent={row.get('paper_intent_id')}. No live or real order was created."
                    )
                else:
                    message = (
                        f"Capital Neuron: I observed paper capital event={event_type} amount={row.get('amount')} "
                        f"balance_after={row.get('balance_after')} available_after={row.get('available_after')}."
                    )
                created += self._insert_neuron_event(
                    conn,
                    row=row,
                    source_table="paper_capital_ledger",
                    source_record_id=row.get("ledger_id") or str(row.get("id")),
                    timestamp=row.get("created_at"),
                    component="Capital Neuron",
                    event_type=f"brain_dialogue.neuron.capital.{event_type.lower()}",
                    status=event_type,
                    severity="WARN" if event_type.endswith("_BLOCK") or event_type == "DAILY_LOSS_GUARD_TRIGGERED" else "INFO",
                    human_message=message,
                    evidence_used={
                        "account_id": row.get("account_id"),
                        "amount": row.get("amount"),
                        "balance_after": row.get("balance_after"),
                        "available_after": row.get("available_after"),
                        "locked_after": row.get("locked_after"),
                        "reason": row.get("reason"),
                    },
                    block_reason=row.get("reason") if event_type.endswith("_BLOCK") or event_type == "DAILY_LOSS_GUARD_TRIGGERED" else None,
                    what_i_saw="A paper capital ledger row exists.",
                    what_i_understand="Paper capital constrains simulated execution only; it does not enable live trading.",
                )
        if _table_exists(conn, "capital_state_v2"):
            rows = conn.execute("SELECT * FROM capital_state_v2 ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
            for row in rows:
                message = (
                    f"Capital Neuron: I observed capital state with available={row.get('available_capital')}, "
                    f"locked={row.get('locked_capital')}, total_exposure={row.get('total_exposure')}, mode={row.get('mode')}."
                )
                created += self._insert_neuron_event(
                    conn,
                    row=row,
                    source_table="capital_state_v2",
                    source_record_id=row.get("capital_state_id") or str(row.get("id")),
                    timestamp=row.get("created_at"),
                    component="Capital Neuron",
                    event_type="brain_dialogue.neuron.capital.observed",
                    status=str(row.get("status") or "OBSERVED"),
                    human_message=message,
                    evidence_used={
                        "available_capital": row.get("available_capital"),
                        "locked_capital": row.get("locked_capital"),
                        "total_exposure": row.get("total_exposure"),
                        "mode": row.get("mode"),
                    },
                    what_i_saw="A capital state row exists.",
                    what_i_understand="Capital state constrains sizing and exposure; it does not enable live trading.",
                )
        if _table_exists(conn, "capital_brain_outputs"):
            rows = conn.execute("SELECT * FROM capital_brain_outputs ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
            for row in rows:
                message = (
                    f"Capital Neuron: I observed capital brain output recommendation={row.get('recommendation')} "
                    f"for market={row.get('market_id')} amount={row.get('recommended_amount')}."
                )
                created += self._insert_neuron_event(
                    conn,
                    row=row,
                    source_table="capital_brain_outputs",
                    source_record_id=row.get("capital_output_id") or str(row.get("id")),
                    timestamp=row.get("created_at"),
                    component="Capital Neuron",
                    event_type="brain_dialogue.neuron.capital.output",
                    market_id=row.get("market_id"),
                    status=str(row.get("recommendation") or "OBSERVED"),
                    human_message=message,
                    evidence_used={
                        "recommendation": row.get("recommendation"),
                        "recommended_amount": row.get("recommended_amount"),
                        "risk_bucket": row.get("risk_bucket"),
                    },
                    what_i_saw="A capital brain output row exists.",
                    what_i_understand="Capital recommendations remain paper-safe and do not create execution.",
                )
        return created

    def _materialize_position_neuron(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "paper_positions"):
            return 0
        rows = conn.execute("SELECT * FROM paper_positions ORDER BY updated_at DESC NULLS LAST, opened_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
        created = 0
        for row in rows:
            message = (
                f"Position Neuron: I observed paper_position={row.get('id')} market={row.get('market_id')} "
                f"status={row.get('current_status')} side={row.get('intended_outcome')} entry={row.get('avg_entry')} "
                f"mark_price={row.get('mark_price')} unrealized_pnl={row.get('unrealized')}."
            )
            created += self._insert_neuron_event(
                conn,
                row=row,
                source_table="paper_positions",
                source_record_id=str(row.get("id")),
                timestamp=row.get("updated_at") or row.get("opened_at"),
                component="Position Neuron",
                event_type="brain_dialogue.neuron.position.observed",
                market_id=row.get("market_id"),
                paper_position_id=str(row.get("id")),
                status=str(row.get("current_status") or "OBSERVED"),
                human_message=message,
                evidence_used={
                    "intended_outcome": row.get("intended_outcome"),
                    "size": row.get("size"),
                    "avg_entry": row.get("avg_entry"),
                    "mark_price": row.get("mark_price"),
                    "unrealized": row.get("unrealized"),
                    "realized": row.get("realized"),
                },
                what_i_saw="A canonical paper position row exists.",
                what_i_understand="Position state is paper-only and supports exit/PnL observability without live execution.",
            )
        return created

    def _insert_neuron_event(
        self,
        conn: Any,
        *,
        row: dict[str, Any],
        source_table: str,
        source_record_id: str,
        timestamp: datetime,
        component: str,
        event_type: str,
        status: str,
        human_message: str,
        market_id: str | None = None,
        paper_position_id: str | None = None,
        severity: str = "INFO",
        evidence_used: dict[str, Any] | None = None,
        what_i_saw: str | None = None,
        what_i_understand: str | None = None,
        decision: str | None = None,
        block_reason: str | None = None,
        next_required_evidence: list[Any] | None = None,
    ) -> int:
        return self._insert_event(
            conn,
            source_table=source_table,
            source_record_id=source_record_id,
            timestamp=timestamp,
            component=component,
            component_type="neuron",
            event_type=event_type,
            severity=severity,
            market_id=market_id,
            paper_position_id=paper_position_id,
            status=status,
            decision=decision or status,
            block_reason=block_reason,
            next_required_evidence=next_required_evidence,
            human_message=human_message,
            raw_payload=row,
            evidence_used=evidence_used or {},
            what_i_saw=what_i_saw,
            what_i_understand=what_i_understand,
        )

    def _materialize_run_table(
        self,
        conn: Any,
        *,
        table: str,
        id_col: str,
        ts_col: str,
        limit: int,
        component: str,
        component_type: str,
        event_type: str,
        message_builder,
    ) -> int:
        if not _table_exists(conn, table):
            return 0
        rows = conn.execute(
            f"SELECT * FROM {table} ORDER BY {ts_col} DESC, id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            status = str(row.get("status") or "UNKNOWN")
            created += self._insert_event(
                conn,
                source_table=table,
                source_record_id=str(row[id_col]),
                cycle_id=row.get("cycle_id"),
                timestamp=row.get(ts_col) or row.get("started_at") or row.get("finished_at"),
                component=component,
                component_type=component_type,
                event_type=event_type,
                severity="INFO" if status in {"OK", "COMPLETED", "NO_VALID_PAPER_INTENTS", "NO_OPEN_PAPER_POSITIONS"} else "WARN",
                status=status,
                decision=status,
                block_reason=row.get("error_message") or row.get("error_summary") or row.get("blocked_reason"),
                human_message=message_builder(row),
                raw_payload=row,
                evidence_used=row.get("metadata_json") or {},
                what_i_saw=f"{table} source record {row[id_col]} status={status}",
                what_i_understand=f"{component} reported its own run summary.",
            )
        return created

    def _materialize_neural_events(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "neural_events"):
            return 0
        rows = conn.execute(
            """
            SELECT e.*,
                   COUNT(d.id) FILTER (WHERE d.delivery_status IN ('DELIVERED', 'REPLAYED')) AS computed_consumed_count
            FROM neural_events e
            LEFT JOIN neural_event_delivery d ON d.event_id = e.event_id
            GROUP BY e.id
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            event_type = str(row.get("event_type") or "UNKNOWN")
            component = str(row.get("source_component") or "Neural Bus")
            message = f"{component}: Published {event_type}"
            if row.get("market_id"):
                message += f" for market={row.get('market_id')}"
            if row.get("candidate_id"):
                message += f" candidate={row.get('candidate_id')}"
            created += self._insert_event(
                conn,
                source_table="neural_events",
                source_record_id=str(row["event_id"]),
                source_event_id=str(row["event_id"]),
                cycle_id=(row.get("metadata_json") or {}).get("cycle_id"),
                correlation_id=row.get("correlation_id"),
                timestamp=row.get("created_at"),
                component=component,
                component_type="neural_event",
                event_type="brain_dialogue.neural_event.published",
                severity="INFO",
                market_id=row.get("market_id"),
                candidate_id=row.get("candidate_id"),
                paper_position_id=row.get("position_id"),
                status=row.get("status") or "PUBLISHED",
                decision=event_type,
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "neural_event_id": row.get("event_id"),
                    "event_type": event_type,
                    "source_table": row.get("source_table"),
                    "source_record_id": row.get("source_record_id"),
                    "consumed_count": row.get("computed_consumed_count"),
                },
                what_i_saw=f"Neural event {row.get('event_id')} was appended to the V3 bus.",
                what_i_understand="Neural events transport source truth to interested organs; they do not become trading truth.",
            )
        return created

    def _materialize_mesh_sessions(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "mesh_sessions"):
            return 0
        created = 0
        sessions = conn.execute(
            """
            SELECT *
            FROM mesh_sessions
            ORDER BY opened_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        for row in sessions:
            entity = _session_entity_text(row)
            created += self._insert_event(
                conn,
                source_table="mesh_sessions",
                source_record_id=str(row["session_id"]),
                timestamp=row.get("opened_at"),
                component="Mesh Session",
                component_type="mesh_session",
                event_type="brain_dialogue.mesh_session.opened",
                severity="INFO",
                market_id=row.get("market_id"),
                candidate_id=row.get("candidate_id"),
                paper_position_id=row.get("position_id"),
                correlation_id=row.get("correlation_id"),
                status=row.get("status") or "OPEN",
                decision=row.get("session_type"),
                human_message=f"Mesh Session: Opened {row.get('session_type')} for {entity}",
                raw_payload=dict(row),
                evidence_used={
                    "session_id": row.get("session_id"),
                    "session_type": row.get("session_type"),
                    "event_count": row.get("event_count"),
                    "participant_count": row.get("participant_count"),
                },
                what_i_saw=f"Mesh session {row.get('session_id')} exists for {entity}.",
                what_i_understand="Mesh sessions organize source-backed neural events without becoming trading truth.",
            )
            if row.get("status") == "ACTIVE":
                created += self._insert_event(
                    conn,
                    source_table="mesh_sessions",
                    source_record_id=str(row["session_id"]),
                    timestamp=row.get("last_event_at") or row.get("opened_at"),
                    component="Mesh Session",
                    component_type="mesh_session",
                    event_type="brain_dialogue.mesh_session.active",
                    severity="INFO",
                    market_id=row.get("market_id"),
                    candidate_id=row.get("candidate_id"),
                    paper_position_id=row.get("position_id"),
                    correlation_id=row.get("correlation_id"),
                    status="ACTIVE",
                    decision=row.get("session_type"),
                    human_message=(
                        "Mesh Session: Session became ACTIVE after "
                        f"{row.get('event_count')} events and {row.get('participant_count')} participants."
                    ),
                    raw_payload=dict(row),
                    evidence_used={"session_id": row.get("session_id")},
                    what_i_saw=f"Mesh session {row.get('session_id')} has multiple events or participants.",
                    what_i_understand="ACTIVE means the room has more than a single source-backed observation.",
                )
        links = conn.execute(
            """
            SELECT se.*, s.session_type, s.market_id, s.candidate_id, s.position_id, s.correlation_id
            FROM mesh_session_events se
            JOIN mesh_sessions s ON s.session_id = se.session_id
            ORDER BY se.linked_at DESC, se.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        for row in links:
            target = _session_link_target(row)
            created += self._insert_event(
                conn,
                source_table="mesh_session_events",
                source_record_id=f"{row.get('session_id')}:{row.get('event_id')}",
                source_event_id=row.get("event_id"),
                timestamp=row.get("linked_at"),
                component="Mesh Session",
                component_type="mesh_session",
                event_type="brain_dialogue.mesh_session.event_linked",
                severity="INFO",
                market_id=row.get("market_id"),
                candidate_id=row.get("candidate_id"),
                paper_position_id=row.get("position_id"),
                correlation_id=row.get("correlation_id"),
                status="LINKED",
                decision=row.get("event_type"),
                human_message=f"Mesh Session: Linked {row.get('event_type')} to {target}",
                raw_payload=dict(row),
                evidence_used={
                    "session_id": row.get("session_id"),
                    "event_id": row.get("event_id"),
                    "role": row.get("role"),
                },
                what_i_saw=f"Neural event {row.get('event_id')} was linked into mesh session {row.get('session_id')}.",
                what_i_understand="A session link is conversational context only; it does not mutate the source event.",
            )
        return created

    def _materialize_shared_awareness(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "mesh_shared_awareness"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM mesh_shared_awareness
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            present = _awareness_present_domains(row)
            missing = row.get("missing_domains_json") or []
            stale = row.get("stale_domains_json") or []
            present_text = "/".join(present[:6]) if present else "no"
            message = f"Shared Awareness: Updated {row.get('session_type')} awareness with {present_text} evidence."
            if row.get("session_type") == "POSITION_SESSION" and "CAPITAL" in present:
                message = "Shared Awareness: Capital state attached to position session."
            created += self._insert_event(
                conn,
                source_table="mesh_shared_awareness",
                source_record_id=str(row["awareness_id"]),
                timestamp=row.get("updated_at"),
                component="Shared Awareness",
                component_type="shared_awareness",
                event_type="brain_dialogue.shared_awareness.updated",
                severity="INFO" if present else "WARN",
                market_id=row.get("market_id"),
                candidate_id=row.get("candidate_id"),
                paper_position_id=row.get("position_id"),
                status=row.get("freshness_status") or row.get("status"),
                decision=row.get("status"),
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "awareness_id": row.get("awareness_id"),
                    "session_id": row.get("session_id"),
                    "present_domains": present,
                    "missing_domains": missing,
                    "stale_domains": stale,
                },
                what_i_saw=f"Shared awareness {row.get('awareness_id')} was derived from session-linked source records.",
                what_i_understand="Shared Awareness is a derived visibility object, not a decision or trading truth.",
            )
            if missing:
                created += self._insert_event(
                    conn,
                    source_table="mesh_shared_awareness",
                    source_record_id=f"{row['awareness_id']}:missing",
                    timestamp=row.get("updated_at"),
                    component="Shared Awareness",
                    component_type="shared_awareness",
                    event_type="brain_dialogue.shared_awareness.missing_domains",
                    severity="WARN",
                    market_id=row.get("market_id"),
                    candidate_id=row.get("candidate_id"),
                    paper_position_id=row.get("position_id"),
                    status="MISSING",
                    decision="MISSING_DOMAINS",
                    human_message=f"Shared Awareness: {', '.join(missing[:6])} missing for session; domains remain MISSING.",
                    raw_payload=dict(row),
                    evidence_used={"awareness_id": row.get("awareness_id"), "missing_domains": missing},
                    what_i_saw=f"Shared awareness {row.get('awareness_id')} has missing domains.",
                    what_i_understand="Missing evidence is intentionally preserved as missing and is not inferred.",
                )
        return created

    def _materialize_capital_brain(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "capital_brain_evaluations"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM capital_brain_evaluations
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            decision = str(row.get("decision") or "CAPITAL_INSUFFICIENT_DATA")
            severity = "WARN" if decision in {"CAPITAL_BLOCK", "CAPITAL_RELEASE_REVIEW", "CAPITAL_INSUFFICIENT_DATA"} else "INFO"
            message = (
                f"Capital Brain: Available={row.get('available_balance')}, locked={row.get('locked_balance')}, "
                f"exposure={row.get('open_exposure')}. I {decision.lower().replace('_', ' ')} "
                f"session {row.get('session_id')} because {row.get('reason')}"
            )
            created += self._insert_event(
                conn,
                source_table="capital_brain_evaluations",
                source_record_id=str(row["evaluation_id"]),
                timestamp=row.get("created_at"),
                component="Capital Brain",
                component_type="capital_brain",
                event_type="brain_dialogue.capital_brain.evaluation",
                severity=severity,
                market_id=row.get("market_id"),
                candidate_id=row.get("candidate_id"),
                paper_position_id=row.get("position_id"),
                status=decision,
                decision=decision,
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "evaluation_id": row.get("evaluation_id"),
                    "session_id": row.get("session_id"),
                    "account_id": row.get("account_id"),
                    "capital_efficiency_score": row.get("capital_efficiency_score"),
                    "risk_flags": row.get("risk_flags_json") or [],
                    "missing_inputs": row.get("missing_inputs_json") or [],
                },
                what_i_saw=f"Capital evaluation {row.get('evaluation_id')} read paper account state and session awareness.",
                what_i_understand="Capital Brain evaluations are upstream constraints only; they do not lock or release capital.",
            )
        return created

    def _materialize_position_awareness(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "position_awareness"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM position_awareness
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            message = (
                f"Position Awareness: Position {row.get('position_id')} awareness updated. "
                f"PnL={row.get('pnl')}, risk={row.get('risk_status')}, exit={row.get('exit_status')}, "
                f"capital={row.get('capital_status')}."
            )
            created += self._insert_event(
                conn,
                source_table="position_awareness",
                source_record_id=str(row["awareness_id"]),
                timestamp=row.get("updated_at"),
                component="Position Awareness",
                component_type="position_awareness",
                event_type="brain_dialogue.position_awareness.updated",
                severity="WARN" if row.get("risk_status") in {"WORSENED", "CAUTION"} or row.get("exit_status") in {"DEGRADED", "CAUTION"} else "INFO",
                market_id=row.get("market_id"),
                paper_position_id=row.get("position_id"),
                status=str(row.get("coordinator_status") or "OBSERVE"),
                decision=str(row.get("capital_status") or "UNKNOWN"),
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "awareness_id": row.get("awareness_id"),
                    "position_id": row.get("position_id"),
                    "session_id": row.get("session_id"),
                    "awareness_score": row.get("awareness_score"),
                },
                what_i_saw=f"Position awareness {row.get('awareness_id')} summarized paper position {row.get('position_id')}.",
                what_i_understand="Position awareness is derived, non-executing position context for brains and coordinator visibility.",
            )
        if not _table_exists(conn, "position_reactions"):
            return created
        reactions = conn.execute(
            """
            SELECT *
            FROM position_reactions
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        for row in reactions:
            created += self._insert_event(
                conn,
                source_table="position_reactions",
                source_record_id=str(row["reaction_id"]),
                timestamp=row.get("created_at"),
                component="Position Awareness",
                component_type="position_awareness",
                event_type="brain_dialogue.position_awareness.reaction",
                severity=row.get("severity") or "INFO",
                paper_position_id=row.get("position_id"),
                status=row.get("reaction_type"),
                decision="OBSERVE",
                human_message=f"Position Awareness: Position {row.get('position_id')} received {row.get('reaction_type')}. {row.get('summary')}",
                raw_payload=dict(row),
                evidence_used={
                    "reaction_id": row.get("reaction_id"),
                    "session_id": row.get("session_id"),
                    "source_event_id": row.get("source_event_id"),
                    "source_domain": row.get("source_domain"),
                },
                what_i_saw=f"Position reaction {row.get('reaction_id')} was derived from source-backed position context.",
                what_i_understand="Position reactions are observations only; they do not close positions or create trades.",
            )
        return created

    def _materialize_multi_brain_consumption(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "mesh_brain_opinions"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM mesh_brain_opinions
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            consumed = row.get("consumed_domains_json") or []
            missing = row.get("missing_domains_json") or []
            stale = row.get("stale_domains_json") or []
            component = str(row.get("brain_name") or row.get("brain_type") or "Brain Opinion")
            message = f"{component}: Consumed {', '.join(consumed[:8]) if consumed else 'no domains'} and produced {row.get('stance')}."
            if row.get("brain_type") == "CONTEXT_BRAIN" and missing:
                message = f"{component}: Missing {', '.join(missing[:5])} remains explicit; produced {row.get('stance')}."
            created += self._insert_event(
                conn,
                source_table="mesh_brain_opinions",
                source_record_id=str(row["opinion_id"]),
                timestamp=row.get("created_at"),
                component=component,
                component_type="brain_opinion",
                event_type="brain_dialogue.multi_brain.opinion",
                severity="WARN" if row.get("stance") in {"BLOCK", "CAUTION"} else "INFO",
                market_id=row.get("market_id"),
                candidate_id=row.get("candidate_id"),
                paper_position_id=row.get("position_id"),
                status=row.get("stance") or "NO_SIGNAL",
                decision=row.get("decision_bias"),
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "opinion_id": row.get("opinion_id"),
                    "session_id": row.get("session_id"),
                    "brain_type": row.get("brain_type"),
                    "consumed_domains": consumed,
                    "missing_domains": missing,
                    "stale_domains": stale,
                    "supporting_sources": row.get("supporting_sources_json") or [],
                    "opposing_sources": row.get("opposing_sources_json") or [],
                },
                what_i_saw=f"{component} consumed shared awareness for session {row.get('session_id')}.",
                what_i_understand="Multi-brain opinions are derived consumption proof and do not create execution decisions.",
            )
        if not _table_exists(conn, "mesh_coordinator_input_bundles"):
            return created
        bundles = conn.execute(
            """
            SELECT *
            FROM mesh_coordinator_input_bundles
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        for row in bundles:
            conflicts = (row.get("stance_summary_json") or {}).get("conflicts") or []
            message = f"Coordinator Observer: Collected {row.get('source_brain_count')} brain opinions."
            if conflicts:
                message += f" Conflict detected: {conflicts[0].get('summary')}"
            created += self._insert_event(
                conn,
                source_table="mesh_coordinator_input_bundles",
                source_record_id=str(row["bundle_id"]),
                timestamp=row.get("created_at"),
                component="Coordinator Observer",
                component_type="coordinator_observer",
                event_type="brain_dialogue.multi_brain.bundle",
                severity="WARN" if row.get("conflicts_detected") else "INFO",
                market_id=row.get("market_id"),
                candidate_id=row.get("candidate_id"),
                paper_position_id=row.get("position_id"),
                status="CONFLICT" if row.get("conflicts_detected") else "READY" if row.get("coordinator_ready") else "OBSERVE",
                decision="COORDINATOR_INPUT_BUNDLE",
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "bundle_id": row.get("bundle_id"),
                    "session_id": row.get("session_id"),
                    "source_brain_count": row.get("source_brain_count"),
                    "opinion_count": row.get("opinion_count"),
                    "conflicts": conflicts,
                },
                what_i_saw=f"Coordinator input bundle {row.get('bundle_id')} collected session brain opinions.",
                what_i_understand="The Coordinator Observer bundles opinions for future Coordinator Evolution without making final decisions.",
            )
        return created

    def _materialize_mesh_coordinator_decisions(self, conn: Any, *, limit: int) -> int:
        if not _table_exists(conn, "mesh_coordinator_decisions"):
            return 0
        rows = conn.execute(
            """
            SELECT *
            FROM mesh_coordinator_decisions
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        created = 0
        for row in rows:
            final_stance = str(row.get("final_stance") or "UNKNOWN")
            final_action = str(row.get("final_action") or "UNKNOWN")
            severity = "WARN" if final_stance in {"BLOCK", "NO_TRADE", "INSUFFICIENT_DATA", "EXIT_RECOMMENDED"} else "INFO"
            message = f"Coordinator: Final mesh decision: {final_stance} with action {final_action} because {row.get('decision_reason')}"
            created += self._insert_event(
                conn,
                source_table="mesh_coordinator_decisions",
                source_record_id=str(row["decision_id"]),
                timestamp=row.get("created_at"),
                component="Coordinator",
                component_type="mesh_coordinator",
                event_type="brain_dialogue.mesh_coordinator.decision",
                severity=severity,
                market_id=row.get("market_id"),
                candidate_id=row.get("candidate_id"),
                paper_position_id=row.get("position_id"),
                status=final_stance,
                decision=final_action,
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "decision_id": row.get("decision_id"),
                    "session_id": row.get("session_id"),
                    "bundle_id": row.get("bundle_id"),
                    "source_brain_count": row.get("source_brain_count"),
                    "opinion_count": row.get("opinion_count"),
                    "winning_brains": row.get("winning_brains_json") or [],
                    "losing_brains": row.get("losing_brains_json") or [],
                },
                what_i_saw=f"Mesh coordinator decision {row.get('decision_id')} judged source-backed brain opinions.",
                what_i_understand="Mesh coordinator decisions are derived, non-executing judgments and do not mutate trading truth.",
            )
        if not _table_exists(conn, "mesh_conflict_records"):
            return created
        conflicts = conn.execute(
            """
            SELECT *
            FROM mesh_conflict_records
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        for row in conflicts:
            message = (
                f"Coordinator: Conflict detected: {row.get('brain_a')} {row.get('stance_a')} "
                f"vs {row.get('brain_b')} {row.get('stance_b')}. {row.get('winner')} wins."
            )
            created += self._insert_event(
                conn,
                source_table="mesh_conflict_records",
                source_record_id=str(row["conflict_id"]),
                timestamp=row.get("created_at"),
                component="Coordinator",
                component_type="mesh_coordinator",
                event_type="brain_dialogue.mesh_coordinator.conflict",
                severity="WARN",
                status=row.get("resolution"),
                decision=row.get("winner"),
                human_message=message,
                raw_payload=dict(row),
                evidence_used={
                    "conflict_id": row.get("conflict_id"),
                    "decision_id": row.get("decision_id"),
                    "session_id": row.get("session_id"),
                    "winner": row.get("winner"),
                },
                what_i_saw=f"Conflict {row.get('conflict_id')} was recorded from mesh brain opinions.",
                what_i_understand="The coordinator records conflict resolution rules but does not execute actions in this phase.",
            )
        return created

    def _insert_event(
        self,
        conn: Any,
        *,
        source_table: str,
        source_record_id: str,
        timestamp: datetime,
        component: str,
        component_type: str,
        event_type: str,
        severity: str,
        status: str,
        human_message: str,
        raw_payload: dict[str, Any],
        source_event_id: str | None = None,
        cycle_id: str | None = None,
        correlation_id: str | None = None,
        market_id: str | None = None,
        candidate_id: str | None = None,
        signal_id: str | None = None,
        risk_decision_id: str | None = None,
        exit_plan_id: str | None = None,
        eligibility_id: str | None = None,
        paper_intent_id: str | None = None,
        paper_order_id: str | None = None,
        paper_fill_id: str | None = None,
        paper_position_id: str | None = None,
        pnl_id: str | None = None,
        inputs_received: dict[str, Any] | None = None,
        evidence_used: dict[str, Any] | None = None,
        agrees_with: list[Any] | None = None,
        conflicts_with: list[Any] | None = None,
        what_i_saw: str | None = None,
        what_i_understand: str | None = None,
        decision: str | None = None,
        block_reason: str | None = None,
        next_required_evidence: list[Any] | None = None,
    ) -> int:
        result = conn.execute(
            """
            INSERT INTO brain_dialogue_events (
                dialogue_id, source_event_id, source_table, source_record_id,
                cycle_id, correlation_id, timestamp, component, component_type,
                event_type, severity, market_id, candidate_id, signal_id,
                risk_decision_id, exit_plan_id, eligibility_id, paper_intent_id,
                paper_order_id, paper_fill_id, paper_position_id, pnl_id,
                inputs_received_json, evidence_used_json, agrees_with_json,
                conflicts_with_json, what_i_saw, what_i_understand, decision,
                status, block_reason, next_required_evidence_json, human_message,
                raw_payload_json
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s
            )
            ON CONFLICT (source_table, source_record_id, event_type) DO NOTHING
            """,
            (
                f"brain_dialogue_{uuid4().hex}",
                source_event_id,
                source_table,
                str(source_record_id),
                cycle_id,
                correlation_id,
                _as_aware(timestamp),
                component,
                component_type,
                event_type,
                severity,
                market_id,
                candidate_id,
                signal_id,
                risk_decision_id,
                exit_plan_id,
                eligibility_id,
                paper_intent_id,
                paper_order_id,
                paper_fill_id,
                paper_position_id,
                pnl_id,
                Jsonb(_json_safe(inputs_received or {})),
                Jsonb(_json_safe(evidence_used or {})),
                Jsonb(_json_safe(agrees_with or [])),
                Jsonb(_json_safe(conflicts_with or [])),
                what_i_saw,
                what_i_understand,
                decision,
                status,
                block_reason,
                Jsonb(_json_safe(next_required_evidence or [])),
                human_message,
                Jsonb(_json_safe(raw_payload)),
            ),
        )
        return int(result.rowcount or 0)


def _component_specs() -> list[dict[str, Any]]:
    return [
        {"key": "system_power", "component": "SystemPower", "table": "system_power_transitions", "timestamp_col": "created_at", "wired": True},
        {"key": "market_service", "component": "MarketService", "table": "runtime_cycles_v2", "timestamp_col": "started_at", "wired": True},
        {"key": "data_foundation", "component": "DataFoundation", "table": "event_log", "timestamp_col": "stored_at", "where": "source_service = 'data_foundation'", "wired": True},
        {"key": "brain_mesh_activation", "component": "Brain Mesh Activation", "table": "brain_mesh_activation_runs", "timestamp_col": "created_at", "wired": True},
        {"key": "evidence_refresh", "component": "Evidence Refresh", "table": "evidence_refresh_runs", "timestamp_col": "created_at", "wired": True},
        {"key": "side_evidence", "component": "Side Evidence", "table": "side_evidence_recovery_runs", "timestamp_col": "created_at", "wired": True},
        {"key": "downstream_recompute", "component": "Downstream Evidence Recompute", "table": "downstream_evidence_recompute_runs", "timestamp_col": "created_at", "wired": True},
        {"key": "risk_exit_readiness", "component": "Risk Exit Readiness Recovery", "table": "post_side_risk_exit_recovery_runs", "timestamp_col": "created_at", "wired": True},
        {"key": "risk_gate", "component": "Risk Gate", "table": "risk_decisions", "timestamp_col": "updated_at", "wired": True},
        {"key": "risk_evidence_mesh", "component": "Risk Evidence Mesh", "table": "risk_evidence_mesh_evaluations", "timestamp_col": "created_at", "wired": True},
        {"key": "exit_cortex", "component": "Exit Cortex", "table": "exit_plans", "timestamp_col": "updated_at", "wired": True},
        {"key": "eligibility_gate", "component": "Eligibility Gate", "table": "paper_eligibility_candidates", "timestamp_col": "updated_at", "wired": True},
        {"key": "same_market_guard", "component": "Same-Market Guard", "table": "same_market_side_guard_decisions", "timestamp_col": "created_at", "wired": True},
        {"key": "payout_odds", "component": "Payout/Odds", "table": "payout_odds_evaluations", "timestamp_col": "created_at", "wired": True},
        {"key": "exit_hold", "component": "Exit/Hold", "table": "exit_hold_evaluations", "timestamp_col": "created_at", "wired": True},
        {"key": "capital_efficiency", "component": "Capital Efficiency", "table": "capital_efficiency_evaluations", "timestamp_col": "created_at", "wired": True},
        {"key": "trade_lifecycle", "component": "Trade Lifecycle", "table": "trade_lifecycle_plans", "timestamp_col": "created_at", "wired": True},
        {"key": "lifecycle_governance", "component": "Lifecycle Governance", "table": "lifecycle_governance_decisions", "timestamp_col": "created_at", "wired": True},
        {"key": "truth_state", "component": "Truth State", "table": "truth_state_registry", "timestamp_col": "updated_at", "wired": True},
        {"key": "paper_intent_gate", "component": "Paper Intent Gate", "table": "paper_intent_runs", "timestamp_col": "created_at", "wired": True},
        {"key": "paper_execution", "component": "Paper Execution", "table": "paper_execution_runs", "timestamp_col": "created_at", "wired": True},
        {"key": "paper_exit_loop", "component": "Paper Exit Loop", "table": "paper_exit_loop_runs", "timestamp_col": "created_at", "wired": True},
        {"key": "pnl_ledger", "component": "PnL Ledger", "table": "paper_daily_pnl", "timestamp_col": "updated_at", "wired": True},
        {"key": "no_trade_ledger", "component": "No-Trade Ledger", "table": "no_trade_log", "timestamp_col": "updated_at", "fallback_timestamp_col": "created_at", "wired": True},
        {"key": "capital_brain", "component": "Capital Brain", "table": "capital_brain_evaluations", "timestamp_col": "created_at", "wired": True},
        {"key": "position_awareness", "component": "Position Awareness", "table": "position_awareness", "timestamp_col": "updated_at", "wired": True},
        {"key": "mesh_coordinator", "component": "Coordinator", "table": "mesh_coordinator_decisions", "timestamp_col": "created_at", "wired": True},
        {"key": "dashboard_truth", "component": "Dashboard Truth", "table": None, "timestamp_col": None, "wired": False},
    ]


def _neuron_specs() -> list[dict[str, Any]]:
    return [
        {
            "key": "news_neuron",
            "neuron_name": "news",
            "component": "News Neuron",
            "sources": [
                {"table": "news_normalized_events", "timestamp_col": "created_at"},
                {"table": "news_raw_events", "timestamp_col": "collected_at"},
                {"table": "news_market_links", "timestamp_col": "created_at"},
            ],
        },
        {
            "key": "social_hype_neuron",
            "neuron_name": "social",
            "component": "Social / Hype Neuron",
            "sources": [
                {"table": "social_normalized_events", "timestamp_col": "created_at"},
                {"table": "social_raw_events", "timestamp_col": "collected_at"},
                {"table": "social_market_links", "timestamp_col": "created_at"},
            ],
        },
        {
            "key": "whale_neuron",
            "neuron_name": "whale",
            "component": "Whale Neuron",
            "sources": [
                {"table": "whale_events", "timestamp_col": "event_time", "fallback_timestamp_col": "event_timestamp", "second_fallback_timestamp_col": "created_at"},
                {"table": "whale_scan_runs", "timestamp_col": "ended_at", "fallback_timestamp_col": "started_at", "second_fallback_timestamp_col": "created_at"},
                {"table": "whale_market_scores", "timestamp_col": "computed_at", "fallback_timestamp_col": "created_at"},
            ],
        },
        {"key": "market_neuron", "neuron_name": "market", "component": "Market Neuron", "sources": [{"table": "market_snapshots", "timestamp_col": "created_at"}, {"table": "markets_v2", "timestamp_col": "updated_at", "fallback_timestamp_col": "last_seen_at"}]},
        {"key": "orderbook_neuron", "neuron_name": "orderbook", "component": "Orderbook Neuron", "sources": [{"table": "orderbook_snapshots", "timestamp_col": "created_at"}]},
        {"key": "liquidity_neuron", "neuron_name": "liquidity", "component": "Liquidity Neuron", "sources": [{"table": "liquidity_snapshots", "timestamp_col": "snapshot_at"}, {"table": "liquidity_signals", "timestamp_col": "created_at"}]},
        {"key": "time_neuron", "neuron_name": "time", "component": "Time Neuron", "sources": [{"table": "market_snapshots", "timestamp_col": "created_at"}, {"table": "market_lifecycle_events", "timestamp_col": "event_at"}]},
        {"key": "rules_wording_neuron", "neuron_name": "rules", "component": "Rules / Wording Neuron", "sources": [{"table": "rules_analysis", "timestamp_col": "created_at"}, {"table": "market_rules", "timestamp_col": "updated_at", "fallback_timestamp_col": "created_at"}, {"table": "wording_risk_scores", "timestamp_col": "created_at"}]},
        {"key": "fees_rewards_neuron", "neuron_name": "fees", "component": "Fees / Rewards Neuron", "sources": [{"table": "fee_snapshots", "timestamp_col": "snapshot_at"}, {"table": "fee_reward_signals", "timestamp_col": "created_at"}]},
        {"key": "ai_context_neuron", "neuron_name": "ai", "component": "AI / Context Neuron", "sources": [{"table": "ai_decision_logs", "timestamp_col": "created_at"}, {"table": "ai_responses", "timestamp_col": "created_at"}, {"table": "brain_outputs", "timestamp_col": "created_at"}]},
        {"key": "capital_neuron", "neuron_name": "capital", "component": "Capital Neuron", "sources": [{"table": "capital_state_v2", "timestamp_col": "created_at"}, {"table": "capital_brain_outputs", "timestamp_col": "created_at"}]},
        {"key": "position_neuron", "neuron_name": "position", "component": "Position Neuron", "sources": [{"table": "paper_positions", "timestamp_col": "updated_at", "fallback_timestamp_col": "opened_at"}, {"table": "paper_trade_ledger", "timestamp_col": "created_at"}]},
    ]


def _query_events(conn: Any, **kwargs: Any) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for key in ("component", "market_id", "candidate_id", "paper_position_id", "severity", "component_type", "status"):
        if kwargs.get(key):
            clauses.append(f"{key} = %s")
            params.append(kwargs[key])
    if kwargs.get("silent") is True:
        clauses.append("status IN ('SILENT_STALE', 'SILENT_NO_SOURCE_RECORD', 'MISSING_SOURCE', 'DISABLED', 'NOT_WIRED')")
    elif kwargs.get("silent") is False:
        clauses.append("status NOT IN ('SILENT_STALE', 'SILENT_NO_SOURCE_RECORD', 'MISSING_SOURCE', 'DISABLED', 'NOT_WIRED')")
    if kwargs.get("since"):
        clauses.append("timestamp >= %s")
        params.append(kwargs["since"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(kwargs.get("limit", 100))
    return conn.execute(
        f"""
        SELECT *
        FROM brain_dialogue_events
        {where}
        ORDER BY timestamp DESC, id DESC
        LIMIT %s
        """,
        params,
    ).fetchall()


def _latest_source_at(conn: Any, spec: dict[str, Any]) -> datetime | None:
    if not spec.get("table") or not spec.get("timestamp_col"):
        return None
    if not _table_exists(conn, spec["table"]):
        return None
    timestamp_col = spec["timestamp_col"]
    fallback = spec.get("fallback_timestamp_col")
    expr = f"COALESCE({timestamp_col}, {fallback})" if fallback else timestamp_col
    where = f"WHERE {spec['where']}" if spec.get("where") else ""
    row = conn.execute(f"SELECT MAX({expr}) AS latest FROM {spec['table']} {where}").fetchone()
    return row["latest"] if row else None


def _latest_neuron_source_at(conn: Any, spec: dict[str, Any]) -> datetime | None:
    latest: datetime | None = None
    for source in spec.get("sources", []):
        if not _table_exists(conn, source["table"]):
            continue
        timestamp_col = source["timestamp_col"]
        fallback = source.get("fallback_timestamp_col")
        second_fallback = source.get("second_fallback_timestamp_col")
        if fallback and second_fallback:
            expr = f"COALESCE({timestamp_col}, {fallback}, {second_fallback})"
        elif fallback:
            expr = f"COALESCE({timestamp_col}, {fallback})"
        else:
            expr = timestamp_col
        row = conn.execute(f"SELECT MAX({expr}) AS latest FROM {source['table']}").fetchone()
        candidate = row["latest"] if row else None
        if candidate and (latest is None or _as_aware(candidate) > _as_aware(latest)):
            latest = candidate
    return latest


def _neuron_registry_row(conn: Any, neuron_name: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "neuron_registry"):
        return None
    row = conn.execute(
        """
        SELECT *
        FROM neuron_registry
        WHERE neuron_name = %s
        LIMIT 1
        """,
        (neuron_name,),
    ).fetchone()
    return dict(row) if row else None


def _latest_dialogue_for_component(conn: Any, component: str) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT *
        FROM brain_dialogue_events
        WHERE component = %s
        ORDER BY timestamp DESC, id DESC
        LIMIT 1
        """,
        (component,),
    ).fetchone()


def _dialogue_count_for_component(conn: Any, component: str, *, since: datetime) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM brain_dialogue_events
        WHERE component = %s AND timestamp >= %s
        """,
        (component, since),
    ).fetchone()
    return int(row["count"] or 0)


def _components_speaking(conn: Any, *, window: timedelta) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT component) AS count
        FROM brain_dialogue_events
        WHERE timestamp >= %s
        """,
        (datetime.now(UTC) - window,),
    ).fetchone()
    return int(row["count"] or 0)


def _top_current_blockers(conn: Any) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for table, column in (
        ("paper_eligibility_candidates", "eligibility_blockers"),
        ("risk_decisions", "blockers"),
        ("exit_plans", "blockers"),
        ("no_trade_log", "blockers"),
    ):
        if not _table_exists(conn, table):
            continue
        rows = conn.execute(f"SELECT {column} AS blockers FROM {table} ORDER BY id DESC LIMIT 500").fetchall()
        for row in rows:
            counter.update(_listify(row.get("blockers")))
    return [{"blocker": key, "count": count} for key, count in counter.most_common(10)]


def _safety_counts(conn: Any) -> dict[str, Any]:
    live_orders = 0
    real_orders = 0
    if _table_exists(conn, "orders_v2"):
        live_orders = _count_where(conn, "orders_v2", "execution_mode IN ('LIVE', 'SMALL_LIVE', 'ATTACK_MODE')")
        real_orders = _count_where(conn, "orders_v2", "COALESCE(execution_mode, '') NOT IN ('PAPER_SIM', 'PAPER', 'DATA_ONLY', '')")
    return {
        "live_orders": live_orders,
        "real_orders": real_orders,
        "live_enabled": False,
        "shadow_enabled": False,
    }


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"] or 0)


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()
    return int(row["count"] or 0)


def _max_timestamp(conn: Any, table: str, column: str) -> datetime | None:
    if not _table_exists(conn, table):
        return None
    row = conn.execute(f"SELECT MAX({column}) AS latest FROM {table}").fetchone()
    return row["latest"] if row else None


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
    return bool(row and row["name"])


def _parse_since(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_aware(parsed)


def _slug(value: Any) -> str:
    return str(value or "unknown").lower().replace(" / ", "_").replace(" ", "_").replace("-", "_")


def _session_entity_text(row: dict[str, Any]) -> str:
    for key in ("position_id", "candidate_id", "market_id", "correlation_id"):
        if row.get(key):
            return f"{key}={row.get(key)}"
    return f"session_id={row.get('session_id')}"


def _session_link_target(row: dict[str, Any]) -> str:
    session_type = str(row.get("session_type") or "mesh session").lower().replace("_", " ")
    for key in ("position_id", "candidate_id", "market_id", "correlation_id"):
        if row.get(key):
            return f"{session_type} {key}={row.get(key)}"
    return f"{session_type} {row.get('session_id')}"


def _awareness_present_domains(row: dict[str, Any]) -> list[str]:
    domains = {
        "NEWS": row.get("news_state_json"),
        "WHALE": row.get("whale_state_json"),
        "SOCIAL": row.get("social_state_json"),
        "RULES": row.get("rules_state_json"),
        "LIQUIDITY": row.get("liquidity_state_json"),
        "ORDERBOOK": row.get("orderbook_state_json"),
        "FEES": row.get("fees_state_json"),
        "TIME": row.get("time_state_json"),
        "RISK": row.get("risk_state_json"),
        "EXIT": row.get("exit_state_json"),
        "CAPITAL": row.get("capital_state_json"),
        "PNL": row.get("pnl_state_json"),
        "MEMORY": row.get("memory_state_json"),
        "POSITION": row.get("position_state_json"),
        "CANDIDATE": row.get("candidate_state_json"),
    }
    return [
        domain
        for domain, state in domains.items()
        if isinstance(state, dict) and state.get("status") in {"PRESENT", "PARTIAL", "STALE"}
    ]


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, dict):
        items: list[str] = []
        for key, item in value.items():
            if isinstance(item, int):
                items.extend([str(key)] * item)
            elif item:
                items.append(str(key))
        return items
    if isinstance(value, str):
        return [value] if value else []
    return [str(value)]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _empty_feed() -> dict[str, Any]:
    return {
        "mock_data": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "system_power": "OFF",
        "events": [],
        "total_events": 0,
        "components_speaking": 0,
        "components_silent": len(_component_specs()),
        "latest_event_at": None,
        "safety": {"live_orders": 0, "real_orders": 0, "live_enabled": False, "shadow_enabled": False},
    }


def _empty_life() -> dict[str, Any]:
    return {
        "mock_data": False,
        "system_power": "OFF",
        "runtime_work_allowed": False,
        "components": [],
        "neuron_coverage": {
            "total_neurons": 0,
            "neuron_components_speaking": 0,
            "neuron_components_silent": 0,
            "neuron_components_missing": 0,
            "neuron_components_disabled": 0,
            "last_neuron_dialogue_at": None,
            "neurons": [],
        },
        "total_neurons": 0,
        "neuron_components_speaking": 0,
        "neuron_components_silent": 0,
        "neuron_components_missing": 0,
        "neuron_components_disabled": 0,
        "last_neuron_dialogue_at": None,
        "active_components": 0,
        "silent_components": 0,
        "stale_components": 0,
        "top_current_blockers": [],
        "open_paper_positions": 0,
        "live_orders": 0,
        "real_orders": 0,
    }

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.paper_intents import NoTradeLedgerRecord, PaperIntent, PaperIntentRun
from app.repositories.paper_intent_repository import (
    PaperIntentRepository,
    no_trade_record_from_row,
    paper_intent_from_row,
)
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.lifecycle_governance import LifecycleGovernanceGateService
from app.services.opportunity_memory import OpportunityMemoryService
from app.services.paper_runtime_decisions import PaperRuntimeDecisionService
from app.services.paper_session import active_paper_session_id as _active_paper_session_id
from app.services.payout_odds import PayoutOddsService
from app.services.same_market_side_guard import SameMarketSideGuardService
from app.services.system_power import SystemPowerService


SAFE_PAPER_NOTIONAL = Decimal("5.00")
MAX_SAFE_PAPER_QUANTITY = Decimal("10.0")


class PaperIntentGateService:
    """Non-executing Paper Intent Gate plus No-Trade ledger.

    This gate is deliberately one step before Paper execution. It can create
    durable Paper intents for fully eligible candidates, or durable NO_TRADE
    records for every candidate that fails a hard requirement. It never creates
    order intents, orders, fills, positions, or live actions.
    """

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: PaperIntentRepository | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        same_market_guard: SameMarketSideGuardService | None = None,
        payout_odds: PayoutOddsService | None = None,
        lifecycle_governance: LifecycleGovernanceGateService | None = None,
        paper_runtime_decisions: PaperRuntimeDecisionService | None = None,
        paper_actionability: Any | None = None,
        opportunity_memory: OpportunityMemoryService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or PaperIntentRepository()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._same_market_guard = same_market_guard or SameMarketSideGuardService(connection_factory=self._factory)
        self._payout_odds = payout_odds or PayoutOddsService(connection_factory=self._factory)
        self._lifecycle_governance = lifecycle_governance or LifecycleGovernanceGateService(connection_factory=self._factory)
        self._paper_runtime_decisions = paper_runtime_decisions or PaperRuntimeDecisionService(connection_factory=self._factory)
        self._paper_actionability = paper_actionability
        self._opportunity_memory = opportunity_memory or OpportunityMemoryService(connection_factory=self._factory)

    def build_intents(
        self,
        *,
        limit: int = 100,
        write_intents: bool = True,
        write_no_trade: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"paper_intent_{uuid4().hex}"
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        if system_power != "ON" or not bool(power.get("runtime_work_allowed")):
            rows: list[dict[str, Any]] = []
            no_trade_records: list[NoTradeLedgerRecord] = []
            if self._factory.enabled and write_no_trade:
                with self._factory.connect() as conn:
                    rows = self._repository.list_candidates(conn, limit=limit, include_dry_run=False)
                for row in rows:
                    blockers = set(_paper_intent_blockers(row))
                    blockers.add("SYSTEM_POWER_OFF" if system_power != "ON" else "RUNTIME_STOPPED")
                    no_trade_records.append(_no_trade_from_candidate(row, blockers=blockers))
            no_trade_created = 0
            no_trade_updated = 0
            if self._factory.enabled and write_no_trade and no_trade_records:
                with self._factory.connect() as conn, conn.transaction():
                    for record in no_trade_records:
                        _, was_created = self._repository.upsert_no_trade_record(conn, record)
                        no_trade_created += 1 if was_created else 0
                        no_trade_updated += 0 if was_created else 1
            accounted_candidates = len(no_trade_records if write_no_trade else [])
            run = PaperIntentRun(
                run_id=run_id,
                status="BLOCKED",
                candidates_checked=len(rows),
                eligible_candidates=len([row for row in rows if str(row.get("status") or "").upper() == "ELIGIBLE"]),
                paper_intents_created=0,
                paper_intents_updated=0,
                no_trade_records_created=no_trade_created,
                no_trade_records_updated=no_trade_updated,
                blocked_candidates=len(no_trade_records),
                missing_eligibility_count=0,
                accounted_candidates=accounted_candidates,
                unaccounted_candidates=max(0, len(rows) - accounted_candidates),
                paper_ready_before=False,
                paper_ready_after=False,
                orders_created=0,
                order_intents_created=0,
                fills_created=0,
                positions_created=0,
                live_actions_created=0,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error_summary="SYSTEM_POWER_OFF",
                paper_intents=[],
                no_trade_records=no_trade_records,
            )
            if self._factory.enabled and (write_intents or write_no_trade):
                with self._factory.connect() as conn, conn.transaction():
                    self._repository.record_run(conn, run)
                    self._repository.record_no_trade_run(conn, run)
            return run.to_api_dict()
        safety_before = _safety_counts(self._factory)
        rows: list[dict[str, Any]] = []
        if self._factory.enabled:
            try:
                with self._factory.connect() as housekeeping_conn, housekeeping_conn.transaction():
                    self._opportunity_memory.expire_stale_intents_for_connection(housekeeping_conn, limit=limit)
            except Exception:
                pass
            with self._factory.connect() as conn:
                try:
                    self._paper_runtime_decisions.refresh(limit=limit, force=True)
                    runtime_rows = self._paper_runtime_decisions.list_for_intent_gate(conn, limit=limit)
                except Exception:
                    runtime_rows = []
                legacy_rows = self._repository.list_candidates(conn, limit=limit, include_dry_run=False)
                rows = [*runtime_rows, *legacy_rows]

        paper_simulation_allowed, paper_simulation_blockers = self._paper_simulation_intent_guard()
        write_intents_effective = bool(write_intents and paper_simulation_allowed)
        strict_actionability_by_candidate = (
            _strict_actionability_by_candidate(
                self._paper_actionability,
                rows,
                connection_factory=self._factory,
            )
            if write_intents_effective
            else {}
        )
        intents: list[PaperIntent] = []
        no_trade_records: list[NoTradeLedgerRecord] = []
        errors: list[str] = []
        missing_eligibility_count = 0
        row_blockers = {
            str(row.get("eligibility_id") or row.get("id")): {
                *_paper_intent_blockers(row),
                *(paper_simulation_blockers if write_intents else set()),
                    *(
                        _strict_actionability_blockers(
                            row,
                            strict_actionability_by_candidate.get(_candidate_actionability_id(row)),
                        )
                        if write_intents_effective and not _is_paper_runtime_decision_row(row)
                        else set()
                    ),
                }
            for row in rows
        }
        batch_sides: dict[str, set[str]] = {}
        for row in rows:
            blockers = row_blockers[str(row.get("eligibility_id") or row.get("id"))]
            market_id = row.get("market_id")
            side = str(row.get("side") or "").upper()
            if not blockers and market_id and side in {"YES", "NO"}:
                batch_sides.setdefault(str(market_id), set()).add(side)

        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                seen_batch_market_sides: set[tuple[str, str]] = set()
                active_session_id = _active_paper_session_id(conn)
                for row in rows:
                    eligibility_id = row.get("eligibility_id")
                    if not eligibility_id:
                        missing_eligibility_count += 1
                    blockers = set(row_blockers[str(row.get("eligibility_id") or row.get("id"))])
                    market_id = row.get("market_id")
                    side = str(row.get("side") or "").upper()
                    memory_gate = None
                    if not blockers and _is_paper_runtime_decision_row(row):
                        memory_gate = self._opportunity_memory.evaluate_runtime_decision(
                            conn,
                            row,
                            paper_session_id=active_session_id,
                        )
                        row = {**row, "opportunity_memory_gate": memory_gate}
                        if bool(memory_gate.get("same_evidence_waiting")):
                            blockers.add("OPPORTUNITY_WAITING_FOR_NEW_EVIDENCE")
                    if not blockers and market_id and side in {"YES", "NO"}:
                        batch_key = (str(market_id), side)
                        if batch_key in seen_batch_market_sides:
                            blockers.add("SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW")
                        else:
                            seen_batch_market_sides.add(batch_key)
                    guard_decision = None
                    if not blockers:
                        guard_decision = self._same_market_guard.evaluate(
                            conn,
                            market_id=str(row.get("market_id")),
                            proposed_side=str(row.get("side") or "").upper(),
                            proposed_candidate_id=str(eligibility_id) if eligibility_id else None,
                            coordinator_decision_id=row.get("coordinator_decision_id"),
                            evidence=row.get("evidence") or {},
                            metadata={"source_layer": "paper_intent_gate", "eligibility_id": eligibility_id},
                            batch_sides=batch_sides,
                            write_decision=write_intents or write_no_trade,
                        )
                        if guard_decision.decision != "ALLOW":
                            blockers.add(guard_decision.blocker_reason or "MISSING_STRATEGIC_RATIONALE")
                            if guard_decision.blocker_reason in {
                                "SAME_MARKET_OPPOSING_SIDE_BLOCK",
                                "SAME_MARKET_OPPOSING_INTENT_BLOCK",
                                "SAME_MARKET_OPEN_OPPOSITE_POSITION_BLOCK",
                                "SAME_MARKET_ACTIVE_OPPOSITE_INTENT_BLOCK",
                                "SAME_MARKET_BATCH_CONFLICT_BLOCK",
                            }:
                                blockers.add("MISSING_STRATEGIC_RATIONALE")
                                if guard_decision.blocker_reason in {"SAME_MARKET_OPEN_OPPOSITE_POSITION_BLOCK", "SAME_MARKET_BATCH_CONFLICT_BLOCK"}:
                                    blockers.add("SAME_MARKET_OPPOSING_SIDE_BLOCK")
                                if guard_decision.blocker_reason == "SAME_MARKET_ACTIVE_OPPOSITE_INTENT_BLOCK":
                                    blockers.add("SAME_MARKET_OPPOSING_INTENT_BLOCK")
                    if not blockers and _is_paper_runtime_decision_row(row):
                        governance_decision = _runtime_paper_governance_decision(row, action="PAPER_INTENT")
                        if not bool(governance_decision.get("allow_paper_intent")):
                            blockers.add("PAPER_RUNTIME_DECISION_DENIED")
                            blockers.update(str(item).upper() for item in _list(governance_decision.get("critical_blockers_json")))
                    elif not blockers:
                        governance_decision = self._lifecycle_governance.authorize_paper_intent(
                            conn,
                            candidate=row,
                            same_market_guard=guard_decision.to_api_dict() if guard_decision else None,
                            write_decision=write_intents or write_no_trade,
                        )
                        if not bool(governance_decision.get("allow_paper_intent")):
                            blockers.add("LIFECYCLE_GOVERNANCE_DENIED")
                            blockers.add(f"LIFECYCLE_ACTIONABILITY_{governance_decision.get('actionability_class') or 'UNKNOWN'}")
                            for item in _list(governance_decision.get("critical_blockers_json")):
                                blockers.add(str(item).upper())
                    else:
                        governance_decision = None
                    if not blockers:
                        try:
                            strict_item = strict_actionability_by_candidate.get(_candidate_actionability_id(row))
                            if strict_item:
                                row = {**row, "strict_paper_actionability": _strict_actionability_evidence(strict_item)}
                            intents.append(
                                _intent_from_candidate(
                                    row,
                                    paper_session_id=active_session_id,
                                    guard_decision=guard_decision.to_api_dict() if guard_decision else None,
                                    governance_decision=governance_decision,
                                )
                            )
                        except Exception as exc:
                            errors.append(f"{eligibility_id or 'unknown'}:{type(exc).__name__}:{exc}")
                            no_trade_records.append(
                                _no_trade_from_candidate(
                                    row,
                                    blockers={"ERROR_CREATING_PAPER_INTENT", type(exc).__name__.upper()},
                                    paper_session_id=active_session_id,
                                    guard_decision=guard_decision.to_api_dict() if guard_decision else None,
                                    governance_decision=governance_decision,
                                )
                            )
                    else:
                        no_trade_records.append(
                            _no_trade_from_candidate(
                                row,
                                blockers=blockers,
                                paper_session_id=active_session_id,
                                guard_decision=guard_decision.to_api_dict() if guard_decision else None,
                                governance_decision=governance_decision,
                            )
                        )
        else:
            for row in rows:
                eligibility_id = row.get("eligibility_id")
                if not eligibility_id:
                    missing_eligibility_count += 1
                blockers = row_blockers[str(row.get("eligibility_id") or row.get("id"))]
                if not blockers:
                    try:
                        intents.append(_intent_from_candidate(row))
                    except Exception as exc:
                        errors.append(f"{eligibility_id or 'unknown'}:{type(exc).__name__}:{exc}")
                        no_trade_records.append(_no_trade_from_candidate(row, blockers={"ERROR_CREATING_PAPER_INTENT", type(exc).__name__.upper()}))
                else:
                    no_trade_records.append(_no_trade_from_candidate(row, blockers=blockers))

        intents_created = 0
        intents_updated = 0
        duplicate_eligibility_encountered = 0
        duplicate_eligibility_reused = 0
        duplicate_eligibility_skipped = 0
        no_trade_created = 0
        no_trade_updated = 0
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                if write_intents_effective:
                    for intent in intents:
                        intent_row, was_created = self._repository.upsert_paper_intent(conn, intent)
                        intent_row = self._opportunity_memory.attach_intent_metadata(conn, intent_row)
                        idempotency = (
                            intent_row.get("evidence", {}).get("paper_intent_gate_idempotency")
                            if isinstance(intent_row.get("evidence"), dict)
                            else {}
                        )
                        if isinstance(idempotency, dict) and idempotency.get("duplicate_eligibility_encountered"):
                            duplicate_eligibility_encountered += 1
                            if idempotency.get("action_taken") == "REUSED_EXISTING_INTENT":
                                duplicate_eligibility_reused += 1
                            else:
                                duplicate_eligibility_skipped += 1
                        subject_id = str(intent_row.get("paper_intent_id") or intent.paper_intent_id)
                        self._payout_odds.evaluate_subject_with_conn(conn, subject_type="PAPER_INTENT", subject_id=subject_id)
                        intents_created += 1 if was_created else 0
                        intents_updated += 0 if was_created else 1
                if write_no_trade:
                    for record in no_trade_records:
                        _, was_created = self._repository.upsert_no_trade_record(conn, record)
                        no_trade_created += 1 if was_created else 0
                        no_trade_updated += 0 if was_created else 1

        safety_after = _safety_counts(self._factory)
        accounted_candidates = len(intents if write_intents_effective else []) + len(no_trade_records if write_no_trade else [])
        error_summary = "; ".join(errors) if errors else None
        if write_intents and not paper_simulation_allowed:
            error_summary = "PAPER_SIMULATION_OFF_NO_INTENT_CREATED"
        run = PaperIntentRun(
            run_id=run_id,
            status="BLOCKED" if write_intents and not paper_simulation_allowed else "ERROR" if errors and not intents and not no_trade_records else "PARTIAL" if errors else "OK",
            candidates_checked=len(rows),
            eligible_candidates=len([row for row in rows if str(row.get("status") or "").upper() == "ELIGIBLE"]),
            paper_intents_created=intents_created,
            paper_intents_updated=intents_updated,
            no_trade_records_created=no_trade_created,
            no_trade_records_updated=no_trade_updated,
            blocked_candidates=len(no_trade_records),
            missing_eligibility_count=missing_eligibility_count,
            accounted_candidates=accounted_candidates,
            unaccounted_candidates=max(0, len(rows) - accounted_candidates),
            paper_ready_before=False,
            paper_ready_after=False,
            orders_created=max(0, safety_after["orders"] - safety_before["orders"]),
            order_intents_created=max(0, safety_after["order_intents"] - safety_before["order_intents"]),
            fills_created=max(0, safety_after["fills"] - safety_before["fills"]),
            positions_created=max(0, safety_after["positions"] - safety_before["positions"]),
            live_actions_created=max(0, safety_after["live_actions"] - safety_before["live_actions"]),
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error_summary=error_summary,
            paper_intents=intents if write_intents_effective else [],
            no_trade_records=no_trade_records,
        )
        if self._factory.enabled and (write_intents or write_no_trade):
            with self._factory.connect() as conn, conn.transaction():
                self._repository.record_run(conn, run)
                self._repository.record_no_trade_run(conn, run)
        payload = run.to_api_dict()
        payload["paper_intent_gate_idempotency"] = {
            "duplicate_eligibility_encountered": duplicate_eligibility_encountered,
            "existing_intent_reused": duplicate_eligibility_reused,
            "duplicate_skipped_safely": duplicate_eligibility_skipped,
            "duplicate_crash_prevented": duplicate_eligibility_encountered > 0,
        }
        return payload

    def list_recent(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "OK", "count": 0, "paper_intents": []}
        with self._factory.connect() as conn:
            rows = self._repository.list_intents(conn, limit=limit, status=status, market_id=market_id)
        return {
            "mock_data": False,
            "status": "OK",
            "count": len(rows),
            "paper_intents": [_json_safe(paper_intent_from_row(row).to_api_dict()) for row in rows],
        }

    def list_no_trade_recent(
        self,
        *,
        limit: int = 50,
        category: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "OK", "count": 0, "no_trade_records": []}
        with self._factory.connect() as conn:
            rows = self._repository.list_no_trade(conn, limit=limit, category=category, market_id=market_id)
        return {
            "mock_data": False,
            "status": "OK",
            "count": len(rows),
            "no_trade_records": [_json_safe(no_trade_record_from_row(row).to_api_dict()) for row in rows],
        }

    def get_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_intent_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        latest_run = summary.get("latest_run") or {}
        return {
            "mock_data": False,
            "status": "OK",
            "latest_run": _json_safe(latest_run) if latest_run else None,
            "candidates_checked": _int(summary.get("candidates_checked")),
            "eligible_candidates": _int(summary.get("eligible_candidates")),
            "paper_intents_created": _int(latest_run.get("paper_intents_created")) if latest_run else 0,
            "total_paper_intents": _int(summary.get("total_paper_intents")),
            "created_intents": _int(summary.get("created_intents")),
            "blocked_intents": _int(summary.get("blocked_intents")),
            "paper_only_true_count": _int(summary.get("paper_only_true_count")),
            "live_true_count": _int(summary.get("live_true_count")),
            "execution_allowed_count": _int(summary.get("execution_allowed_count")),
            "order_intent_created_count": _int(summary.get("order_intent_created_count")),
            "no_trade_records_created": _int(summary.get("no_trade_records_created")),
            "accounted_candidates": _int(summary.get("accounted_candidates")),
            "unaccounted_candidates": _int(summary.get("unaccounted_candidates")),
            "paper_intent_gate_idempotency": _json_safe(summary.get("paper_intent_gate_idempotency") or {}),
            "latest_intents": [_json_safe(paper_intent_from_row(row).to_api_dict()) for row in summary.get("latest_intents", [])],
            "paper_ready": False,
            "orders_created": _int(latest_run.get("orders_created")) if latest_run else 0,
            "order_intents_created": _int(latest_run.get("order_intents_created")) if latest_run else 0,
            "fills_created": _int(latest_run.get("fills_created")) if latest_run else 0,
            "positions_created": _int(latest_run.get("positions_created")) if latest_run else 0,
            "live_actions_created": _int(latest_run.get("live_actions_created")) if latest_run else 0,
            "analysis_status": "OK",
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def get_no_trade_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_no_trade_summary()
        with self._factory.connect() as conn:
            summary = self._repository.no_trade_summary(conn, limit=limit)
        payload = {
            "mock_data": False,
            "status": "OK",
            "total_no_trade_records": _int(summary.get("total_no_trade_records")),
            "latest_run": _json_safe(summary.get("latest_run")),
            "counts_by_category": [_json_safe(row) for row in summary.get("counts_by_category", [])],
            "top_no_trade_reasons": [_json_safe(row) for row in summary.get("top_no_trade_reasons", [])],
            "blocked_candidates": _int(summary.get("blocked_candidates")),
            "missing_requirements_summary": [_json_safe(row) for row in summary.get("missing_requirements_summary", [])],
            "unaccounted_candidates": _int(summary.get("unaccounted_candidates")),
            "latest_no_trade": [_json_safe(no_trade_record_from_row(row).to_api_dict()) for row in summary.get("latest_no_trade", [])],
            "paper_ready": False,
            "analysis_status": "OK",
            "last_updated": datetime.now(UTC).isoformat(),
        }

        payload.update(
            {
                "updated_at": payload["last_updated"],
                "stale": False,
                "stale_reason": None,
                "data_source": {
                    "type": "postgres_runtime_truth",
                    "service": "PaperIntentGateService",
                    "tables": ["paper_eligibility_candidates", "paper_intents", "no_trade_log", "paper_intent_runs", "no_trade_runs"],
                    "mock_data": False,
                },
                "data_confidence": 1.0,
                "errors": [],
                "data": {
                    "total_no_trade_records": payload["total_no_trade_records"],
                    "counts_by_category": payload["counts_by_category"],
                    "top_no_trade_reasons": payload["top_no_trade_reasons"],
                    "blocked_candidates": payload["blocked_candidates"],
                    "unaccounted_candidates": payload["unaccounted_candidates"],
                    "paper_ready": False,
                },
            }
        )
        return payload

    def _paper_simulation_intent_guard(self) -> tuple[bool, set[str]]:
        blockers: set[str] = set()
        try:
            state = self._governor.get_current_state()
            metadata = dict(state.metadata_json or {})
            paper_meta = dict(metadata.get("paper_simulation") or {})
            if not bool(paper_meta.get("enabled")):
                blockers.add("PAPER_SIMULATION_OFF")
                blockers.add("PAPER_SIMULATION_OFF_NO_INTENT_CREATED")
        except Exception:
            blockers.add("PAPER_SIMULATION_STATE_UNAVAILABLE")
            blockers.add("PAPER_SIMULATION_OFF_NO_INTENT_CREATED")
        try:
            if not self._governor.can_execute(RuntimeAction.RUN_PAPER_SIMULATION):
                blockers.add("GOVERNOR_DENIED_PAPER")
                blockers.add("PAPER_SIMULATION_OFF_NO_INTENT_CREATED")
        except Exception:
            blockers.add("GOVERNOR_DENIED_PAPER")
            blockers.add("PAPER_SIMULATION_OFF_NO_INTENT_CREATED")
        return not blockers, blockers

    def get_recovery_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_recovery_summary()
        power = self._system_power.get_power_state()
        try:
            paper_simulation_allowed = self._governor.can_execute(RuntimeAction.RUN_PAPER_SIMULATION)
        except Exception:
            paper_simulation_allowed = False
        with self._factory.connect() as conn:
            latest_intent_run = self._repository.latest_run(conn)
            eligibility = _eligibility_totals(conn)
            intent_summary = self._repository.summary(conn, limit=limit)
            execution = _execution_totals(conn)
            top_blockers = _top_candidate_blockers(conn, limit=limit)
            blocker_trace = _candidate_blocker_trace(conn, limit=limit)
            latest_execution_run = _latest_execution_run(conn)
        no_valid_reason = None
        if _int(eligibility.get("eligible_count")) == 0:
            no_valid_reason = "NO_ELIGIBLE_CANDIDATES"
        elif _int(intent_summary.get("created_intents")) == 0:
            no_valid_reason = "ELIGIBLE_CANDIDATES_FAILED_INTENT_HARD_REQUIREMENTS"
        elif _int(execution.get("executable_paper_intents")) == 0:
            no_valid_reason = "NO_EXECUTABLE_PAPER_INTENTS"
        return {
            "mock_data": False,
            "status": "OK",
            "system_power": power.get("power"),
            "runtime_work_allowed": bool(power.get("runtime_work_allowed")),
            "paper_simulation_allowed": bool(paper_simulation_allowed),
            "paper_execution_allowed": bool(paper_simulation_allowed),
            "paper_allowed": bool(power.get("paper_allowed", False)),
            "live_allowed": False,
            "shadow_allowed": False,
            "real_orders_allowed": False,
            "eligibility_candidates_total": _int(eligibility.get("total_candidates")),
            "eligible_candidates": _int(eligibility.get("eligible_count")),
            "blocked_candidates": _int(eligibility.get("blocked_count")),
            "ineligible_candidates": _int(eligibility.get("ineligible_count")),
            "incomplete_candidates": _int(eligibility.get("incomplete_count")),
            "top_candidate_blockers": top_blockers,
            "candidate_blocker_trace": blocker_trace,
            "paper_intents_total": _int(intent_summary.get("total_paper_intents")),
            "created_paper_intents": _int(intent_summary.get("created_intents")),
            "executable_paper_intents": _int(execution.get("executable_paper_intents")),
            "paper_intents_created_last_run": _int((latest_intent_run or {}).get("paper_intents_created")),
            "paper_intents_blocked_last_run": _int((latest_intent_run or {}).get("blocked_candidates")),
            "latest_intent_run": _json_safe(latest_intent_run),
            "latest_execution_run": _json_safe(latest_execution_run),
            "paper_orders": _int(execution.get("paper_orders")),
            "paper_fills": _int(execution.get("paper_fills")),
            "paper_positions": _int(execution.get("paper_positions")),
            "open_paper_positions": _int(execution.get("open_paper_positions")),
            "live_orders": _int(execution.get("live_orders")),
            "real_orders": _int(execution.get("real_orders")),
            "no_valid_paper_intents_reason": no_valid_reason,
            "paper_ready": False,
            "no_live_execution": True,
            "analysis_status": "OK",
            "last_updated": datetime.now(UTC).isoformat(),
        }


def _paper_intent_blockers(row: dict[str, Any]) -> set[str]:
    blockers = {str(item).upper() for item in _list(row.get("eligibility_blockers"))}
    missing = {str(item).upper() for item in _list(row.get("missing_requirements"))}
    evidence = row.get("evidence") or {}
    blockers.update(missing)
    if str(row.get("status") or "").upper() != "ELIGIBLE":
        blockers.add("CANDIDATE_NOT_ELIGIBLE")
    for key, code in {
        "eligibility_id": "MISSING_ELIGIBILITY",
        "thesis_id": "MISSING_THESIS",
        "risk_decision_id": "MISSING_RISK_DECISION",
        "exit_plan_id": "MISSING_EXIT_PLAN",
        "market_id": "MISSING_MARKET_ID",
        "side": "MISSING_SIDE",
        "orderbook_snapshot_id": "MISSING_FRESH_ORDERBOOK",
    }.items():
        if row.get(key) in (None, "", []):
            blockers.add(code)
    if not bool(row.get("risk_approved")):
        blockers.add("RISK_NOT_APPROVED")
    if not bool(row.get("exit_ready")):
        blockers.add("EXIT_NOT_READY")
    if not bool(row.get("lineage_trusted")):
        blockers.add("WEAK_LINEAGE_OR_PROVENANCE")
    if not bool(row.get("not_dry_run")) or bool(row.get("is_dry_run_generated")):
        blockers.add("DRY_RUN_EVIDENCE")
    if bool(row.get("execution_allowed")):
        blockers.add("CANDIDATE_EXECUTION_ALLOWED_UNSAFE")
    if _execution_price_from_evidence(evidence) is None:
        blockers.add("MISSING_EXECUTABLE_PRICE")
    return blockers


def _is_paper_runtime_decision_row(row: dict[str, Any]) -> bool:
    if row.get("paper_runtime_decision_id"):
        return True
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    return str(row.get("source_layer") or evidence.get("source_layer") or "").upper() == "PAPER_RUNTIME_DECISION"


def _runtime_paper_governance_decision(row: dict[str, Any], *, action: str) -> dict[str, Any]:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    runtime_decision = evidence.get("paper_runtime_decision") if isinstance(evidence.get("paper_runtime_decision"), dict) else {}
    policy = evidence.get("paper_mode_policy") if isinstance(evidence.get("paper_mode_policy"), dict) else {}
    blockers = {
        str(item).upper()
        for item in [
            *_list(row.get("eligibility_blockers")),
            *_list(row.get("missing_requirements")),
            *_list(runtime_decision.get("blockers_json") if isinstance(runtime_decision, dict) else []),
            *_list(policy.get("blockers") if isinstance(policy, dict) else []),
        ]
        if str(item or "").strip()
    }
    hard_states = {
        "RISK_HARD_BLOCKED",
        "CAPITAL_HARD_BLOCKED",
        "EXIT_NOT_READY",
        "TOKEN_SIDE_NOT_VERIFIED",
        "MISSING_FRESH_ORDERBOOK",
        "STALE_ORDERBOOK",
        "DUPLICATE_OPEN_PAPER_EXPOSURE",
        "SOURCE_REVIEW_EXECUTION_FLAG_TRUE",
    }
    hard_blockers = sorted(blockers.intersection(hard_states) or blockers)
    paper_enter_allowed = bool(evidence.get("paper_enter_allowed") or policy.get("paper_enter_allowed"))
    allow = paper_enter_allowed and not hard_blockers
    return {
        "allow_paper_intent": allow if action == "PAPER_INTENT" else False,
        "allow_paper_execution": allow if action == "PAPER_EXECUTION" else False,
        "actionability_class": "PAPER_LEARNING_ENTER" if allow else "PAPER_RUNTIME_BLOCKED",
        "critical_blockers_json": [] if allow else hard_blockers,
        "warnings_json": _list(policy.get("warnings") if isinstance(policy, dict) else []),
        "policy_source": "paper_runtime_decision",
        "live_enter_allowed": False,
        "paper_is_execution_adapter_only": True,
        "execution_mode": "PAPER",
    }


def _intent_from_candidate(
    row: dict[str, Any],
    *,
    paper_session_id: str | None = None,
    guard_decision: dict[str, Any] | None = None,
    governance_decision: dict[str, Any] | None = None,
) -> PaperIntent:
    evidence = row.get("evidence") or {}
    intended_price = _execution_price_from_evidence(evidence)
    paper_defense = evidence.get("paper_defense") if isinstance(evidence.get("paper_defense"), dict) else {}
    quantity = _safe_paper_quantity(intended_price, paper_defense=paper_defense)
    price_basis = "ORDERBOOK_BEST_ASK" if _maybe_float(evidence.get("orderbook_best_ask")) is not None else "ORDERBOOK_MID"
    is_runtime_decision = _is_paper_runtime_decision_row(row)
    original_eligibility_id = str(row["eligibility_id"])
    intent_eligibility_id = original_eligibility_id
    paper_intent_id = f"paper_intent_{original_eligibility_id}"
    if is_runtime_decision and paper_session_id:
        intent_eligibility_id = f"{original_eligibility_id}_{paper_session_id}"
        paper_intent_id = f"paper_intent_{intent_eligibility_id}"
    return PaperIntent(
        paper_intent_id=paper_intent_id,
        eligibility_id=intent_eligibility_id,
        thesis_id=str(row["thesis_id"]),
        risk_decision_id=str(row["risk_decision_id"]),
        exit_plan_id=str(row["exit_plan_id"]),
        coordinator_decision_id=row.get("coordinator_decision_id"),
        market_id=str(row["market_id"]),
        side=str(row["side"]).upper(),
        price_basis=price_basis,
        orderbook_snapshot_id=int(row["orderbook_snapshot_id"]) if row.get("orderbook_snapshot_id") is not None else None,
        intended_price=_maybe_float(intended_price),
        max_slippage=0.02,
        confidence=_maybe_float(row.get("eligibility_score")),
        intent_status="CREATED",
        intent_type="PAPER_ENTRY_INTENT",
        intent_reason=(
            "Unified PAPER runtime decision passed Paper Intent Gate; PAPER adapter only."
            if is_runtime_decision
            else "Candidate passed Paper Eligibility and hard Paper Intent evidence checks."
        ),
        evidence={
            "eligibility_status": row.get("status"),
            "original_eligibility_id": original_eligibility_id,
            "eligibility_score": _maybe_float(row.get("eligibility_score")),
            "bridge_outcome": "PAPER_INTENT_CREATED",
            "bridge_state": "RESOLVED",
            "paper_session_id": paper_session_id,
            "intent_identity_scope": "CURRENT_SESSION" if is_runtime_decision and paper_session_id else "GLOBAL",
            "eligibility_identity_scope": "CURRENT_SESSION" if is_runtime_decision and paper_session_id else "GLOBAL",
            "paper_runtime_decision_id": row.get("paper_runtime_decision_id") if is_runtime_decision else None,
            "paper_runtime_decision": evidence.get("paper_runtime_decision") if is_runtime_decision else None,
            "paper_mode_policy": evidence.get("paper_mode_policy") if is_runtime_decision else None,
            "required_to_create_intent": [],
            "risk_approved": bool(row.get("risk_approved")),
            "exit_ready": bool(row.get("exit_ready")),
            "lineage_trusted": bool(row.get("lineage_trusted")),
            "not_dry_run": bool(row.get("not_dry_run")),
            "quantity": _maybe_float(quantity),
            "intended_notional": _maybe_float(SAFE_PAPER_NOTIONAL),
            "paper_sizing_policy": "FIXED_SAFE_PAPER_NOTIONAL_CLAMPED_QUANTITY",
            "orderbook_best_bid": _maybe_float(evidence.get("orderbook_best_bid")),
            "orderbook_best_ask": _maybe_float(evidence.get("orderbook_best_ask")),
            "orderbook_mid_price": _maybe_float(evidence.get("orderbook_mid_price") or evidence.get("orderbook_mid")),
            "source_evidence": evidence,
            "strict_paper_actionability": row.get("strict_paper_actionability"),
            "same_market_guard_decision": guard_decision,
            "lifecycle_governance_decision": governance_decision,
            "opportunity_memory_gate": row.get("opportunity_memory_gate"),
        },
        blockers=[],
        paper_only=True,
        live=False,
        execution_allowed=False,
        order_intent_created=False,
        generated_by="runtime",
        producer_name="paper_intent_gate",
        is_runtime_generated=True,
        is_dry_run_generated=False,
    )


def _no_trade_from_candidate(
    row: dict[str, Any],
    *,
    blockers: set[str],
    paper_session_id: str | None = None,
    guard_decision: dict[str, Any] | None = None,
    governance_decision: dict[str, Any] | None = None,
) -> NoTradeLedgerRecord:
    missing = {str(item).upper() for item in _list(row.get("missing_requirements"))}
    category = _category_for(blockers, missing)
    reason = _primary_reason(blockers, missing)
    bridge_outcome = _bridge_outcome_for_blockers(blockers)
    eligibility_id = row.get("eligibility_id")
    if _is_paper_runtime_decision_row(row) and eligibility_id and paper_session_id:
        record_eligibility_id = f"{eligibility_id}_{paper_session_id}"
    else:
        record_eligibility_id = str(eligibility_id) if eligibility_id else None
    no_trade_id = f"no_trade_{record_eligibility_id}" if record_eligibility_id else f"no_trade_missing_{uuid4().hex}"
    return NoTradeLedgerRecord(
        no_trade_id=no_trade_id,
        eligibility_id=record_eligibility_id,
        thesis_id=row.get("thesis_id"),
        risk_decision_id=row.get("risk_decision_id"),
        exit_plan_id=row.get("exit_plan_id"),
        market_id=row.get("market_id"),
        side=row.get("side"),
        no_trade_reason=reason,
        no_trade_category=category,
        blockers=sorted(blockers),
        missing_requirements=sorted(missing),
        evidence={
            "eligibility_status": row.get("status"),
            "original_eligibility_id": str(eligibility_id) if eligibility_id else None,
            "eligibility_score": _maybe_float(row.get("eligibility_score")),
            "paper_runtime_decision_id": row.get("paper_runtime_decision_id") if _is_paper_runtime_decision_row(row) else None,
            "bridge_outcome": bridge_outcome,
            "bridge_state": _bridge_state_for_outcome(bridge_outcome),
            "paper_session_id": paper_session_id,
            "no_trade_identity_scope": "CURRENT_SESSION" if _is_paper_runtime_decision_row(row) and paper_session_id else "GLOBAL",
            "required_to_create_intent": _required_to_create_for_blockers(blockers),
            "risk_approved": bool(row.get("risk_approved")),
            "exit_ready": bool(row.get("exit_ready")),
            "lineage_trusted": bool(row.get("lineage_trusted")),
            "not_dry_run": bool(row.get("not_dry_run")),
            "source_evidence": row.get("evidence") or {},
            "strict_paper_actionability": row.get("strict_paper_actionability"),
            "same_market_guard_decision": guard_decision,
            "lifecycle_governance_decision": governance_decision,
            "opportunity_memory_gate": row.get("opportunity_memory_gate"),
        },
        source_status=str(row.get("status") or "ERROR").upper(),
        source_layer="paper_intent_gate",
        generated_by="runtime",
        producer_name="no_trade_ledger",
        is_runtime_generated=True,
        is_dry_run_generated=bool(row.get("is_dry_run_generated")),
    )


def _category_for(blockers: set[str], missing: set[str]) -> str:
    if "RISK_NOT_APPROVED" in blockers or "RISK_BLOCKED" in blockers or "RISK_REJECTED" in blockers:
        return "RISK_BLOCKED"
    if "EXIT_NOT_READY" in blockers or "MISSING_EXIT_PLAN" in blockers:
        return "EXIT_BLOCKED"
    if "PAPER_SIMULATION_OFF_NO_INTENT_CREATED" in blockers or "PAPER_SIMULATION_OFF" in blockers:
        return "NO_ELIGIBLE_CANDIDATE"
    if "OPPORTUNITY_WAITING_FOR_NEW_EVIDENCE" in blockers:
        return "NO_ELIGIBLE_CANDIDATE"
    if "STRICT_PAPER_ACTIONABILITY_NOT_QUALIFIED" in blockers or "STRICT_PAPER_ACTIONABILITY_NOT_FOUND" in blockers:
        return "ELIGIBILITY_BLOCKED"
    if "MISSING_FRESH_ORDERBOOK" in blockers:
        return "STALE_DATA"
    if "WEAK_LINEAGE_OR_PROVENANCE" in blockers:
        return "WEAK_LINEAGE"
    if "DRY_RUN_EVIDENCE" in blockers:
        return "DRY_RUN_ONLY"
    if "LIFECYCLE_GOVERNANCE_DENIED" in blockers:
        return "LIFECYCLE_GOVERNANCE_BLOCKED"
    if missing:
        return "MISSING_EVIDENCE"
    if any("ERROR" in item for item in blockers):
        return "ERROR"
    return "ELIGIBILITY_BLOCKED"


def _primary_reason(blockers: set[str], missing: set[str]) -> str:
    for code in (
        "RISK_NOT_APPROVED",
        "RISK_BLOCKED",
        "EXIT_NOT_READY",
        "MISSING_EXIT_PLAN",
        "MISSING_FRESH_ORDERBOOK",
        "MISSING_SIGNAL_MARKET_BINDING",
        "WEAK_LINEAGE_OR_PROVENANCE",
        "DRY_RUN_EVIDENCE",
        "CANDIDATE_NOT_ELIGIBLE",
        "LIFECYCLE_GOVERNANCE_DENIED",
        "PAPER_SIMULATION_OFF_NO_INTENT_CREATED",
        "STRICT_PAPER_ACTIONABILITY_NOT_QUALIFIED",
        "STRICT_PAPER_ACTIONABILITY_NOT_FOUND",
        "STRICT_PAPER_ACTIONABILITY_LOOKUP_FAILED",
        "PAPER_SIMULATION_OFF",
        "OPPORTUNITY_WAITING_FOR_NEW_EVIDENCE",
        "SYSTEM_POWER_OFF",
        "RUNTIME_STOPPED",
    ):
        if code in blockers:
            return code
    if missing:
        return sorted(missing)[0]
    return sorted(blockers)[0] if blockers else "NO_ELIGIBLE_CANDIDATE"


def _bridge_outcome_for_blockers(blockers: set[str]) -> str:
    priority = (
        ("GOVERNOR_DENIED_PAPER", "BLOCKED_BY_GOVERNOR"),
        ("SYSTEM_POWER_OFF", "BLOCKED_BY_RUNTIME"),
        ("RUNTIME_STOPPED", "BLOCKED_BY_RUNTIME"),
        ("RUNTIME_NOT_ALIVE", "BLOCKED_BY_RUNTIME"),
        ("PAPER_SIMULATION_OFF_NO_INTENT_CREATED", "BLOCKED_BY_PAPER_SIMULATION"),
        ("PAPER_SIMULATION_OFF", "BLOCKED_BY_PAPER_SIMULATION"),
        ("OPPORTUNITY_WAITING_FOR_NEW_EVIDENCE", "WAITING_FOR_NEW_EVIDENCE"),
        ("STRICT_PAPER_ACTIONABILITY_NOT_QUALIFIED", "BLOCKED_BY_STRICT_ACTIONABILITY"),
        ("STRICT_PAPER_ACTIONABILITY_NOT_FOUND", "BLOCKED_BY_STRICT_ACTIONABILITY"),
        ("STRICT_PAPER_ACTIONABILITY_LOOKUP_FAILED", "BLOCKED_BY_STRICT_ACTIONABILITY"),
        ("STALE_ORDERBOOK", "WAITING_FOR_REFRESH"),
        ("MISSING_FRESH_ORDERBOOK", "WAITING_FOR_REFRESH"),
        ("MISSING_TRUSTED_ORDERBOOK", "WAITING_FOR_REFRESH"),
        ("MISSING_EXECUTABLE_PRICE", "BLOCKED_BY_PRICE"),
        ("MISSING_QUANTITY", "BLOCKED_BY_PRICE"),
        ("CAPITAL_NOT_OK", "BLOCKED_BY_CAPITAL"),
        ("MAX_OPEN_POSITIONS", "BLOCKED_BY_CAPITAL"),
        ("LIFECYCLE_GOVERNANCE_DENIED", "BLOCKED_BY_LIFECYCLE"),
        ("RISK_BLOCKED", "BLOCKED_BY_RISK"),
        ("RISK_NOT_APPROVED", "BLOCKED_BY_RISK"),
        ("EXIT_NOT_READY", "BLOCKED_BY_EXIT"),
        ("MISSING_MARKET_ID", "BLOCKED_BY_DATA"),
        ("MISSING_SIDE", "BLOCKED_BY_DATA"),
        ("MISSING_SIGNAL_MARKET_BINDING", "BLOCKED_BY_DATA"),
        ("SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW", "BLOCKED_BY_DUPLICATE"),
        ("SAME_MARKET_OPPOSING_SIDE_BLOCK", "BLOCKED_BY_DUPLICATE"),
        ("SAME_MARKET_OPPOSING_INTENT_BLOCK", "BLOCKED_BY_DUPLICATE"),
        ("SAME_MARKET_OPPOSING_ENTER_CONFLICT", "BLOCKED_BY_DUPLICATE"),
        ("SAME_MARKET_OPPOSING_SIDE_LOST_ARBITRATION", "BLOCKED_BY_DUPLICATE"),
    )
    normalized = {str(item).upper() for item in blockers}
    for blocker, outcome in priority:
        if blocker in normalized:
            return outcome
    if normalized:
        return "NO_TRADE_WITH_REASON"
    return "UNKNOWN_WITH_EXPLANATION"


def _bridge_state_for_outcome(outcome: str) -> str:
    if outcome in {"PAPER_INTENT_CREATED", "ALREADY_HAS_INTENT", "NO_TRADE_WITH_REASON"}:
        return "RESOLVED"
    if outcome in {"WAITING_FOR_REFRESH", "WAITING_FOR_NEW_EVIDENCE"}:
        return "WAITING"
    if outcome.startswith("BLOCKED_BY"):
        return "BLOCKED"
    return "UNKNOWN"


def _required_to_create_for_blockers(blockers: set[str]) -> list[str]:
    mapping = {
        "SYSTEM_POWER_OFF": "System power must be ON.",
        "RUNTIME_STOPPED": "Runtime must be alive.",
        "RUNTIME_NOT_ALIVE": "Runtime must be alive.",
        "PAPER_SIMULATION_OFF_NO_INTENT_CREATED": "Paper Intent creation requires Paper Simulation to be explicitly ON.",
        "PAPER_SIMULATION_OFF": "Paper Simulation must be explicitly ON.",
        "OPPORTUNITY_WAITING_FOR_NEW_EVIDENCE": "Opportunity memory already contains this evidence fingerprint; new evidence is required before reactivation.",
        "STRICT_PAPER_ACTIONABILITY_NOT_QUALIFIED": "Selected Paper Actionability row must satisfy the strict Paper qualification contract.",
        "STRICT_PAPER_ACTIONABILITY_NOT_FOUND": "A matching strict Paper Actionability row must exist for the candidate.",
        "STRICT_PAPER_ACTIONABILITY_LOOKUP_FAILED": "Paper Actionability strict qualification lookup must succeed before creating an intent.",
        "GOVERNOR_DENIED_PAPER": "State Governor must allow paper simulation.",
        "MISSING_FRESH_ORDERBOOK": "Fresh trusted orderbook must be available.",
        "STALE_ORDERBOOK": "Orderbook must be refreshed within execution TTL.",
        "MISSING_TRUSTED_ORDERBOOK": "Trusted orderbook must be available.",
        "MISSING_EXECUTABLE_PRICE": "Executable orderbook price must exist.",
        "MISSING_QUANTITY": "Safe paper quantity must be derivable from price.",
        "CAPITAL_NOT_OK": "Paper account must have available capital.",
        "MAX_OPEN_POSITIONS": "Open paper position count must fall below max_open_positions.",
        "LIFECYCLE_GOVERNANCE_DENIED": "Lifecycle governance must allow paper intent.",
        "RISK_BLOCKED": "Risk blockers must clear.",
        "RISK_NOT_APPROVED": "Risk decision must approve the candidate.",
        "EXIT_NOT_READY": "Exit plan must be paper_exit_ready.",
        "MISSING_MARKET_ID": "Candidate must be linked to canonical market_id.",
        "MISSING_SIDE": "Candidate must include YES or NO side.",
        "MISSING_SIGNAL_MARKET_BINDING": "Signal-market binding must exist.",
        "WEAK_LINEAGE_OR_PROVENANCE": "Candidate lineage/provenance must be trusted.",
        "DRY_RUN_EVIDENCE": "Candidate must be generated from runtime evidence, not dry-run evidence.",
        "SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW": "Duplicate same-market same-side candidate must be reviewed or deduplicated before intent creation.",
        "SAME_MARKET_OPPOSING_ENTER_CONFLICT": "Resolve same-market opposing ENTER evidence before intent creation.",
        "SAME_MARKET_OPPOSING_SIDE_LOST_ARBITRATION": "Only the strongest same-market side may remain ENTER in the current PAPER batch.",
    }
    required: list[str] = []
    for blocker in sorted(str(item).upper() for item in blockers):
        if blocker in mapping:
            required.append(mapping[blocker])
    return required


def _strict_actionability_by_candidate(
    service: Any | None,
    rows: list[dict[str, Any]],
    *,
    connection_factory: DatabaseConnectionFactory,
) -> dict[str, dict[str, Any]]:
    if service is None:
        from app.control_center.paper_actionability import PaperActionabilityService

        service = PaperActionabilityService(connection_factory=connection_factory)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate_id = _candidate_actionability_id(row)
        if not candidate_id or candidate_id in out:
            continue
        try:
            response = service.list_actionability(limit=10, candidate_id=candidate_id)
            items = _actionability_items(response)
            selected = next((item for item in items if str(item.get("candidate_id") or "") == candidate_id), None)
            out[candidate_id] = selected or {
                "candidate_id": candidate_id,
                "strict_paper_qualification": {
                    "qualified": False,
                    "state": "STRICT_PAPER_ACTIONABILITY_NOT_FOUND",
                    "blockers": ["STRICT_PAPER_ACTIONABILITY_NOT_FOUND"],
                    "required_to_pass": ["A matching strict Paper Actionability row must exist for the candidate."],
                },
            }
        except Exception as exc:
            out[candidate_id] = {
                "candidate_id": candidate_id,
                "strict_paper_qualification": {
                    "qualified": False,
                    "state": "STRICT_PAPER_ACTIONABILITY_LOOKUP_FAILED",
                    "blockers": ["STRICT_PAPER_ACTIONABILITY_LOOKUP_FAILED", type(exc).__name__.upper()],
                    "required_to_pass": ["Paper Actionability strict qualification lookup must succeed before creating an intent."],
                    "error": f"{type(exc).__name__}: {exc}",
                },
            }
    return out


def _strict_actionability_blockers(row: dict[str, Any], item: dict[str, Any] | None) -> set[str]:
    from app.control_center.paper_actionability import STRICT_ACTIONABLE_STATES, is_strictly_paper_actionable

    candidate_id = _candidate_actionability_id(row)
    if not candidate_id:
        return {"STRICT_PAPER_ACTIONABILITY_NOT_FOUND"}
    if not item:
        return {"STRICT_PAPER_ACTIONABILITY_NOT_FOUND"}
    row["strict_paper_actionability"] = _strict_actionability_evidence(item)
    if str(item.get("candidate_id") or "") != candidate_id:
        return {"STRICT_PAPER_ACTIONABILITY_NOT_FOUND"}
    ok, state, blockers, _required = is_strictly_paper_actionable(item)
    actionability_state = str(item.get("candidate_paper_actionability_state") or item.get("paper_actionability_state") or "").upper()
    if not ok or actionability_state not in STRICT_ACTIONABLE_STATES:
        strict_state = state or actionability_state or "STRICT_PAPER_ACTIONABILITY_NOT_QUALIFIED"
        return {
            "STRICT_PAPER_ACTIONABILITY_NOT_QUALIFIED",
            str(strict_state).upper(),
            *{str(blocker).upper() for blocker in blockers},
        }
    return set()


def _strict_actionability_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": item.get("candidate_id"),
        "candidate_paper_actionability_state": item.get("candidate_paper_actionability_state"),
        "paper_actionability_state": item.get("paper_actionability_state"),
        "strict_paper_qualification": item.get("strict_paper_qualification"),
        "risk_gate_state": item.get("risk_gate_state"),
        "candidate_event_scope": item.get("candidate_event_scope"),
        "candidate_event_link_state": item.get("candidate_event_link_state"),
        "thesis_id": item.get("thesis_id"),
        "trade_thesis_type": item.get("trade_thesis_type"),
        "exit_intent": item.get("exit_intent"),
        "expected_hold_time_hours": item.get("expected_hold_time_hours"),
        "hold_time_source": item.get("hold_time_source"),
        "source_refresh_cycle_id": item.get("source_refresh_cycle_id"),
        "blockers": item.get("blockers") or [],
        "required_to_pass": item.get("required_to_pass") or [],
    }


def _candidate_actionability_id(row: dict[str, Any]) -> str | None:
    for key in ("candidate_id", "eligibility_id", "id"):
        value = row.get(key)
        if value not in (None, "", []):
            return str(value)
    return None


def _actionability_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data") if isinstance(response, dict) else None
    payload = data if isinstance(data, dict) else response if isinstance(response, dict) else {}
    items = payload.get("items") if isinstance(payload, dict) else []
    return [item for item in (items or []) if isinstance(item, dict)]


def _safety_counts(factory: DatabaseConnectionFactory) -> dict[str, int]:
    counts = {"orders": 0, "order_intents": 0, "fills": 0, "positions": 0, "live_actions": 0}
    if not factory.enabled:
        return counts
    with factory.connect() as conn:
        for key, table in {
            "orders": "paper_orders",
            "order_intents": "order_intents",
            "fills": "fills_v2",
            "positions": "positions",
            "live_actions": "live_orders",
        }.items():
            if _table_exists(conn, table):
                counts[key] = _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
    return counts


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _execution_price_from_evidence(evidence: dict[str, Any]) -> Decimal | None:
    for key in ("orderbook_best_ask", "orderbook_mid_price", "orderbook_mid"):
        value = evidence.get(key)
        if value is None or value == "":
            continue
        try:
            price = Decimal(str(value))
        except Exception:
            continue
        if Decimal("0.01") <= price <= Decimal("0.99"):
            return price
    return None


def _safe_paper_quantity(price: Decimal | None, *, paper_defense: dict[str, Any] | None = None) -> Decimal | None:
    if price is None or price <= 0:
        return None
    profile = (paper_defense or {}).get("profile") if isinstance((paper_defense or {}).get("profile"), dict) else {}
    try:
        defense_level = int((paper_defense or {}).get("defense_level", 100))
    except (TypeError, ValueError):
        defense_level = 100
    max_single_pct = Decimal(str(profile.get("max_single_trade_pct") or (20 if defense_level <= 0 else 15 if defense_level <= 20 else 5 if defense_level <= 60 else 2)))
    notional = SAFE_PAPER_NOTIONAL
    if defense_level < 100:
        notional = max(SAFE_PAPER_NOTIONAL, Decimal("1000") * max_single_pct / Decimal("100"))
    quantity = notional / price
    max_quantity = MAX_SAFE_PAPER_QUANTITY if defense_level >= 100 else max(MAX_SAFE_PAPER_QUANTITY, Decimal("1000"))
    if quantity > max_quantity:
        return max_quantity
    return quantity.quantize(Decimal("0.0001"))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"])


def _eligibility_totals(conn: Any) -> dict[str, Any]:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return {"total_candidates": 0, "eligible_count": 0, "blocked_count": 0, "ineligible_count": 0, "incomplete_count": 0}
    return dict(
        conn.execute(
            """
            SELECT
                COUNT(*) AS total_candidates,
                COUNT(*) FILTER (WHERE status = 'ELIGIBLE') AS eligible_count,
                COUNT(*) FILTER (WHERE status = 'BLOCKED') AS blocked_count,
                COUNT(*) FILTER (WHERE status = 'INELIGIBLE') AS ineligible_count,
                COUNT(*) FILTER (WHERE status = 'INCOMPLETE') AS incomplete_count
            FROM paper_eligibility_candidates
            """
        ).fetchone()
    )


def _execution_totals(conn: Any) -> dict[str, Any]:
    executable_where = """
        intent_status = 'CREATED'
        AND intent_type = 'PAPER_ENTRY_INTENT'
        AND paper_only = true
        AND live = false
        AND execution_allowed = false
        AND order_intent_created = false
        AND COALESCE(is_dry_run_generated, false) = false
        AND market_id IS NOT NULL
        AND side IS NOT NULL
        AND intended_price IS NOT NULL
        AND orderbook_snapshot_id IS NOT NULL
        AND (
            evidence ? 'quantity'
            OR evidence ? 'size'
            OR evidence ? 'intended_size'
            OR evidence ? 'open_quantity'
            OR evidence ? 'notional'
            OR evidence ? 'intended_notional'
        )
    """
    return {
        "executable_paper_intents": _count_where(conn, "paper_intents", executable_where),
        "paper_orders": _count_table(conn, "paper_orders"),
        "paper_fills": _count_table(conn, "paper_fills"),
        "paper_positions": _count_table(conn, "paper_positions"),
        "open_paper_positions": _count_where(conn, "paper_positions", "current_status = 'OPEN' AND closed_at IS NULL"),
        "live_orders": _count_table(conn, "live_orders"),
        "real_orders": _count_table(conn, "orders_v2"),
    }


def _top_candidate_blockers(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return []
    rows = conn.execute(
        """
        SELECT item AS blocker, COUNT(*) AS count
        FROM paper_eligibility_candidates,
             jsonb_array_elements_text(eligibility_blockers) AS item
        GROUP BY item
        ORDER BY count DESC, blocker ASC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _candidate_blocker_trace(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return []
    rows = conn.execute(
        """
        SELECT
            eligibility_id, status, market_id, side, risk_approved,
            exit_ready, lineage_trusted, not_dry_run, orderbook_snapshot_id,
            eligibility_blockers, missing_requirements, created_at, updated_at
        FROM paper_eligibility_candidates
        ORDER BY updated_at DESC NULLS LAST, created_at DESC, id DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_json_safe(dict(row)) for row in rows]


def _latest_execution_run(conn: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_execution_runs"):
        return None
    row = conn.execute("SELECT * FROM paper_execution_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _empty_recovery_summary() -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": "OK",
        "system_power": "OFF",
        "runtime_work_allowed": False,
        "paper_simulation_allowed": False,
        "paper_execution_allowed": False,
        "paper_allowed": False,
        "live_allowed": False,
        "shadow_allowed": False,
        "real_orders_allowed": False,
        "eligibility_candidates_total": 0,
        "eligible_candidates": 0,
        "blocked_candidates": 0,
        "ineligible_candidates": 0,
        "incomplete_candidates": 0,
        "top_candidate_blockers": [],
        "candidate_blocker_trace": [],
        "paper_intents_total": 0,
        "created_paper_intents": 0,
        "executable_paper_intents": 0,
        "paper_intents_created_last_run": 0,
        "paper_intents_blocked_last_run": 0,
        "latest_intent_run": None,
        "latest_execution_run": None,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "open_paper_positions": 0,
        "live_orders": 0,
        "real_orders": 0,
        "no_valid_paper_intents_reason": "DATABASE_UNAVAILABLE",
        "paper_ready": False,
        "no_live_execution": True,
        "analysis_status": "OK",
        "last_updated": datetime.now(UTC).isoformat(),
    }


def _empty_intent_summary() -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": "OK",
        "latest_run": None,
        "candidates_checked": 0,
        "eligible_candidates": 0,
        "paper_intents_created": 0,
        "total_paper_intents": 0,
        "created_intents": 0,
        "blocked_intents": 0,
        "paper_only_true_count": 0,
        "live_true_count": 0,
        "execution_allowed_count": 0,
        "order_intent_created_count": 0,
        "no_trade_records_created": 0,
        "accounted_candidates": 0,
        "unaccounted_candidates": 0,
        "paper_intent_gate_idempotency": {
            "duplicate_eligibility_encountered": 0,
            "existing_intent_reused": 0,
            "duplicate_skipped_safely": 0,
            "duplicate_crash_prevented": False,
            "latest": None,
        },
        "paper_ready": False,
        "orders_created": 0,
        "order_intents_created": 0,
        "fills_created": 0,
        "positions_created": 0,
        "live_actions_created": 0,
        "analysis_status": "OK",
    }


def _empty_no_trade_summary() -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "mock_data": False,
        "status": "OK",
        "updated_at": now,
        "stale": False,
        "stale_reason": None,
        "data_source": {
            "type": "postgres_runtime_truth",
            "service": "PaperIntentGateService",
            "tables": ["paper_eligibility_candidates", "paper_intents", "no_trade_log", "paper_intent_runs", "no_trade_runs"],
            "mock_data": False,
        },
        "data_confidence": 1.0,
        "errors": [],
        "data": {
            "total_no_trade_records": 0,
            "counts_by_category": [],
            "top_no_trade_reasons": [],
            "blocked_candidates": 0,
            "unaccounted_candidates": 0,
            "paper_ready": False,
        },
        "total_no_trade_records": 0,
        "latest_run": None,
        "counts_by_category": [],
        "top_no_trade_reasons": [],
        "blocked_candidates": 0,
        "missing_requirements_summary": [],
        "unaccounted_candidates": 0,
        "paper_ready": False,
        "analysis_status": "OK",
    }

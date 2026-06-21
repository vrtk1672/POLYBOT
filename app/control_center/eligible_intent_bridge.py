from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.control_center.runtime_readiness import RuntimeReadinessService
from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    truth_envelope,
)
from app.control_center.truth_hardening import classify_freshness, truth_from_freshness
from app.control_center.orderbook_price_readiness import build_candidate_price_path_for_candidate
from app.control_center.mesh_evidence_bundle import MeshEvidenceBundleService
from app.control_center.unified_blockers import unified_blockers
from app.db.connection import DatabaseConnectionFactory
from app.repositories.runtime_state_repository import RuntimeStateRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.paper_intents import _execution_price_from_evidence, _paper_intent_blockers, _safe_paper_quantity


BRIDGE_FRESH_SECONDS = 600
ORDERBOOK_FRESH_SECONDS = 180

SOURCE_MAP = {
    "paper_eligibility_candidates": "paper_eligibility_candidates",
    "paper_intents": "paper_intents",
    "no_trade_log": "no_trade_log",
    "runtime": "/dashboard/api/v2/control/runtime-readiness",
    "paper_simulation": "system_state.metadata_json.paper_simulation",
    "governor": "StateGovernor.can_execute(RUN_PAPER_SIMULATION)",
    "orderbook": "orderbook_snapshots",
    "price": "paper_eligibility_candidates.evidence",
    "capital": "paper_accounts + paper_positions",
    "risk": "risk_decisions + paper_eligibility_candidates",
    "exit": "exit_plans + paper_eligibility_candidates",
    "lifecycle": "lifecycle_governance_decisions",
}

OUTCOME_TO_COUNT = {
    "ALREADY_HAS_INTENT": "already_has_intent",
    "WAITING_FOR_REFRESH": "waiting_for_refresh",
    "BLOCKED_BY_GOVERNOR": "blocked_by_governor",
    "BLOCKED_BY_RUNTIME": "blocked_by_runtime",
    "BLOCKED_BY_PAPER_SIMULATION": "blocked_by_paper_simulation",
    "BLOCKED_BY_PRICE": "blocked_by_price",
    "BLOCKED_BY_CAPITAL": "blocked_by_capital",
    "BLOCKED_BY_LIFECYCLE": "blocked_by_lifecycle",
    "BLOCKED_BY_RISK": "blocked_by_risk",
    "BLOCKED_BY_EXIT": "blocked_by_exit",
    "BLOCKED_BY_DATA": "blocked_by_data",
    "UNKNOWN_WITH_EXPLANATION": "unknown",
}

REQUIRED_TO_CREATE = {
    "ALREADY_HAS_INTENT": "Existing paper intent must progress through the normal paper execution path if execution gates allow it.",
    "BLOCKED_BY_RUNTIME": "System power and runtime readiness must allow paper work.",
    "BLOCKED_BY_GOVERNOR": "State Governor must allow RUN_PAPER_SIMULATION.",
    "BLOCKED_BY_PAPER_SIMULATION": "Paper Simulation must be explicitly ON.",
    "WAITING_FOR_REFRESH": "Fresh trusted market and orderbook evidence must be refreshed before intent creation.",
    "BLOCKED_BY_PRICE": "Executable price and derived safe paper quantity must be available.",
    "BLOCKED_BY_CAPITAL": "Paper account capital and open-position limits must allow a safe paper intent.",
    "BLOCKED_BY_LIFECYCLE": "Lifecycle governance must allow paper intent for this candidate.",
    "BLOCKED_BY_RISK": "Risk decision must be approved and risk blockers must clear.",
    "BLOCKED_BY_EXIT": "Exit plan must be paper_exit_ready and exit blockers must clear.",
    "BLOCKED_BY_DATA": "Missing or inconsistent candidate evidence must be repaired.",
    "BLOCKED_BY_DUPLICATE": "Existing duplicate or same-market conflict must clear.",
    "NO_TRADE_WITH_REASON": "The listed hard blockers must clear before the candidate can create a paper intent.",
    "UNKNOWN_WITH_EXPLANATION": "Missing explanation source must be restored or investigated.",
    "READY_FOR_INTENT": "Normal paper intent gate must run while runtime, paper simulation, Governor, risk, exit, data, capital, and lifecycle gates allow it.",
    "MISSING_CANDIDATE_EVENT_LINK": "A fresh orderbook event must link to this exact candidate before candidate actionability.",
    "MARKET_SCOPED_ONLY_EVENT": "Market-level mesh events must not be used for candidate actionability.",
    "AMBIGUOUS_CANDIDATE_EVENT_LINK": "Candidate/event correlation must resolve to one unambiguous candidate.",
    "TOKEN_SIDE_MISMATCH": "Candidate market, side, and token must match the orderbook event.",
    "STALE_CANDIDATE_EVENT_LINK": "Candidate/event correlation must be refreshed.",
}


class EligibleIntentBridgeService:
    """Explains the ELIGIBLE candidate to paper intent bridge without creating paper artifacts."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        governor: StateGovernor | None = None,
        runtime_readiness: RuntimeReadinessService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._runtime_readiness = runtime_readiness or RuntimeReadinessService(connection_factory=self._factory, governor=self._governor)
        self._states = RuntimeStateRepository()

    def list_bridge(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        outcome: str | None = None,
        bridge_state: str | None = None,
        market_id: str | None = None,
        side: str | None = None,
        include_ready: bool = True,
        include_blocked: bool = True,
        include_waiting: bool = True,
        include_existing_intents: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(
                self._empty_payload(now, warnings=["Eligible-to-intent bridge source is unavailable because the database is not configured."]),
                status=ControlCenterStatus.MISSING,
            )
        try:
            runtime = self._runtime_context()
            with self._factory.connect() as conn:
                if not _table_exists(conn, "paper_eligibility_candidates"):
                    return self._enveloped(
                        self._empty_payload(now, warnings=["paper_eligibility_candidates table is missing."]),
                        status=ControlCenterStatus.MISSING,
                    )
                context = self._bridge_context(conn, runtime=runtime, now=now)
                rows = self._eligible_rows(conn, market_id=market_id, side=side)
                items = [self._explain_row(conn, row, context=context, now=now) for row in rows]
                paper_intents = _count_table(conn, "paper_intents")
                latest_at = _latest_of([item.get("updated_at") or item.get("created_at") for item in items])
        except Exception as exc:
            payload = self._empty_payload(now, errors=[f"Eligible-to-intent bridge query failed: {type(exc).__name__}: {exc}"])
            return self._enveloped(payload, status=ControlCenterStatus.ERROR)

        filtered = self._filter_items(
            items,
            outcome=outcome,
            bridge_state=bridge_state,
            include_ready=include_ready,
            include_blocked=include_blocked,
            include_waiting=include_waiting,
            include_existing_intents=include_existing_intents,
        )
        paged = filtered[offset : offset + limit]
        counts = self._counts(items, paper_intents=paper_intents)
        top_outcomes = self._top(items, key="bridge_outcome", label="outcome")
        top_blockers = self._top_blockers(items)
        eligible_without = counts["eligible_without_intent"]
        explained_without = sum(1 for item in items if not item.get("existing_intent_id") and item["bridge_outcome"] != "UNKNOWN_WITH_EXPLANATION")
        unexplained_without = max(0, eligible_without - explained_without)
        freshness, age = classify_freshness(latest_at, stale_after_seconds=BRIDGE_FRESH_SECONDS, now=now)
        payload = {
            "status": self._payload_status(counts, freshness, unexplained_without),
            "source": SOURCE_MAP,
            "last_updated": _iso(latest_at or now),
            "freshness_state": freshness.value,
            "readiness_state": self._readiness_state(counts, unexplained_without),
            "truth_state": self._truth_state(freshness, latest_at).value,
            "counts": counts,
            "top_outcomes": top_outcomes,
            "top_blockers": top_blockers,
            "eligible_intent_gap": {
                "eligible_candidates": counts["eligible_candidates"],
                "paper_intents": paper_intents,
                "eligible_without_intent": eligible_without,
                "explained_without_intent": explained_without,
                "unexplained_without_intent": unexplained_without,
            },
            "items": paged,
            "warnings": self._warnings(counts, freshness, unexplained_without),
            "errors": [],
            "limit": limit,
            "offset": offset,
            "generated_at": now.isoformat(),
            "age_seconds": age,
        }
        return self._enveloped(payload, status=ControlCenterStatus(payload["status"]))

    def get_bridge(self, candidate_id: str) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(
                self._empty_payload(now, warnings=["Eligible-to-intent bridge source is unavailable because the database is not configured."]),
                status=ControlCenterStatus.MISSING,
            )
        with self._factory.connect() as conn:
            if not _table_exists(conn, "paper_eligibility_candidates"):
                return None
            row = _fetchone(
                conn,
                """
                SELECT *
                FROM paper_eligibility_candidates
                WHERE eligibility_id = %s OR id::text = %s
                LIMIT 1
                """,
                (candidate_id, candidate_id),
            )
            if not row:
                return None
            runtime = self._runtime_context()
            context = self._bridge_context(conn, runtime=runtime, now=now)
            item = self._explain_row(conn, row, context=context, now=now, include_related=True)
        latest_at = item.get("updated_at") or item.get("created_at")
        freshness, age = classify_freshness(latest_at, stale_after_seconds=BRIDGE_FRESH_SECONDS, now=now)
        payload = {
            "status": "REAL" if item["candidate_status"] == "ELIGIBLE" and freshness == ControlCenterFreshnessState.FRESH else "PARTIAL" if item["candidate_status"] != "ELIGIBLE" else "STALE",
            "source": SOURCE_MAP,
            "last_updated": _iso(latest_at or now),
            "freshness_state": freshness.value,
            "readiness_state": "PARTIAL" if item["bridge_state"] in {"WAITING", "READY_FOR_INTENT"} else "BLOCKED" if item["bridge_state"] == "BLOCKED" else "READY",
            "truth_state": self._truth_state(freshness, latest_at).value,
            "candidate": item,
            "items": [item],
            "warnings": [] if item["candidate_status"] == "ELIGIBLE" else ["Candidate is not ELIGIBLE and is outside the eligible-to-intent bridge scope."],
            "errors": [],
            "generated_at": now.isoformat(),
            "age_seconds": age,
        }
        return self._enveloped(payload, status=ControlCenterStatus(payload["status"]))

    def _eligible_rows(self, conn: Any, *, market_id: str | None, side: str | None) -> list[dict[str, Any]]:
        clauses = ["status = 'ELIGIBLE'"]
        params: list[Any] = []
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        if side:
            clauses.append("upper(side) = %s")
            params.append(side.upper())
        return _fetchall(
            conn,
            f"""
            SELECT *
            FROM paper_eligibility_candidates
            WHERE {' AND '.join(clauses)}
            ORDER BY COALESCE(updated_at, created_at) DESC NULLS LAST, id DESC
            """,
            tuple(params),
        )

    def _explain_row(self, conn: Any, row: dict[str, Any], *, context: dict[str, Any], now: datetime, include_related: bool = False) -> dict[str, Any]:
        candidate_id = str(row.get("eligibility_id") or row.get("id"))
        evidence = row.get("evidence") or {}
        candidate_status = str(row.get("status") or "UNKNOWN").upper()
        intent = self._intent_for_candidate(conn, candidate_id)
        no_trade = self._no_trade_for_candidate(conn, candidate_id)
        orderbook = self._orderbook_for_candidate(conn, row, now)
        risk = self._risk_for_candidate(conn, row)
        exit_plan = self._exit_for_candidate(conn, row)
        lifecycle = self._lifecycle_for_candidate(conn, row)
        capital = self._capital_state(conn)
        price = _execution_price_from_evidence(evidence)
        quantity = _safe_paper_quantity(price)
        candidate_freshness, candidate_age = classify_freshness(row.get("updated_at") or row.get("created_at"), stale_after_seconds=BRIDGE_FRESH_SECONDS, now=now)

        gate_blockers = _unique(sorted(_paper_intent_blockers(row)))
        blockers = set(gate_blockers)
        missing_data: list[str] = []
        stale_data: list[str] = []

        if candidate_status != "ELIGIBLE":
            blockers.add("CANDIDATE_NOT_ELIGIBLE")
        if not row.get("market_id"):
            missing_data.append("market_id")
        if not row.get("side"):
            missing_data.append("side")
        if not orderbook.get("row"):
            missing_data.append("orderbook")
        if orderbook["freshness_state"] == "STALE":
            stale_data.append("orderbook")
            blockers.add("STALE_ORDERBOOK")
        if not orderbook.get("trusted"):
            blockers.add("MISSING_TRUSTED_ORDERBOOK")
        price_path = orderbook.get("price_path") if isinstance(orderbook.get("price_path"), dict) else {}
        blockers.update(price_path.get("blockers") or [])
        for item in price_path.get("missing_data") or []:
            missing_data.append(str(item))
        for item in price_path.get("stale_data") or []:
            stale_data.append(str(item))
        if price is None:
            missing_data.append("executable_price")
            blockers.add("MISSING_EXECUTABLE_PRICE")
        if quantity is None:
            missing_data.append("quantity")
            blockers.add("MISSING_QUANTITY")
        if risk is None:
            missing_data.append("risk_decision")
        elif (not bool(risk.get("risk_approved"))) or str(risk.get("decision") or "").upper() == "BLOCK":
            blockers.add("RISK_BLOCKED")
        if exit_plan is None:
            missing_data.append("exit_plan")
        elif not bool(exit_plan.get("paper_exit_ready")):
            blockers.add("EXIT_NOT_READY")
        if lifecycle is None:
            missing_data.append("lifecycle_governance")
        elif not bool(lifecycle.get("allow_paper_intent")):
            blockers.add("LIFECYCLE_GOVERNANCE_DENIED")
        if capital["state"] == "BLOCKED":
            blockers.add(capital["reason"])
        elif capital["state"] == "UNKNOWN":
            missing_data.append("paper_capital")
        if candidate_freshness == ControlCenterFreshnessState.STALE:
            stale_data.append("candidate")

        runtime_blockers = list(context["blockers"])
        if not intent:
            blockers.update(runtime_blockers)
        mesh_bundle = MeshEvidenceBundleService(connection_factory=self._factory).latest_bundle_link(
            conn,
            market_id=row.get("market_id"),
            candidate_id=candidate_id,
            token_id=price_path.get("token_id"),
            side=row.get("side"),
        )
        if not mesh_bundle:
            blockers.add("MISSING_CANDIDATE_EVENT_LINK")
        else:
            scope = str(mesh_bundle.get("candidate_event_actionability_scope") or "UNKNOWN")
            link_state = str(mesh_bundle.get("candidate_event_link_state") or "UNKNOWN")
            if scope == "MARKET_SCOPED_ONLY":
                blockers.add("MARKET_SCOPED_ONLY_EVENT")
            elif scope == "AMBIGUOUS":
                blockers.add("AMBIGUOUS_CANDIDATE_EVENT_LINK")
            elif link_state == "TOKEN_SIDE_MISMATCH":
                blockers.add("TOKEN_SIDE_MISMATCH")
            elif link_state == "STALE_CANDIDATE_LINK":
                blockers.add("STALE_CANDIDATE_EVENT_LINK")
            elif scope not in {"CANDIDATE_SCOPED"}:
                blockers.add("MISSING_CANDIDATE_EVENT_LINK")
        blockers = set(_unique([_normalize_blocker(item) for item in blockers]))

        outcome = self._bridge_outcome(intent=intent, blockers=blockers, context=context, candidate_status=candidate_status)
        bridge_state = self._bridge_state(outcome)
        required = self._required_to_create_intent(outcome, blockers, missing_data, stale_data)
        can_create_now = outcome == "READY_FOR_INTENT"
        would_create_if_enabled = can_create_now or (outcome in {"BLOCKED_BY_RUNTIME", "BLOCKED_BY_PAPER_SIMULATION", "BLOCKED_BY_GOVERNOR"} and not self._has_candidate_hard_blockers(blockers))
        intent_age = _age_seconds(intent.get("updated_at") or intent.get("created_at"), now) if intent else None
        result = {
            "candidate_id": candidate_id,
            "market_id": row.get("market_id"),
            "side": row.get("side"),
            "candidate_status": candidate_status,
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
            "bridge_state": bridge_state,
            "bridge_outcome": outcome,
            "candidate_price_path_state": price_path.get("candidate_price_path_state"),
            "candidate_trusted_orderbook_state": price_path.get("candidate_trusted_orderbook_state"),
            "refresh_before_execution_state": price_path.get("refresh_before_execution_state"),
            "mesh_evidence_bundle": mesh_bundle,
            "mesh_evidence_bundle_state": mesh_bundle.get("bundle_state") if mesh_bundle else "MISSING",
            "mesh_evidence_correlation_id": mesh_bundle.get("correlation_id") if mesh_bundle else None,
            "candidate_event_link_state": mesh_bundle.get("candidate_event_link_state") if mesh_bundle else "UNLINKED_WITH_REASON",
            "correlation_confidence": mesh_bundle.get("correlation_confidence") if mesh_bundle else "NONE",
            "candidate_event_actionability_scope": mesh_bundle.get("candidate_event_actionability_scope") if mesh_bundle else "NOT_ACTIONABLE",
            "candidate_event_link_blockers": mesh_bundle.get("candidate_link_blockers") if mesh_bundle else ["MISSING_CANDIDATE_EVENT_LINK"],
            "existing_intent_id": intent.get("paper_intent_id") if intent else None,
            "intent_status": intent.get("intent_status") if intent else None,
            "intent_age_seconds": intent_age,
            "can_create_intent_now": can_create_now,
            "would_create_intent_if_enabled": would_create_if_enabled,
            "blockers": sorted(blockers),
            "unified_blockers": unified_blockers(
                sorted(blockers),
                source="eligible_intent_bridge",
                candidate_id=candidate_id,
                market_id=row.get("market_id"),
                side=row.get("side"),
            ),
            "required_to_create_intent": required,
            "missing_data": _unique(missing_data),
            "stale_data": _unique(stale_data),
            "source_evidence": {
                "runtime": context["runtime"],
                "paper_simulation": context["paper_simulation"],
                "governor": context["governor"],
                "orderbook": orderbook,
                "price": {
                    "executable_price": _float(price),
                    "quantity": _float(quantity),
                    "source": SOURCE_MAP["price"],
                    "price_path": price_path,
                },
                "capital": capital,
                "risk": _json_safe(risk),
                "exit": _json_safe(exit_plan),
                "lifecycle": _json_safe(lifecycle),
                "intent": _json_safe(intent),
            },
            "operator_summary": self._operator_summary(candidate_id, outcome, sorted(blockers), required),
            "freshness_state": candidate_freshness.value,
            "age_seconds": candidate_age,
        }
        if include_related:
            result["related_no_trade_rows"] = no_trade
            result["related_paper_intent_rows"] = [intent] if intent else []
        return _json_safe(result)

    def _bridge_context(self, conn: Any, *, runtime: dict[str, Any], now: datetime) -> dict[str, Any]:
        state = self._states.get_current_state(conn)
        metadata = state.metadata_json if state else {}
        paper_meta = metadata.get("paper_simulation") if isinstance(metadata, dict) else None
        paper_enabled = bool((paper_meta or {}).get("enabled")) if isinstance(paper_meta, dict) else False
        system_power = state.system_power.value if state else "UNKNOWN"
        runtime_life = str(runtime.get("runtime_life_state") or "UNKNOWN")
        try:
            governor_allows = bool(self._governor.can_execute(RuntimeAction.RUN_PAPER_SIMULATION))
        except Exception:
            governor_allows = False
        blockers: list[str] = []
        if system_power != "ON":
            blockers.append("SYSTEM_POWER_OFF")
        if runtime_life != "ALIVE":
            blockers.append("RUNTIME_STOPPED" if runtime_life == "STOPPED" else "RUNTIME_NOT_ALIVE")
        if not paper_enabled:
            blockers.append("PAPER_SIMULATION_OFF")
        if not governor_allows:
            blockers.append("GOVERNOR_DENIED_PAPER")
        return {
            "runtime": {"runtime_life_state": runtime_life, "system_power_state": system_power, "source": SOURCE_MAP["runtime"]},
            "paper_simulation": {"enabled": paper_enabled, "state": "ON" if paper_enabled else "OFF", "source": SOURCE_MAP["paper_simulation"]},
            "governor": {"allows_paper": governor_allows, "source": SOURCE_MAP["governor"]},
            "blockers": _unique(blockers),
            "now": now,
        }

    def _runtime_context(self) -> dict[str, Any]:
        try:
            payload = self._runtime_readiness.get_readiness()
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            return data or payload
        except Exception as exc:
            return {"runtime_life_state": "UNKNOWN", "errors": [f"Runtime readiness query failed: {type(exc).__name__}: {exc}"]}

    def _bridge_outcome(self, *, intent: dict[str, Any] | None, blockers: set[str], context: dict[str, Any], candidate_status: str) -> str:
        if intent:
            return "ALREADY_HAS_INTENT"
        if candidate_status != "ELIGIBLE":
            return "NO_TRADE_WITH_REASON"
        priority = (
            ("GOVERNOR_DENIED_PAPER", "BLOCKED_BY_GOVERNOR"),
            ("SYSTEM_POWER_OFF", "BLOCKED_BY_RUNTIME"),
            ("RUNTIME_STOPPED", "BLOCKED_BY_RUNTIME"),
            ("RUNTIME_NOT_ALIVE", "BLOCKED_BY_RUNTIME"),
            ("PAPER_SIMULATION_OFF", "BLOCKED_BY_PAPER_SIMULATION"),
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
        )
        for blocker, outcome in priority:
            if blocker in blockers:
                return outcome
        if blockers:
            return "NO_TRADE_WITH_REASON"
        if not context["blockers"]:
            return "READY_FOR_INTENT"
        return "UNKNOWN_WITH_EXPLANATION"

    def _bridge_state(self, outcome: str) -> str:
        if outcome in {"PAPER_INTENT_CREATED", "ALREADY_HAS_INTENT", "NO_TRADE_WITH_REASON"}:
            return "RESOLVED"
        if outcome == "READY_FOR_INTENT":
            return "READY_FOR_INTENT"
        if outcome == "WAITING_FOR_REFRESH":
            return "WAITING"
        if outcome.startswith("BLOCKED_BY"):
            return "BLOCKED"
        return "UNKNOWN"

    def _has_candidate_hard_blockers(self, blockers: set[str]) -> bool:
        runtime_only = {"SYSTEM_POWER_OFF", "RUNTIME_STOPPED", "RUNTIME_NOT_ALIVE", "PAPER_SIMULATION_OFF", "GOVERNOR_DENIED_PAPER"}
        return bool(set(blockers) - runtime_only)

    def _required_to_create_intent(self, outcome: str, blockers: set[str], missing_data: list[str], stale_data: list[str]) -> list[str]:
        required = [REQUIRED_TO_CREATE.get(outcome, REQUIRED_TO_CREATE["UNKNOWN_WITH_EXPLANATION"])]
        for blocker in sorted(blockers):
            requirement = _required_for_blocker(blocker)
            if requirement:
                required.append(requirement)
        for item in missing_data:
            required.append(f"Missing {item} must be supplied.")
        for item in stale_data:
            required.append(f"Stale {item} must be refreshed.")
        return _unique(required)

    def _intent_for_candidate(self, conn: Any, candidate_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "paper_intents"):
            return None
        return _fetchone(conn, "SELECT * FROM paper_intents WHERE eligibility_id = %s ORDER BY updated_at DESC NULLS LAST, created_at DESC LIMIT 1", (candidate_id,))

    def _no_trade_for_candidate(self, conn: Any, candidate_id: str) -> list[dict[str, Any]]:
        if not _table_exists(conn, "no_trade_log"):
            return []
        return [_json_safe(row) for row in _fetchall(conn, "SELECT * FROM no_trade_log WHERE eligibility_id = %s ORDER BY updated_at DESC NULLS LAST, created_at DESC LIMIT 10", (candidate_id,))]

    def _risk_for_candidate(self, conn: Any, row: dict[str, Any]) -> dict[str, Any] | None:
        risk_id = row.get("risk_decision_id")
        if not risk_id or not _table_exists(conn, "risk_decisions"):
            return None
        return _fetchone(conn, "SELECT * FROM risk_decisions WHERE risk_decision_id = %s LIMIT 1", (risk_id,))

    def _exit_for_candidate(self, conn: Any, row: dict[str, Any]) -> dict[str, Any] | None:
        exit_id = row.get("exit_plan_id")
        if not exit_id or not _table_exists(conn, "exit_plans"):
            return None
        return _fetchone(conn, "SELECT * FROM exit_plans WHERE exit_plan_id = %s LIMIT 1", (exit_id,))

    def _lifecycle_for_candidate(self, conn: Any, row: dict[str, Any]) -> dict[str, Any] | None:
        candidate_id = row.get("eligibility_id")
        if not candidate_id or not _table_exists(conn, "lifecycle_governance_decisions"):
            return None
        return _fetchone(
            conn,
            """
            SELECT *
            FROM lifecycle_governance_decisions
            WHERE (subject_type = 'PAPER_CANDIDATE' AND subject_id = %s)
               OR (subject_type = 'PAPER_INTENT' AND subject_id = %s)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (candidate_id, f"paper_intent_{candidate_id}"),
        )

    def _orderbook_for_candidate(self, conn: Any, row: dict[str, Any], now: datetime) -> dict[str, Any]:
        price_path = build_candidate_price_path_for_candidate(conn, row, now=now)
        return {
            "row": price_path.get("orderbook"),
            "freshness_state": price_path.get("orderbook_state") if price_path.get("orderbook_state") in {"FRESH", "STALE", "MISSING"} else "PARTIAL",
            "age_seconds": price_path.get("orderbook_age_seconds"),
            "trusted": price_path.get("trusted_orderbook_state") == "TRUSTED_FRESH",
            "source": SOURCE_MAP["orderbook"],
            "price_path": price_path,
            "token_id": price_path.get("token_id"),
            "trusted_orderbook_state": price_path.get("trusted_orderbook_state"),
            "candidate_price_path_state": price_path.get("candidate_price_path_state"),
            "candidate_trusted_orderbook_state": price_path.get("candidate_trusted_orderbook_state"),
            "price_path_state": price_path.get("price_path_state"),
            "refresh_before_execution_state": price_path.get("refresh_before_execution_state"),
        }

    def _capital_state(self, conn: Any) -> dict[str, Any]:
        if not _table_exists(conn, "paper_accounts"):
            return {"state": "UNKNOWN", "reason": "PAPER_ACCOUNT_MISSING", "source": SOURCE_MAP["capital"]}
        account = _fetchone(conn, "SELECT * FROM paper_accounts WHERE account_id='paper_default' ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 1")
        if not account:
            return {"state": "UNKNOWN", "reason": "PAPER_ACCOUNT_MISSING", "source": SOURCE_MAP["capital"]}
        active_open = _count_where(conn, "paper_positions", "closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING') AND COALESCE(excluded_from_active_paper_truth, false) = false")
        max_open = _int(account.get("max_open_positions"))
        available = _decimal_or_none(account.get("available_balance")) or Decimal("0")
        if max_open > 0 and active_open >= max_open:
            return {"state": "BLOCKED", "reason": "MAX_OPEN_POSITIONS", "active_open_positions": active_open, "source": SOURCE_MAP["capital"]}
        if available <= 0:
            return {"state": "BLOCKED", "reason": "CAPITAL_NOT_OK", "available_balance": float(available), "source": SOURCE_MAP["capital"]}
        return {"state": "OK", "available_balance": float(available), "active_open_positions": active_open, "source": SOURCE_MAP["capital"]}

    def _counts(self, items: list[dict[str, Any]], *, paper_intents: int) -> dict[str, int]:
        counts = {
            "eligible_candidates": len(items),
            "paper_intents": paper_intents,
            "eligible_without_intent": sum(1 for item in items if not item.get("existing_intent_id")),
            "already_has_intent": 0,
            "ready_for_intent": 0,
            "waiting_for_refresh": 0,
            "blocked_by_governor": 0,
            "blocked_by_runtime": 0,
            "blocked_by_paper_simulation": 0,
            "blocked_by_price": 0,
            "blocked_by_capital": 0,
            "blocked_by_lifecycle": 0,
            "blocked_by_risk": 0,
            "blocked_by_exit": 0,
            "blocked_by_data": 0,
            "unknown": 0,
        }
        for item in items:
            outcome = item.get("bridge_outcome")
            if outcome == "READY_FOR_INTENT":
                counts["ready_for_intent"] += 1
            else:
                key = OUTCOME_TO_COUNT.get(str(outcome))
                if key:
                    counts[key] += 1
        return counts

    def _top(self, items: list[dict[str, Any]], *, key: str, label: str) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for item in items:
            value = str(item.get(key) or "UNKNOWN")
            counts[value] = counts.get(value, 0) + 1
        return [{label: name, "count": count} for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:20]]

    def _top_blockers(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for item in items:
            for blocker in item.get("blockers") or []:
                counts[str(blocker)] = counts.get(str(blocker), 0) + 1
        return [{"blocker": name, "count": count} for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:20]]

    def _filter_items(self, items: list[dict[str, Any]], *, outcome: str | None, bridge_state: str | None, include_ready: bool, include_blocked: bool, include_waiting: bool, include_existing_intents: bool) -> list[dict[str, Any]]:
        filtered = items
        if outcome:
            filtered = [item for item in filtered if item["bridge_outcome"] == outcome.upper()]
        if bridge_state:
            filtered = [item for item in filtered if item["bridge_state"] == bridge_state.upper()]
        if not include_ready:
            filtered = [item for item in filtered if item["bridge_state"] != "READY_FOR_INTENT"]
        if not include_blocked:
            filtered = [item for item in filtered if item["bridge_state"] != "BLOCKED"]
        if not include_waiting:
            filtered = [item for item in filtered if item["bridge_state"] != "WAITING"]
        if not include_existing_intents:
            filtered = [item for item in filtered if item["bridge_outcome"] != "ALREADY_HAS_INTENT"]
        return filtered

    def _payload_status(self, counts: dict[str, int], freshness: ControlCenterFreshnessState, unexplained_without: int) -> str:
        if counts["eligible_candidates"] == 0:
            return "MISSING"
        if unexplained_without:
            return "PARTIAL"
        if freshness == ControlCenterFreshnessState.STALE:
            return "STALE"
        return "REAL"

    def _readiness_state(self, counts: dict[str, int], unexplained_without: int) -> str:
        if counts["eligible_candidates"] == 0:
            return "UNKNOWN"
        if unexplained_without or counts["unknown"]:
            return "PARTIAL"
        if counts["ready_for_intent"] == counts["eligible_without_intent"] and counts["eligible_without_intent"] > 0:
            return "READY"
        if counts["waiting_for_refresh"]:
            return "PARTIAL"
        return "BLOCKED"

    def _truth_state(self, freshness: ControlCenterFreshnessState, latest: Any) -> ControlCenterTruthState:
        if freshness == ControlCenterFreshnessState.FRESH:
            return ControlCenterTruthState.ACTIVE_FRESH
        if latest:
            return truth_from_freshness(freshness, has_history=True)
        return ControlCenterTruthState.UNKNOWN

    def _warnings(self, counts: dict[str, int], freshness: ControlCenterFreshnessState, unexplained_without: int) -> list[str]:
        warnings = []
        if counts["eligible_candidates"] == 0:
            warnings.append("No ELIGIBLE candidates are available for bridge explanation.")
        if counts["eligible_without_intent"]:
            warnings.append("Eligible-to-intent gap is present; this endpoint explains the gap and does not create intents.")
        if unexplained_without:
            warnings.append("Some eligible candidates remain UNKNOWN_WITH_EXPLANATION.")
        if freshness == ControlCenterFreshnessState.STALE:
            warnings.append("Bridge truth is based on stale candidate rows; refresh is required before action.")
        return warnings

    def _operator_summary(self, candidate_id: str, outcome: str, blockers: list[str], required: list[str]) -> str:
        if outcome == "ALREADY_HAS_INTENT":
            return f"Candidate {candidate_id} already has a paper intent; normal execution gates decide the next step."
        if outcome == "READY_FOR_INTENT":
            return f"Candidate {candidate_id} is eligible and ready for the normal paper intent gate."
        primary = blockers[0] if blockers else outcome
        need = required[0] if required else "Missing requirement must be investigated."
        return f"Candidate {candidate_id} did not create an intent because {primary}. Required: {need}"

    def _empty_payload(self, now: datetime, *, warnings: list[str] | None = None, errors: list[str] | None = None) -> dict[str, Any]:
        return {
            "status": "ERROR" if errors else "MISSING",
            "source": SOURCE_MAP,
            "last_updated": now.isoformat(),
            "freshness_state": ControlCenterFreshnessState.MISSING.value,
            "readiness_state": ControlCenterReadinessState.UNKNOWN.value,
            "truth_state": ControlCenterTruthState.UNKNOWN.value,
            "counts": {
                "eligible_candidates": 0,
                "paper_intents": 0,
                "eligible_without_intent": 0,
                "already_has_intent": 0,
                "ready_for_intent": 0,
                "waiting_for_refresh": 0,
                "blocked_by_governor": 0,
                "blocked_by_runtime": 0,
                "blocked_by_paper_simulation": 0,
                "blocked_by_price": 0,
                "blocked_by_capital": 0,
                "blocked_by_lifecycle": 0,
                "blocked_by_risk": 0,
                "blocked_by_exit": 0,
                "blocked_by_data": 0,
                "unknown": 0,
            },
            "top_outcomes": [],
            "top_blockers": [],
            "eligible_intent_gap": {"eligible_candidates": 0, "paper_intents": 0, "eligible_without_intent": 0, "explained_without_intent": 0, "unexplained_without_intent": 0},
            "items": [],
            "warnings": warnings or [],
            "errors": errors or [],
            "generated_at": now.isoformat(),
        }

    def _enveloped(self, payload: dict[str, Any], *, status: ControlCenterStatus) -> dict[str, Any]:
        freshness = ControlCenterFreshnessState(payload.get("freshness_state") or ControlCenterFreshnessState.MISSING)
        readiness = ControlCenterReadinessState(payload.get("readiness_state") if payload.get("readiness_state") in {item.value for item in ControlCenterReadinessState} else ControlCenterReadinessState.UNKNOWN)
        envelope = truth_envelope(
            status=status,
            source="eligible intent bridge: paper_eligibility_candidates + paper_intents + no_trade_log + runtime/governor/data/capital/lifecycle sources",
            truth_state=payload.get("truth_state") or ControlCenterTruthState.UNKNOWN,
            data=payload,
            last_updated=payload.get("last_updated"),
            stale_after_seconds=BRIDGE_FRESH_SECONDS,
            age_seconds=payload.get("age_seconds"),
            freshness_state=freshness,
            runtime_state=ControlCenterRuntimeState.STALE if freshness == ControlCenterFreshnessState.STALE else ControlCenterRuntimeState.RUNNING if status == ControlCenterStatus.REAL else ControlCenterRuntimeState.UNKNOWN,
            readiness_state=readiness,
            warnings=list(payload.get("warnings") or []),
            errors=list(payload.get("errors") or []),
        ).to_dict()
        return {**envelope, **payload}


def _required_for_blocker(blocker: str) -> str | None:
    mapping = {
        "SYSTEM_POWER_OFF": "System power must be ON.",
        "RUNTIME_STOPPED": "Runtime must be alive.",
        "RUNTIME_NOT_ALIVE": "Runtime must be alive.",
        "PAPER_SIMULATION_OFF": "Paper Simulation must be explicitly ON.",
        "GOVERNOR_DENIED_PAPER": "State Governor must allow paper simulation.",
        "MISSING_FRESH_ORDERBOOK": "Fresh trusted orderbook must be available.",
        "STALE_ORDERBOOK": "Orderbook must be refreshed within execution TTL.",
        "MISSING_TRUSTED_ORDERBOOK": "Trusted orderbook must be available.",
        "MISSING_EXECUTABLE_PRICE": "Executable orderbook price must be present.",
        "BLOCKED_MISSING_TOKEN": "Candidate side must map to a CLOB token_id.",
        "BLOCKED_MISSING_SIDE": "Candidate must include YES or NO side.",
        "BLOCKED_UNTRUSTED_SOURCE": "Trusted orderbook source must be available.",
        "TOKEN_MISMATCH": "Candidate orderbook token must match the candidate expected token_id.",
        "SIDE_MISMATCH": "Candidate orderbook side must match the candidate side.",
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
    }
    return mapping.get(blocker)


def _normalize_blocker(value: Any) -> str:
    text = str(value or "").upper().strip()
    aliases = {
        "MISSING_RISK_DECISION": "RISK_NOT_APPROVED",
        "MISSING_EXIT_PLAN": "EXIT_NOT_READY",
        "MISSING_ORDERBOOK": "MISSING_FRESH_ORDERBOOK",
        "STALE_TRUSTED_ORDERBOOK": "STALE_ORDERBOOK",
        "MISSING_MARKET_LINK": "MISSING_MARKET_ID",
    }
    return aliases.get(text, text or "UNKNOWN_WITH_EXPLANATION")


def _table_exists(conn: Any, table: str) -> bool:
    try:
        row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
        return bool(row and row["table_name"])
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return None


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"])


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _latest_of(values: list[Any]) -> Any:
    latest: datetime | None = None
    raw_latest: Any = None
    for value in values:
        parsed = _timestamp(value)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
            raw_latest = value
    return raw_latest


def _age_seconds(value: Any, now: datetime) -> float | None:
    parsed = _timestamp(value)
    if not parsed:
        return None
    return max(0.0, (now - parsed).total_seconds())


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    return str(value)


def _unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in output:
            output.append(text)
    return output


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return _iso(value)
    return value

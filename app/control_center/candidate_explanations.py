from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    truth_envelope,
)
from app.control_center.unified_blockers import unified_blockers
from app.control_center.orderbook_price_readiness import build_candidate_price_path_for_candidate
from app.control_center.mesh_evidence_bundle import MeshEvidenceBundleService
from app.control_center.truth_hardening import classify_freshness, truth_from_freshness
from app.db.connection import DatabaseConnectionFactory


CANDIDATE_FRESH_SECONDS = 600
ORDERBOOK_FRESH_SECONDS = 180
INTENT_FRESH_SECONDS = 600

SOURCE_MAP = {
    "paper_eligibility_candidates": "paper_eligibility_candidates",
    "paper_intents": "paper_intents",
    "no_trade_log": "no_trade_log",
    "risk_decisions": "risk_decisions",
    "exit_plans": "exit_plans",
    "thesis": "thesis_profiles",
    "lifecycle_governance": "lifecycle_governance_decisions",
    "orderbook_snapshots": "orderbook_snapshots",
    "market_snapshots": "market_snapshots_v2",
    "signal_bindings": "neuron_signal_bindings",
    "paper_readiness": "/dashboard/api/v2/control/paper-readiness",
}

BLOCKER_META = {
    "RISK_BLOCKED": ("HARD_BLOCK", "risk_decisions", "Risk blockers must clear and a fresh risk evaluation must approve."),
    "RISK_NOT_APPROVED": ("HARD_BLOCK", "risk_decisions", "Risk decision must become approved."),
    "RISK_REVIEW_REQUIRED": ("SOFT_BLOCK", "risk_decisions", "Risk review must complete."),
    "RISK_STALE": ("STALE_DATA", "risk_decisions", "Risk decision must be refreshed."),
    "RISK_MISSING": ("MISSING_DATA", "risk_decisions", "Risk decision must exist."),
    "MISSING_RISK_DECISION": ("MISSING_DATA", "risk_decisions", "Risk decision must exist."),
    "EXIT_NOT_READY": ("HARD_BLOCK", "exit_plans", "Exit plan must be paper_exit_ready and blockers must clear."),
    "EXIT_MISSING": ("MISSING_DATA", "exit_plans", "Exit plan must exist."),
    "MISSING_EXIT_PLAN": ("MISSING_DATA", "exit_plans", "Exit plan must exist."),
    "EXIT_STALE": ("STALE_DATA", "exit_plans", "Exit plan must be refreshed."),
    "THESIS_NOT_COMPLETE": ("HARD_BLOCK", "thesis_profiles", "Thesis profile must be complete."),
    "THESIS_MISSING": ("MISSING_DATA", "thesis_profiles", "Thesis profile must exist."),
    "MISSING_THESIS": ("MISSING_DATA", "thesis_profiles", "Thesis profile must exist."),
    "THESIS_STALE": ("STALE_DATA", "thesis_profiles", "Thesis profile must be refreshed."),
    "LIFECYCLE_GOVERNANCE_DENIED": ("GOVERNANCE_DENIED", "lifecycle_governance_decisions", "Lifecycle governance must allow paper intent and execution."),
    "GOVERNANCE_MISSING": ("MISSING_DATA", "lifecycle_governance_decisions", "Lifecycle governance decision must exist."),
    "GOVERNANCE_STALE": ("STALE_DATA", "lifecycle_governance_decisions", "Lifecycle governance must be refreshed."),
    "MISSING_MARKET_ID": ("MISSING_DATA", "paper_eligibility_candidates", "Candidate must be linked to canonical market_id."),
    "MISSING_SIDE": ("MISSING_DATA", "paper_eligibility_candidates", "Candidate must include YES or NO side."),
    "MISSING_SIGNAL_MARKET_BINDING": ("MISSING_DATA", "neuron_signal_bindings", "Signal-market binding must exist."),
    "MARKET_STALE": ("STALE_DATA", "market_snapshots_v2", "Market snapshot must be refreshed."),
    "SIGNAL_STALE": ("STALE_DATA", "neuron_signal_bindings", "Signal binding must be refreshed."),
    "MISSING_FRESH_ORDERBOOK": ("MISSING_DATA", "orderbook_snapshots", "Fresh trusted orderbook must be refreshed within execution TTL."),
    "MISSING_TRUSTED_ORDERBOOK": ("MISSING_DATA", "orderbook_snapshots", "Trusted orderbook must be available."),
    "STALE_ORDERBOOK": ("STALE_DATA", "orderbook_snapshots", "Orderbook must be refreshed within execution TTL."),
    "STALE_TRUSTED_ORDERBOOK": ("STALE_DATA", "orderbook_snapshots", "Trusted orderbook must be refreshed within execution TTL."),
    "NO_PAPER_INTENT": ("WAITING_ON_REFRESH", "paper_intents", "Eligible candidate must be converted by the paper intent gate."),
    "ONLY_STALE_PAPER_INTENT": ("STALE_DATA", "paper_intents", "Paper intent must be refreshed."),
    "INTENT_BLOCKED": ("HARD_BLOCK", "paper_intents", "Paper intent blockers must clear."),
    "INTENT_ALREADY_EXECUTED": ("HARD_BLOCK", "paper_intents", "A new unconsumed paper intent is required."),
    "SYSTEM_POWER_OFF": ("HARD_BLOCK", "system_state", "System must be ON before paper simulation can run."),
    "RUNTIME_STOPPED": ("HARD_BLOCK", "runtime_readiness", "Runtime must be alive."),
    "PAPER_SIMULATION_OFF": ("HARD_BLOCK", "system_state.metadata_json.paper_simulation", "Paper Simulation must be explicitly ON."),
    "GOVERNOR_DENIED_PAPER": ("GOVERNANCE_DENIED", "state_governor", "State Governor must allow RUN_PAPER_SIMULATION."),
    "UNKNOWN_BLOCKER": ("UNKNOWN", "unknown", "Unknown blocker must be investigated."),
    "UNKNOWN_SOURCE": ("UNKNOWN", "unknown", "Missing source must be restored."),
    "EXPLANATION_INCOMPLETE": ("UNKNOWN", "candidate_explanations", "Missing explanation source must be added or restored."),
    "WEAK_LINEAGE_OR_PROVENANCE": ("MISSING_DATA", "paper_eligibility_candidates", "Candidate must have trusted lineage and provenance."),
    "DRY_RUN_EVIDENCE": ("HARD_BLOCK", "paper_eligibility_candidates", "Candidate must be generated by runtime evidence, not dry-run evidence."),
    "MISSING_EXECUTABLE_PRICE": ("MISSING_DATA", "paper_intents", "Executable price must exist."),
    "BLOCKED_MISSING_TOKEN": ("MISSING_DATA", "markets_v2", "Candidate side must map to a CLOB token_id."),
    "BLOCKED_MISSING_SIDE": ("MISSING_DATA", "paper_eligibility_candidates", "Candidate must include YES or NO side."),
    "BLOCKED_UNTRUSTED_SOURCE": ("MISSING_DATA", "trusted_orderbook_evidence_links", "Trusted orderbook source must be available."),
    "TOKEN_MISMATCH": ("HARD_BLOCK", "orderbook_snapshots", "Orderbook token must match candidate expected token_id."),
    "SIDE_MISMATCH": ("HARD_BLOCK", "orderbook_snapshots", "Orderbook side must match candidate side."),
    "MISSING_CANDIDATE_EVENT_LINK": ("MISSING_DATA", "event_log + paper_eligibility_candidates", "Candidate must have a fresh candidate-scoped orderbook event link."),
    "MARKET_SCOPED_ONLY_EVENT": ("HARD_BLOCK", "event_log", "Market-level orderbook events cannot authorize candidate actionability."),
    "AMBIGUOUS_CANDIDATE_EVENT_LINK": ("HARD_BLOCK", "event_log + paper_eligibility_candidates", "Orderbook event must resolve to one candidate without ambiguity."),
    "STALE_CANDIDATE_EVENT_LINK": ("STALE_DATA", "event_log + paper_eligibility_candidates", "Candidate-scoped event link must be refreshed."),
}


class CandidateExplanationLedgerService:
    """Builds read-only candidate explanations from persisted candidate truth."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def list_explanations(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        market_id: str | None = None,
        side: str | None = None,
        blocker: str | None = None,
        final_outcome: str | None = None,
        freshness_state: str | None = None,
        include_evidence: bool = True,
        include_required_to_pass: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(
                self._empty_payload(now, warnings=["Candidate explanation source is unavailable because the database is not configured."]),
                status=ControlCenterStatus.MISSING,
            )
        try:
            with self._factory.connect() as conn:
                if not _table_exists(conn, "paper_eligibility_candidates"):
                    return self._enveloped(
                        self._empty_payload(now, warnings=["paper_eligibility_candidates table is missing."]),
                        status=ControlCenterStatus.MISSING,
                    )
                counts = self._counts(conn, now)
                top_blockers = self._top_blockers(conn)
                gap = self._eligible_intent_gap(conn)
                rows = self._candidate_rows(
                    conn,
                    limit=limit,
                    offset=offset,
                    status=status,
                    market_id=market_id,
                    side=side,
                    blocker=blocker,
                )
                items = [
                    self._explain_row(conn, row, now=now, include_evidence=include_evidence, include_required_to_pass=include_required_to_pass)
                    for row in rows
                ]
        except Exception as exc:
            payload = self._empty_payload(now, errors=[f"Candidate explanation query failed: {type(exc).__name__}: {exc}"])
            return self._enveloped(payload, status=ControlCenterStatus.ERROR)

        if final_outcome:
            items = [item for item in items if item["final_outcome"] == final_outcome.upper()]
        if freshness_state:
            items = [item for item in items if item["freshness_state"] == freshness_state.upper()]

        latest = _latest_of([item.get("updated_at") or item.get("created_at") for item in items])
        if latest is None:
            latest = self._latest_candidate_at()
        freshness, age = classify_freshness(latest, stale_after_seconds=CANDIDATE_FRESH_SECONDS, now=now)
        payload = {
            "status": self._payload_status(freshness, counts),
            "source": SOURCE_MAP,
            "last_updated": _iso(latest or now),
            "freshness_state": freshness.value,
            "readiness_state": self._readiness_state(counts),
            "truth_state": self._truth_state(freshness, latest).value,
            "counts": counts,
            "top_blockers": top_blockers,
            "eligible_intent_gap": gap,
            "items": items[:limit],
            "warnings": self._warnings(counts, gap, freshness),
            "errors": [],
            "limit": limit,
            "offset": offset,
            "generated_at": now.isoformat(),
            "age_seconds": age,
        }
        return self._enveloped(payload, status=ControlCenterStatus(payload["status"]))

    def get_explanation(
        self,
        candidate_id: str,
        *,
        include_evidence: bool = True,
        include_required_to_pass: bool = True,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(
                self._empty_payload(now, warnings=["Candidate explanation source is unavailable because the database is not configured."]),
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
            item = self._explain_row(conn, row, now=now, include_evidence=include_evidence, include_required_to_pass=include_required_to_pass, full=True)
        freshness = ControlCenterFreshnessState(item["freshness_state"])
        payload = {
            "status": "STALE" if freshness == ControlCenterFreshnessState.STALE else "REAL",
            "source": SOURCE_MAP,
            "last_updated": item.get("updated_at") or item.get("created_at") or now.isoformat(),
            "freshness_state": freshness.value,
            "readiness_state": "BLOCKED" if item["final_outcome"] == "BLOCKED" else "PARTIAL",
            "truth_state": self._truth_state(freshness, item.get("updated_at") or item.get("created_at")).value,
            "candidate": item,
            "items": [item],
            "warnings": item.get("warnings", []),
            "errors": [],
            "generated_at": now.isoformat(),
        }
        return self._enveloped(payload, status=ControlCenterStatus(payload["status"]))

    def _candidate_rows(
        self,
        conn: Any,
        *,
        limit: int,
        offset: int,
        status: str | None,
        market_id: str | None,
        side: str | None,
        blocker: str | None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = %s")
            params.append(status.upper())
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        if side:
            clauses.append("upper(side) = %s")
            params.append(side.upper())
        if blocker:
            clauses.append("(eligibility_blockers ? %s OR missing_requirements ? %s)")
            params.extend([blocker.upper(), blocker.upper()])
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.extend([limit, offset])
        return _fetchall(
            conn,
            f"""
            SELECT *
            FROM paper_eligibility_candidates
            {where}
            ORDER BY COALESCE(updated_at, created_at) DESC NULLS LAST, id DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params),
        )

    def _explain_row(
        self,
        conn: Any,
        row: dict[str, Any],
        *,
        now: datetime,
        include_evidence: bool,
        include_required_to_pass: bool,
        full: bool = False,
    ) -> dict[str, Any]:
        candidate_id = str(row.get("eligibility_id") or row.get("id"))
        updated_at = _timestamp(row.get("updated_at") or row.get("created_at"))
        freshness, age = classify_freshness(updated_at, stale_after_seconds=CANDIDATE_FRESH_SECONDS, now=now)
        intent = self._intent_for_candidate(conn, candidate_id)
        no_trade_rows = self._no_trade_for_candidate(conn, candidate_id, full=full)
        risk = self._risk_for_candidate(conn, row)
        exit_plan = self._exit_for_candidate(conn, row)
        thesis = self._thesis_for_candidate(conn, row)
        governance = self._governance_for_candidate(conn, row)
        orderbook = self._orderbook_for_candidate(conn, row, now)
        market = self._market_for_candidate(conn, row, now)
        signal = self._signal_for_candidate(conn, row)

        blockers = _unique(
            [
                *_list(row.get("eligibility_blockers")),
                *_list(row.get("missing_requirements")),
                *self._risk_blockers(risk),
                *self._exit_blockers(exit_plan),
                *self._thesis_blockers(thesis, row),
                *self._governance_blockers(governance),
                *self._orderbook_blockers(orderbook),
            ]
        )
        if not row.get("market_id"):
            blockers.append("MISSING_MARKET_ID")
        if not row.get("side"):
            blockers.append("MISSING_SIDE")
        if str(row.get("status") or "").upper() == "ELIGIBLE" and not intent:
            blockers.append("NO_PAPER_INTENT")
        if intent and self._is_stale(intent.get("updated_at") or intent.get("created_at"), INTENT_FRESH_SECONDS, now):
            blockers.append("ONLY_STALE_PAPER_INTENT")
        if intent and _list(intent.get("blockers")):
            blockers.append("INTENT_BLOCKED")
        if orderbook["freshness_state"] == "STALE":
            blockers.append("STALE_ORDERBOOK")
        if market["freshness_state"] == "STALE":
            blockers.append("MARKET_STALE")
        missing_data = self._missing_data(row, risk, exit_plan, thesis, governance, signal, intent)
        stale_data = self._stale_data(freshness, risk, exit_plan, thesis, governance, orderbook, market, intent, signal, now)
        if missing_data:
            blockers.append("EXPLANATION_INCOMPLETE")
        blockers = _unique([_normalize_blocker(item) for item in blockers])
        blocker_stack = [self._blocker_entry(blocker) for blocker in blockers]
        final_blocker = self._final_blocker(blockers, row, intent, freshness)
        final_outcome = self._final_outcome(row, intent, blockers, freshness)
        explanation_state = self._explanation_state(final_outcome, intent, freshness)

        evidence = {
            "market": market,
            "signal": signal,
            "orderbook": orderbook,
            "risk": risk,
            "exit": exit_plan,
            "thesis": thesis,
            "governance": governance,
            "eligibility": _json_safe(row),
            "intent": _json_safe(intent) if intent else None,
        }
        if full:
            evidence["no_trade"] = no_trade_rows
        candidate_price_path = orderbook.get("price_path") if isinstance(orderbook.get("price_path"), dict) else {}
        mesh_bundle = MeshEvidenceBundleService(connection_factory=self._factory).latest_bundle_link(
            conn,
            market_id=row.get("market_id"),
            candidate_id=candidate_id,
            token_id=candidate_price_path.get("token_id"),
            side=row.get("side"),
        )
        result = {
            "candidate_id": candidate_id,
            "market_id": row.get("market_id"),
            "side": row.get("side"),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
            "candidate_source": row.get("producer_name") or "paper_eligibility_gate",
            "created_by": row.get("generated_by") or "runtime",
            "explanation_state": explanation_state,
            "progress_state": self._progress_state(risk, exit_plan, thesis, governance, intent),
            "final_outcome": final_outcome,
            "final_blocker": final_blocker,
            "blockers": blockers,
            "unified_blockers": unified_blockers(
                blockers,
                source="candidate_explanations",
                candidate_id=candidate_id,
                market_id=row.get("market_id"),
                side=row.get("side"),
            ),
            "blocker_stack": blocker_stack,
            "evidence": evidence if include_evidence else {},
            "results": {
                "risk_result": self._risk_result(risk, row),
                "exit_result": self._exit_result(exit_plan, row),
                "thesis_result": self._thesis_result(thesis, row),
                "governance_result": self._governance_result(governance),
                "eligibility_result": str(row.get("status") or "UNKNOWN").upper(),
                "intent_result": self._intent_result(intent),
            },
            "mesh_evidence_bundle": mesh_bundle,
            "mesh_evidence_bundle_state": mesh_bundle.get("bundle_state") if mesh_bundle else "MISSING",
            "mesh_evidence_correlation_id": mesh_bundle.get("correlation_id") if mesh_bundle else None,
            "latest_event_correlation_id": mesh_bundle.get("correlation_id") if mesh_bundle else None,
            "latest_mesh_bundle_id": mesh_bundle.get("bundle_id") if mesh_bundle else None,
            "candidate_event_link_state": mesh_bundle.get("candidate_event_link_state") if mesh_bundle else "UNLINKED_WITH_REASON",
            "correlation_confidence": mesh_bundle.get("correlation_confidence") if mesh_bundle else "NONE",
            "candidate_event_actionability_scope": mesh_bundle.get("candidate_event_actionability_scope") if mesh_bundle else "NOT_ACTIONABLE",
            "required_to_link_event": mesh_bundle.get("required_to_link_event") if mesh_bundle else ["A fresh orderbook event must match candidate market, side, and token."],
            "missing_data": missing_data,
            "stale_data": stale_data,
            "required_to_pass": self._required_to_pass(blockers) if include_required_to_pass else [],
            "next_possible_state": self._next_possible_state(final_outcome, blockers),
            "operator_summary": self._operator_summary(candidate_id, final_outcome, final_blocker, blockers),
            "freshness_state": freshness.value,
            "age_seconds": age,
        }
        if full:
            result.update(
                {
                    "related_no_trade_rows": no_trade_rows,
                    "related_paper_intent_rows": [intent] if intent else [],
                    "related_risk_decision": risk,
                    "related_exit_plan": exit_plan,
                    "related_lifecycle_decision": governance,
                    "related_orderbook_freshness": orderbook,
                    "related_signal_market_binding": signal,
                }
            )
        return _json_safe(result)

    def _counts(self, conn: Any, now: datetime) -> dict[str, int]:
        cutoff = now - timedelta(seconds=CANDIDATE_FRESH_SECONDS)
        row = _fetchone(
            conn,
            """
            SELECT
              COUNT(*) AS total_candidates,
              COUNT(*) FILTER (WHERE status = 'BLOCKED') AS blocked,
              COUNT(*) FILTER (WHERE status = 'ELIGIBLE') AS eligible,
              COUNT(*) FILTER (
                WHERE status = 'ELIGIBLE'
                  AND NOT EXISTS (SELECT 1 FROM paper_intents pi WHERE pi.eligibility_id = paper_eligibility_candidates.eligibility_id)
              ) AS ready_for_intent,
              COUNT(*) FILTER (
                WHERE EXISTS (SELECT 1 FROM paper_intents pi WHERE pi.eligibility_id = paper_eligibility_candidates.eligibility_id)
              ) AS intent_created,
              COUNT(*) FILTER (WHERE COALESCE(updated_at, created_at) < %s) AS stale,
              COUNT(*) FILTER (WHERE status NOT IN ('BLOCKED','ELIGIBLE','INELIGIBLE','INCOMPLETE','ERROR')) AS unknown
            FROM paper_eligibility_candidates
            """,
            (cutoff,),
        ) or {}
        stale = _int(row.get("stale"))
        ready = _int(row.get("ready_for_intent"))
        return {
            "total_candidates": _int(row.get("total_candidates")),
            "blocked": _int(row.get("blocked")),
            "eligible": _int(row.get("eligible")),
            "waiting_for_refresh": stale,
            "ready_for_intent": ready,
            "intent_created": _int(row.get("intent_created")),
            "stale": stale,
            "unknown": _int(row.get("unknown")),
        }

    def _top_blockers(self, conn: Any) -> list[dict[str, Any]]:
        rows = _fetchall(
            conn,
            """
            SELECT item AS blocker, COUNT(*) AS count
            FROM paper_eligibility_candidates,
                 jsonb_array_elements_text(eligibility_blockers) AS item
            GROUP BY item
            ORDER BY count DESC, blocker ASC
            LIMIT 20
            """,
        )
        return [{"blocker": row["blocker"], "count": _int(row["count"]), "severity": self._severity(row["blocker"])} for row in rows]

    def _eligible_intent_gap(self, conn: Any) -> dict[str, Any]:
        row = _fetchone(
            conn,
            """
            SELECT
              COUNT(*) FILTER (WHERE pec.status = 'ELIGIBLE') AS eligible_candidates,
              (SELECT COUNT(*) FROM paper_intents) AS paper_intents,
              COUNT(*) FILTER (WHERE pec.status = 'ELIGIBLE' AND pi.paper_intent_id IS NULL) AS eligible_without_intent
            FROM paper_eligibility_candidates pec
            LEFT JOIN paper_intents pi ON pi.eligibility_id = pec.eligibility_id
            """,
        ) or {}
        eligible_without = _int(row.get("eligible_without_intent"))
        return {
            "eligible_candidates": _int(row.get("eligible_candidates")),
            "paper_intents": _int(row.get("paper_intents")),
            "eligible_without_intent": eligible_without,
            "top_reasons": [{"reason": "NO_PAPER_INTENT", "count": eligible_without, "required_to_clear": "Run the normal paper intent gate when system, data, risk, exit, and governance gates allow it."}]
            if eligible_without
            else [],
        }

    def _intent_for_candidate(self, conn: Any, candidate_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "paper_intents"):
            return None
        return _fetchone(conn, "SELECT * FROM paper_intents WHERE eligibility_id = %s ORDER BY updated_at DESC NULLS LAST, created_at DESC LIMIT 1", (candidate_id,))

    def _no_trade_for_candidate(self, conn: Any, candidate_id: str, *, full: bool) -> list[dict[str, Any]]:
        if not _table_exists(conn, "no_trade_log"):
            return []
        limit = 25 if full else 3
        return [_json_safe(row) for row in _fetchall(conn, "SELECT * FROM no_trade_log WHERE eligibility_id = %s ORDER BY updated_at DESC NULLS LAST, created_at DESC LIMIT %s", (candidate_id, limit))]

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

    def _thesis_for_candidate(self, conn: Any, row: dict[str, Any]) -> dict[str, Any] | None:
        thesis_id = row.get("thesis_id")
        if not thesis_id or not _table_exists(conn, "thesis_profiles"):
            return None
        return _fetchone(conn, "SELECT * FROM thesis_profiles WHERE thesis_id = %s LIMIT 1", (thesis_id,))

    def _governance_for_candidate(self, conn: Any, row: dict[str, Any]) -> dict[str, Any] | None:
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
            ORDER BY created_at DESC
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
            "source": SOURCE_MAP["orderbook_snapshots"],
            "price_path": price_path,
            "token_id": price_path.get("token_id"),
            "trusted_orderbook_state": price_path.get("trusted_orderbook_state"),
            "candidate_price_path_state": price_path.get("candidate_price_path_state"),
            "candidate_trusted_orderbook_state": price_path.get("candidate_trusted_orderbook_state"),
            "price_path_state": price_path.get("price_path_state"),
            "refresh_before_execution_state": price_path.get("refresh_before_execution_state"),
            "required_to_pass": price_path.get("required_to_be_candidate_price_ready") or price_path.get("required_to_be_price_ready") or [],
        }

    def _market_for_candidate(self, conn: Any, row: dict[str, Any], now: datetime) -> dict[str, Any]:
        market_id = row.get("market_id")
        market = None
        snapshot = None
        if market_id and _table_exists(conn, "markets_v2"):
            market = _fetchone(conn, "SELECT * FROM markets_v2 WHERE market_id = %s LIMIT 1", (market_id,))
        if market_id and _table_exists(conn, "market_snapshots_v2"):
            snapshot = _fetchone(conn, "SELECT * FROM market_snapshots_v2 WHERE market_id = %s ORDER BY snapshot_at DESC LIMIT 1", (market_id,))
        latest = _timestamp((snapshot or {}).get("snapshot_at") or (market or {}).get("updated_at"))
        freshness, age = classify_freshness(latest, stale_after_seconds=CANDIDATE_FRESH_SECONDS, now=now)
        return {"market": _json_safe(market), "latest_snapshot": _json_safe(snapshot), "freshness_state": freshness.value, "age_seconds": age}

    def _signal_for_candidate(self, conn: Any, row: dict[str, Any]) -> dict[str, Any]:
        signal_ids = _list(row.get("signal_ids"))
        if not signal_ids or not _table_exists(conn, "neuron_signal_bindings"):
            return {"bindings": [], "state": "MISSING"}
        bindings = _fetchall(conn, "SELECT * FROM neuron_signal_bindings WHERE signal_id = ANY(%s) LIMIT 10", (signal_ids,))
        return {"bindings": _json_safe(bindings), "state": "LINKED" if bindings else "MISSING"}

    def _risk_blockers(self, risk: dict[str, Any] | None) -> list[str]:
        if risk is None:
            return ["RISK_MISSING"]
        blockers = _list(risk.get("blockers"))
        if str(risk.get("decision") or "").upper() == "BLOCK":
            blockers.append("RISK_BLOCKED")
        if not bool(risk.get("risk_approved")):
            blockers.append("RISK_NOT_APPROVED")
        return blockers

    def _exit_blockers(self, exit_plan: dict[str, Any] | None) -> list[str]:
        if exit_plan is None:
            return ["EXIT_MISSING"]
        blockers = _list(exit_plan.get("blockers"))
        if not bool(exit_plan.get("paper_exit_ready")):
            blockers.append("EXIT_NOT_READY")
        return blockers

    def _thesis_blockers(self, thesis: dict[str, Any] | None, row: dict[str, Any]) -> list[str]:
        if row.get("thesis_id") and thesis is None:
            return ["THESIS_MISSING"]
        if not row.get("thesis_id"):
            return ["THESIS_MISSING"]
        status = str((thesis or {}).get("status") or "").upper()
        if status and status != "COMPLETE":
            return ["THESIS_NOT_COMPLETE"]
        if "THESIS_NOT_COMPLETE" in _list(row.get("eligibility_blockers")):
            return ["THESIS_NOT_COMPLETE"]
        return []

    def _governance_blockers(self, governance: dict[str, Any] | None) -> list[str]:
        if governance is None:
            return ["GOVERNANCE_MISSING"]
        blockers = _list(governance.get("critical_blockers_json"))
        if not bool(governance.get("allow_paper_intent")):
            blockers.append("LIFECYCLE_GOVERNANCE_DENIED")
        return blockers

    def _orderbook_blockers(self, orderbook: dict[str, Any]) -> list[str]:
        price_path = orderbook.get("price_path") if isinstance(orderbook.get("price_path"), dict) else {}
        blockers = list(price_path.get("blockers") or [])
        if blockers:
            return blockers
        if not orderbook.get("row"):
            return ["MISSING_FRESH_ORDERBOOK"]
        if orderbook.get("freshness_state") == "STALE":
            return ["STALE_ORDERBOOK"]
        if not orderbook.get("trusted"):
            return ["MISSING_TRUSTED_ORDERBOOK"]
        return []

    def _missing_data(self, row: dict[str, Any], risk: Any, exit_plan: Any, thesis: Any, governance: Any, signal: dict[str, Any], intent: Any) -> list[str]:
        missing = []
        if not row.get("market_id"):
            missing.append("market_id")
        if not row.get("side"):
            missing.append("side")
        if risk is None:
            missing.append("risk_decision")
        if exit_plan is None:
            missing.append("exit_plan")
        if thesis is None:
            missing.append("thesis")
        if governance is None:
            missing.append("lifecycle_governance")
        if signal.get("state") == "MISSING":
            missing.append("signal_market_binding")
        if str(row.get("status") or "").upper() == "ELIGIBLE" and intent is None:
            missing.append("paper_intent")
        return _unique(missing)

    def _stale_data(self, freshness: ControlCenterFreshnessState, risk: Any, exit_plan: Any, thesis: Any, governance: Any, orderbook: dict[str, Any], market: dict[str, Any], intent: Any, signal: dict[str, Any], now: datetime) -> list[str]:
        stale = []
        if freshness == ControlCenterFreshnessState.STALE:
            stale.append("candidate")
        for name, payload in (("risk", risk), ("exit", exit_plan), ("thesis", thesis), ("intent", intent)):
            if payload and self._is_stale(payload.get("updated_at") or payload.get("created_at"), CANDIDATE_FRESH_SECONDS, now):
                stale.append(name)
        if governance and self._is_stale(governance.get("created_at"), CANDIDATE_FRESH_SECONDS, now):
            stale.append("lifecycle_governance")
        if orderbook.get("freshness_state") == "STALE":
            stale.append("orderbook")
        if market.get("freshness_state") == "STALE":
            stale.append("market")
        bindings = signal.get("bindings") or []
        if bindings and self._is_stale(bindings[0].get("created_at"), CANDIDATE_FRESH_SECONDS, now):
            stale.append("signal")
        return _unique(stale)

    def _is_stale(self, value: Any, seconds: int, now: datetime) -> bool:
        ts = _timestamp(value)
        return bool(ts and ts < now - timedelta(seconds=seconds))

    def _risk_result(self, risk: dict[str, Any] | None, row: dict[str, Any]) -> str:
        if risk is None:
            return "UNKNOWN"
        if bool(risk.get("risk_approved")) or bool(row.get("risk_approved")):
            return "APPROVED"
        if str(risk.get("decision") or "").upper() == "BLOCK":
            return "BLOCKED"
        return "NOT_APPROVED"

    def _exit_result(self, exit_plan: dict[str, Any] | None, row: dict[str, Any]) -> str:
        if exit_plan is None:
            return "UNKNOWN"
        return "READY" if bool(exit_plan.get("paper_exit_ready")) or bool(row.get("exit_ready")) else "NOT_READY"

    def _thesis_result(self, thesis: dict[str, Any] | None, row: dict[str, Any]) -> str:
        if thesis is None:
            return "UNKNOWN"
        return str(thesis.get("status") or "UNKNOWN").upper()

    def _governance_result(self, governance: dict[str, Any] | None) -> str:
        if governance is None:
            return "UNKNOWN"
        return "ALLOWED" if bool(governance.get("allow_paper_intent")) else "DENIED"

    def _intent_result(self, intent: dict[str, Any] | None) -> str:
        if intent is None:
            return "NO_PAPER_INTENT"
        if intent.get("executed_at") or intent.get("consumed_at") or intent.get("closed_at"):
            return "INTENT_ALREADY_EXECUTED"
        if _list(intent.get("blockers")) or intent.get("execution_block_reason"):
            return "INTENT_BLOCKED"
        return str(intent.get("intent_status") or "UNKNOWN").upper()

    def _final_blocker(self, blockers: list[str], row: dict[str, Any], intent: Any, freshness: ControlCenterFreshnessState) -> str | None:
        if blockers:
            priority = ("MISSING_MARKET_ID", "MISSING_SIDE", "RISK_BLOCKED", "RISK_NOT_APPROVED", "EXIT_NOT_READY", "THESIS_NOT_COMPLETE", "LIFECYCLE_GOVERNANCE_DENIED", "MISSING_FRESH_ORDERBOOK", "STALE_ORDERBOOK", "NO_PAPER_INTENT")
            for item in priority:
                if item in blockers:
                    return item
            return blockers[0]
        if str(row.get("status") or "").upper() == "ELIGIBLE" and not intent:
            return "NO_PAPER_INTENT"
        if freshness == ControlCenterFreshnessState.STALE:
            return "STALE_CANDIDATE"
        return None

    def _final_outcome(self, row: dict[str, Any], intent: Any, blockers: list[str], freshness: ControlCenterFreshnessState) -> str:
        status = str(row.get("status") or "").upper()
        if status == "ELIGIBLE" and intent:
            return "INTENT_CREATED"
        if status == "ELIGIBLE" and freshness == ControlCenterFreshnessState.STALE:
            return "WAITING_FOR_REFRESH"
        if status == "ELIGIBLE":
            return "READY_FOR_INTENT"
        if status == "BLOCKED" or any(self._severity(item) in {"HARD_BLOCK", "GOVERNANCE_DENIED", "MISSING_DATA"} for item in blockers):
            return "BLOCKED"
        if freshness == ControlCenterFreshnessState.STALE:
            return "STALE"
        if status in {"INELIGIBLE", "INCOMPLETE"}:
            return "NO_TRADE"
        return "UNKNOWN"

    def _explanation_state(self, final_outcome: str, intent: Any, freshness: ControlCenterFreshnessState) -> str:
        if final_outcome == "BLOCKED":
            return "EXPLAINED_BLOCKED"
        if final_outcome == "ELIGIBLE":
            return "EXPLAINED_ELIGIBLE"
        if final_outcome == "WAITING_FOR_REFRESH":
            return "EXPLAINED_WAITING_FOR_REFRESH"
        if final_outcome == "READY_FOR_INTENT":
            return "EXPLAINED_READY_FOR_INTENT"
        if final_outcome == "INTENT_CREATED":
            return "EXPLAINED_INTENT_CREATED"
        if freshness == ControlCenterFreshnessState.STALE:
            return "EXPLAINED_STALE"
        return "EXPLAINED_UNKNOWN"

    def _progress_state(self, risk: Any, exit_plan: Any, thesis: Any, governance: Any, intent: Any) -> str:
        if intent:
            return "INTENT_REVIEWED"
        if governance:
            return "GOVERNANCE_REVIEWED"
        if thesis:
            return "THESIS_REVIEWED"
        if exit_plan:
            return "EXIT_REVIEWED"
        if risk:
            return "RISK_REVIEWED"
        return "ELIGIBILITY_REVIEWED"

    def _blocker_entry(self, blocker: str) -> dict[str, str]:
        severity, source, required = BLOCKER_META.get(blocker, BLOCKER_META["UNKNOWN_BLOCKER"])
        return {
            "blocker": blocker,
            "severity": severity,
            "source": source,
            "reason": blocker.replace("_", " ").title(),
            "required_to_clear": required,
        }

    def _required_to_pass(self, blockers: list[str]) -> list[str]:
        return _unique([self._blocker_entry(blocker)["required_to_clear"] for blocker in blockers])

    def _next_possible_state(self, final_outcome: str, blockers: list[str]) -> str:
        if final_outcome == "INTENT_CREATED":
            return "INTENT_REVIEWED"
        if "NO_PAPER_INTENT" in blockers:
            return "READY_FOR_INTENT_AFTER_REFRESH"
        if any(self._severity(item) == "STALE_DATA" for item in blockers):
            return "WAITING_FOR_REFRESH"
        if blockers:
            return "REVIEW_REQUIRED"
        return "READY_FOR_INTENT"

    def _operator_summary(self, candidate_id: str, final_outcome: str, final_blocker: str | None, blockers: list[str]) -> str:
        if final_blocker:
            return f"Candidate {candidate_id} is {final_outcome} because {final_blocker}; {len(blockers)} blocker(s) are visible."
        return f"Candidate {candidate_id} is {final_outcome}; no blocker stack was returned."

    def _severity(self, blocker: str) -> str:
        return BLOCKER_META.get(_normalize_blocker(blocker), BLOCKER_META["UNKNOWN_BLOCKER"])[0]

    def _empty_payload(self, now: datetime, *, warnings: list[str] | None = None, errors: list[str] | None = None) -> dict[str, Any]:
        return {
            "status": "MISSING" if not errors else "ERROR",
            "source": SOURCE_MAP,
            "last_updated": now.isoformat(),
            "freshness_state": ControlCenterFreshnessState.MISSING.value,
            "readiness_state": ControlCenterReadinessState.UNKNOWN.value,
            "truth_state": ControlCenterTruthState.UNKNOWN.value,
            "counts": {"total_candidates": 0, "blocked": 0, "eligible": 0, "waiting_for_refresh": 0, "ready_for_intent": 0, "intent_created": 0, "stale": 0, "unknown": 0},
            "top_blockers": [],
            "eligible_intent_gap": {"eligible_candidates": 0, "paper_intents": 0, "eligible_without_intent": 0, "top_reasons": []},
            "items": [],
            "warnings": warnings or [],
            "errors": errors or [],
            "generated_at": now.isoformat(),
        }

    def _payload_status(self, freshness: ControlCenterFreshnessState, counts: dict[str, int]) -> str:
        if counts["total_candidates"] == 0:
            return "MISSING"
        if freshness == ControlCenterFreshnessState.STALE:
            return "STALE"
        if counts["unknown"]:
            return "PARTIAL"
        return "REAL"

    def _readiness_state(self, counts: dict[str, int]) -> str:
        if counts["total_candidates"] == 0:
            return "UNKNOWN"
        if counts["blocked"] > 0:
            return "BLOCKED"
        if counts["ready_for_intent"] > 0 or counts["stale"] > 0:
            return "PARTIAL"
        return "READY"

    def _truth_state(self, freshness: ControlCenterFreshnessState, latest: Any) -> ControlCenterTruthState:
        if freshness == ControlCenterFreshnessState.FRESH:
            return ControlCenterTruthState.ACTIVE_FRESH
        if latest:
            return truth_from_freshness(freshness, has_history=True)
        return ControlCenterTruthState.UNKNOWN

    def _warnings(self, counts: dict[str, int], gap: dict[str, Any], freshness: ControlCenterFreshnessState) -> list[str]:
        warnings = []
        if counts.get("total_candidates", 0) == 0:
            warnings.append("No candidate rows are available in paper_eligibility_candidates.")
        if freshness == ControlCenterFreshnessState.STALE:
            warnings.append("Candidate explanation ledger is based on stale candidate rows; refresh is required before action.")
        if gap.get("eligible_without_intent"):
            warnings.append("Eligible-to-intent gap is present; this phase exposes the gap but does not bridge it.")
        if counts.get("blocked"):
            warnings.append("Blocked candidates are explained with persisted blockers; no eligibility decision was changed.")
        return warnings

    def _latest_candidate_at(self) -> Any:
        try:
            with self._factory.connect() as conn:
                return _fetch_scalar(conn, "SELECT MAX(COALESCE(updated_at, created_at)) AS ts FROM paper_eligibility_candidates")
        except Exception:
            return None

    def _enveloped(self, payload: dict[str, Any], *, status: ControlCenterStatus) -> dict[str, Any]:
        freshness = ControlCenterFreshnessState(payload.get("freshness_state") or ControlCenterFreshnessState.MISSING)
        readiness = ControlCenterReadinessState(payload.get("readiness_state") if payload.get("readiness_state") in {item.value for item in ControlCenterReadinessState} else ControlCenterReadinessState.UNKNOWN)
        runtime_state = ControlCenterRuntimeState.STALE if freshness == ControlCenterFreshnessState.STALE else ControlCenterRuntimeState.RUNNING if status == ControlCenterStatus.REAL else ControlCenterRuntimeState.UNKNOWN
        envelope = truth_envelope(
            status=status,
            source="candidate explanations: paper_eligibility_candidates + no_trade_log + paper_intents + risk/exit/thesis/governance/orderbook sources",
            truth_state=payload.get("truth_state") or ControlCenterTruthState.UNKNOWN,
            data=payload,
            last_updated=payload.get("last_updated"),
            stale_after_seconds=CANDIDATE_FRESH_SECONDS,
            age_seconds=payload.get("age_seconds"),
            freshness_state=freshness,
            runtime_state=runtime_state,
            readiness_state=readiness,
            warnings=list(payload.get("warnings") or []),
            errors=list(payload.get("errors") or []),
        ).to_dict()
        return {**envelope, **payload}


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


def _fetch_scalar(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = _fetchone(conn, sql, params)
    if not row:
        return None
    return row.get("ts") or next(iter(row.values()))


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).upper() for item in value if item is not None]
    if isinstance(value, tuple):
        return [str(item).upper() for item in value if item is not None]
    return [str(value).upper()]


def _normalize_blocker(value: Any) -> str:
    text = str(value or "").upper().strip()
    aliases = {
        "RISK_REJECTED": "RISK_BLOCKED",
        "CANDIDATE_NOT_ELIGIBLE": "UNKNOWN_BLOCKER",
        "MISSING_EXIT_PLAN": "EXIT_MISSING",
        "MISSING_RISK_DECISION": "RISK_MISSING",
        "MISSING_THESIS": "THESIS_MISSING",
    }
    return aliases.get(text, text or "UNKNOWN_BLOCKER")


def _unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in output:
            output.append(text)
    return output


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


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    return str(value)


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

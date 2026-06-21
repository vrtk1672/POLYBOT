from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import InvalidOperation
from typing import Any

from app.control_center.candidate_event_correlation import build_event_correlation
from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    truth_envelope,
)
from app.control_center.unified_blockers import unified_blockers
from app.db.connection import DatabaseConnectionFactory
from app.events.types import EventType


EVENT_TYPE = EventType.ORDERBOOK_SNAPSHOT_CREATED.value
STALE_AFTER_SECONDS = 300
REQUIRED_OPINIONS = ("liquidity", "risk", "exit", "capital", "lifecycle")
REACTION_BRAINS = ("liquidity", "risk", "exit", "capital", "lifecycle")


class MeshEvidenceBundleService:
    """Read-only shared evidence bundle view for event-driven mesh sessions."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def list_bundles(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        market_id: str | None = None,
        candidate_id: str | None = None,
        correlation_id: str | None = None,
        event_id: str | None = None,
        state: str | None = None,
        include_opinions: bool = True,
        include_conflicts: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(
                self._empty_payload(now, warnings=["Mesh evidence bundle source is unavailable because the database is not configured."]),
                status=ControlCenterStatus.MISSING,
            )
        try:
            with self._factory.connect() as conn:
                missing = [table for table in ("event_log", "brain_outputs", "coordinator_decisions", "orderbook_snapshots") if not _table_exists(conn, table)]
                if missing:
                    payload = self._empty_payload(now, warnings=[f"Missing mesh evidence source tables: {', '.join(missing)}."])
                    return self._enveloped(payload, status=ControlCenterStatus.MISSING)
                rows = self._fetch_events(
                    conn,
                    limit=max(limit + offset, limit),
                    market_id=market_id,
                    candidate_id=candidate_id,
                    correlation_id=correlation_id,
                    event_id=event_id,
                )
                items = [
                    self._build_bundle(conn, dict(row), now=now, include_opinions=include_opinions, include_conflicts=include_conflicts)
                    for row in rows
                ]
                if state:
                    wanted = state.upper()
                    items = [item for item in items if item.get("bundle_state") == wanted or item.get("mesh_session_state") == wanted]
                paged = items[offset : offset + limit]
                latest = _latest_of([item.get("created_at") for item in items])
                counts = self._counts(items)
        except Exception as exc:
            return self._enveloped(
                self._empty_payload(now, errors=[f"Mesh evidence bundle query failed: {type(exc).__name__}: {exc}"]),
                status=ControlCenterStatus.ERROR,
            )

        freshness_state, truth_state, age = _freshness(latest, now)
        bundle_state = self._overall_bundle_state(counts)
        payload = {
            "status": self._payload_status(bundle_state, freshness_state),
            "source": _source_map(),
            "last_updated": latest or now.isoformat(),
            "freshness_state": freshness_state,
            "readiness_state": "READY" if bundle_state == "COMPLETE" else "PARTIAL" if bundle_state in {"PARTIAL", "CONFLICTED"} else "BLOCKED" if bundle_state == "MISSING" else "UNKNOWN",
            "truth_state": truth_state,
            "bundle_state": bundle_state,
            "counts": counts,
            "top_conflicts": self._top_conflicts(items),
            "top_missing_opinions": self._top_missing_opinions(items),
            "items": paged,
            "warnings": self._warnings(bundle_state, counts),
            "errors": [],
            "limit": limit,
            "offset": offset,
            "event_type": EVENT_TYPE,
            "include_opinions": include_opinions,
            "include_conflicts": include_conflicts,
            "generated_at": now.isoformat(),
            "age_seconds": age,
        }
        return self._enveloped(payload, status=ControlCenterStatus(payload["status"]))

    def get_bundle(self, correlation_id: str) -> dict[str, Any] | None:
        payload = self.list_bundles(limit=50, correlation_id=correlation_id, include_opinions=True, include_conflicts=True)
        items = payload.get("items") or payload.get("data", {}).get("items") or []
        if not items:
            return None
        data = dict(payload.get("data") or payload)
        data["items"] = items
        data["bundle"] = items[0]
        return self._enveloped(data, status=ControlCenterStatus(payload.get("status", "PARTIAL")))

    def latest_bundle_link(
        self,
        conn: Any,
        *,
        market_id: str | None,
        candidate_id: str | None = None,
        token_id: str | None = None,
        side: str | None = None,
    ) -> dict[str, Any] | None:
        if not _table_exists(conn, "event_log"):
            return None
        clauses = ["event_type = %s"]
        params: list[Any] = [EVENT_TYPE]
        if market_id:
            clauses.append("payload_json->>'market_id' = %s")
            params.append(market_id)
        if token_id:
            clauses.append("payload_json->>'token_id' = %s")
            params.append(token_id)
        if side:
            clauses.append("upper(payload_json->>'side') = %s")
            params.append(side.upper())
        row = conn.execute(
            f"""
            SELECT event_id, correlation_id, payload_json, stored_at
            FROM event_log
            WHERE {' AND '.join(clauses)}
            ORDER BY stored_at DESC, id DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
        if not row:
            return None
        payload = row.get("payload_json") or {}
        correlation = build_event_correlation(conn, dict(row), include_bundle=False, include_candidates=False)
        candidate_link_blockers = list(correlation.get("blockers") or [])
        required_to_link_event = list(correlation.get("required_to_link_candidate") or [])
        link_candidate_id = correlation.get("candidate_id") or payload.get("candidate_id")
        candidate_link_state = correlation.get("candidate_event_link_state")
        candidate_actionability_scope = correlation.get("candidate_event_actionability_scope")
        correlation_confidence = correlation.get("correlation_confidence")
        if candidate_id and link_candidate_id and str(link_candidate_id) != str(candidate_id):
            candidate_link_state = "UNLINKED_WITH_REASON"
            candidate_actionability_scope = "NOT_ACTIONABLE"
            correlation_confidence = "NONE"
            candidate_link_blockers.append("CANDIDATE_EVENT_LINK_POINTS_TO_DIFFERENT_CANDIDATE")
            required_to_link_event.append("Event correlation must resolve to this candidate_id, not a different candidate.")
        link = {
            "bundle_id": f"mesh_bundle_{row['correlation_id']}",
            "correlation_id": row["correlation_id"],
            "event_id": row["event_id"],
            "market_id": payload.get("market_id"),
            "candidate_id": link_candidate_id,
            "side": payload.get("side"),
            "token_id": payload.get("token_id"),
            "bundle_state": "UNKNOWN",
            "latest_event_at": _iso(row.get("stored_at")),
            "candidate_event_link_state": candidate_link_state,
            "candidate_event_actionability_scope": candidate_actionability_scope,
            "correlation_confidence": correlation_confidence,
            "candidate_link_blockers": sorted(set(candidate_link_blockers)),
            "candidate_link_unified_blockers": unified_blockers(
                sorted(set(candidate_link_blockers)),
                source="mesh_evidence_bundle",
                candidate_id=link_candidate_id,
                event_id=row["event_id"],
                correlation_id=row["correlation_id"],
                market_id=payload.get("market_id"),
                side=payload.get("side"),
                token_id=payload.get("token_id"),
            ),
            "required_to_link_event": required_to_link_event,
        }
        link.update(_latest_mesh_opinion_summary(conn, str(row["correlation_id"])))
        return link

    def _fetch_events(
        self,
        conn: Any,
        *,
        limit: int,
        market_id: str | None,
        candidate_id: str | None,
        correlation_id: str | None,
        event_id: str | None,
    ) -> list[dict[str, Any]]:
        clauses = ["event_type = %s"]
        params: list[Any] = [EVENT_TYPE]
        if market_id:
            clauses.append("payload_json->>'market_id' = %s")
            params.append(market_id)
        if candidate_id:
            clauses.append("payload_json->>'candidate_id' = %s")
            params.append(candidate_id)
        if correlation_id:
            clauses.append("correlation_id = %s")
            params.append(correlation_id)
        if event_id:
            clauses.append("event_id = %s")
            params.append(event_id)
        params.append(limit)
        return conn.execute(
            f"""
            SELECT *
            FROM event_log
            WHERE {' AND '.join(clauses)}
            ORDER BY
                CASE
                    WHEN payload_json ? 'candidate_id' AND COALESCE(payload_json->>'candidate_id', '') <> '' THEN 0
                    ELSE 1
                END,
                stored_at DESC,
                id DESC
            LIMIT %s
            """,
            tuple(params),
        ).fetchall()

    def _build_bundle(
        self,
        conn: Any,
        event: dict[str, Any],
        *,
        now: datetime,
        include_opinions: bool,
        include_conflicts: bool,
    ) -> dict[str, Any]:
        payload = event.get("payload_json") or {}
        correlation_id = str(event.get("correlation_id") or "")
        correlation = build_event_correlation(conn, event, now=now, include_bundle=False, include_candidates=True)
        market_id = payload.get("market_id")
        candidate_id = correlation.get("candidate_id") or payload.get("candidate_id")
        side = payload.get("side")
        token_id = payload.get("token_id")
        orderbook = self._orderbook(conn, payload, event, now)
        brain_rows = self._brain_rows(conn, correlation_id)
        opinions = self._opinions(conn, brain_rows, market_id=market_id, candidate_id=candidate_id, side=side, token_id=token_id)
        coordinator = self._coordinator(conn, correlation_id)
        opinion_states = {key: opinion.get("state", "MISSING") for key, opinion in opinions.items()}
        conflicts = self._conflicts(
            payload=payload,
            orderbook=orderbook,
            opinions=opinions,
            opinion_states=opinion_states,
            coordinator=coordinator,
            event_at=event.get("stored_at") or event.get("occurred_at"),
        ) if include_conflicts else []
        bundle_state = self._bundle_state(payload, orderbook, opinion_states, coordinator, conflicts)
        mesh_consensus_state = self._mesh_consensus_state(coordinator, opinion_states, conflicts)
        mesh_session_state = self._mesh_session_state(bundle_state, conflicts, opinion_states, mesh_consensus_state)
        missing_fields = [name for name, value in (("market_id", market_id), ("side", side), ("token_id", token_id)) if not value]
        required = self._required_to_progress(missing_fields, opinion_states, conflicts, coordinator)
        return {
            "bundle_id": f"mesh_bundle_{correlation_id or event.get('event_id')}",
            "session_id": self._session_id(conn, correlation_id, market_id, candidate_id),
            "event_id": event.get("event_id"),
            "correlation_id": correlation_id,
            "event_type": event.get("event_type"),
            "market_id": market_id,
            "candidate_id": candidate_id,
            "side": side,
            "token_id": token_id,
            "bundle_state": bundle_state,
            "mesh_session_state": mesh_session_state,
            "mesh_consensus_state": mesh_consensus_state,
            "candidate_event_link_state": correlation.get("candidate_event_link_state"),
            "candidate_event_link_freshness": correlation.get("candidate_event_link_freshness"),
            "candidate_event_actionability_scope": correlation.get("candidate_event_actionability_scope"),
            "correlation_confidence": correlation.get("correlation_confidence"),
            "candidate_link_blockers": correlation.get("blockers") or [],
            "candidate_link_unified_blockers": unified_blockers(
                correlation.get("blockers") or [],
                source="mesh_evidence_bundle",
                candidate_id=candidate_id,
                event_id=event.get("event_id"),
                correlation_id=correlation_id,
                market_id=market_id,
                side=side,
                token_id=token_id,
            ),
            "required_to_link_candidate": correlation.get("required_to_link_candidate") or [],
            "matched_candidates": correlation.get("matched_candidates") or [],
            "ambiguous_candidates": correlation.get("ambiguous_candidates") or [],
            "orderbook": orderbook,
            "opinions": opinions if include_opinions else {},
            "opinion_states": opinion_states,
            "conflicts": conflicts if include_conflicts else [],
            "coordinator": {
                **coordinator,
                "required_to_progress": required,
            },
            "missing_fields": missing_fields,
            "created_at": _iso(event.get("stored_at") or event.get("occurred_at")),
            "operator_summary": self._summary(market_id, bundle_state, opinion_states, conflicts, coordinator),
        }

    def _orderbook(self, conn: Any, payload: dict[str, Any], event: dict[str, Any], now: datetime) -> dict[str, Any]:
        snapshot_ref = payload.get("orderbook_snapshot_id")
        row = None
        if snapshot_ref:
            row = conn.execute(
                """
                SELECT *
                FROM orderbook_snapshots
                WHERE orderbook_snapshot_id = %s OR id::text = %s
                ORDER BY collected_at DESC NULLS LAST, snapshot_at DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                (snapshot_ref, str(payload.get("orderbook_snapshot_pk") or snapshot_ref)),
            ).fetchone()
        if not row and payload.get("market_id"):
            clauses = ["market_id = %s"]
            params: list[Any] = [payload.get("market_id")]
            if payload.get("token_id"):
                clauses.append("token_id = %s")
                params.append(payload.get("token_id"))
            if payload.get("side"):
                clauses.append("upper(side) = upper(%s)")
                params.append(payload.get("side"))
            row = conn.execute(
                f"""
                SELECT *
                FROM orderbook_snapshots
                WHERE {' AND '.join(clauses)}
                ORDER BY collected_at DESC NULLS LAST, snapshot_at DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        source = dict(row) if row else {}
        ts = source.get("collected_at") or source.get("snapshot_at") or event.get("stored_at")
        age = _age_seconds(ts, now)
        fresh = age is not None and age <= 180 and not bool(source.get("is_stale"))
        return {
            "snapshot_id": source.get("orderbook_snapshot_id") or snapshot_ref,
            "trusted_state": "TRUSTED_FRESH" if fresh else "TRUSTED_STALE" if source else "MISSING",
            "freshness_state": "FRESH" if fresh else "STALE" if source else "MISSING",
            "best_bid": _float(source.get("best_bid") if source else payload.get("best_bid")),
            "best_ask": _float(source.get("best_ask") if source else payload.get("best_ask")),
            "spread": _float(source.get("spread") if source else payload.get("spread")),
            "depth_1c": _float(source.get("depth_1c")),
            "depth_2c": _float(source.get("depth_2c")),
            "depth_5c": _float(source.get("depth_5c")),
            "age_seconds": age,
            "last_orderbook_at": _iso(ts),
            "source": source.get("source") or payload.get("source"),
            "status": source.get("snapshot_status"),
            "blockers": [] if fresh else ["MISSING_ORDERBOOK"] if not source else ["STALE_ORDERBOOK"],
        }

    def _brain_rows(self, conn: Any, correlation_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM brain_outputs
                WHERE correlation_id = %s
                  AND generated_by = 'minimal_event_mesh_proof'
                ORDER BY created_at ASC, id ASC
                """,
                (correlation_id,),
            ).fetchall()
        ]

    def _opinions(
        self,
        conn: Any,
        rows: list[dict[str, Any]],
        *,
        market_id: str | None,
        candidate_id: str | None,
        side: str | None,
        token_id: str | None,
    ) -> dict[str, dict[str, Any]]:
        opinions: dict[str, dict[str, Any]] = {}
        latest_by_brain = {str(row.get("brain")): row for row in rows}
        for brain in REACTION_BRAINS:
            row = latest_by_brain.get(brain)
            if row:
                opinions[brain] = _brain_opinion(row, brain)
            elif brain == "capital":
                opinions[brain] = self._capital_opinion(conn, market_id=market_id, candidate_id=candidate_id)
            elif brain == "lifecycle":
                opinions[brain] = self._lifecycle_opinion(conn, market_id=market_id, candidate_id=candidate_id, side=side, token_id=token_id)
            else:
                opinions[brain] = _missing_opinion(brain, f"No {brain} brain output exists for this bundle correlation.")
        return opinions

    def _capital_opinion(self, conn: Any, *, market_id: str | None, candidate_id: str | None) -> dict[str, Any]:
        if not _table_exists(conn, "capital_brain_evaluations"):
            return _missing_opinion("capital", "capital_brain_evaluations table is missing.")
        clauses: list[str] = []
        params: list[Any] = []
        if candidate_id:
            clauses.append("candidate_id = %s")
            params.append(candidate_id)
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        if not clauses:
            return _missing_opinion("capital", "No candidate_id or market_id is available to locate a capital opinion.")
        row = conn.execute(
            f"""
            SELECT *
            FROM capital_brain_evaluations
            WHERE {' OR '.join(clauses)}
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
        if not row:
            return _missing_opinion("capital", "No source-backed capital opinion exists for this market or candidate.")
        data = dict(row)
        blockers = data.get("risk_flags_json") or []
        state = "PRESENT" if str(data.get("decision")) not in {"CAPITAL_BLOCK", "CAPITAL_INSUFFICIENT_DATA"} else "CONFLICTING"
        return {
            "brain": "capital",
            "state": state,
            "event_native_state": "JOINED_HISTORICAL",
            "capital_opinion_state": "CAPITAL_BLOCKED" if state == "CONFLICTING" else "CAPITAL_OK",
            "decision": data.get("decision"),
            "summary": data.get("reason"),
            "blockers": blockers,
            "warnings": data.get("missing_inputs_json") or [],
            "evaluation_id": data.get("evaluation_id"),
            "created_at": _iso(data.get("created_at")),
        }

    def _lifecycle_opinion(
        self,
        conn: Any,
        *,
        market_id: str | None,
        candidate_id: str | None,
        side: str | None,
        token_id: str | None,
    ) -> dict[str, Any]:
        if not _table_exists(conn, "lifecycle_governance_decisions"):
            return _missing_opinion("lifecycle", "lifecycle_governance_decisions table is missing.")
        clauses: list[str] = []
        params: list[Any] = []
        if candidate_id:
            clauses.append("subject_id = %s")
            params.append(candidate_id)
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        if side:
            clauses.append("upper(side) = %s")
            params.append(side.upper())
        if token_id:
            clauses.append("token_id = %s")
            params.append(token_id)
        if not clauses:
            return _missing_opinion("lifecycle", "No candidate, market, side, or token is available to locate lifecycle governance.")
        row = conn.execute(
            f"""
            SELECT *
            FROM lifecycle_governance_decisions
            WHERE {' OR '.join(clauses)}
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
        if not row:
            return _missing_opinion("lifecycle", "No source-backed lifecycle governance opinion exists for this bundle.")
        data = dict(row)
        blockers = data.get("critical_blockers_json") or []
        allowed = bool(data.get("allow_paper_intent") or data.get("allow_paper_execution"))
        return {
            "brain": "lifecycle",
            "state": "PRESENT" if allowed else "CONFLICTING",
            "event_native_state": "JOINED_HISTORICAL",
            "lifecycle_opinion_state": "LIFECYCLE_ALLOWED" if allowed else "LIFECYCLE_DENIED",
            "decision": data.get("actionability_class"),
            "summary": data.get("reason"),
            "blockers": blockers,
            "warnings": (data.get("optional_missing_json") or []) + (data.get("context_dependent_missing_json") or []),
            "decision_id": data.get("decision_id"),
            "allow_paper_intent": data.get("allow_paper_intent"),
            "allow_paper_execution": data.get("allow_paper_execution"),
            "created_at": _iso(data.get("created_at")),
        }

    def _coordinator(self, conn: Any, correlation_id: str) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT *
            FROM coordinator_decisions
            WHERE correlation_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (correlation_id,),
        ).fetchone()
        if not row:
            return {
                "decision_id": None,
                "state": "NO_DECISION",
                "decision": "NO_ACTION",
                "reason": "No coordinator decision exists for this bundle correlation.",
                "required_to_progress": ["Coordinator must produce a decision trace."],
                "execution_allowed": False,
            }
        data = dict(row)
        metadata = data.get("metadata_json") or {}
        return {
            "decision_id": data.get("coordinator_decision_id"),
            "state": metadata.get("coordinator_state") or "RESOLVED",
            "decision": metadata.get("decision") or data.get("final_state"),
            "mesh_consensus_state": metadata.get("mesh_consensus_state"),
            "capital_opinion_state": metadata.get("capital_opinion_state"),
            "lifecycle_opinion_state": metadata.get("lifecycle_opinion_state"),
            "reason": data.get("primary_reason"),
            "conflicts": metadata.get("conflicts") or [],
            "required_to_progress": data.get("required_reviews_json") or [],
            "execution_allowed": bool(data.get("execution_allowed")),
            "created_at": _iso(data.get("created_at")),
        }

    def _session_id(self, conn: Any, correlation_id: str, market_id: str | None, candidate_id: str | None) -> str | None:
        if not _table_exists(conn, "mesh_sessions"):
            return None
        clauses = ["correlation_id = %s"]
        params: list[Any] = [correlation_id]
        if candidate_id:
            clauses.append("candidate_id = %s")
            params.append(candidate_id)
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        row = conn.execute(
            f"""
            SELECT session_id
            FROM mesh_sessions
            WHERE {' OR '.join(clauses)}
            ORDER BY last_event_at DESC NULLS LAST, opened_at DESC, id DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
        return str(row["session_id"]) if row else None

    def _conflicts(
        self,
        *,
        payload: dict[str, Any],
        orderbook: dict[str, Any],
        opinions: dict[str, dict[str, Any]],
        opinion_states: dict[str, str],
        coordinator: dict[str, Any],
        event_at: Any,
    ) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        liquidity = opinions["liquidity"]
        risk = opinions["risk"]
        exit_opinion = opinions["exit"]
        if liquidity.get("state") == "PRESENT" and risk.get("state") in {"CONFLICTING", "STALE"}:
            conflicts.append(_conflict("LIQUIDITY_USABLE_RISK_BLOCKED", "HARD_CONFLICT", ["liquidity", "risk"], "Liquidity is usable but risk opinion is blocked.", "Risk blockers must clear or coordinator must choose PRICE_BLOCKED."))
        if exit_opinion.get("state") != "PRESENT" and coordinator.get("decision") == "PRICE_READY":
            conflicts.append(_conflict("EXIT_NOT_READY_COORDINATOR_PRICE_READY", "HARD_CONFLICT", ["exit", "coordinator"], "Exit opinion is not ready while coordinator says price ready.", "Coordinator must downgrade or exit opinion must become ready."))
        if orderbook.get("freshness_state") == "FRESH" and payload.get("candidate_id") and _candidate_claims_stale(opinions):
            conflicts.append(_conflict("ORDERBOOK_FRESH_CANDIDATE_STALE", "SOFT_CONFLICT", ["orderbook", "candidate"], "Orderbook is fresh but a linked candidate source still reports stale data.", "Candidate explanation must refresh against latest orderbook."))
        if opinion_states.get("capital") == "MISSING" and coordinator.get("decision") == "PRICE_READY":
            conflicts.append(_conflict("CAPITAL_MISSING_COORDINATOR_PRICE_READY", "MISSING_OPINION", ["capital", "coordinator"], "Capital opinion is missing while coordinator says price ready.", "Capital opinion must be present before intent readiness can rely on this bundle."))
        if opinions.get("capital", {}).get("capital_opinion_state") == "CAPITAL_BLOCKED" and coordinator.get("decision") == "PRICE_READY":
            conflicts.append(_conflict("CAPITAL_BLOCKED_COORDINATOR_PRICE_READY", "HARD_CONFLICT", ["capital", "coordinator"], "Capital blocks progress while coordinator says price ready.", "Coordinator must downgrade or capital blockers must clear."))
        if opinions.get("lifecycle", {}).get("lifecycle_opinion_state") == "LIFECYCLE_DENIED" and coordinator.get("decision") == "PRICE_READY":
            conflicts.append(_conflict("LIFECYCLE_DENIED_COORDINATOR_PRICE_READY", "HARD_CONFLICT", ["lifecycle", "coordinator"], "Lifecycle governance denies progress while coordinator says price ready.", "Coordinator must downgrade or lifecycle blockers must clear."))
        if payload.get("token_id"):
            for name, opinion in opinions.items():
                op_token = opinion.get("token_id")
                if op_token and op_token != payload.get("token_id"):
                    conflicts.append(_conflict("TOKEN_MISMATCH", "HARD_CONFLICT", [name, "event"], "Opinion token does not match event token.", "All opinions must reference the bundle token_id."))
        for name, opinion in opinions.items():
            created_at = opinion.get("created_at")
            if created_at and opinion.get("event_native_state") != "EVENT_NATIVE" and _is_before(created_at, event_at):
                conflicts.append(_conflict("STALE_OPINION_RELATIVE_TO_EVENT", "STALE_OPINION", [name, "event"], f"{name} opinion predates the orderbook event.", "Brain opinion must be refreshed from the event evidence."))
        return conflicts

    def _bundle_state(self, payload: dict[str, Any], orderbook: dict[str, Any], opinion_states: dict[str, str], coordinator: dict[str, Any], conflicts: list[dict[str, Any]]) -> str:
        if any(conflict.get("severity") == "HARD_CONFLICT" for conflict in conflicts):
            return "CONFLICTED"
        if not payload.get("market_id") or not payload.get("token_id") or orderbook.get("freshness_state") == "MISSING":
            return "MISSING"
        if conflicts:
            return "CONFLICTED"
        if coordinator.get("state") == "NO_DECISION":
            return "PARTIAL"
        if all(opinion_states.get(name) == "PRESENT" for name in REQUIRED_OPINIONS):
            return "COMPLETE"
        if any(opinion_states.get(name) == "STALE" for name in REQUIRED_OPINIONS):
            return "STALE"
        return "PARTIAL"

    def _mesh_session_state(self, bundle_state: str, conflicts: list[dict[str, Any]], opinion_states: dict[str, str], consensus_state: str) -> str:
        if bundle_state == "COMPLETE":
            if consensus_state == "CONSENSUS_BLOCKED":
                return "SESSION_BLOCKED"
            if consensus_state == "CONSENSUS_CONFLICTED":
                return "SESSION_CONFLICTED"
            return "SESSION_READY"
        if bundle_state == "CONFLICTED":
            return "SESSION_CONFLICTED"
        if bundle_state == "STALE":
            return "SESSION_STALE"
        if bundle_state == "MISSING":
            return "SESSION_MISSING"
        if any(state == "MISSING" for state in opinion_states.values()):
            return "SESSION_PARTIAL"
        return "UNKNOWN"

    def _mesh_consensus_state(self, coordinator: dict[str, Any], opinion_states: dict[str, str], conflicts: list[dict[str, Any]]) -> str:
        if any(conflict.get("severity") == "HARD_CONFLICT" for conflict in conflicts):
            return "CONSENSUS_CONFLICTED"
        decision = str(coordinator.get("decision") or "")
        if decision == "PRICE_READY":
            return "CONSENSUS_READY"
        if decision in {"PRICE_BLOCKED", "CAPITAL_BLOCKED", "LIFECYCLE_BLOCKED"}:
            return "CONSENSUS_BLOCKED"
        if decision == "WAITING_FOR_CAPITAL":
            return "CONSENSUS_WAITING_FOR_CAPITAL"
        if decision == "WAITING_FOR_LIFECYCLE":
            return "CONSENSUS_WAITING_FOR_LIFECYCLE"
        if any(state == "MISSING" for state in opinion_states.values()):
            return "CONSENSUS_PARTIAL"
        return "UNKNOWN"

    def _required_to_progress(self, missing_fields: list[str], opinion_states: dict[str, str], conflicts: list[dict[str, Any]], coordinator: dict[str, Any]) -> list[str]:
        required: list[str] = []
        for field in missing_fields:
            required.append(f"Bundle must include {field}.")
        for opinion, state in opinion_states.items():
            if state == "MISSING":
                required.append(f"{opinion} opinion must be attached or explicitly marked not applicable.")
            if state in {"CONFLICTING", "STALE"}:
                required.append(f"{opinion} opinion must clear {state.lower()} state.")
        for conflict in conflicts:
            required.extend(conflict.get("required_to_resolve") or [])
        if coordinator.get("state") == "NO_DECISION":
            required.append("Coordinator decision trace must be created.")
        if coordinator.get("execution_allowed"):
            required.append("Coordinator execution permission must remain false for Phase 9.")
        return _unique(required) or ["Keep shared evidence fresh before any future paper readiness decision."]

    def _counts(self, items: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "bundles": len(items),
            "complete": sum(1 for item in items if item.get("bundle_state") == "COMPLETE"),
            "partial": sum(1 for item in items if item.get("bundle_state") == "PARTIAL"),
            "conflicted": sum(1 for item in items if item.get("bundle_state") == "CONFLICTED"),
            "stale": sum(1 for item in items if item.get("bundle_state") == "STALE"),
            "missing": sum(1 for item in items if item.get("bundle_state") == "MISSING"),
            "with_liquidity_opinion": sum(1 for item in items if item.get("opinion_states", {}).get("liquidity") == "PRESENT"),
            "with_risk_opinion": sum(1 for item in items if item.get("opinion_states", {}).get("risk") == "PRESENT"),
            "with_exit_opinion": sum(1 for item in items if item.get("opinion_states", {}).get("exit") == "PRESENT"),
            "with_capital_opinion": sum(1 for item in items if item.get("opinion_states", {}).get("capital") == "PRESENT"),
            "with_lifecycle_opinion": sum(1 for item in items if item.get("opinion_states", {}).get("lifecycle") == "PRESENT"),
            "with_event_native_capital": sum(1 for item in items if (item.get("opinions", {}).get("capital") or {}).get("event_native_state") == "EVENT_NATIVE"),
            "with_event_native_lifecycle": sum(1 for item in items if (item.get("opinions", {}).get("lifecycle") or {}).get("event_native_state") == "EVENT_NATIVE"),
            "with_all_five_opinions": sum(1 for item in items if all(item.get("opinion_states", {}).get(name) == "PRESENT" for name in REQUIRED_OPINIONS)),
            "consensus_ready": sum(1 for item in items if item.get("mesh_consensus_state") == "CONSENSUS_READY"),
            "consensus_blocked": sum(1 for item in items if item.get("mesh_consensus_state") == "CONSENSUS_BLOCKED"),
            "consensus_waiting_for_capital": sum(1 for item in items if item.get("mesh_consensus_state") == "CONSENSUS_WAITING_FOR_CAPITAL"),
            "consensus_waiting_for_lifecycle": sum(1 for item in items if item.get("mesh_consensus_state") == "CONSENSUS_WAITING_FOR_LIFECYCLE"),
            "with_coordinator_decision": sum(1 for item in items if item.get("coordinator", {}).get("state") != "NO_DECISION"),
            "candidate_scoped": sum(1 for item in items if item.get("candidate_event_actionability_scope") == "CANDIDATE_SCOPED"),
            "market_scoped_only": sum(1 for item in items if item.get("candidate_event_actionability_scope") == "MARKET_SCOPED_ONLY"),
            "unlinked_events": sum(1 for item in items if item.get("candidate_event_link_state") in {"UNLINKED_WITH_REASON", "MISSING_CANDIDATE", "MISSING_EVENT"}),
            "ambiguous_events": sum(1 for item in items if item.get("candidate_event_link_state") == "AMBIGUOUS_MULTIPLE_CANDIDATES"),
        }

    def _overall_bundle_state(self, counts: dict[str, int]) -> str:
        if counts["complete"]:
            return "COMPLETE"
        if counts["conflicted"]:
            return "CONFLICTED"
        if counts["partial"]:
            return "PARTIAL"
        if counts["stale"]:
            return "STALE"
        if counts["missing"] or counts["bundles"] == 0:
            return "MISSING"
        return "UNKNOWN"

    def _payload_status(self, bundle_state: str, freshness_state: str) -> str:
        if bundle_state == "COMPLETE" and freshness_state == "FRESH":
            return "REAL"
        if bundle_state == "MISSING":
            return "MISSING"
        if freshness_state == "STALE":
            return "STALE"
        return "PARTIAL"

    def _top_conflicts(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        for item in items:
            counts.update(conflict.get("conflict_type", "UNKNOWN") for conflict in item.get("conflicts") or [])
        return [{"conflict": key, "count": value} for key, value in counts.most_common(10)]

    def _top_missing_opinions(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        for item in items:
            for opinion, state in (item.get("opinion_states") or {}).items():
                if state == "MISSING":
                    counts[opinion] += 1
        return [{"opinion": key, "count": value} for key, value in counts.most_common(10)]

    def _warnings(self, bundle_state: str, counts: dict[str, int]) -> list[str]:
        warnings: list[str] = []
        if counts["bundles"] == 0:
            warnings.append("No orderbook event evidence bundles exist yet.")
        if counts["bundles"] and counts["complete"] == 0:
            warnings.append("Mesh bundles exist, but none are complete across liquidity, risk, exit, capital, lifecycle, and coordinator.")
        if counts["with_capital_opinion"] == 0 and counts["bundles"]:
            warnings.append("Capital opinion is missing from current mesh bundles.")
        if counts["with_lifecycle_opinion"] == 0 and counts["bundles"]:
            warnings.append("Lifecycle opinion is missing from current mesh bundles.")
        if bundle_state == "CONFLICTED":
            warnings.append("One or more bundles contain explicit conflicts.")
        return warnings

    def _summary(self, market_id: str | None, bundle_state: str, opinion_states: dict[str, str], conflicts: list[dict[str, Any]], coordinator: dict[str, Any]) -> str:
        missing = [name for name, state in opinion_states.items() if state == "MISSING"]
        if bundle_state == "COMPLETE":
            return f"Mesh bundle for market {market_id} has shared evidence, all required opinions, and coordinator decision {coordinator.get('decision')}."
        if conflicts:
            return f"Mesh bundle for market {market_id} has {len(conflicts)} explicit conflict(s)."
        if missing:
            return f"Mesh bundle for market {market_id} is partial; missing opinions: {', '.join(missing)}."
        return f"Mesh bundle for market {market_id} is {bundle_state.lower()}."

    def _empty_payload(self, now: datetime, *, warnings: list[str] | None = None, errors: list[str] | None = None) -> dict[str, Any]:
        return {
            "status": "ERROR" if errors else "MISSING",
            "source": _source_map(),
            "last_updated": now.isoformat(),
            "freshness_state": "MISSING",
            "readiness_state": "UNKNOWN",
            "truth_state": "UNKNOWN",
            "bundle_state": "MISSING",
            "counts": {
                "bundles": 0,
                "complete": 0,
                "partial": 0,
                "conflicted": 0,
                "stale": 0,
                "missing": 0,
                "with_liquidity_opinion": 0,
                "with_risk_opinion": 0,
                "with_exit_opinion": 0,
                "with_capital_opinion": 0,
                "with_lifecycle_opinion": 0,
                "with_event_native_capital": 0,
                "with_event_native_lifecycle": 0,
                "with_all_five_opinions": 0,
                "consensus_ready": 0,
                "consensus_blocked": 0,
                "consensus_waiting_for_capital": 0,
                "consensus_waiting_for_lifecycle": 0,
                "with_coordinator_decision": 0,
                "candidate_scoped": 0,
                "market_scoped_only": 0,
                "unlinked_events": 0,
                "ambiguous_events": 0,
            },
            "top_conflicts": [],
            "top_missing_opinions": [],
            "items": [],
            "warnings": warnings or [],
            "errors": errors or [],
        }

    def _enveloped(self, payload: dict[str, Any], *, status: ControlCenterStatus) -> dict[str, Any]:
        freshness = ControlCenterFreshnessState(payload.get("freshness_state") if payload.get("freshness_state") in {"FRESH", "STALE", "MISSING"} else "MISSING")
        readiness = ControlCenterReadinessState(payload.get("readiness_state") if payload.get("readiness_state") in {"READY", "NOT_READY", "PARTIAL", "BLOCKED", "UNKNOWN"} else "UNKNOWN")
        envelope = truth_envelope(
            status=status,
            source="event_log + orderbook_snapshots + brain_outputs + coordinator_decisions + capital/lifecycle sources",
            truth_state=payload.get("truth_state") if payload.get("truth_state") in {"ACTIVE_FRESH", "LAST_KNOWN", "HISTORICAL_ONLY", "REFRESH_REQUIRED", "UNKNOWN"} else ControlCenterTruthState.UNKNOWN,
            data=payload,
            last_updated=payload.get("last_updated"),
            stale_after_seconds=STALE_AFTER_SECONDS,
            age_seconds=payload.get("age_seconds"),
            freshness_state=freshness,
            runtime_state=ControlCenterRuntimeState.RUNNING if status == ControlCenterStatus.REAL else ControlCenterRuntimeState.STALE if status in {ControlCenterStatus.PARTIAL, ControlCenterStatus.STALE} else ControlCenterRuntimeState.UNKNOWN,
            readiness_state=readiness,
            warnings=payload.get("warnings") or [],
            errors=payload.get("errors") or [],
        ).to_dict()
        return {**payload, **envelope, "data": payload}


def _brain_opinion(row: dict[str, Any], brain: str) -> dict[str, Any]:
    metadata = row.get("metadata_json") or {}
    blockers = metadata.get("blockers") or row.get("risk_flags_json") or []
    state = metadata.get("reaction_state") or "UNKNOWN"
    event_native = metadata.get("event_native_state") or "UNKNOWN"
    capital_state = metadata.get("capital_opinion_state")
    lifecycle_state = metadata.get("lifecycle_opinion_state")
    opinion_state = "PRESENT" if state == "REACTED" else "UNKNOWN"
    if brain in {"liquidity", "risk", "exit"} and blockers:
        opinion_state = "CONFLICTING"
    if brain == "capital" and capital_state in {"CAPITAL_MISSING", "CAPITAL_UNKNOWN"}:
        opinion_state = "PRESENT" if event_native == "EVENT_NATIVE" else "MISSING"
    if brain == "lifecycle" and lifecycle_state in {"LIFECYCLE_MISSING", "LIFECYCLE_UNKNOWN"}:
        opinion_state = "PRESENT" if event_native == "EVENT_NATIVE" else "MISSING"
    return {
        "brain": brain,
        "state": opinion_state,
        "reaction_state": state,
        "event_native_state": event_native,
        "capital_opinion_state": capital_state,
        "lifecycle_opinion_state": lifecycle_state,
        "recommendation": row.get("recommendation"),
        "confidence": _float(row.get("confidence")),
        "summary": row.get("reasoning_summary"),
        "blockers": blockers,
        "warnings": metadata.get("warnings") or [],
        "available_capital": metadata.get("available_capital"),
        "locked_capital": metadata.get("locked_capital"),
        "open_exposure": metadata.get("open_exposure"),
        "decision_source": metadata.get("decision_source"),
        "source_created_at": metadata.get("source_created_at"),
        "brain_output_id": row.get("brain_output_id"),
        "side": metadata.get("side"),
        "token_id": metadata.get("token_id"),
        "candidate_id": metadata.get("candidate_id"),
        "created_at": _iso(row.get("created_at")),
    }


def _missing_opinion(brain: str, reason: str) -> dict[str, Any]:
    return {
        "brain": brain,
        "state": "MISSING",
        "event_native_state": "MISSING",
        "summary": reason,
        "blockers": [f"MISSING_{brain.upper()}_OPINION"],
        "warnings": [],
        "required_to_attach": reason,
    }


def _latest_mesh_opinion_summary(conn: Any, correlation_id: str) -> dict[str, Any]:
    if not _table_exists(conn, "brain_outputs"):
        return {}
    rows = conn.execute(
        """
        SELECT brain, metadata_json
        FROM brain_outputs
        WHERE correlation_id = %s
          AND generated_by = 'minimal_event_mesh_proof'
        ORDER BY created_at DESC, id DESC
        """,
        (correlation_id,),
    ).fetchall()
    by_brain: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_brain.setdefault(str(row.get("brain")), row.get("metadata_json") or {})
    coordinator = {}
    if _table_exists(conn, "coordinator_decisions"):
        coord_row = conn.execute(
            """
            SELECT metadata_json
            FROM coordinator_decisions
            WHERE correlation_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (correlation_id,),
        ).fetchone()
        coordinator = (coord_row.get("metadata_json") or {}) if coord_row else {}
    return {
        "mesh_capital_opinion_state": by_brain.get("capital", {}).get("capital_opinion_state"),
        "mesh_lifecycle_opinion_state": by_brain.get("lifecycle", {}).get("lifecycle_opinion_state"),
        "mesh_capital_event_native_state": by_brain.get("capital", {}).get("event_native_state"),
        "mesh_lifecycle_event_native_state": by_brain.get("lifecycle", {}).get("event_native_state"),
        "mesh_consensus_state": coordinator.get("mesh_consensus_state"),
        "mesh_coordinator_decision": coordinator.get("decision"),
        "mesh_conflicts": coordinator.get("conflicts") or [],
    }


def _conflict(conflict_type: str, severity: str, sources: list[str], explanation: str, required: str) -> dict[str, Any]:
    return {
        "conflict_type": conflict_type,
        "severity": severity,
        "sources": sources,
        "explanation": explanation,
        "required_to_resolve": [required],
    }


def _candidate_claims_stale(opinions: dict[str, dict[str, Any]]) -> bool:
    return any("STALE" in str(blocker) for opinion in opinions.values() for blocker in opinion.get("blockers", []))


def _source_map() -> dict[str, str]:
    return {
        "events": "event_log",
        "orderbook": "orderbook_snapshots",
        "brain_outputs": "brain_outputs",
        "coordinator": "coordinator_decisions + coordinator_decision_inputs",
        "capital": "capital_brain_evaluations",
        "lifecycle": "lifecycle_governance_decisions",
        "mesh_sessions": "mesh_sessions",
    }


def _freshness(latest: str | None, now: datetime) -> tuple[str, str, float | None]:
    if not latest:
        return "MISSING", "UNKNOWN", None
    try:
        dt = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        age = max(0.0, (now - dt).total_seconds())
    except ValueError:
        return "STALE", "LAST_KNOWN", None
    if age <= STALE_AFTER_SECONDS:
        return "FRESH", "ACTIVE_FRESH", age
    return "STALE", "LAST_KNOWN", age


def _age_seconds(value: Any, now: datetime) -> float | None:
    if not value:
        return None
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return max(0.0, (now - dt).total_seconds())
    except ValueError:
        return None


def _is_before(left: str, right: Any) -> bool:
    if not right:
        return False
    try:
        left_dt = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        right_dt = right if isinstance(right, datetime) else datetime.fromisoformat(str(right).replace("Z", "+00:00"))
        if left_dt.tzinfo is None:
            left_dt = left_dt.replace(tzinfo=UTC)
        if right_dt.tzinfo is None:
            right_dt = right_dt.replace(tzinfo=UTC)
        return left_dt < right_dt
    except ValueError:
        return False


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _latest_of(values: list[Any]) -> str | None:
    cleaned = [str(value) for value in values if value]
    return max(cleaned) if cleaned else None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return None


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None

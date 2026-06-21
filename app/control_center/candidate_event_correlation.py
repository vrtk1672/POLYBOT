from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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
from app.db.connection import DatabaseConnectionFactory
from app.events.types import EventType


EVENT_TYPE = EventType.ORDERBOOK_SNAPSHOT_CREATED.value
EVENT_FRESH_SECONDS = 300
CANDIDATE_FRESH_SECONDS = 600


class CandidateEventCorrelationService:
    """Read-only candidate/event correlation truth for orderbook mesh events."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def list_correlations(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        candidate_id: str | None = None,
        market_id: str | None = None,
        side: str | None = None,
        token_id: str | None = None,
        correlation_id: str | None = None,
        event_id: str | None = None,
        link_state: str | None = None,
        confidence: str | None = None,
        include_bundle: bool = True,
        include_candidates: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(
                self._empty_payload(now, warnings=["Candidate/event correlation source is unavailable because the database is not configured."]),
                status=ControlCenterStatus.MISSING,
            )
        try:
            with self._factory.connect() as conn:
                missing = [table for table in ("event_log", "paper_eligibility_candidates") if not _table_exists(conn, table)]
                if missing:
                    payload = self._empty_payload(now, warnings=[f"Missing candidate/event correlation source tables: {', '.join(missing)}."])
                    return self._enveloped(payload, status=ControlCenterStatus.MISSING)
                rows = self._fetch_events(
                    conn,
                    limit=max(limit + offset, limit),
                    candidate_id=candidate_id,
                    market_id=market_id,
                    side=side,
                    token_id=token_id,
                    correlation_id=correlation_id,
                    event_id=event_id,
                )
                items = [
                    build_event_correlation(conn, dict(row), now=now, include_bundle=include_bundle, include_candidates=include_candidates)
                    for row in rows
                ]
                if candidate_id:
                    items = [item for item in items if item.get("candidate_id") == candidate_id or any(c.get("candidate_id") == candidate_id for c in item.get("matched_candidates") or [])]
                if link_state:
                    items = [item for item in items if item.get("candidate_event_link_state") == link_state.upper()]
                if confidence:
                    items = [item for item in items if item.get("correlation_confidence") == confidence.upper()]
                paged = items[offset : offset + limit]
                counts = self._counts(items)
                latest = _latest_of([item.get("event_at") for item in items])
        except Exception as exc:
            payload = self._empty_payload(now, errors=[f"Candidate/event correlation query failed: {type(exc).__name__}: {exc}"])
            return self._enveloped(payload, status=ControlCenterStatus.ERROR)

        freshness_state, truth_state, age = _freshness(latest, now)
        payload = {
            "status": self._payload_status(counts, freshness_state),
            "source": _source_map(),
            "last_updated": latest or now.isoformat(),
            "freshness_state": freshness_state,
            "readiness_state": self._readiness_state(counts),
            "truth_state": truth_state,
            "counts": counts,
            "top_unlinked_reasons": self._top_reasons(items, states={"MARKET_LEVEL_ONLY_WITH_REASON", "UNLINKED_WITH_REASON", "MISSING_CANDIDATE"}),
            "top_ambiguity_reasons": self._top_reasons(items, states={"AMBIGUOUS_MULTIPLE_CANDIDATES", "TOKEN_SIDE_MISMATCH"}),
            "items": paged,
            "warnings": self._warnings(counts),
            "errors": [],
            "limit": limit,
            "offset": offset,
            "generated_at": now.isoformat(),
            "age_seconds": age,
        }
        return self._enveloped(payload, status=ControlCenterStatus(payload["status"]))

    def get_candidate(self, candidate_id: str, *, limit: int = 50) -> dict[str, Any] | None:
        payload = self.list_correlations(limit=limit, candidate_id=candidate_id)
        items = payload.get("items") or payload.get("data", {}).get("items") or []
        if items:
            data = dict(payload.get("data") or payload)
            data["candidate_id"] = candidate_id
            data["items"] = items
            return self._enveloped(data, status=ControlCenterStatus(payload.get("status", "PARTIAL")))
        now = datetime.now(UTC)
        data = self._empty_payload(now, warnings=[f"No orderbook event is linked to candidate {candidate_id}."])
        data.update(
            {
                "candidate_id": candidate_id,
                "link_state": "UNLINKED_WITH_REASON",
                "reason": "No event with matching candidate_id, market/side/token, or candidate price path was found.",
                "required_to_link_candidate": ["A fresh orderbook event must match the candidate market, side, and token."],
            }
        )
        return self._enveloped(data, status=ControlCenterStatus.MISSING)

    def _fetch_events(
        self,
        conn: Any,
        *,
        limit: int,
        candidate_id: str | None,
        market_id: str | None,
        side: str | None,
        token_id: str | None,
        correlation_id: str | None,
        event_id: str | None,
    ) -> list[dict[str, Any]]:
        clauses = ["event_type = %s"]
        params: list[Any] = [EVENT_TYPE]
        if market_id:
            clauses.append("payload_json->>'market_id' = %s")
            params.append(market_id)
        if side:
            clauses.append("upper(payload_json->>'side') = %s")
            params.append(side.upper())
        if token_id:
            clauses.append("payload_json->>'token_id' = %s")
            params.append(token_id)
        if correlation_id:
            clauses.append("correlation_id = %s")
            params.append(correlation_id)
        if event_id:
            clauses.append("event_id = %s")
            params.append(event_id)
        if candidate_id:
            clauses.append("(payload_json->>'candidate_id' = %s OR payload_json->>'market_id' IN (SELECT market_id FROM paper_eligibility_candidates WHERE eligibility_id = %s))")
            params.extend([candidate_id, candidate_id])
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

    def _counts(self, items: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "events_checked": len(items),
            "linked_to_candidate": sum(1 for item in items if item.get("candidate_event_link_state") == "LINKED_TO_CANDIDATE"),
            "market_level_only": sum(1 for item in items if item.get("candidate_event_link_state") == "MARKET_LEVEL_ONLY_WITH_REASON"),
            "unlinked": sum(1 for item in items if item.get("candidate_event_link_state") in {"UNLINKED_WITH_REASON", "MISSING_CANDIDATE", "MISSING_EVENT"}),
            "ambiguous_multiple_candidates": sum(1 for item in items if item.get("candidate_event_link_state") == "AMBIGUOUS_MULTIPLE_CANDIDATES"),
            "token_side_mismatch": sum(1 for item in items if item.get("candidate_event_link_state") == "TOKEN_SIDE_MISMATCH"),
            "stale_candidate_link": sum(1 for item in items if item.get("candidate_event_link_state") == "STALE_CANDIDATE_LINK"),
            "candidate_scoped": sum(1 for item in items if item.get("candidate_event_actionability_scope") == "CANDIDATE_SCOPED"),
            "market_scoped_only": sum(1 for item in items if item.get("candidate_event_actionability_scope") == "MARKET_SCOPED_ONLY"),
            "not_actionable": sum(1 for item in items if item.get("candidate_event_actionability_scope") == "NOT_ACTIONABLE"),
        }

    def _payload_status(self, counts: dict[str, int], freshness_state: str) -> str:
        if counts["events_checked"] == 0:
            return "MISSING"
        if counts["linked_to_candidate"] or counts["market_level_only"] or counts["unlinked"]:
            return "REAL" if freshness_state == "FRESH" else "STALE"
        return "PARTIAL"

    def _readiness_state(self, counts: dict[str, int]) -> str:
        if counts["candidate_scoped"]:
            return "READY"
        if counts["events_checked"]:
            return "PARTIAL"
        return "UNKNOWN"

    def _top_reasons(self, items: list[dict[str, Any]], *, states: set[str]) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        for item in items:
            if item.get("candidate_event_link_state") in states:
                counts.update(item.get("blockers") or ["UNKNOWN_LINK_REASON"])
        return [{"reason": key, "count": value} for key, value in counts.most_common(10)]

    def _warnings(self, counts: dict[str, int]) -> list[str]:
        warnings: list[str] = []
        if counts["events_checked"] == 0:
            warnings.append("No orderbook.snapshot.created events were available for candidate correlation.")
        if counts["market_level_only"]:
            warnings.append("Some orderbook events are market-level only and cannot support candidate actionability.")
        if counts["ambiguous_multiple_candidates"]:
            warnings.append("Some orderbook events match multiple candidates and are not candidate-actionable.")
        if counts["unlinked"]:
            warnings.append("Some orderbook events have no candidate link.")
        return warnings

    def _empty_payload(self, now: datetime, *, warnings: list[str] | None = None, errors: list[str] | None = None) -> dict[str, Any]:
        return {
            "status": "ERROR" if errors else "MISSING",
            "source": _source_map(),
            "last_updated": now.isoformat(),
            "freshness_state": "MISSING",
            "readiness_state": "UNKNOWN",
            "truth_state": "UNKNOWN",
            "counts": {
                "events_checked": 0,
                "linked_to_candidate": 0,
                "market_level_only": 0,
                "unlinked": 0,
                "ambiguous_multiple_candidates": 0,
                "token_side_mismatch": 0,
                "stale_candidate_link": 0,
                "candidate_scoped": 0,
                "market_scoped_only": 0,
                "not_actionable": 0,
            },
            "top_unlinked_reasons": [],
            "top_ambiguity_reasons": [],
            "items": [],
            "warnings": warnings or [],
            "errors": errors or [],
        }

    def _enveloped(self, payload: dict[str, Any], *, status: ControlCenterStatus) -> dict[str, Any]:
        freshness = ControlCenterFreshnessState(payload.get("freshness_state") if payload.get("freshness_state") in {"FRESH", "STALE", "MISSING"} else "MISSING")
        readiness = ControlCenterReadinessState(payload.get("readiness_state") if payload.get("readiness_state") in {"READY", "NOT_READY", "PARTIAL", "BLOCKED", "UNKNOWN"} else "UNKNOWN")
        envelope = truth_envelope(
            status=status,
            source="event_log + paper_eligibility_candidates + mesh evidence correlation",
            truth_state=payload.get("truth_state") if payload.get("truth_state") in {"ACTIVE_FRESH", "LAST_KNOWN", "HISTORICAL_ONLY", "REFRESH_REQUIRED", "UNKNOWN"} else ControlCenterTruthState.UNKNOWN,
            data=payload,
            last_updated=payload.get("last_updated"),
            stale_after_seconds=EVENT_FRESH_SECONDS,
            age_seconds=payload.get("age_seconds"),
            freshness_state=freshness,
            runtime_state=ControlCenterRuntimeState.RUNNING if status == ControlCenterStatus.REAL else ControlCenterRuntimeState.STALE if status in {ControlCenterStatus.PARTIAL, ControlCenterStatus.STALE} else ControlCenterRuntimeState.UNKNOWN,
            readiness_state=readiness,
            warnings=payload.get("warnings") or [],
            errors=payload.get("errors") or [],
        ).to_dict()
        return {**payload, **envelope, "data": payload}


def build_event_correlation(
    conn: Any,
    event: dict[str, Any],
    *,
    now: datetime | None = None,
    include_bundle: bool = True,
    include_candidates: bool = True,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    payload = event.get("payload_json") or {}
    market_id = payload.get("market_id")
    side = payload.get("side")
    token_id = payload.get("token_id")
    direct_candidate_id = payload.get("candidate_id")
    event_at = event.get("stored_at") or event.get("occurred_at")
    event_age = _age_seconds(event_at, now)
    candidates = _candidate_rows(conn, market_id=market_id)
    matched, ambiguous, state, confidence, blockers, required = _classify_link(
        candidates,
        direct_candidate_id=direct_candidate_id,
        market_id=market_id,
        side=side,
        token_id=token_id,
        event_age=event_age,
        now=now,
    )
    candidate = matched[0] if len(matched) == 1 else None
    freshness = _link_freshness(state, candidate, event_age, now)
    scope = _actionability_scope(state, confidence, freshness)
    coordinator = _coordinator(conn, str(event.get("correlation_id") or ""))
    bundle_id = f"mesh_bundle_{event.get('correlation_id')}" if event.get("correlation_id") else None
    return {
        "event_id": event.get("event_id"),
        "correlation_id": event.get("correlation_id"),
        "event_type": event.get("event_type"),
        "market_id": market_id,
        "side": side,
        "token_id": token_id,
        "orderbook_snapshot_id": payload.get("orderbook_snapshot_id"),
        "candidate_id": candidate.get("candidate_id") if candidate else direct_candidate_id,
        "candidate_event_link_state": state,
        "candidate_event_link_freshness": freshness,
        "candidate_event_actionability_scope": scope,
        "correlation_confidence": confidence,
        "matched_candidates": matched if include_candidates else [],
        "ambiguous_candidates": ambiguous if include_candidates else [],
        "mesh_bundle_id": bundle_id if include_bundle else None,
        "mesh_bundle_state": _bundle_state(conn, event.get("correlation_id")) if include_bundle else None,
        "coordinator_decision": coordinator.get("decision"),
        "coordinator_decision_id": coordinator.get("decision_id"),
        "execution_allowed": bool(coordinator.get("execution_allowed")) if coordinator else False,
        "blockers": blockers,
        "unified_blockers": unified_blockers(
            blockers,
            source="candidate_event_correlation",
            candidate_id=candidate.get("candidate_id") if candidate else direct_candidate_id,
            event_id=event.get("event_id"),
            correlation_id=event.get("correlation_id"),
            market_id=market_id,
            side=side,
            token_id=token_id,
        ),
        "warnings": [] if scope == "CANDIDATE_SCOPED" else ["Event is not candidate-actionable."],
        "required_to_link_candidate": required,
        "event_at": _iso(event_at),
        "event_age_seconds": event_age,
        "operator_summary": _operator_summary(market_id, side, token_id, state, confidence, scope, blockers),
    }


def latest_candidate_event_link(
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
    if side:
        clauses.append("upper(payload_json->>'side') = %s")
        params.append(side.upper())
    if token_id:
        clauses.append("payload_json->>'token_id' = %s")
        params.append(token_id)
    if candidate_id:
        clauses.append("(payload_json->>'candidate_id' = %s OR payload_json->>'candidate_id' IS NULL)")
        params.append(candidate_id)
    row = conn.execute(
        f"""
        SELECT *
        FROM event_log
        WHERE {' AND '.join(clauses)}
        ORDER BY stored_at DESC, id DESC
        LIMIT 20
        """,
        tuple(params),
    ).fetchall()
    for event in row:
        item = build_event_correlation(conn, dict(event), include_bundle=True, include_candidates=True)
        if candidate_id and item.get("candidate_id") not in {candidate_id, None}:
            continue
        if candidate_id and item.get("matched_candidates") and not any(c.get("candidate_id") == candidate_id for c in item["matched_candidates"]):
            continue
        return item
    return None


def _classify_link(
    candidates: list[dict[str, Any]],
    *,
    direct_candidate_id: str | None,
    market_id: str | None,
    side: str | None,
    token_id: str | None,
    event_age: float | None,
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str, list[str], list[str]]:
    if not market_id:
        return [], [], "MISSING_EVENT", "NONE", ["MISSING_EVENT_MARKET_ID"], ["Orderbook event must include market_id."]
    if direct_candidate_id:
        direct = [_candidate_summary(row, now) for row in candidates if str(row.get("eligibility_id")) == str(direct_candidate_id)]
        if not direct:
            return [], [], "MISSING_CANDIDATE", "NONE", ["EVENT_CANDIDATE_NOT_FOUND"], ["Referenced candidate must exist in paper_eligibility_candidates."]
        mismatch = _mismatch_reasons(direct[0], side, token_id)
        if mismatch:
            return direct, [], "TOKEN_SIDE_MISMATCH", "LOW", mismatch, ["Candidate side/token must match the event side/token."]
        if _is_stale_candidate(direct[0], now):
            return direct, [], "STALE_CANDIDATE_LINK", "MEDIUM", ["STALE_CANDIDATE_LINK"], ["Candidate must refresh after the event or within freshness TTL."]
        return direct, [], "LINKED_TO_CANDIDATE", "HIGH", [], ["Keep candidate/event link fresh before candidate actionability."]
    if not candidates:
        return [], [], "UNLINKED_WITH_REASON", "NONE", ["NO_CANDIDATE_FOR_MARKET"], ["Create or refresh a candidate for this market before using this event for paper."]
    side_matches = [row for row in candidates if not side or _upper(row.get("side")) == _upper(side)]
    if not side_matches:
        return [], [_candidate_summary(row, now) for row in candidates[:10]], "TOKEN_SIDE_MISMATCH", "LOW", ["NO_CANDIDATE_SIDE_MATCH"], ["Candidate side must match event side."]
    exact = [row for row in side_matches if token_id and _candidate_token(row) == token_id]
    if len(exact) == 1:
        summary = _candidate_summary(exact[0], now)
        if _is_stale_candidate(summary, now):
            return [summary], [], "STALE_CANDIDATE_LINK", "MEDIUM", ["STALE_CANDIDATE_LINK"], ["Candidate must refresh after the event or within freshness TTL."]
        if event_age is not None and event_age > EVENT_FRESH_SECONDS:
            return [summary], [], "STALE_CANDIDATE_LINK", "MEDIUM", ["STALE_EVENT_LINK"], ["Orderbook event must be fresh before candidate actionability."]
        return [summary], [], "LINKED_TO_CANDIDATE", "HIGH", [], ["Keep candidate-scoped event evidence fresh."]
    if len(exact) > 1:
        return [], [_candidate_summary(row, now) for row in exact[:10]], "AMBIGUOUS_MULTIPLE_CANDIDATES", "LOW", ["MULTIPLE_CANDIDATES_MATCH_EVENT"], ["Dedupe or select one candidate before event can become candidate-actionable."]
    tokenless = [row for row in side_matches if not _candidate_token(row)]
    if len(side_matches) == 1 and tokenless:
        return [_candidate_summary(side_matches[0], now)], [], "MARKET_LEVEL_ONLY_WITH_REASON", "LOW", ["MISSING_CANDIDATE_TOKEN"], ["Candidate must carry expected_token_id or trusted orderbook token evidence."]
    if token_id and side_matches:
        return [], [_candidate_summary(row, now) for row in side_matches[:10]], "TOKEN_SIDE_MISMATCH", "LOW", ["NO_CANDIDATE_TOKEN_MATCH"], ["Candidate token must match event token."]
    return [], [_candidate_summary(row, now) for row in side_matches[:10]], "MARKET_LEVEL_ONLY_WITH_REASON", "LOW", ["EVENT_TOKEN_MISSING_OR_NOT_PROVEN"], ["Event and candidate must share market, side, and token for candidate actionability."]


def _candidate_rows(conn: Any, *, market_id: str | None) -> list[dict[str, Any]]:
    if not market_id or not _table_exists(conn, "paper_eligibility_candidates"):
        return []
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                pec.*,
                m.yes_token_id,
                m.no_token_id,
                trusted.expected_token_id AS trusted_expected_token_id,
                trusted.orderbook_token_id AS trusted_orderbook_token_id
            FROM paper_eligibility_candidates pec
            LEFT JOIN markets_v2 m ON m.market_id = pec.market_id
            LEFT JOIN LATERAL (
                SELECT expected_token_id, orderbook_token_id
                FROM trusted_orderbook_evidence_links
                WHERE candidate_id = pec.eligibility_id
                ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
                LIMIT 1
            ) trusted ON TRUE
            WHERE pec.market_id = %s
            ORDER BY pec.updated_at DESC NULLS LAST, pec.created_at DESC NULLS LAST, pec.id DESC
            LIMIT 100
            """,
            (market_id,),
        ).fetchall()
    ]


def _candidate_summary(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    updated_at = row.get("updated_at") or row.get("created_at")
    return {
        "candidate_id": str(row.get("eligibility_id")),
        "market_id": row.get("market_id"),
        "side": row.get("side"),
        "token_id": _candidate_token(row),
        "status": row.get("status"),
        "updated_at": _iso(updated_at),
        "age_seconds": _age_seconds(updated_at, now),
    }


def _candidate_token(row: dict[str, Any]) -> str | None:
    if row.get("expected_token_id"):
        return str(row.get("expected_token_id"))
    for key in ("trusted_expected_token_id", "trusted_orderbook_token_id"):
        if row.get(key):
            return str(row.get(key))
    evidence = row.get("evidence") or {}
    if isinstance(evidence, dict):
        trusted = evidence.get("trusted_orderbook") or {}
        price_path = evidence.get("candidate_price_path") or evidence.get("price_path") or {}
        for source in (trusted, price_path):
            if isinstance(source, dict):
                value = source.get("expected_token_id") or source.get("token_id")
                if value:
                    return str(value)
    side = _upper(row.get("side"))
    if side == "YES" and row.get("yes_token_id"):
        return str(row.get("yes_token_id"))
    if side == "NO" and row.get("no_token_id"):
        return str(row.get("no_token_id"))
    return None


def _mismatch_reasons(candidate: dict[str, Any], side: str | None, token_id: str | None) -> list[str]:
    blockers: list[str] = []
    if side and _upper(candidate.get("side")) != _upper(side):
        blockers.append("SIDE_MISMATCH")
    candidate_token = candidate.get("token_id")
    if token_id and candidate_token and candidate_token != token_id:
        blockers.append("TOKEN_MISMATCH")
    if token_id and not candidate_token:
        blockers.append("MISSING_CANDIDATE_TOKEN")
    return blockers


def _link_freshness(state: str, candidate: dict[str, Any] | None, event_age: float | None, now: datetime) -> str:
    if state in {"MISSING_EVENT", "MISSING_CANDIDATE", "UNLINKED_WITH_REASON"}:
        return "MISSING"
    if state == "STALE_CANDIDATE_LINK":
        return "STALE"
    if event_age is None:
        return "UNKNOWN"
    if event_age > EVENT_FRESH_SECONDS:
        return "STALE"
    if candidate and _is_stale_candidate(candidate, now):
        return "STALE"
    return "FRESH"


def _actionability_scope(state: str, confidence: str, freshness: str) -> str:
    if state == "LINKED_TO_CANDIDATE" and confidence == "HIGH" and freshness == "FRESH":
        return "CANDIDATE_SCOPED"
    if state == "MARKET_LEVEL_ONLY_WITH_REASON":
        return "MARKET_SCOPED_ONLY"
    if state == "AMBIGUOUS_MULTIPLE_CANDIDATES":
        return "AMBIGUOUS"
    if state in {"UNLINKED_WITH_REASON", "TOKEN_SIDE_MISMATCH", "STALE_CANDIDATE_LINK", "MISSING_CANDIDATE", "MISSING_EVENT"}:
        return "NOT_ACTIONABLE"
    return "UNKNOWN"


def _coordinator(conn: Any, correlation_id: str) -> dict[str, Any]:
    if not correlation_id or not _table_exists(conn, "coordinator_decisions"):
        return {}
    row = conn.execute(
        """
        SELECT coordinator_decision_id, execution_allowed, final_state, metadata_json
        FROM coordinator_decisions
        WHERE correlation_id = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (correlation_id,),
    ).fetchone()
    if not row:
        return {}
    metadata = row.get("metadata_json") or {}
    return {
        "decision_id": row.get("coordinator_decision_id"),
        "decision": metadata.get("decision") or row.get("final_state"),
        "execution_allowed": row.get("execution_allowed"),
    }


def _bundle_state(conn: Any, correlation_id: str | None) -> str | None:
    if not correlation_id or not _table_exists(conn, "brain_outputs") or not _table_exists(conn, "coordinator_decisions"):
        return None
    brain_count = int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT brain) AS count
            FROM brain_outputs
            WHERE correlation_id = %s
              AND generated_by = 'minimal_event_mesh_proof'
              AND brain IN ('liquidity','risk','exit','capital','lifecycle')
            """,
            (correlation_id,),
        ).fetchone()["count"]
        or 0
    )
    coordinator = conn.execute("SELECT 1 FROM coordinator_decisions WHERE correlation_id = %s LIMIT 1", (correlation_id,)).fetchone()
    if brain_count >= 5 and coordinator:
        return "COMPLETE"
    if brain_count or coordinator:
        return "PARTIAL"
    return "MISSING"


def _is_stale_candidate(candidate: dict[str, Any], now: datetime) -> bool:
    age = candidate.get("age_seconds")
    if age is None:
        updated = candidate.get("updated_at")
        age = _age_seconds(updated, now)
    return age is None or age > CANDIDATE_FRESH_SECONDS


def _operator_summary(market_id: str | None, side: str | None, token_id: str | None, state: str, confidence: str, scope: str, blockers: list[str]) -> str:
    if state == "LINKED_TO_CANDIDATE":
        return f"Orderbook event for market {market_id} side {side} token {token_id} is candidate-scoped with {confidence} confidence."
    if blockers:
        return f"Orderbook event for market {market_id} is {scope.lower()}: {', '.join(blockers)}."
    return f"Orderbook event for market {market_id} is classified as {state}."


def _source_map() -> dict[str, str]:
    return {
        "events": "event_log",
        "orderbooks": "orderbook_snapshots",
        "candidates": "paper_eligibility_candidates",
        "mesh_bundles": "brain_outputs + coordinator_decisions",
        "coordinator": "coordinator_decisions",
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
    if age <= EVENT_FRESH_SECONDS:
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
    except (TypeError, ValueError):
        return None


def _latest_of(values: list[Any]) -> str | None:
    cleaned = [str(value) for value in values if value]
    return max(cleaned) if cleaned else None


def _upper(value: Any) -> str:
    return str(value or "").upper()


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return None

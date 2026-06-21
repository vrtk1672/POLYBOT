from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
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
from app.control_center.truth_hardening import classify_freshness, truth_from_freshness
from app.db.connection import DatabaseConnectionFactory


EXECUTION_ORDERBOOK_TTL_SECONDS = 180
READINESS_TTL_SECONDS = 180

SOURCE_MAP = {
    "paper_eligibility_candidates": "paper_eligibility_candidates",
    "paper_intents": "paper_intents",
    "orderbook_snapshots": "orderbook_snapshots",
    "trusted_orderbook_evidence_links": "trusted_orderbook_evidence_links",
    "markets_v2": "markets_v2",
    "live_orderbook_watcher": "live_orderbook_watcher_runs + live_orderbook_watcher_traces",
    "clob_token_book_verification": "clob_token_book_verification_runs + clob_token_book_verification_traces",
}


class OrderbookPriceReadinessService:
    """Read-only trusted orderbook and executable price-path truth."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def get_readiness(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        market_id: str | None = None,
        candidate_id: str | None = None,
        side: str | None = None,
        state: str | None = None,
        freshness_state: str | None = None,
        include_candidates: bool = True,
        include_depth: bool = True,
        include_exit_liquidity: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(
                self._empty_payload(now, warnings=["Orderbook price readiness source is unavailable because the database is not configured."]),
                status=ControlCenterStatus.MISSING,
            )
        try:
            with self._factory.connect() as conn:
                if not _table_exists(conn, "orderbook_snapshots"):
                    payload = self._empty_payload(now, warnings=["orderbook_snapshots table is missing."])
                    payload["blockers"] = ["MISSING_ORDERBOOK"]
                    return self._enveloped(payload, status=ControlCenterStatus.MISSING)
                rows = self._candidate_rows(
                    conn,
                    limit=max(limit + offset, limit),
                    market_id=market_id,
                    candidate_id=candidate_id,
                    side=side,
                    include_candidates=include_candidates,
                )
                items = [build_price_path_for_candidate(conn, row, now=now) for row in rows]
                items = self._filter_items(items, state=state, freshness_state=freshness_state)
                paged = items[offset : offset + limit]
                latest = _latest_of([item.get("last_orderbook_at") for item in items])
                counts = self._counts(conn, items)
                refresh_truth = self._refresh_truth(conn)
        except Exception as exc:
            payload = self._empty_payload(now, errors=[f"Orderbook price readiness query failed: {type(exc).__name__}: {exc}"])
            return self._enveloped(payload, status=ControlCenterStatus.ERROR)

        freshness, age = classify_freshness(latest, stale_after_seconds=READINESS_TTL_SECONDS, now=now)
        if counts["trusted_fresh_orderbooks"]:
            overall_freshness = ControlCenterFreshnessState.FRESH
        elif counts["markets_checked"] and counts["missing_orderbooks"] < counts["markets_checked"]:
            overall_freshness = ControlCenterFreshnessState.STALE
        elif counts["markets_checked"]:
            overall_freshness = ControlCenterFreshnessState.MISSING
        else:
            overall_freshness = freshness
        top_blockers = self._top_blockers(items)
        readiness_state = self._readiness_state(counts)
        payload = {
            "status": self._payload_status(readiness_state, overall_freshness),
            "source": SOURCE_MAP,
            "last_updated": _iso(latest or now),
            "freshness_state": overall_freshness.value,
            "readiness_state": readiness_state,
            "truth_state": self._truth_state(overall_freshness, latest, readiness_state).value,
            "counts": counts,
            "ttl": {
                "execution_orderbook_ttl_seconds": EXECUTION_ORDERBOOK_TTL_SECONDS,
                "readiness_ttl_seconds": READINESS_TTL_SECONDS,
            },
            "top_blockers": top_blockers,
            "items": [self._item_visibility(item, include_depth=include_depth, include_exit_liquidity=include_exit_liquidity) for item in paged],
            "refresh_path": refresh_truth,
            "blockers": [entry["blocker"] for entry in top_blockers],
            "warnings": self._warnings(counts, refresh_truth, overall_freshness),
            "errors": [],
            "limit": limit,
            "offset": offset,
            "generated_at": now.isoformat(),
            "age_seconds": age,
        }
        return self._enveloped(payload, status=ControlCenterStatus(payload["status"]))

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(self._empty_payload(now), status=ControlCenterStatus.MISSING)
        with self._factory.connect() as conn:
            row = self._candidate_row(conn, candidate_id)
            if not row:
                return None
            item = build_price_path_for_candidate(conn, row, now=now)
        payload = {
            "status": "REAL" if item["price_path_state"] == "PRICE_READY" else "STALE" if item["orderbook_state"] == "STALE" else "PARTIAL",
            "source": SOURCE_MAP,
            "last_updated": item.get("last_orderbook_at") or now.isoformat(),
            "freshness_state": item["orderbook_state"] if item["orderbook_state"] in {"FRESH", "STALE", "MISSING"} else "PARTIAL",
            "readiness_state": "READY" if item["price_path_state"] == "PRICE_READY" else "BLOCKED",
            "truth_state": ControlCenterTruthState.ACTIVE_FRESH.value if item["price_path_state"] == "PRICE_READY" else ControlCenterTruthState.REFRESH_REQUIRED.value,
            "candidate": item,
            "items": [item],
            "warnings": [],
            "errors": [],
            "generated_at": now.isoformat(),
        }
        return self._enveloped(payload, status=ControlCenterStatus(payload["status"]))

    def _candidate_rows(
        self,
        conn: Any,
        *,
        limit: int,
        market_id: str | None,
        candidate_id: str | None,
        side: str | None,
        include_candidates: bool,
    ) -> list[dict[str, Any]]:
        if include_candidates and _table_exists(conn, "paper_eligibility_candidates"):
            clauses: list[str] = []
            params: list[Any] = []
            if market_id:
                clauses.append("pec.market_id = %s")
                params.append(market_id)
            if candidate_id:
                clauses.append("(pec.eligibility_id = %s OR pec.id::text = %s)")
                params.extend([candidate_id, candidate_id])
            if side:
                clauses.append("upper(pec.side) = %s")
                params.append(side.upper())
            where = "WHERE " + " AND ".join(clauses) if clauses else ""
            params.append(limit)
            return _fetchall(
                conn,
                f"""
                SELECT pec.*, m.question, m.yes_token_id, m.no_token_id, m.condition_id
                FROM paper_eligibility_candidates pec
                LEFT JOIN markets_v2 m ON m.market_id = pec.market_id
                {where}
                ORDER BY
                    CASE WHEN pec.status = 'ELIGIBLE' THEN 0 ELSE 1 END,
                    COALESCE(pec.updated_at, pec.created_at) DESC NULLS LAST,
                    pec.id DESC
                LIMIT %s
                """,
                tuple(params),
            )
        params = []
        clauses = []
        if market_id:
            clauses.append("obs.market_id = %s")
            params.append(market_id)
        if side:
            clauses.append("upper(obs.side) = %s")
            params.append(side.upper())
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        return _fetchall(
            conn,
            f"""
            SELECT
                NULL::text AS eligibility_id,
                obs.market_id,
                obs.side,
                NULL::text AS status,
                obs.token_id AS expected_token_id,
                obs.id AS orderbook_snapshot_id,
                m.question,
                m.yes_token_id,
                m.no_token_id,
                m.condition_id
            FROM orderbook_snapshots obs
            LEFT JOIN markets_v2 m ON m.market_id = obs.market_id
            {where}
            ORDER BY COALESCE(obs.snapshot_at, obs.collected_at, obs.created_at) DESC, obs.id DESC
            LIMIT %s
            """,
            tuple(params),
        )

    def _candidate_row(self, conn: Any, candidate_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "paper_eligibility_candidates"):
            return None
        return _fetchone(
            conn,
            """
            SELECT pec.*, m.question, m.yes_token_id, m.no_token_id, m.condition_id
            FROM paper_eligibility_candidates pec
            LEFT JOIN markets_v2 m ON m.market_id = pec.market_id
            WHERE pec.eligibility_id = %s OR pec.id::text = %s
            LIMIT 1
            """,
            (candidate_id, candidate_id),
        )

    def _counts(self, conn: Any, items: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "markets_checked": len({str(item.get("market_id")) for item in items if item.get("market_id")}),
            "candidates_checked": len([item for item in items if item.get("candidate_id")]),
            "trusted_fresh_orderbooks": sum(1 for item in items if item["trusted_orderbook_state"] == "TRUSTED_FRESH"),
            "trusted_stale_orderbooks": sum(1 for item in items if item["trusted_orderbook_state"] == "TRUSTED_STALE"),
            "missing_orderbooks": sum(1 for item in items if item["orderbook_state"] == "MISSING"),
            "missing_tokens": sum(1 for item in items if "token_id" in item.get("missing_data", [])),
            "price_ready": sum(1 for item in items if item["price_path_state"] == "PRICE_READY"),
            "waiting_for_refresh": sum(1 for item in items if item["price_path_state"] == "WAITING_FOR_ORDERBOOK_REFRESH"),
        }

    def _refresh_truth(self, conn: Any) -> dict[str, Any]:
        watcher = _fetchone(conn, "SELECT * FROM live_orderbook_watcher_runs ORDER BY created_at DESC, id DESC LIMIT 1") if _table_exists(conn, "live_orderbook_watcher_runs") else None
        verifier = _fetchone(conn, "SELECT * FROM clob_token_book_verification_runs ORDER BY created_at DESC, id DESC LIMIT 1") if _table_exists(conn, "clob_token_book_verification_runs") else None
        available = _table_exists(conn, "live_orderbook_watcher_runs") or _table_exists(conn, "clob_token_book_verification_runs")
        state = "REFRESH_AVAILABLE" if available else "REFRESH_BLOCKED"
        blockers = [] if available else ["ORDERBOOK_REFRESH_SOURCE_MISSING"]
        return {
            "refresh_before_execution_state": state,
            "safe_refresh_path_available": available,
            "latest_live_orderbook_watcher_run": _json_safe(watcher),
            "latest_clob_token_book_verification_run": _json_safe(verifier),
            "blockers": blockers,
        }

    def _filter_items(self, items: list[dict[str, Any]], *, state: str | None, freshness_state: str | None) -> list[dict[str, Any]]:
        if state:
            items = [item for item in items if item.get("price_path_state") == state.upper()]
        if freshness_state:
            items = [item for item in items if item.get("orderbook_state") == freshness_state.upper()]
        return items

    def _top_blockers(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        for item in items:
            for blocker in item.get("blockers") or []:
                counts[str(blocker)] += 1
        return [{"blocker": blocker, "count": count} for blocker, count in counts.most_common(20)]

    def _readiness_state(self, counts: dict[str, int]) -> str:
        if counts["price_ready"] > 0:
            return "READY"
        if counts["waiting_for_refresh"] > 0:
            return "PARTIAL"
        if counts["markets_checked"] == 0 and counts["candidates_checked"] == 0:
            return "UNKNOWN"
        return "BLOCKED"

    def _payload_status(self, readiness_state: str, freshness: ControlCenterFreshnessState) -> str:
        if readiness_state == "READY":
            return "REAL"
        if readiness_state == "PARTIAL":
            return "PARTIAL"
        if freshness == ControlCenterFreshnessState.STALE:
            return "STALE"
        if readiness_state == "UNKNOWN":
            return "MISSING"
        return "PARTIAL"

    def _truth_state(self, freshness: ControlCenterFreshnessState, latest: Any, readiness_state: str) -> ControlCenterTruthState:
        if readiness_state == "READY" and freshness == ControlCenterFreshnessState.FRESH:
            return ControlCenterTruthState.ACTIVE_FRESH
        if latest:
            return truth_from_freshness(freshness, has_history=True)
        return ControlCenterTruthState.UNKNOWN

    def _warnings(self, counts: dict[str, int], refresh_truth: dict[str, Any], freshness: ControlCenterFreshnessState) -> list[str]:
        warnings: list[str] = []
        if counts["missing_orderbooks"]:
            warnings.append("Some candidates have no matching orderbook snapshot.")
        if counts["trusted_stale_orderbooks"] or freshness == ControlCenterFreshnessState.STALE:
            warnings.append("Orderbook data is stale against execution TTL; refresh is required before execution.")
        if not refresh_truth.get("safe_refresh_path_available"):
            warnings.append("Safe orderbook refresh path is not wired.")
        return warnings

    def _item_visibility(self, item: dict[str, Any], *, include_depth: bool, include_exit_liquidity: bool) -> dict[str, Any]:
        output = dict(item)
        if not include_depth:
            for key in ("depth_1c", "depth_2c", "depth_5c"):
                output.pop(key, None)
        if not include_exit_liquidity:
            output.pop("exit_liquidity_state", None)
            output.pop("exit_price_source", None)
        return output

    def _empty_payload(self, now: datetime, *, warnings: list[str] | None = None, errors: list[str] | None = None) -> dict[str, Any]:
        return {
            "status": "ERROR" if errors else "MISSING",
            "source": SOURCE_MAP,
            "last_updated": now.isoformat(),
            "freshness_state": ControlCenterFreshnessState.MISSING.value,
            "readiness_state": ControlCenterReadinessState.UNKNOWN.value,
            "truth_state": ControlCenterTruthState.UNKNOWN.value,
            "counts": {
                "markets_checked": 0,
                "candidates_checked": 0,
                "trusted_fresh_orderbooks": 0,
                "trusted_stale_orderbooks": 0,
                "missing_orderbooks": 0,
                "missing_tokens": 0,
                "price_ready": 0,
                "waiting_for_refresh": 0,
            },
            "ttl": {
                "execution_orderbook_ttl_seconds": EXECUTION_ORDERBOOK_TTL_SECONDS,
                "readiness_ttl_seconds": READINESS_TTL_SECONDS,
            },
            "top_blockers": [],
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
            source="orderbook price readiness: paper candidates + orderbook_snapshots + trusted_orderbook_evidence_links + markets_v2",
            truth_state=payload.get("truth_state") or ControlCenterTruthState.UNKNOWN,
            data=payload,
            last_updated=payload.get("last_updated"),
            stale_after_seconds=READINESS_TTL_SECONDS,
            age_seconds=payload.get("age_seconds"),
            freshness_state=freshness,
            runtime_state=ControlCenterRuntimeState.RUNNING if status == ControlCenterStatus.REAL else ControlCenterRuntimeState.STALE if status in {ControlCenterStatus.PARTIAL, ControlCenterStatus.STALE} else ControlCenterRuntimeState.UNKNOWN,
            readiness_state=readiness,
            warnings=list(payload.get("warnings") or []),
            errors=list(payload.get("errors") or []),
        ).to_dict()
        return {**envelope, **payload}


class CandidatePricePathService:
    """Read-only candidate-specific trusted price path truth."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def get_readiness(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        candidate_id: str | None = None,
        market_id: str | None = None,
        side: str | None = None,
        token_id: str | None = None,
        state: str | None = None,
        include_refresh_plan: bool = True,
        include_depth: bool = True,
        include_exit_liquidity: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(self._empty_payload(now, warnings=["Candidate price path source is unavailable because the database is not configured."]), status=ControlCenterStatus.MISSING)
        try:
            with self._factory.connect() as conn:
                rows = OrderbookPriceReadinessService(connection_factory=self._factory)._candidate_rows(
                    conn,
                    limit=max(limit + offset, limit),
                    market_id=market_id,
                    candidate_id=candidate_id,
                    side=side,
                    include_candidates=True,
                )
                items = [_candidate_price_item(build_price_path_for_candidate(conn, row, now=now), conn=conn) for row in rows]
                if token_id:
                    items = [item for item in items if str(item.get("token_id") or "") == str(token_id)]
                if state:
                    items = [item for item in items if item.get("candidate_price_path_state") == state.upper()]
                paged = items[offset : offset + limit]
                latest = _latest_of([item.get("last_orderbook_at") for item in items])
                refresh_truth = OrderbookPriceReadinessService(connection_factory=self._factory)._refresh_truth(conn)
        except Exception as exc:
            return self._enveloped(self._empty_payload(now, errors=[f"Candidate price path query failed: {type(exc).__name__}: {exc}"]), status=ControlCenterStatus.ERROR)

        counts = _candidate_price_counts(items)
        top_blockers = _candidate_top_blockers(items)
        freshness = _candidate_overall_freshness(counts, latest)
        readiness = "READY" if counts["candidate_price_ready"] else "PARTIAL" if counts["waiting_for_refresh"] or counts["refresh_available"] else "BLOCKED" if counts["candidates_checked"] else "UNKNOWN"
        payload = {
            "status": "REAL" if readiness == "READY" else "PARTIAL" if readiness == "PARTIAL" else "STALE" if freshness == "STALE" else "MISSING" if readiness == "UNKNOWN" else "PARTIAL",
            "source": {
                **SOURCE_MAP,
                "candidate_price_path": "paper_eligibility_candidates + exact market/side/token orderbook lookup",
                "candidate_targeted_refresh": "TrustedOrderbookEvidenceService.resolve(refresh_orderbooks=True)",
            },
            "last_updated": _iso(latest or now),
            "freshness_state": freshness,
            "readiness_state": readiness,
            "truth_state": ControlCenterTruthState.ACTIVE_FRESH.value if readiness == "READY" and freshness == "FRESH" else ControlCenterTruthState.REFRESH_REQUIRED.value if items else ControlCenterTruthState.UNKNOWN.value,
            "counts": counts,
            "ttl": {"execution_orderbook_ttl_seconds": EXECUTION_ORDERBOOK_TTL_SECONDS},
            "top_blockers": top_blockers,
            "items": [_candidate_item_visibility(item, include_refresh_plan=include_refresh_plan, include_depth=include_depth, include_exit_liquidity=include_exit_liquidity) for item in paged],
            "refresh_path": refresh_truth,
            "blockers": [entry["blocker"] for entry in top_blockers],
            "warnings": _candidate_price_warnings(counts, refresh_truth),
            "errors": [],
            "limit": limit,
            "offset": offset,
            "generated_at": now.isoformat(),
        }
        return self._enveloped(payload, status=ControlCenterStatus(payload["status"]))

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(self._empty_payload(now), status=ControlCenterStatus.MISSING)
        with self._factory.connect() as conn:
            row = OrderbookPriceReadinessService(connection_factory=self._factory)._candidate_row(conn, candidate_id)
            if not row:
                return None
            item = _candidate_price_item(build_price_path_for_candidate(conn, row, now=now), conn=conn)
        readiness = "READY" if item["candidate_price_path_state"] == "CANDIDATE_PRICE_READY" else "BLOCKED"
        payload = {
            "status": "REAL" if readiness == "READY" else "PARTIAL",
            "source": SOURCE_MAP,
            "last_updated": item.get("last_orderbook_at") or now.isoformat(),
            "freshness_state": "FRESH" if readiness == "READY" else "STALE" if "orderbook" in item.get("stale_data", []) else "MISSING" if item.get("missing_data") else "PARTIAL",
            "readiness_state": readiness,
            "truth_state": ControlCenterTruthState.ACTIVE_FRESH.value if readiness == "READY" else ControlCenterTruthState.REFRESH_REQUIRED.value,
            "candidate": item,
            "items": [item],
            "warnings": [],
            "errors": [],
            "generated_at": now.isoformat(),
        }
        return self._enveloped(payload, status=ControlCenterStatus(payload["status"]))

    def _empty_payload(self, now: datetime, *, warnings: list[str] | None = None, errors: list[str] | None = None) -> dict[str, Any]:
        return {
            "status": "ERROR" if errors else "MISSING",
            "source": SOURCE_MAP,
            "last_updated": now.isoformat(),
            "freshness_state": ControlCenterFreshnessState.MISSING.value,
            "readiness_state": ControlCenterReadinessState.UNKNOWN.value,
            "truth_state": ControlCenterTruthState.UNKNOWN.value,
            "counts": _candidate_price_counts([]),
            "ttl": {"execution_orderbook_ttl_seconds": EXECUTION_ORDERBOOK_TTL_SECONDS},
            "top_blockers": [],
            "items": [],
            "warnings": warnings or [],
            "errors": errors or [],
            "generated_at": now.isoformat(),
        }

    def _enveloped(self, payload: dict[str, Any], *, status: ControlCenterStatus) -> dict[str, Any]:
        freshness = ControlCenterFreshnessState(payload.get("freshness_state") if payload.get("freshness_state") in {item.value for item in ControlCenterFreshnessState} else ControlCenterFreshnessState.UNKNOWN)
        readiness = ControlCenterReadinessState(payload.get("readiness_state") if payload.get("readiness_state") in {item.value for item in ControlCenterReadinessState} else ControlCenterReadinessState.UNKNOWN)
        envelope = truth_envelope(
            status=status,
            source="candidate price path: candidate-specific market/side/token orderbook truth",
            truth_state=payload.get("truth_state") or ControlCenterTruthState.UNKNOWN,
            data=payload,
            last_updated=payload.get("last_updated"),
            stale_after_seconds=EXECUTION_ORDERBOOK_TTL_SECONDS,
            freshness_state=freshness,
            runtime_state=ControlCenterRuntimeState.RUNNING if status == ControlCenterStatus.REAL else ControlCenterRuntimeState.STALE if status in {ControlCenterStatus.PARTIAL, ControlCenterStatus.STALE} else ControlCenterRuntimeState.UNKNOWN,
            readiness_state=readiness,
            warnings=list(payload.get("warnings") or []),
            errors=list(payload.get("errors") or []),
        ).to_dict()
        return {**envelope, **payload}


def build_price_path_for_candidate(conn: Any, row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    candidate_id = row.get("eligibility_id") or row.get("candidate_id")
    market_id = row.get("market_id")
    side = _normalize_side(row.get("side"))
    token_id = _expected_token(row, side)
    trusted_link = _trusted_link(conn, str(candidate_id)) if candidate_id else None
    orderbook = _latest_orderbook(conn, row=row, market_id=market_id, token_id=token_id)
    last_at = _timestamp((orderbook or {}).get("snapshot_at") or (orderbook or {}).get("collected_at") or (orderbook or {}).get("created_at"))
    freshness, age = classify_freshness(last_at, stale_after_seconds=EXECUTION_ORDERBOOK_TTL_SECONDS, now=now)
    is_execution_fresh = bool(
        orderbook
        and freshness == ControlCenterFreshnessState.FRESH
        and str(orderbook.get("snapshot_status") or "").upper() in {"OK", "PARTIAL"}
        and not bool(orderbook.get("is_stale"))
    )
    trusted = bool(
        trusted_link
        and trusted_link.get("trusted") is True
        and orderbook
        and str(trusted_link.get("expected_token_id") or trusted_link.get("orderbook_token_id") or token_id or "") == str(token_id or orderbook.get("token_id") or "")
        and str(trusted_link.get("side") or side or "").upper() == str(side or "").upper()
    )
    token_matches = bool(orderbook and token_id and str(orderbook.get("token_id") or "") == str(token_id))
    side_matches = bool(orderbook and side and str(orderbook.get("side") or side or "").upper() == str(side))
    orderbook_state = _orderbook_state(orderbook, freshness)
    trusted_state = _trusted_state(trusted=trusted, orderbook=orderbook, freshness=freshness)
    entry_source, entry_price = _entry_price(orderbook)
    exit_source, exit_liquidity_state = _exit_liquidity(orderbook, freshness)
    blockers, missing_data, stale_data = _price_blockers(
        market_id=market_id,
        side=side,
        token_id=token_id,
        orderbook=orderbook,
        trusted=trusted,
        freshness=freshness,
        entry_price=entry_price,
        token_matches=token_matches,
        side_matches=side_matches,
    )
    price_state = _price_path_state(blockers, freshness)
    refresh_state = "NOT_REQUIRED" if is_execution_fresh and trusted and entry_price is not None else "REQUIRED" if orderbook else "REFRESH_AVAILABLE"
    required = _required_to_be_price_ready(blockers, refresh_state)
    best_bid = _float((orderbook or {}).get("best_bid"))
    best_ask = _float((orderbook or {}).get("best_ask"))
    return _json_safe(
        {
            "candidate_id": candidate_id,
            "market_id": market_id,
            "side": side,
            "token_id": token_id,
            "question": row.get("question"),
            "orderbook_state": orderbook_state,
            "trusted_orderbook_state": trusted_state,
            "price_path_state": price_state,
            "entry_price_source": entry_source,
            "entry_price": entry_price,
            "exit_price_source": exit_source,
            "exit_liquidity_state": exit_liquidity_state,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": _float((orderbook or {}).get("spread")) if (orderbook or {}).get("spread") is not None else _spread(best_bid, best_ask),
            "depth_1c": _float((orderbook or {}).get("depth_1c")),
            "depth_2c": _float((orderbook or {}).get("depth_2c")),
            "depth_5c": _float((orderbook or {}).get("depth_5c")),
            "expected_slippage": _expected_slippage(orderbook),
            "last_orderbook_at": _iso(last_at),
            "orderbook_age_seconds": age,
            "execution_ttl_seconds": EXECUTION_ORDERBOOK_TTL_SECONDS,
            "is_execution_fresh": is_execution_fresh,
            "candidate_token_matches_orderbook": token_matches,
            "candidate_side_matches_orderbook": side_matches,
            "refresh_before_execution_state": refresh_state,
            "blockers": blockers,
            "stale_data": stale_data,
            "missing_data": missing_data,
            "required_to_be_price_ready": required,
            "operator_summary": _operator_summary(candidate_id, price_state, blockers, age),
            "orderbook": _json_safe(orderbook),
            "trusted_link": _json_safe(trusted_link),
            "source": SOURCE_MAP,
        }
    )


def build_candidate_price_path_for_candidate(conn: Any, row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    return _candidate_price_item(build_price_path_for_candidate(conn, row, now=now), conn=conn)


def _expected_token(row: dict[str, Any], side: str | None) -> str | None:
    if row.get("expected_token_id"):
        return str(row["expected_token_id"])
    if side == "YES" and row.get("yes_token_id"):
        return str(row["yes_token_id"])
    if side == "NO" and row.get("no_token_id"):
        return str(row["no_token_id"])
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    for key in ("expected_token_id", "token_id", "orderbook_token_id"):
        if evidence.get(key):
            return str(evidence[key])
    return None


def _latest_orderbook(conn: Any, *, row: dict[str, Any], market_id: Any, token_id: str | None) -> dict[str, Any] | None:
    if not _table_exists(conn, "orderbook_snapshots"):
        return None
    if market_id and token_id:
        found = _fetchone(
            conn,
            """
            SELECT *
            FROM orderbook_snapshots
            WHERE market_id = %s AND token_id = %s
            ORDER BY COALESCE(snapshot_at, collected_at, created_at) DESC, id DESC
            LIMIT 1
            """,
            (market_id, token_id),
        )
        if found:
            return found
    snapshot_id = row.get("orderbook_snapshot_id")
    if snapshot_id:
        found = _fetchone(
            conn,
            "SELECT * FROM orderbook_snapshots WHERE id = %s OR orderbook_snapshot_id = %s LIMIT 1",
            (snapshot_id, str(snapshot_id)),
        )
        if found:
            return found
    if market_id:
        return _fetchone(
            conn,
            """
            SELECT *
            FROM orderbook_snapshots
            WHERE market_id = %s
            ORDER BY COALESCE(snapshot_at, collected_at, created_at) DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        )
    return None


def _trusted_link(conn: Any, candidate_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "trusted_orderbook_evidence_links"):
        return None
    return _fetchone(
        conn,
        "SELECT * FROM trusted_orderbook_evidence_links WHERE candidate_id = %s ORDER BY updated_at DESC, id DESC LIMIT 1",
        (candidate_id,),
    )


def _orderbook_state(orderbook: dict[str, Any] | None, freshness: ControlCenterFreshnessState) -> str:
    if not orderbook:
        return "MISSING"
    status = str(orderbook.get("snapshot_status") or "").upper()
    if freshness == ControlCenterFreshnessState.STALE or bool(orderbook.get("is_stale")) or status == "STALE":
        return "STALE"
    if status == "PARTIAL":
        return "PARTIAL"
    if status == "OK":
        return "FRESH"
    return "UNKNOWN"


def _trusted_state(*, trusted: bool, orderbook: dict[str, Any] | None, freshness: ControlCenterFreshnessState) -> str:
    if not orderbook:
        return "MISSING"
    if not trusted:
        return "UNTRUSTED"
    if freshness == ControlCenterFreshnessState.FRESH and not bool(orderbook.get("is_stale")):
        return "TRUSTED_FRESH"
    return "TRUSTED_STALE"


def _entry_price(orderbook: dict[str, Any] | None) -> tuple[str, float | None]:
    if not orderbook:
        return "MISSING", None
    best_ask = _float(orderbook.get("best_ask"))
    if best_ask is not None:
        return "BEST_ASK", best_ask
    mid = _float(orderbook.get("mid_price"))
    if mid is not None:
        return "MID", mid
    return "MISSING", None


def _exit_liquidity(orderbook: dict[str, Any] | None, freshness: ControlCenterFreshnessState) -> tuple[str, str]:
    if not orderbook:
        return "MISSING", "EXIT_LIQUIDITY_MISSING"
    if freshness == ControlCenterFreshnessState.STALE:
        return "BEST_BID" if orderbook.get("best_bid") is not None else "MISSING", "EXIT_LIQUIDITY_STALE"
    bid = _float(orderbook.get("best_bid"))
    depth = _float(orderbook.get("depth_bid_2c") or orderbook.get("depth_2c") or orderbook.get("total_bid_depth"))
    liquidity = _float(orderbook.get("liquidity_score"))
    if bid is None:
        return "MISSING", "EXIT_LIQUIDITY_MISSING"
    if (depth is not None and depth <= 0) or (liquidity is not None and liquidity < 0.25):
        return "BEST_BID", "EXIT_LIQUIDITY_WEAK"
    return "BEST_BID", "EXIT_LIQUIDITY_READY"


def _price_blockers(
    *,
    market_id: Any,
    side: str | None,
    token_id: str | None,
    orderbook: dict[str, Any] | None,
    trusted: bool,
    freshness: ControlCenterFreshnessState,
    entry_price: float | None,
    token_matches: bool,
    side_matches: bool,
) -> tuple[list[str], list[str], list[str]]:
    blockers: list[str] = []
    missing: list[str] = []
    stale: list[str] = []
    if not market_id:
        blockers.append("MISSING_MARKET_ID")
        missing.append("market_id")
    if side not in {"YES", "NO"}:
        blockers.append("BLOCKED_MISSING_SIDE")
        missing.append("side")
    if not token_id:
        blockers.append("BLOCKED_MISSING_TOKEN")
        missing.append("token_id")
    if not orderbook:
        blockers.append("MISSING_ORDERBOOK")
        missing.append("orderbook")
    elif freshness == ControlCenterFreshnessState.STALE or bool(orderbook.get("is_stale")):
        blockers.append("STALE_ORDERBOOK")
        stale.append("orderbook")
    if orderbook and not trusted:
        blockers.append("MISSING_TRUSTED_ORDERBOOK")
    if orderbook and token_id and not token_matches:
        blockers.append("TOKEN_MISMATCH")
    if orderbook and side and not side_matches:
        blockers.append("SIDE_MISMATCH")
    if entry_price is None:
        blockers.append("MISSING_EXECUTABLE_PRICE")
        missing.append("entry_price")
    return _unique(blockers), _unique(missing), _unique(stale)


def _price_path_state(blockers: list[str], freshness: ControlCenterFreshnessState) -> str:
    if not blockers and freshness == ControlCenterFreshnessState.FRESH:
        return "PRICE_READY"
    if "BLOCKED_MISSING_TOKEN" in blockers:
        return "BLOCKED_MISSING_TOKEN"
    if "BLOCKED_MISSING_SIDE" in blockers:
        return "BLOCKED_MISSING_SIDE"
    if "MISSING_ORDERBOOK" in blockers:
        return "BLOCKED_MISSING_ORDERBOOK"
    if "STALE_ORDERBOOK" in blockers:
        return "WAITING_FOR_ORDERBOOK_REFRESH"
    if "MISSING_TRUSTED_ORDERBOOK" in blockers:
        return "BLOCKED_UNTRUSTED_SOURCE"
    if "TOKEN_MISMATCH" in blockers:
        return "BLOCKED_UNTRUSTED_SOURCE"
    if "SIDE_MISMATCH" in blockers:
        return "BLOCKED_UNTRUSTED_SOURCE"
    if "MISSING_EXECUTABLE_PRICE" in blockers:
        return "BLOCKED_MISSING_ORDERBOOK"
    return "UNKNOWN"


def _required_to_be_price_ready(blockers: list[str], refresh_state: str) -> list[str]:
    mapping = {
        "MISSING_MARKET_ID": "Candidate must be linked to canonical market_id.",
        "BLOCKED_MISSING_SIDE": "Candidate must include YES or NO side.",
        "BLOCKED_MISSING_TOKEN": "Candidate side must map to a CLOB token_id.",
        "MISSING_ORDERBOOK": "Trusted orderbook must be collected for market/token/side.",
        "STALE_ORDERBOOK": "Orderbook must be refreshed within execution TTL.",
        "MISSING_TRUSTED_ORDERBOOK": "Orderbook evidence must be trusted for candidate token and side.",
        "TOKEN_MISMATCH": "Orderbook token must match the candidate's exact expected token_id.",
        "SIDE_MISMATCH": "Orderbook side must match the candidate side.",
        "MISSING_EXECUTABLE_PRICE": "Best ask or explicit allowed price source must be present.",
    }
    required = [mapping[item] for item in blockers if item in mapping]
    if refresh_state in {"REQUIRED", "REFRESH_AVAILABLE"}:
        required.append("Refresh-before-execution must run before any paper execution attempt.")
    return _unique(required)


def _expected_slippage(orderbook: dict[str, Any] | None) -> float | None:
    if not orderbook:
        return None
    spread = _float(orderbook.get("spread"))
    if spread is not None:
        return round(spread / 2.0, 6)
    best_bid = _float(orderbook.get("best_bid"))
    best_ask = _float(orderbook.get("best_ask"))
    if best_bid is not None and best_ask is not None:
        return round((best_ask - best_bid) / 2.0, 6)
    return None


def _operator_summary(candidate_id: Any, price_state: str, blockers: list[str], age: float | None) -> str:
    label = f"Candidate {candidate_id}" if candidate_id else "Market/orderbook item"
    if price_state == "PRICE_READY":
        return f"{label} has fresh trusted orderbook price evidence."
    primary = blockers[0] if blockers else price_state
    age_text = f" Age: {int(age)}s." if age is not None else ""
    return f"{label} is not price-ready because {primary}.{age_text}"


def _candidate_price_item(item: dict[str, Any], *, conn: Any | None = None) -> dict[str, Any]:
    output = dict(item)
    blockers = list(output.get("blockers") or [])
    refresh_plan = _candidate_refresh_plan(output, conn=conn)
    output["candidate_price_path_state"] = _candidate_price_path_state(output, refresh_plan)
    output["candidate_trusted_orderbook_state"] = _candidate_trusted_orderbook_state(output)
    output["required_to_be_candidate_price_ready"] = list(output.get("required_to_be_price_ready") or [])
    if refresh_plan.get("required_before_execution") and "Candidate-targeted trusted orderbook refresh must run before candidate can progress." not in output["required_to_be_candidate_price_ready"]:
        output["required_to_be_candidate_price_ready"].append("Candidate-targeted trusted orderbook refresh must run before candidate can progress.")
    output["refresh_plan"] = refresh_plan
    output["blockers"] = blockers
    output["operator_summary"] = _candidate_operator_summary(output)
    return _json_safe(output)


def _candidate_price_path_state(item: dict[str, Any], refresh_plan: dict[str, Any]) -> str:
    blockers = set(item.get("blockers") or [])
    if item.get("price_path_state") == "PRICE_READY" and item.get("trusted_orderbook_state") == "TRUSTED_FRESH":
        return "CANDIDATE_PRICE_READY"
    if "MISSING_MARKET_ID" in blockers:
        return "CANDIDATE_MISSING_MARKET"
    if "BLOCKED_MISSING_SIDE" in blockers or "MISSING_SIDE" in blockers:
        return "CANDIDATE_MISSING_SIDE"
    if "BLOCKED_MISSING_TOKEN" in blockers:
        return "CANDIDATE_MISSING_TOKEN"
    if "TOKEN_MISMATCH" in blockers or "SIDE_MISMATCH" in blockers:
        return "CANDIDATE_UNTRUSTED_ORDERBOOK"
    if "MISSING_ORDERBOOK" in blockers:
        return "CANDIDATE_MISSING_ORDERBOOK"
    if "STALE_ORDERBOOK" in blockers:
        return "CANDIDATE_STALE_ORDERBOOK"
    if "MISSING_TRUSTED_ORDERBOOK" in blockers:
        return "CANDIDATE_UNTRUSTED_ORDERBOOK"
    if item.get("exit_liquidity_state") == "EXIT_LIQUIDITY_MISSING":
        return "CANDIDATE_EXIT_LIQUIDITY_MISSING"
    if refresh_plan.get("can_refresh"):
        return "CANDIDATE_REFRESH_AVAILABLE"
    if refresh_plan.get("blocked_reason"):
        return "CANDIDATE_REFRESH_BLOCKED"
    return "UNKNOWN"


def _candidate_trusted_orderbook_state(item: dict[str, Any]) -> str:
    blockers = set(item.get("blockers") or [])
    if "TOKEN_MISMATCH" in blockers:
        return "TOKEN_MISMATCH"
    if "SIDE_MISMATCH" in blockers:
        return "SIDE_MISMATCH"
    state = item.get("trusted_orderbook_state")
    if state == "TRUSTED_FRESH":
        return "TRUSTED_FRESH_FOR_CANDIDATE"
    if state == "TRUSTED_STALE":
        return "TRUSTED_STALE_FOR_CANDIDATE"
    if state == "MISSING":
        return "TRUSTED_MISSING_FOR_CANDIDATE"
    if state == "UNTRUSTED":
        return "UNTRUSTED_FOR_CANDIDATE"
    return "UNKNOWN"


def _candidate_refresh_plan(item: dict[str, Any], *, conn: Any | None = None) -> dict[str, Any]:
    blockers = set(item.get("blockers") or [])
    required = item.get("candidate_price_path_state") != "CANDIDATE_PRICE_READY" and item.get("price_path_state") != "PRICE_READY"
    has_identity = bool(item.get("market_id") and item.get("side") in {"YES", "NO"} and item.get("token_id"))
    blocked_reason = None
    if not item.get("market_id"):
        blocked_reason = "CANDIDATE_MISSING_MARKET"
    elif item.get("side") not in {"YES", "NO"}:
        blocked_reason = "CANDIDATE_MISSING_SIDE"
    elif not item.get("token_id"):
        blocked_reason = "CANDIDATE_MISSING_TOKEN"
    elif "TOKEN_MISMATCH" in blockers:
        blocked_reason = "TOKEN_MISMATCH"
    elif "SIDE_MISMATCH" in blockers:
        blocked_reason = "SIDE_MISMATCH"
    can_refresh = bool(has_identity and not blocked_reason and _safe_refresh_source_available(conn))
    return {
        "can_refresh": can_refresh,
        "refresh_source": "TrustedOrderbookEvidenceService.resolve(refresh_orderbooks=True)" if can_refresh else None,
        "required_before_execution": bool(required),
        "blocked_reason": blocked_reason if not can_refresh else None,
    }


def _safe_refresh_source_available(conn: Any | None) -> bool:
    if conn is None:
        return True
    return _table_exists(conn, "trusted_orderbook_evidence_runs") or _table_exists(conn, "orderbook_snapshots")


def _candidate_operator_summary(item: dict[str, Any]) -> str:
    label = f"Candidate {item.get('candidate_id')}" if item.get("candidate_id") else "Candidate"
    state = item.get("candidate_price_path_state")
    if state == "CANDIDATE_PRICE_READY":
        return f"{label} has fresh trusted orderbook evidence for its exact market/side/token."
    blockers = item.get("blockers") or []
    primary = blockers[0] if blockers else state
    age = item.get("orderbook_age_seconds")
    age_text = f" Age: {int(age)}s." if age is not None else ""
    token = item.get("token_id") or "missing-token"
    return f"{label} is not candidate-price-ready for token {token} because {primary}.{age_text}"


def _candidate_price_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "candidates_checked": len([item for item in items if item.get("candidate_id")]),
        "candidate_price_ready": sum(1 for item in items if item.get("candidate_price_path_state") == "CANDIDATE_PRICE_READY"),
        "waiting_for_refresh": sum(1 for item in items if item.get("candidate_price_path_state") in {"CANDIDATE_WAITING_FOR_REFRESH", "CANDIDATE_STALE_ORDERBOOK"}),
        "refresh_available": sum(1 for item in items if (item.get("refresh_plan") or {}).get("can_refresh")),
        "refresh_blocked": sum(1 for item in items if item.get("candidate_price_path_state") == "CANDIDATE_REFRESH_BLOCKED"),
        "missing_market": sum(1 for item in items if item.get("candidate_price_path_state") == "CANDIDATE_MISSING_MARKET"),
        "missing_side": sum(1 for item in items if item.get("candidate_price_path_state") == "CANDIDATE_MISSING_SIDE"),
        "missing_token": sum(1 for item in items if item.get("candidate_price_path_state") == "CANDIDATE_MISSING_TOKEN"),
        "missing_orderbook": sum(1 for item in items if item.get("candidate_price_path_state") == "CANDIDATE_MISSING_ORDERBOOK"),
        "stale_orderbook": sum(1 for item in items if item.get("candidate_price_path_state") == "CANDIDATE_STALE_ORDERBOOK"),
        "trusted_fresh_for_candidate": sum(1 for item in items if item.get("candidate_trusted_orderbook_state") == "TRUSTED_FRESH_FOR_CANDIDATE"),
        "trusted_stale_for_candidate": sum(1 for item in items if item.get("candidate_trusted_orderbook_state") == "TRUSTED_STALE_FOR_CANDIDATE"),
    }


def _candidate_top_blockers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for item in items:
        for blocker in item.get("blockers") or []:
            counts[str(blocker)] += 1
    return [{"blocker": blocker, "count": count} for blocker, count in counts.most_common(20)]


def _candidate_overall_freshness(counts: dict[str, int], latest: Any) -> str:
    if counts["candidate_price_ready"]:
        return "FRESH"
    if counts["stale_orderbook"] or counts["trusted_stale_for_candidate"]:
        return "STALE"
    if counts["missing_orderbook"] or counts["missing_market"] or counts["missing_side"] or counts["missing_token"]:
        return "MISSING"
    return "UNKNOWN" if latest is None else "PARTIAL"


def _candidate_price_warnings(counts: dict[str, int], refresh_truth: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if counts["stale_orderbook"]:
        warnings.append("Candidate-specific orderbook evidence is stale; refresh-before-execution is required.")
    if counts["missing_orderbook"]:
        warnings.append("Some candidates have no exact market/side/token orderbook evidence.")
    if counts["missing_token"] or counts["missing_side"] or counts["missing_market"]:
        warnings.append("Some candidates cannot resolve a complete market/side/token path.")
    if not refresh_truth.get("safe_refresh_path_available"):
        warnings.append("Candidate-targeted refresh path is blocked or unavailable.")
    return warnings


def _candidate_item_visibility(item: dict[str, Any], *, include_refresh_plan: bool, include_depth: bool, include_exit_liquidity: bool) -> dict[str, Any]:
    output = dict(item)
    if not include_refresh_plan:
        output.pop("refresh_plan", None)
    if not include_depth:
        for key in ("depth_1c", "depth_2c", "depth_5c"):
            output.pop(key, None)
    if not include_exit_liquidity:
        output.pop("exit_liquidity_state", None)
        output.pop("exit_price_source", None)
    return output


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


def _normalize_side(value: Any) -> str | None:
    side = str(value or "").strip().upper()
    return side if side in {"YES", "NO"} else None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return None


def _spread(best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None:
        return None
    return round(best_ask - best_bid, 6)


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
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value

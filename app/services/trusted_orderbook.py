from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
import os
import time
from typing import Any
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.source_status import DEFAULT_CLOB_BASE_URL
from app.services.system_power import SystemPowerService


TRUSTED_LINK_CONFIDENCE = 0.8
FRESHNESS_SECONDS = 180
MAX_SPREAD = 0.08
MIN_LIQUIDITY_SCORE = 0.25


class TrustedOrderbookEvidenceService:
    """Resolve side/token-aware trusted orderbook evidence for paper candidates."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        http_client: Any | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._snapshotter = OrderbookSnapshotter(connection_factory=self._factory)
        self._orderbooks = OrderbookSnapshotRepository()
        self._http = http_client or _TrustedOrderbookHttpClient()

    def resolve(
        self,
        *,
        cycle_id: str | None = None,
        limit: int = 200,
        refresh_orderbooks: bool | None = None,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"trusted_orderbook_{uuid4().hex}"
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        if system_power != "ON" or not bool(power.get("runtime_work_allowed")):
            payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, "SYSTEM_POWER_OFF")
            self._record_run(payload)
            return _json_safe(payload)
        if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
            payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, "STATE_GOVERNOR_BLOCKED_INTELLIGENCE")
            self._record_run(payload)
            return _json_safe(payload)
        existing = self._existing_for_cycle(cycle_id)
        if existing:
            existing["mock_data"] = False
            existing["idempotent"] = True
            return _json_safe(existing)

        before = self._counts()
        safety_before = self._safety_counts()
        extended_safety_before = self._extended_safety_counts()
        candidates = self._load_candidates(limit=limit)
        should_refresh = bool(refresh_orderbooks) if refresh_orderbooks is not None else bool(os.getenv("TRUSTED_ORDERBOOK_CLOB_RECOVERY") == "true")
        reasons: Counter[str] = Counter()
        refresh_reasons: Counter[str] = Counter()
        trusted_created = 0
        trusted_refreshed = 0
        trusted_count = 0
        rejected_count = 0
        snapshots_created = 0
        errors: list[str] = []

        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                for candidate in candidates:
                    try:
                        result = self._resolve_candidate(conn, candidate, run_id=run_id, refresh_orderbooks=should_refresh)
                        was_created = self._upsert_link(conn, result)
                        refresh = result.get("refresh_result") or {}
                        if refresh:
                            refresh_reasons[str(refresh.get("status") or "UNKNOWN")] += 1
                            if refresh.get("snapshot_created"):
                                snapshots_created += 1
                        if result["trusted"]:
                            trusted_count += 1
                            if was_created:
                                trusted_created += 1
                            else:
                                trusted_refreshed += 1
                            self._attach_trusted_orderbook(conn, result)
                        else:
                            rejected_count += 1
                            reasons[str(result["trust_reason"])] += 1
                    except Exception as exc:
                        rejected_count += 1
                        reasons["OTHER_EXACT_REASON"] += 1
                        errors.append(f"{candidate.get('eligibility_id') or 'unknown'}:{type(exc).__name__}:{exc}")

        after = self._counts()
        safety_after = self._safety_counts()
        extended_safety_after = self._extended_safety_counts()
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "DEGRADED" if errors else "OK",
            "candidates_checked": len(candidates),
            "candidates_with_side": before["candidates_with_side"],
            "candidates_with_trusted_binding": before["candidates_with_trusted_binding"],
            "candidates_with_orderbook": before["candidates_with_orderbook"],
            "trusted_matches_created": trusted_created,
            "trusted_matches_refreshed": trusted_refreshed,
            "orderbook_snapshots_created": snapshots_created,
            "trusted_orderbook_matches": after["trusted_orderbook_matches"],
            "rejected_count": rejected_count,
            "missing_orderbook_count": reasons["NO_ORDERBOOK_FOR_MARKET"] + reasons["NO_ORDERBOOK_FOR_TOKEN"] + reasons["CLOB_NO_BOOK"],
            "stale_count": reasons["ORDERBOOK_STALE"],
            "token_mismatch_count": reasons["TOKEN_SIDE_MISMATCH"],
            "missing_mid_price_count": reasons["MISSING_MID_PRICE"],
            "spread_too_wide_count": reasons["SPREAD_TOO_WIDE"],
            "liquidity_too_low_count": reasons["LIQUIDITY_TOO_LOW"],
            "missing_trusted_orderbook_before": before["missing_trusted_orderbook"],
            "missing_trusted_orderbook_after": after["missing_trusted_orderbook"],
            "missing_fresh_orderbook_before": before["missing_fresh_orderbook"],
            "missing_fresh_orderbook_after": after["missing_fresh_orderbook"],
            "live_orders_delta": max(0, safety_after["live_orders"] - safety_before["live_orders"]),
            "real_orders_delta": max(0, safety_after["real_orders"] - safety_before["real_orders"]),
            "safety_counts_before": extended_safety_before,
            "safety_counts_after": extended_safety_after,
            "rejected_reason_counts": [{"reason": key, "count": value} for key, value in reasons.most_common()],
            "error_message": "; ".join(errors) if errors else None,
            "metadata": {
                "freshness_threshold_seconds": FRESHNESS_SECONDS,
                "max_spread": MAX_SPREAD,
                "min_liquidity_score": MIN_LIQUIDITY_SCORE,
                "non_trading_evidence_only": True,
                "candidate_specific_clob_refresh_enabled": should_refresh,
                "orderbook_snapshots_created": snapshots_created,
                "orderbook_refresh_reason_counts": [{"reason": key, "count": value} for key, value in refresh_reasons.most_common()],
            },
        }
        self._record_run(payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        latest = self._latest_run()
        counts = self._counts()
        power = self._system_power.get_power_state()
        return {
            "mock_data": False,
            "status": "OK" if latest else "EMPTY",
            "trusted_orderbook_allowed": bool(power.get("runtime_work_allowed")),
            "latest_run_status": latest.get("status") if latest else None,
            "latest_run_at": latest.get("finished_at") if latest else None,
            "latest_run": latest,
            "candidates_checked": _int((latest or {}).get("candidates_checked")),
            "candidates_with_side": counts["candidates_with_side"],
            "candidates_with_trusted_binding": counts["candidates_with_trusted_binding"],
            "candidates_with_orderbook": counts["candidates_with_orderbook"],
            "trusted_orderbook_matches": counts["trusted_orderbook_matches"],
            "rejected_count": _int((latest or {}).get("rejected_count")),
            "missing_orderbook_count": _int((latest or {}).get("missing_orderbook_count")),
            "orderbook_snapshots_created": _int((latest or {}).get("metadata_json", {}).get("orderbook_snapshots_created") if isinstance((latest or {}).get("metadata_json"), dict) else 0),
            "stale_orderbook_count": _int((latest or {}).get("stale_count")),
            "token_mismatch_count": _int((latest or {}).get("token_mismatch_count")),
            "missing_mid_price_count": _int((latest or {}).get("missing_mid_price_count")),
            "spread_too_wide_count": _int((latest or {}).get("spread_too_wide_count")),
            "liquidity_too_low_count": _int((latest or {}).get("liquidity_too_low_count")),
            "missing_trusted_orderbook_before": _int((latest or {}).get("missing_trusted_orderbook_before")),
            "missing_trusted_orderbook_after": counts["missing_trusted_orderbook"],
            "missing_fresh_orderbook_before": _int((latest or {}).get("missing_fresh_orderbook_before")),
            "missing_fresh_orderbook_after": counts["missing_fresh_orderbook"],
            "sample_trusted_links": self._sample_links(limit=limit, trusted=True),
            "sample_rejected_links": self._sample_links(limit=limit, trusted=False),
            "candidate_trace": self.candidate_trace(limit=20),
            "live_orders": counts["live_orders"],
            "real_orders": counts["real_orders"],
            "no_live_execution": counts["live_orders"] == 0,
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def get_blocker_dashboard(self, *, limit: int = 50) -> dict[str, Any]:
        counts = self._blocker_counts()
        latest = self._latest_run()
        return {
            "mock_data": False,
            "status": "OK",
            "total_blocked": counts["total_blocked"],
            "missing_trusted_orderbook_count": counts["missing_trusted_orderbook_count"],
            "missing_fresh_orderbook_count": counts["missing_fresh_orderbook_count"],
            "stale_snapshot_count": counts["stale_snapshot_count"],
            "token_mismatch_count": counts["token_mismatch_count"],
            "clob_no_book_count": counts["clob_no_book_count"],
            "no_snapshot_count": counts["no_snapshot_count"],
            "trusted_link_not_consumed_count": counts["trusted_link_not_consumed_count"],
            "already_executed_intent_count": counts["already_executed_intent_count"],
            "top_markets": self._top_blocked_markets(limit=20),
            "sample_traces": self.candidate_trace(limit=limit),
            "latest_recovery_run": latest,
            "safety_counts": self._extended_safety_counts(),
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def candidate_trace(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "paper_eligibility_candidates"):
                return []
            rows = conn.execute(
                """
                WITH target_candidates AS (
                    SELECT *
                    FROM paper_eligibility_candidates
                    WHERE side IN ('YES','NO')
                    ORDER BY
                        CASE WHEN eligibility_blockers @> '["MISSING_TRUSTED_ORDERBOOK"]'::jsonb THEN 0 ELSE 1 END,
                        CASE WHEN eligibility_blockers @> '["MISSING_FRESH_ORDERBOOK"]'::jsonb THEN 0 ELSE 1 END,
                        updated_at DESC NULLS LAST,
                        id DESC
                    LIMIT %s
                )
                SELECT
                    pec.eligibility_id AS candidate_id,
                    pec.market_id,
                    pec.side,
                    sml.side_source AS matched_side_source,
                    sml.id AS signal_market_link_id,
                    nsb.id AS neuron_signal_binding_id,
                    CASE WHEN sml.id IS NOT NULL THEN 'YES' ELSE 'NO' END AS trusted_binding,
                    m.condition_id,
                    CASE WHEN pec.side = 'YES' THEN m.yes_token_id WHEN pec.side = 'NO' THEN m.no_token_id ELSE NULL END AS expected_token,
                    m.yes_token_id,
                    m.no_token_id,
                    obs.id AS latest_orderbook_snapshot_id,
                    obs.orderbook_snapshot_id AS latest_orderbook_snapshot_ref,
                    obs.token_id AS latest_orderbook_token_id,
                    obs.side AS latest_orderbook_side,
                    EXTRACT(EPOCH FROM (now() - COALESCE(obs.snapshot_at, obs.collected_at, obs.created_at)))::int AS orderbook_age_seconds,
                    %s AS freshness_threshold,
                    obs.best_bid,
                    obs.best_ask,
                    COALESCE(obs.mid_price, (obs.best_bid + obs.best_ask) / 2.0) AS mid_price,
                    COALESCE(obs.spread, obs.best_ask - obs.best_bid) AS spread,
                    obs.liquidity_score,
                    tol.trust_status,
                    tol.trust_reason,
                    tol.trusted AS trusted_orderbook,
                    rd.decision AS risk_status,
                    rd.blockers AS risk_blockers,
                    ep.status AS exit_status,
                    ep.blockers AS exit_blockers,
                    pec.status AS eligibility_status,
                    pec.eligibility_blockers,
                    CASE
                        WHEN tol.trusted IS true THEN 'TRUSTED_ORDERBOOK_ATTACHED'
                        WHEN tol.trust_reason IS NOT NULL THEN tol.trust_reason
                        WHEN pec.market_id IS NULL THEN 'MISSING_MARKET_ID'
                        WHEN pec.side NOT IN ('YES','NO') THEN 'MISSING_SIDE'
                        WHEN sml.id IS NULL THEN 'WEAK_BINDING'
                        WHEN obs.id IS NULL THEN 'NO_ORDERBOOK_FOR_TOKEN'
                        ELSE 'UNRESOLVED'
                    END AS why_orderbook_is_not_trusted,
                    CASE
                        WHEN tol.trusted IS true THEN 'Already attached.'
                        ELSE 'Run TrustedOrderbookEvidenceService after side recovery and evidence refresh.'
                    END AS exact_next_fix
                FROM target_candidates pec
                LEFT JOIN markets_v2 m ON m.market_id = pec.market_id
                LEFT JOIN trusted_orderbook_evidence_links tol ON tol.candidate_id = pec.eligibility_id
                LEFT JOIN risk_decisions rd ON rd.risk_decision_id = pec.risk_decision_id
                LEFT JOIN exit_plans ep ON ep.exit_plan_id = pec.exit_plan_id
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM signal_market_links link
                    WHERE link.market_id = pec.market_id
                      AND link.signal_id IN (SELECT jsonb_array_elements_text(COALESCE(pec.signal_ids, '[]'::jsonb)))
                      AND link.matched_side = pec.side
                      AND link.link_status IN ('confirmed', 'suggested')
                      AND COALESCE(link.is_review_required, false) = false
                      AND COALESCE(link.link_confidence, link.confidence, 0) >= %s
                    ORDER BY COALESCE(link.link_confidence, link.confidence, 0) DESC, link.id DESC
                    LIMIT 1
                ) sml ON true
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM neuron_signal_bindings binding
                    WHERE binding.market_id = pec.market_id
                      AND binding.matched_side = pec.side
                    ORDER BY binding.id DESC
                    LIMIT 1
                ) nsb ON true
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM orderbook_snapshots book
                    WHERE book.market_id = pec.market_id
                      AND book.token_id = CASE WHEN pec.side = 'YES' THEN m.yes_token_id WHEN pec.side = 'NO' THEN m.no_token_id ELSE NULL END
                    ORDER BY COALESCE(book.snapshot_at, book.collected_at, book.created_at) DESC, book.id DESC
                    LIMIT 1
                ) obs ON true
                """,
                (limit, FRESHNESS_SECONDS, TRUSTED_LINK_CONFIDENCE),
            ).fetchall()
        return [_json_safe(dict(row)) for row in rows]

    def _resolve_candidate(
        self,
        conn: Any,
        row: dict[str, Any],
        *,
        run_id: str,
        refresh_orderbooks: bool,
    ) -> dict[str, Any]:
        candidate_id = str(row["eligibility_id"])
        side = str(row.get("side") or "").upper()
        market_id = row.get("market_id")
        expected_token = row.get("yes_token_id") if side == "YES" else row.get("no_token_id") if side == "NO" else None
        base = {
            "link_id": f"trusted_orderbook_{candidate_id}",
            "candidate_id": candidate_id,
            "market_id": market_id,
            "side": side if side in {"YES", "NO"} else None,
            "expected_token_id": str(expected_token) if expected_token else None,
            "signal_market_link_id": row.get("signal_market_link_id"),
            "neuron_signal_binding_id": row.get("neuron_signal_binding_id"),
            "freshness_threshold_seconds": FRESHNESS_SECONDS,
            "trusted": False,
            "trust_status": "REJECTED",
            "trust_reason": "OTHER_EXACT_REASON",
            "orderbook_snapshot_id": None,
            "orderbook_snapshot_ref": None,
            "orderbook_token_id": None,
            "best_bid": None,
            "best_ask": None,
            "mid_price": None,
            "spread": None,
            "liquidity_score": None,
            "age_seconds": None,
            "evidence_json": {},
            "refresh_result": {},
        }
        if not market_id:
            return {**base, "trust_reason": "MISSING_MARKET_ID"}
        if side not in {"YES", "NO"}:
            return {**base, "trust_reason": "MISSING_SIDE"}
        if not row.get("signal_market_link_id"):
            return {**base, "trust_reason": "WEAK_BINDING"}
        if not row.get("yes_token_id") or not row.get("no_token_id") or row.get("yes_token_id") == row.get("no_token_id"):
            return {**base, "trust_reason": "MISSING_YES_NO_TOKEN_MAPPING"}
        if not expected_token:
            return {**base, "trust_reason": "MISSING_EXPECTED_TOKEN"}

        latest_expected = self._latest_expected_book(conn, market_id=market_id, expected_token=str(expected_token))
        refresh_needed = _should_refresh_candidate_book(latest_expected) or _missing_candidate_scope(
            latest_expected,
            candidate_id=candidate_id,
        )
        if refresh_orderbooks and refresh_needed and _market_allows_orderbook(row):
            refreshed = self._refresh_candidate_orderbook(
                conn,
                candidate_id=candidate_id,
                market_id=str(market_id),
                token_id=str(expected_token),
                side=side,
                run_id=run_id,
            )
            base["refresh_result"] = refreshed
            if refreshed.get("snapshot_created"):
                latest_expected = self._latest_expected_book(conn, market_id=market_id, expected_token=str(expected_token))
            elif not latest_expected:
                return {**base, "trust_reason": str(refreshed.get("trust_reason") or "CLOB_NO_BOOK")}

        refresh_needed = _should_refresh_candidate_book(latest_expected) or _missing_candidate_scope(
            latest_expected,
            candidate_id=candidate_id,
        )
        if refresh_orderbooks and refresh_needed and not _market_allows_orderbook(row):
            return {**base, "trust_reason": "STALE_CANDIDATE", "refresh_result": {"status": "SKIPPED", "reason": "MARKET_NOT_ACTIVE_OPEN_ORDERBOOK"}}

        market_books = _int(conn.execute("SELECT COUNT(*) AS count FROM orderbook_snapshots WHERE market_id = %s", (market_id,)).fetchone()["count"])
        if market_books == 0:
            return {**base, "trust_reason": "NO_ORDERBOOK_FOR_MARKET"}
        token_books = _int(conn.execute("SELECT COUNT(*) AS count FROM orderbook_snapshots WHERE market_id = %s AND token_id = %s", (market_id, expected_token)).fetchone()["count"])
        if token_books == 0:
            latest = conn.execute(
                """
                SELECT token_id, side
                FROM orderbook_snapshots
                WHERE market_id = %s
                ORDER BY COALESCE(snapshot_at, collected_at, created_at) DESC, id DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
            reason = "TOKEN_SIDE_MISMATCH" if latest else "NO_ORDERBOOK_FOR_TOKEN"
            return {**base, "trust_reason": reason, "orderbook_token_id": latest["token_id"] if latest else None}

        book = self._latest_expected_book(conn, market_id=market_id, expected_token=str(expected_token))
        if not book:
            return {**base, "trust_reason": "NO_ORDERBOOK_FOR_TOKEN"}
        data = dict(book)
        best_bid = _float_or_none(data.get("best_bid"))
        best_ask = _float_or_none(data.get("best_ask"))
        mid_price = _float_or_none(data.get("mid_price"))
        spread = _float_or_none(data.get("spread"))
        if mid_price is None and best_bid is not None and best_ask is not None:
            mid_price = round((best_bid + best_ask) / 2.0, 6)
        if spread is None and best_bid is not None and best_ask is not None:
            spread = round(max(best_ask - best_bid, 0.0), 6)
        age_seconds = _float_or_none(data.get("age_seconds"))
        result = {
            **base,
            "orderbook_snapshot_id": data.get("id"),
            "orderbook_snapshot_ref": data.get("orderbook_snapshot_id"),
            "orderbook_token_id": data.get("token_id"),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "spread": spread,
            "liquidity_score": _float_or_none(data.get("liquidity_score")),
            "age_seconds": age_seconds,
            "evidence_json": {
                "source": "trusted_orderbook_evidence",
                "snapshot_status": data.get("snapshot_status"),
                "is_stale": bool(data.get("is_stale")),
                "snapshot_at": _iso(data.get("snapshot_at") or data.get("collected_at") or data.get("created_at")),
                "market_id": market_id,
                "side": side,
                "expected_token_id": str(expected_token),
                "orderbook_token_id": data.get("token_id"),
                "refresh_result": base.get("refresh_result") or {},
            },
        }
        if str(data.get("snapshot_status") or "").upper() != "OK" or bool(data.get("is_stale")) or (age_seconds is not None and age_seconds > FRESHNESS_SECONDS):
            refresh_result = result.get("refresh_result") or {}
            if refresh_orderbooks and refresh_result.get("status") == "FAILED":
                return {
                    **result,
                    "trust_reason": str(refresh_result.get("trust_reason") or "CLOB_NO_BOOK"),
                }
            return {**result, "trust_reason": "ORDERBOOK_STALE"}
        if str(data.get("token_id") or "") != str(expected_token):
            return {**result, "trust_reason": "TOKEN_SIDE_MISMATCH"}
        if best_bid is None:
            return {**result, "trust_reason": "MISSING_BEST_BID"}
        if best_ask is None:
            return {**result, "trust_reason": "MISSING_BEST_ASK"}
        if mid_price is None:
            return {**result, "trust_reason": "MISSING_MID_PRICE"}
        if spread is None:
            return {**result, "trust_reason": "MISSING_SPREAD"}
        if spread > MAX_SPREAD:
            return {**result, "trust_reason": "SPREAD_TOO_WIDE"}
        liquidity = _float_or_none(data.get("liquidity_score"))
        if liquidity is not None and liquidity < MIN_LIQUIDITY_SCORE:
            return {**result, "trust_reason": "LIQUIDITY_TOO_LOW"}
        return {**result, "trusted": True, "trust_status": "TRUSTED", "trust_reason": "TRUSTED_ORDERBOOK"}

    def _latest_expected_book(self, conn: Any, *, market_id: str, expected_token: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *,
                   EXTRACT(EPOCH FROM (now() - COALESCE(snapshot_at, collected_at, created_at))) AS age_seconds
            FROM orderbook_snapshots
            WHERE market_id = %s
              AND token_id = %s
            ORDER BY COALESCE(snapshot_at, collected_at, created_at) DESC, id DESC
            LIMIT 1
            """,
            (market_id, expected_token),
        ).fetchone()
        return dict(row) if row else None

    def _refresh_candidate_orderbook(
        self,
        conn: Any,
        *,
        candidate_id: str,
        market_id: str,
        token_id: str,
        side: str,
        run_id: str,
    ) -> dict[str, Any]:
        endpoint = f"{(os.getenv('POLYMARKET_CLOB_HOST') or DEFAULT_CLOB_BASE_URL).rstrip('/')}/book"
        started = time.perf_counter()
        try:
            raw, latency_ms = self._http.get_json(endpoint, params={"token_id": token_id})
        except Exception as exc:
            return {"status": "FAILED", "trust_reason": "CLOB_NO_BOOK", "error_type": type(exc).__name__, "error_summary": str(exc)[:160]}
        if latency_ms is None:
            latency_ms = int((time.perf_counter() - started) * 1000)
        if not isinstance(raw, dict) or not raw:
            return {"status": "FAILED", "trust_reason": "CLOB_NO_BOOK", "latency_ms": latency_ms}
        bids = raw.get("bids") or raw.get("buy") or []
        asks = raw.get("asks") or raw.get("sell") or []
        if not bids or not asks:
            return {"status": "FAILED", "trust_reason": "CLOB_NO_BOOK", "latency_ms": latency_ms}
        collected_at = datetime.now(UTC)
        snapshot = self._snapshotter.normalize_orderbook(
            raw,
            market_id=market_id,
            token_id=token_id,
            side=side,
            source="polymarket_clob_candidate_recovery",
            correlation_id=run_id,
            raw_payload_ref=f"clob:/book:{token_id}:{collected_at.isoformat()}",
            collected_at=collected_at,
            freshness_window_seconds=FRESHNESS_SECONDS,
            metadata_json={
                "candidate_id": candidate_id,
                "candidate_source": "paper_eligibility_candidates",
                "refresh_reason": "candidate_targeted_price_path",
                "refresh_scope": "CANDIDATE_SCOPED",
                "source_service": "TrustedOrderbookEvidenceService",
                "market_id": market_id,
                "side": side,
                "token_id": token_id,
                "correlation_id": run_id,
                "candidate_event_scope": "CANDIDATE_TARGETED_REFRESH",
                "candidate_event_scoped": True,
                "candidate_refresh_run_id": run_id,
            },
        )
        self._orderbooks.append_snapshot(conn, snapshot)
        return {
            "status": "SNAPSHOT_CREATED",
            "snapshot_created": True,
            "orderbook_snapshot_id": snapshot.orderbook_snapshot_id,
            "latency_ms": latency_ms,
            "snapshot_status": snapshot.snapshot_status,
            "best_bid": snapshot.best_bid,
            "best_ask": snapshot.best_ask,
            "mid_price": snapshot.mid_price,
            "spread": snapshot.spread,
            "liquidity_score": snapshot.liquidity_score,
            "source": snapshot.source,
        }

    def _upsert_link(self, conn: Any, result: dict[str, Any]) -> bool:
        existing = conn.execute("SELECT 1 FROM trusted_orderbook_evidence_links WHERE candidate_id = %s", (result["candidate_id"],)).fetchone()
        conn.execute(
            """
            INSERT INTO trusted_orderbook_evidence_links (
                link_id, candidate_id, market_id, side, expected_token_id,
                orderbook_snapshot_id, orderbook_snapshot_ref, orderbook_token_id,
                trusted, trust_status, trust_reason, best_bid, best_ask,
                mid_price, spread, liquidity_score, age_seconds,
                freshness_threshold_seconds, signal_market_link_id,
                neuron_signal_binding_id, evidence_json, created_at, updated_at
            )
            VALUES (
                %(link_id)s, %(candidate_id)s, %(market_id)s, %(side)s,
                %(expected_token_id)s, %(orderbook_snapshot_id)s,
                %(orderbook_snapshot_ref)s, %(orderbook_token_id)s,
                %(trusted)s, %(trust_status)s, %(trust_reason)s, %(best_bid)s,
                %(best_ask)s, %(mid_price)s, %(spread)s, %(liquidity_score)s,
                %(age_seconds)s, %(freshness_threshold_seconds)s,
                %(signal_market_link_id)s, %(neuron_signal_binding_id)s,
                %(evidence_json)s, now(), now()
            )
            ON CONFLICT (candidate_id) DO UPDATE SET
                market_id = EXCLUDED.market_id,
                side = EXCLUDED.side,
                expected_token_id = EXCLUDED.expected_token_id,
                orderbook_snapshot_id = EXCLUDED.orderbook_snapshot_id,
                orderbook_snapshot_ref = EXCLUDED.orderbook_snapshot_ref,
                orderbook_token_id = EXCLUDED.orderbook_token_id,
                trusted = EXCLUDED.trusted,
                trust_status = EXCLUDED.trust_status,
                trust_reason = EXCLUDED.trust_reason,
                best_bid = EXCLUDED.best_bid,
                best_ask = EXCLUDED.best_ask,
                mid_price = EXCLUDED.mid_price,
                spread = EXCLUDED.spread,
                liquidity_score = EXCLUDED.liquidity_score,
                age_seconds = EXCLUDED.age_seconds,
                freshness_threshold_seconds = EXCLUDED.freshness_threshold_seconds,
                signal_market_link_id = EXCLUDED.signal_market_link_id,
                neuron_signal_binding_id = EXCLUDED.neuron_signal_binding_id,
                evidence_json = EXCLUDED.evidence_json,
                updated_at = now()
            """,
            {**result, "evidence_json": Jsonb(_json_safe(result.get("evidence_json") or {}))},
        )
        return existing is None

    def _attach_trusted_orderbook(self, conn: Any, result: dict[str, Any]) -> None:
        evidence = {
            "trusted_orderbook": {
                "trusted": True,
                "trust_reason": result["trust_reason"],
                "orderbook_snapshot_id": result["orderbook_snapshot_id"],
                "orderbook_snapshot_ref": result.get("orderbook_snapshot_ref"),
                "expected_token_id": result.get("expected_token_id"),
                "orderbook_token_id": result.get("orderbook_token_id"),
                "side": result.get("side"),
                "best_bid": result.get("best_bid"),
                "best_ask": result.get("best_ask"),
                "mid_price": result.get("mid_price"),
                "spread": result.get("spread"),
                "age_seconds": result.get("age_seconds"),
                "resolved_at": datetime.now(UTC).isoformat(),
            }
        }
        conn.execute(
            """
            UPDATE paper_eligibility_candidates
            SET orderbook_snapshot_id = %s,
                evidence = COALESCE(evidence, '{}'::jsonb) || %s,
                eligibility_blockers = _jsonb_without_codes(COALESCE(eligibility_blockers, '[]'::jsonb), ARRAY['MISSING_TRUSTED_ORDERBOOK','MISSING_FRESH_ORDERBOOK']),
                missing_requirements = _jsonb_without_codes(COALESCE(missing_requirements, '[]'::jsonb), ARRAY['MISSING_TRUSTED_ORDERBOOK','MISSING_FRESH_ORDERBOOK']),
                updated_at = now()
            WHERE eligibility_id = %s
            """,
            (result["orderbook_snapshot_id"], Jsonb(evidence), result["candidate_id"]),
        )
        candidate = conn.execute(
            "SELECT thesis_id FROM paper_eligibility_candidates WHERE eligibility_id = %s",
            (result["candidate_id"],),
        ).fetchone()
        thesis_id = candidate["thesis_id"] if candidate else None
        if thesis_id:
            conn.execute(
                """
                UPDATE thesis_profiles
                SET orderbook_snapshot_id = %s,
                    evidence = COALESCE(evidence, '{}'::jsonb) || %s,
                    missing_evidence = _jsonb_without_codes(COALESCE(missing_evidence, '[]'::jsonb), ARRAY['MISSING_TRUSTED_ORDERBOOK','MISSING_FRESH_ORDERBOOK','ORDERBOOK_SNAPSHOTS_MISSING']),
                    updated_at = now()
                WHERE thesis_id = %s
                """,
                (result["orderbook_snapshot_id"], Jsonb(evidence), thesis_id),
            )

    def _load_candidates(self, *, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "paper_eligibility_candidates"):
                return []
            rows = conn.execute(
                """
                SELECT
                    pec.*,
                    m.yes_token_id,
                    m.no_token_id,
                    m.condition_id,
                    m.active AS market_active,
                    m.closed AS market_closed,
                    m.archived AS market_archived,
                    m.accepting_orders AS market_accepting_orders,
                    m.raw_market_json AS market_raw_json,
                    sml.id AS signal_market_link_id,
                    nsb.id AS neuron_signal_binding_id,
                    obs.id AS latest_expected_orderbook_id,
                    obs.metadata_json AS latest_expected_orderbook_metadata,
                    EXTRACT(EPOCH FROM (now() - COALESCE(obs.snapshot_at, obs.collected_at, obs.created_at))) AS latest_expected_orderbook_age_seconds,
                    obs.snapshot_status AS latest_expected_orderbook_status,
                    obs.is_stale AS latest_expected_orderbook_is_stale
                FROM paper_eligibility_candidates pec
                LEFT JOIN markets_v2 m ON m.market_id = pec.market_id
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM signal_market_links link
                    WHERE link.market_id = pec.market_id
                      AND link.signal_id IN (SELECT jsonb_array_elements_text(COALESCE(pec.signal_ids, '[]'::jsonb)))
                      AND link.matched_side = pec.side
                      AND link.link_status IN ('confirmed', 'suggested')
                      AND COALESCE(link.is_review_required, false) = false
                      AND COALESCE(link.link_confidence, link.confidence, 0) >= %s
                    ORDER BY COALESCE(link.link_confidence, link.confidence, 0) DESC, link.id DESC
                    LIMIT 1
                ) sml ON true
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM neuron_signal_bindings binding
                    WHERE binding.market_id = pec.market_id
                      AND binding.matched_side = pec.side
                    ORDER BY binding.id DESC
                    LIMIT 1
                ) nsb ON true
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM orderbook_snapshots book
                    WHERE book.market_id = pec.market_id
                      AND book.token_id = CASE WHEN pec.side = 'YES' THEN m.yes_token_id WHEN pec.side = 'NO' THEN m.no_token_id ELSE NULL END
                    ORDER BY COALESCE(book.snapshot_at, book.collected_at, book.created_at) DESC, book.id DESC
                    LIMIT 1
                ) obs ON true
                WHERE pec.side IN ('YES','NO')
                  AND pec.is_runtime_generated = true
                  AND COALESCE(pec.is_dry_run_generated, false) = false
                ORDER BY
                    CASE
                        WHEN obs.id IS NOT NULL
                         AND COALESCE(obs.snapshot_status, 'OK') = 'OK'
                         AND COALESCE(obs.is_stale, false) = false
                         AND EXTRACT(EPOCH FROM (now() - COALESCE(obs.snapshot_at, obs.collected_at, obs.created_at))) <= %s
                         AND COALESCE(obs.metadata_json->>'candidate_id', '') <> pec.eligibility_id
                        THEN 0 ELSE 1
                    END,
                    CASE WHEN pec.eligibility_blockers @> '["MISSING_TRUSTED_ORDERBOOK"]'::jsonb THEN 0 ELSE 1 END,
                    CASE WHEN pec.eligibility_blockers @> '["MISSING_FRESH_ORDERBOOK"]'::jsonb THEN 0 ELSE 1 END,
                    pec.updated_at DESC NULLS LAST,
                    pec.id DESC
                LIMIT %s
                """,
                (TRUSTED_LINK_CONFIDENCE, FRESHNESS_SECONDS, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return _zero_counts()
        with self._factory.connect() as conn:
            return {
                "candidates_total": _count_table(conn, "paper_eligibility_candidates"),
                "candidates_with_side": _count_where(conn, "paper_eligibility_candidates", "side IN ('YES','NO')"),
                "candidates_with_trusted_binding": _trusted_binding_count(conn),
                "candidates_with_orderbook": _count_where(conn, "paper_eligibility_candidates", "orderbook_snapshot_id IS NOT NULL"),
                "trusted_orderbook_matches": _count_where(conn, "trusted_orderbook_evidence_links", "trusted = true"),
                "missing_trusted_orderbook": _candidate_code_count(conn, "MISSING_TRUSTED_ORDERBOOK"),
                "missing_fresh_orderbook": _candidate_code_count(conn, "MISSING_FRESH_ORDERBOOK"),
                "live_orders": _count_table(conn, "live_orders"),
                "real_orders": _count_table(conn, "orders_v2"),
            }

    def _safety_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {"live_orders": 0, "real_orders": 0}
        with self._factory.connect() as conn:
            return {"live_orders": _count_table(conn, "live_orders"), "real_orders": _count_table(conn, "orders_v2")}

    def _extended_safety_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {}
        with self._factory.connect() as conn:
            return {
                "live_orders": _count_table(conn, "live_orders"),
                "paper_intents": _count_table(conn, "paper_intents"),
                "paper_orders": _count_table(conn, "paper_orders"),
                "paper_fills": _count_table(conn, "paper_fills"),
                "paper_positions": _count_table(conn, "paper_positions"),
                "paper_capital_ledger": _count_table(conn, "paper_capital_ledger"),
                "orders_v2": _count_table(conn, "orders_v2"),
                "fills_v2": _count_table(conn, "fills_v2"),
                "canonical_positions": _count_table(conn, "positions"),
            }

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "trusted_orderbook_evidence_runs"):
                return
            conn.execute(
                """
                INSERT INTO trusted_orderbook_evidence_runs (
                    run_id, cycle_id, system_power, started_at, finished_at,
                    status, candidates_checked, candidates_with_side,
                    candidates_with_trusted_binding, candidates_with_orderbook,
                    trusted_matches_created, trusted_matches_refreshed,
                    rejected_count, missing_orderbook_count, stale_count,
                    token_mismatch_count, missing_mid_price_count,
                    spread_too_wide_count, liquidity_too_low_count,
                    missing_trusted_orderbook_before,
                    missing_trusted_orderbook_after,
                    missing_fresh_orderbook_before, missing_fresh_orderbook_after,
                    live_orders_delta, real_orders_delta, metadata_json,
                    error_message
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(system_power)s, %(started_at)s,
                    %(finished_at)s, %(status)s, %(candidates_checked)s,
                    %(candidates_with_side)s, %(candidates_with_trusted_binding)s,
                    %(candidates_with_orderbook)s, %(trusted_matches_created)s,
                    %(trusted_matches_refreshed)s, %(rejected_count)s,
                    %(missing_orderbook_count)s, %(stale_count)s,
                    %(token_mismatch_count)s, %(missing_mid_price_count)s,
                    %(spread_too_wide_count)s, %(liquidity_too_low_count)s,
                    %(missing_trusted_orderbook_before)s,
                    %(missing_trusted_orderbook_after)s,
                    %(missing_fresh_orderbook_before)s,
                    %(missing_fresh_orderbook_after)s,
                    %(live_orders_delta)s, %(real_orders_delta)s,
                    %(metadata_json)s, %(error_message)s
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                {**payload, "metadata_json": Jsonb(_json_safe(payload.get("metadata") or {}))},
            )

    def _latest_run(self) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "trusted_orderbook_evidence_runs"):
                return None
            row = conn.execute("SELECT * FROM trusted_orderbook_evidence_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _existing_for_cycle(self, cycle_id: str | None) -> dict[str, Any] | None:
        if not cycle_id or not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "trusted_orderbook_evidence_runs"):
                return None
            row = conn.execute("SELECT * FROM trusted_orderbook_evidence_runs WHERE cycle_id = %s ORDER BY id DESC LIMIT 1", (cycle_id,)).fetchone()
            return dict(row) if row else None

    def _sample_links(self, *, limit: int, trusted: bool) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "trusted_orderbook_evidence_links"):
                return []
            rows = conn.execute(
                """
                SELECT *
                FROM trusted_orderbook_evidence_links
                WHERE trusted = %s
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (trusted, limit),
            ).fetchall()
        return [_json_safe(dict(row)) for row in rows]

    def _blocked_payload(self, run_id: str, cycle_id: str | None, system_power: str, started_at: datetime, reason: str) -> dict[str, Any]:
        counts = self._counts()
        safety = self._extended_safety_counts()
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "BLOCKED",
            "candidates_checked": 0,
            "candidates_with_side": counts["candidates_with_side"],
            "candidates_with_trusted_binding": counts["candidates_with_trusted_binding"],
            "candidates_with_orderbook": counts["candidates_with_orderbook"],
            "trusted_matches_created": 0,
            "trusted_matches_refreshed": 0,
            "orderbook_snapshots_created": 0,
            "trusted_orderbook_matches": counts["trusted_orderbook_matches"],
            "rejected_count": 0,
            "missing_orderbook_count": 0,
            "stale_count": 0,
            "token_mismatch_count": 0,
            "missing_mid_price_count": 0,
            "spread_too_wide_count": 0,
            "liquidity_too_low_count": 0,
            "missing_trusted_orderbook_before": counts["missing_trusted_orderbook"],
            "missing_trusted_orderbook_after": counts["missing_trusted_orderbook"],
            "missing_fresh_orderbook_before": counts["missing_fresh_orderbook"],
            "missing_fresh_orderbook_after": counts["missing_fresh_orderbook"],
            "live_orders_delta": 0,
            "real_orders_delta": 0,
            "safety_counts_before": safety,
            "safety_counts_after": safety,
            "rejected_reason_counts": [{"reason": reason, "count": 1}],
            "error_message": reason,
            "metadata": {"blocked_reason": reason},
        }

    def _blocker_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {
                "total_blocked": 0,
                "missing_trusted_orderbook_count": 0,
                "missing_fresh_orderbook_count": 0,
                "stale_snapshot_count": 0,
                "token_mismatch_count": 0,
                "clob_no_book_count": 0,
                "no_snapshot_count": 0,
                "trusted_link_not_consumed_count": 0,
                "already_executed_intent_count": 0,
            }
        with self._factory.connect() as conn:
            categories = {
                str(row["category"]): _int(row["count"])
                for row in conn.execute(_BLOCKER_CATEGORY_SQL).fetchall()
            }
            return {
                "total_blocked": _candidate_code_count(conn, "MISSING_TRUSTED_ORDERBOOK") + _candidate_code_count(conn, "MISSING_FRESH_ORDERBOOK"),
                "missing_trusted_orderbook_count": _candidate_code_count(conn, "MISSING_TRUSTED_ORDERBOOK"),
                "missing_fresh_orderbook_count": _candidate_code_count(conn, "MISSING_FRESH_ORDERBOOK"),
                "stale_snapshot_count": categories.get("SNAPSHOT_STALE", 0),
                "token_mismatch_count": categories.get("TOKEN_MISMATCH", 0) + categories.get("SIDE_MISMATCH", 0),
                "clob_no_book_count": _count_where(conn, "trusted_orderbook_evidence_links", "trust_reason = 'CLOB_NO_BOOK'"),
                "no_snapshot_count": categories.get("NO_SNAPSHOT", 0),
                "trusted_link_not_consumed_count": categories.get("TRUSTED_LINK_NOT_CONSUMED", 0),
                "already_executed_intent_count": categories.get("OLD_ALREADY_EXECUTED_INTENT", 0),
            }

    def _top_blocked_markets(self, *, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = conn.execute(
                """
                SELECT pec.market_id, pec.side, COUNT(DISTINCT pec.eligibility_id) AS count,
                       m.condition_id, m.yes_token_id, m.no_token_id,
                       COUNT(DISTINCT tol.candidate_id) FILTER (WHERE tol.trusted) AS trusted_links
                FROM paper_eligibility_candidates pec
                LEFT JOIN markets_v2 m ON m.market_id = pec.market_id
                LEFT JOIN trusted_orderbook_evidence_links tol ON tol.candidate_id = pec.eligibility_id
                WHERE pec.eligibility_blockers @> '["MISSING_FRESH_ORDERBOOK"]'::jsonb
                   OR pec.eligibility_blockers @> '["MISSING_TRUSTED_ORDERBOOK"]'::jsonb
                   OR pec.missing_requirements @> '["MISSING_FRESH_ORDERBOOK"]'::jsonb
                   OR pec.missing_requirements @> '["MISSING_TRUSTED_ORDERBOOK"]'::jsonb
                GROUP BY pec.market_id, pec.side, m.condition_id, m.yes_token_id, m.no_token_id
                ORDER BY count DESC, pec.market_id NULLS LAST
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [_json_safe(dict(row)) for row in rows]


def _trusted_binding_count(conn: Any) -> int:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return 0
    return _int(conn.execute(
        """
        SELECT COUNT(DISTINCT pec.eligibility_id) AS count
        FROM paper_eligibility_candidates pec
        WHERE pec.side IN ('YES','NO')
          AND EXISTS (
              SELECT 1
              FROM signal_market_links sml
              WHERE sml.market_id = pec.market_id
                AND sml.signal_id IN (SELECT jsonb_array_elements_text(COALESCE(pec.signal_ids, '[]'::jsonb)))
                AND sml.matched_side = pec.side
                AND sml.link_status IN ('confirmed', 'suggested')
                AND COALESCE(sml.is_review_required, false) = false
                AND COALESCE(sml.link_confidence, sml.confidence, 0) >= %s
          )
        """,
        (TRUSTED_LINK_CONFIDENCE,),
    ).fetchone()["count"])


class _TrustedOrderbookHttpClient:
    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> tuple[Any, int]:
        started = time.perf_counter()
        with httpx.Client(timeout=self._timeout_seconds, follow_redirects=True, headers={"User-Agent": "POLYBOT-trusted-orderbook-recovery/1.0"}) as client:
            response = client.get(url, params=params)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms


def _should_refresh_candidate_book(book: dict[str, Any] | None) -> bool:
    if not book:
        return True
    age_seconds = _float_or_none(book.get("age_seconds"))
    return (
        str(book.get("snapshot_status") or "").upper() != "OK"
        or bool(book.get("is_stale"))
        or (age_seconds is not None and age_seconds > FRESHNESS_SECONDS)
    )


def _missing_candidate_scope(book: dict[str, Any] | None, *, candidate_id: str) -> bool:
    if not book:
        return False
    metadata = book.get("metadata_json") if isinstance(book.get("metadata_json"), dict) else {}
    return str(metadata.get("candidate_id") or "") != str(candidate_id)


def _market_allows_orderbook(row: dict[str, Any]) -> bool:
    if row.get("market_active") is False:
        return False
    if row.get("market_closed") is True or row.get("market_archived") is True:
        return False
    if row.get("market_accepting_orders") is False:
        return False
    raw = row.get("market_raw_json") if isinstance(row.get("market_raw_json"), dict) else {}
    if raw.get("enableOrderBook") is False or raw.get("enable_orderbook") is False:
        return False
    if raw.get("acceptingOrders") is False or raw.get("accepting_orders") is False:
        return False
    return True


_BLOCKER_CATEGORY_SQL = """
WITH blocked AS (
  SELECT pec.*, m.yes_token_id, m.no_token_id,
         CASE WHEN pec.side='YES' THEN m.yes_token_id WHEN pec.side='NO' THEN m.no_token_id ELSE NULL END expected_token
  FROM paper_eligibility_candidates pec
  LEFT JOIN markets_v2 m ON m.market_id = pec.market_id
  WHERE pec.eligibility_blockers @> '["MISSING_FRESH_ORDERBOOK"]'::jsonb
     OR pec.eligibility_blockers @> '["MISSING_TRUSTED_ORDERBOOK"]'::jsonb
     OR pec.missing_requirements @> '["MISSING_FRESH_ORDERBOOK"]'::jsonb
     OR pec.missing_requirements @> '["MISSING_TRUSTED_ORDERBOOK"]'::jsonb
), traced AS (
  SELECT b.eligibility_id,
         CASE
           WHEN b.market_id IS NULL THEN 'NO_MARKET_ID'
           WHEN b.side NOT IN ('YES','NO') THEN 'NO_SIDE'
           WHEN b.expected_token IS NULL THEN 'NO_EXPECTED_TOKEN'
           WHEN EXISTS (
                SELECT 1 FROM paper_intents pi
                WHERE pi.eligibility_id = b.eligibility_id
                  AND (pi.intent_status IN ('BUILT','EXECUTED','ORDERED','FILLED','CLOSED')
                       OR pi.executed_at IS NOT NULL
                       OR pi.consumed_at IS NOT NULL
                       OR pi.closed_at IS NOT NULL)
           ) THEN 'OLD_ALREADY_EXECUTED_INTENT'
           WHEN NOT EXISTS (SELECT 1 FROM orderbook_snapshots os WHERE os.market_id=b.market_id) THEN 'NO_SNAPSHOT'
           WHEN NOT EXISTS (SELECT 1 FROM orderbook_snapshots os WHERE os.market_id=b.market_id AND os.token_id=b.expected_token) THEN 'TOKEN_MISMATCH'
           WHEN EXISTS (
                SELECT 1 FROM orderbook_snapshots os
                WHERE os.market_id=b.market_id
                  AND os.token_id=b.expected_token
                  AND (os.snapshot_status <> 'OK'
                       OR COALESCE(os.is_stale,false)
                       OR COALESCE(os.snapshot_at,os.collected_at,os.created_at) < now() - interval '180 seconds')
           ) THEN 'SNAPSHOT_STALE'
           WHEN EXISTS (SELECT 1 FROM orderbook_snapshots os WHERE os.market_id=b.market_id AND os.token_id=b.expected_token AND (os.best_bid IS NULL OR os.best_ask IS NULL)) THEN 'BID_ASK_MISSING'
           WHEN EXISTS (SELECT 1 FROM orderbook_snapshots os WHERE os.market_id=b.market_id AND os.token_id=b.expected_token AND os.mid_price IS NULL AND NOT (os.best_bid IS NOT NULL AND os.best_ask IS NOT NULL)) THEN 'MID_PRICE_MISSING'
           WHEN EXISTS (SELECT 1 FROM orderbook_snapshots os WHERE os.market_id=b.market_id AND os.token_id=b.expected_token AND COALESCE(os.spread, os.best_ask-os.best_bid) > 0.08) THEN 'SPREAD_TOO_WIDE'
           WHEN EXISTS (SELECT 1 FROM orderbook_snapshots os WHERE os.market_id=b.market_id AND os.token_id=b.expected_token AND os.liquidity_score IS NOT NULL AND os.liquidity_score < 0.25) THEN 'LIQUIDITY_TOO_LOW'
           WHEN EXISTS (SELECT 1 FROM trusted_orderbook_evidence_links tol WHERE tol.candidate_id=b.eligibility_id AND tol.trusted) THEN 'TRUSTED_LINK_NOT_CONSUMED'
           ELSE 'OTHER'
         END AS category
  FROM blocked b
)
SELECT category, COUNT(*) AS count FROM traced GROUP BY category ORDER BY count DESC, category
"""


def _json_code_count(conn: Any, table: str, column: str, code: str) -> int:
    if not _table_exists(conn, table) or not _column_exists(conn, table, column):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {column} @> %s::jsonb", (Jsonb([code]),)).fetchone()["count"])


def _candidate_code_count(conn: Any, code: str) -> int:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return 0
    columns = [
        column for column in ("eligibility_blockers", "missing_requirements")
        if _column_exists(conn, "paper_eligibility_candidates", column)
    ]
    if not columns:
        return 0
    where = " OR ".join(f"{column} @> %s::jsonb" for column in columns)
    params = tuple(Jsonb([code]) for _ in columns)
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM paper_eligibility_candidates WHERE {where}", params).fetchone()["count"])


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"])


def _zero_counts() -> dict[str, int]:
    return {
        "candidates_total": 0,
        "candidates_with_side": 0,
        "candidates_with_trusted_binding": 0,
        "candidates_with_orderbook": 0,
        "trusted_orderbook_matches": 0,
        "missing_trusted_orderbook": 0,
        "missing_fresh_orderbook": 0,
        "live_orders": 0,
        "real_orders": 0,
    }


def _column_exists(conn: Any, table: str, column: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s", (table, column)).fetchone())


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


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

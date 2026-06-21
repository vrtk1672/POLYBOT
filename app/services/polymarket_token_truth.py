from __future__ import annotations

import json
import os
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.security.redaction import redact_secrets
from app.services.source_status import DEFAULT_CLOB_BASE_URL
from app.services.system_power import SystemPowerService
from app.services.trusted_orderbook import FRESHNESS_SECONDS, MAX_SPREAD, MIN_LIQUIDITY_SCORE


class PolymarketTokenTruthService:
    """Audit and repair source-backed Polymarket outcome token bindings."""

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
        self._http = http_client or _TokenTruthHttpClient()
        self._snapshotter = OrderbookSnapshotter(connection_factory=self._factory)
        self._orderbooks = OrderbookSnapshotRepository()

    def run_recovery(
        self,
        *,
        cycle_id: str | None = None,
        candidate_limit: int = 100,
        gamma_market_limit: int = 20,
        verify_clob: bool = True,
        apply_backfill: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"polymarket_token_truth_{uuid4().hex}"
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

        before = self._counts()
        safety_before = self._safety_counts()
        traces: list[dict[str, Any]] = []
        blockers: Counter[str] = Counter()
        errors: list[str] = []
        trusted_created = 0
        trusted_refreshed = 0
        snapshots_created = 0

        with self._factory.connect() as conn, conn.transaction():
            candidates = self._load_candidate_targets(conn, limit=candidate_limit)
            for candidate in candidates:
                try:
                    trace, side_effects = self._process_candidate(
                        conn,
                        candidate,
                        run_id=run_id,
                        verify_clob=verify_clob,
                        apply_backfill=apply_backfill,
                    )
                    traces.append(trace)
                    blockers[trace["classification"]] += 1
                    trusted_created += int(side_effects.get("trusted_created", 0))
                    trusted_refreshed += int(side_effects.get("trusted_refreshed", 0))
                    snapshots_created += int(side_effects.get("snapshot_created", 0))
                except Exception as exc:
                    errors.append(f"{candidate.get('eligibility_id') or 'unknown'}:{type(exc).__name__}:{redact_secrets(str(exc))[:160]}")
                    blockers["UNKNOWN"] += 1
            gamma_markets = self._load_gamma_market_targets(conn, limit=gamma_market_limit)
            for market in gamma_markets:
                try:
                    trace, _ = self._process_gamma_market(conn, market, run_id=run_id, verify_clob=verify_clob)
                    traces.append(trace)
                    blockers[trace["classification"]] += 1
                except Exception as exc:
                    errors.append(f"{market.get('market_id') or 'unknown'}:{type(exc).__name__}:{redact_secrets(str(exc))[:160]}")
                    blockers["UNKNOWN"] += 1
            self._record_traces(conn, traces)

        after = self._counts()
        safety_after = self._safety_counts()
        candidates_checked = sum(1 for trace in traces if trace["trace_type"] == "candidate")
        gamma_checked = sum(1 for trace in traces if trace["trace_type"] == "gamma_market")
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "DEGRADED" if errors else "OK",
            "candidates_checked": candidates_checked,
            "gamma_markets_checked": gamma_checked,
            "tokens_resolved": sum(1 for trace in traces if trace.get("expected_token_id")),
            "clob_checks_attempted": sum(1 for trace in traces if trace.get("clob_book_attempted")),
            "verified_token_books": sum(1 for trace in traces if trace.get("classification") == "VERIFIED_BY_CLOB_BOOK"),
            "token_not_found_count": blockers["TOKEN_NOT_FOUND"] + blockers["CLOB_TOKEN_NOT_FOUND_DESPITE_GAMMA_TOKEN"],
            "token_parse_error_count": blockers["TOKEN_JSON_ARRAY_PARSE_BUG"] + blockers["TOKEN_OUTCOME_ORDER_MISMATCH"],
            "ambiguous_token_count": blockers["AMBIGUOUS_TOKEN_MAPPING"],
            "trusted_links_created": trusted_created,
            "trusted_links_refreshed": trusted_refreshed,
            "orderbook_snapshots_created": snapshots_created,
            "blocker_counts": dict(blockers),
            "live_orders_delta": max(0, safety_after["live_orders"] - safety_before["live_orders"]),
            "real_orders_delta": max(0, safety_after["orders_v2"] - safety_before["orders_v2"]),
            "metadata": {
                "verify_clob": verify_clob,
                "apply_backfill": apply_backfill,
                "read_only_clob_book_endpoint": True,
                "no_trading_mutation": True,
                "before": before,
                "after": after,
            },
            "error_message": "; ".join(errors[:10]) if errors else None,
            "before": before,
            "after": after,
            "sample_traces": traces[:20],
        }
        self._record_run(payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 100) -> dict[str, Any]:
        counts = self._counts()
        latest = self._latest_run()
        return {
            "mock_data": False,
            "status": "OK",
            "total_markets": counts["total_markets"],
            "markets_with_condition_id": counts["markets_with_condition_id"],
            "markets_with_yes_no_tokens": counts["markets_with_yes_no_tokens"],
            "candidates_with_expected_token": counts["candidates_with_expected_token"],
            "candidates_verified_by_clob": counts["candidates_verified_by_clob"],
            "token_not_found_count": counts["token_not_found_count"],
            "token_parse_error_count": counts["token_parse_error_count"],
            "ambiguous_token_count": counts["ambiguous_token_count"],
            "verified_token_book_count": counts["verified_token_book_count"],
            "blocker_counts": self._latest_blockers(),
            "sample_successes": self._sample_traces("VERIFIED_BY_CLOB_BOOK", limit=limit),
            "sample_failures": self._sample_failures(limit=limit),
            "top_failure_causes": self._top_failure_causes(),
            "latest_run": latest,
            "security_status_summary": {
                "mock_data": False,
                "secret_exposure_status": "ROTATION_REQUIRED",
                "raw_values_returned": False,
            },
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _process_candidate(
        self,
        conn: Any,
        candidate: dict[str, Any],
        *,
        run_id: str,
        verify_clob: bool,
        apply_backfill: bool,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        candidate_id = str(candidate.get("eligibility_id"))
        market_id = _clean(candidate.get("market_id"))
        side = _valid_side(candidate.get("side"))
        market = self._load_market(conn, market_id) if market_id else None
        raw_row = self._latest_gamma_payload(conn, market_id=market_id) if market_id else None
        raw = raw_row.get("raw") if raw_row else (market or {}).get("raw_market_json") or {}
        parsed = parse_gamma_token_binding(raw)
        if market_id and parsed["status"] == "OK" and apply_backfill:
            market = self._upsert_source_truth(conn, market=market, market_id=market_id, parsed=parsed, raw=raw, row=raw_row)

        condition_id = _clean((market or {}).get("condition_id") or parsed.get("condition_id"))
        stored_yes = _clean((market or {}).get("yes_token_id"))
        stored_no = _clean((market or {}).get("no_token_id"))
        source_yes = _clean((parsed.get("tokens") or {}).get("YES"))
        source_no = _clean((parsed.get("tokens") or {}).get("NO"))
        yes_token = source_yes or stored_yes
        no_token = source_no or stored_no
        expected_token = yes_token if side == "YES" else no_token if side == "NO" else None
        stored_expected = stored_yes if side == "YES" else stored_no if side == "NO" else None

        classification = self._preflight_classification(
            market_id=market_id,
            side=side,
            parsed=parsed,
            expected_token=expected_token,
            condition_id=condition_id,
            market=market,
            raw=raw,
        )
        clob = {"status": "NOT_ATTEMPTED"}
        effects = {"trusted_created": 0, "trusted_refreshed": 0, "snapshot_created": 0}
        book_metrics: dict[str, Any] = {}
        snapshot_id = None
        trust_link_id = None
        if classification == "READY_FOR_CLOB_CHECK" and verify_clob and expected_token:
            clob = self._fetch_book(expected_token)
            classification = self._classify_clob_result(clob, expected_token=expected_token, condition_id=condition_id, stored_expected=stored_expected)
            if classification == "VERIFIED_BY_CLOB_BOOK" and clob.get("raw"):
                snapshot_id, book_metrics = self._persist_snapshot(conn, raw=clob["raw"], market_id=market_id, token_id=expected_token, side=side, run_id=run_id)
                effects["snapshot_created"] = int(bool(snapshot_id))
                created = self._upsert_trusted_link(
                    conn,
                    candidate_id=candidate_id,
                    market_id=market_id,
                    side=side,
                    expected_token=expected_token,
                    snapshot_id=snapshot_id,
                    snapshot_ref=book_metrics.get("snapshot_ref"),
                    metrics=book_metrics,
                )
                trust_link_id = f"trusted_orderbook_{candidate_id}" if snapshot_id else None
                effects["trusted_created"] = int(bool(created and trust_link_id))
                effects["trusted_refreshed"] = int(bool((not created) and trust_link_id))
                if trust_link_id:
                    self._attach_trusted_orderbook(conn, candidate_id=candidate_id, snapshot_id=snapshot_id, expected_token=expected_token)

        if side and expected_token:
            self._upsert_token_binding(conn, market_id=market_id, condition_id=condition_id, raw=raw, side=side, token_id=expected_token, parsed=parsed, classification=classification, clob=clob)

        return (
            self._trace(
                run_id=run_id,
                trace_type="candidate",
                candidate_id=candidate_id,
                market_id=market_id,
                side=side,
                condition_id=condition_id,
                stored_yes=stored_yes,
                stored_no=stored_no,
                candidate_token=_clean(candidate.get("token_id")),
                expected_token=expected_token,
                attempted_token=expected_token if clob.get("status") != "NOT_ATTEMPTED" else None,
                parsed=parsed,
                raw=raw,
                market=market,
                classification=classification,
                clob=clob,
                metrics=book_metrics,
                snapshot_id=snapshot_id,
                trust_link_id=trust_link_id,
            ),
            effects,
        )

    def _process_gamma_market(self, conn: Any, market: dict[str, Any], *, run_id: str, verify_clob: bool) -> tuple[dict[str, Any], dict[str, int]]:
        raw = market.get("raw") or {}
        market_id = _clean(market.get("market_id") or raw.get("id"))
        parsed = parse_gamma_token_binding(raw)
        side = "YES"
        expected_token = (parsed.get("tokens") or {}).get("YES") if parsed["status"] == "OK" else None
        classification = self._preflight_classification(
            market_id=market_id,
            side=side,
            parsed=parsed,
            expected_token=expected_token,
            condition_id=_clean(parsed.get("condition_id")),
            market=None,
            raw=raw,
        )
        clob = {"status": "NOT_ATTEMPTED"}
        if classification == "READY_FOR_CLOB_CHECK" and verify_clob and expected_token:
            clob = self._fetch_book(expected_token)
            classification = self._classify_clob_result(clob, expected_token=expected_token, condition_id=_clean(parsed.get("condition_id")), stored_expected=None)
        if expected_token:
            self._upsert_token_binding(conn, market_id=market_id, condition_id=_clean(parsed.get("condition_id")), raw=raw, side=side, token_id=expected_token, parsed=parsed, classification=classification, clob=clob)
        return (
            self._trace(
                run_id=run_id,
                trace_type="gamma_market",
                candidate_id=None,
                market_id=market_id,
                side=side,
                condition_id=_clean(parsed.get("condition_id")),
                stored_yes=None,
                stored_no=None,
                candidate_token=None,
                expected_token=expected_token,
                attempted_token=expected_token if clob.get("status") != "NOT_ATTEMPTED" else None,
                parsed=parsed,
                raw=raw,
                market=None,
                classification=classification,
                clob=clob,
                metrics={},
                snapshot_id=None,
                trust_link_id=None,
            ),
            {},
        )

    def _preflight_classification(
        self,
        *,
        market_id: str | None,
        side: str | None,
        parsed: dict[str, Any],
        expected_token: str | None,
        condition_id: str | None,
        market: dict[str, Any] | None,
        raw: dict[str, Any],
    ) -> str:
        if not market_id:
            return "NO_MARKET_ID"
        if not condition_id:
            return "NO_CONDITION_ID"
        if side not in {"YES", "NO"}:
            return "NO_SIDE"
        if parsed["status"] != "OK":
            return str(parsed["status"])
        if not expected_token:
            return "EXPECTED_TOKEN_MISSING"
        if expected_token == condition_id:
            return "CONDITION_ID_USED_AS_TOKEN"
        if expected_token == market_id:
            return "MARKET_ID_USED_AS_TOKEN"
        if _market_closed(market, raw):
            return "MARKET_CLOSED"
        if _accepting_orders_false(market, raw):
            return "ACCEPTING_ORDERS_FALSE"
        if _orderbook_disabled(raw):
            return "NOT_CLOB_TRADABLE"
        return "READY_FOR_CLOB_CHECK"

    def _classify_clob_result(self, clob: dict[str, Any], *, expected_token: str, condition_id: str | None, stored_expected: str | None) -> str:
        status = str(clob.get("status") or "UNKNOWN")
        if status == "OK":
            if _clean(clob.get("asset_id")) != expected_token:
                return "TOKEN_MISMATCH"
            if condition_id and _clean(clob.get("market")) != condition_id:
                return "CONDITION_ID_MISMATCH"
            return "VERIFIED_BY_CLOB_BOOK"
        if status == "TOKEN_NOT_FOUND":
            if stored_expected and stored_expected != expected_token:
                return "INTERNAL_STALE_TOKEN"
            return "CLOB_TOKEN_NOT_FOUND_DESPITE_GAMMA_TOKEN"
        return status

    def _fetch_book(self, token_id: str) -> dict[str, Any]:
        endpoint = f"{(os.getenv('POLYMARKET_CLOB_HOST') or DEFAULT_CLOB_BASE_URL).rstrip('/')}/book"
        started = time.perf_counter()
        try:
            raw, latency_ms = self._http.get_json(endpoint, params={"token_id": token_id})
        except httpx.HTTPStatusError as exc:
            body = redact_secrets(exc.response.text or "")[:240]
            status = "TOKEN_NOT_FOUND" if exc.response.status_code == 404 else "CLOB_ENDPOINT_ERROR"
            return {"status": status, "latency_ms": int((time.perf_counter() - started) * 1000), "error_type": type(exc).__name__, "error_summary": body}
        except Exception as exc:
            text = redact_secrets(str(exc))[:240]
            status = "TOKEN_NOT_FOUND" if "token" in text.lower() and "not" in text.lower() else "CLOB_NO_BOOK" if "orderbook" in text.lower() else "NETWORK_ERROR"
            return {"status": status, "latency_ms": int((time.perf_counter() - started) * 1000), "error_type": type(exc).__name__, "error_summary": text}
        latency = latency_ms if latency_ms is not None else int((time.perf_counter() - started) * 1000)
        if not isinstance(raw, dict) or not raw:
            return {"status": "CLOB_NO_BOOK", "latency_ms": latency}
        bids = raw.get("bids") or raw.get("buy") or []
        asks = raw.get("asks") or raw.get("sell") or []
        if not bids or not asks:
            return {"status": "CLOB_NO_BOOK", "latency_ms": latency, "asset_id": raw.get("asset_id"), "market": raw.get("market")}
        return {"status": "OK", "latency_ms": latency, "raw": raw, "asset_id": raw.get("asset_id"), "market": raw.get("market")}

    def _persist_snapshot(self, conn: Any, *, raw: dict[str, Any], market_id: str, token_id: str, side: str | None, run_id: str) -> tuple[int | None, dict[str, Any]]:
        snapshot = self._snapshotter.normalize_orderbook(
            raw,
            market_id=market_id,
            token_id=token_id,
            side=side,
            source="polymarket_token_truth",
            correlation_id=run_id,
            raw_payload_ref=f"clob:/book:{token_id}:{datetime.now(UTC).isoformat()}",
            collected_at=datetime.now(UTC),
            freshness_window_seconds=FRESHNESS_SECONDS,
        )
        self._orderbooks.append_snapshot(conn, snapshot)
        row = conn.execute("SELECT * FROM orderbook_snapshots WHERE orderbook_snapshot_id=%s", (snapshot.orderbook_snapshot_id,)).fetchone()
        return (
            int(row["id"]) if row else None,
            {
                "snapshot_ref": snapshot.orderbook_snapshot_id,
                "best_bid": snapshot.best_bid,
                "best_ask": snapshot.best_ask,
                "mid_price": snapshot.mid_price,
                "spread": snapshot.spread,
                "liquidity_score": snapshot.liquidity_score,
                "snapshot_status": snapshot.snapshot_status,
            },
        )

    def _upsert_trusted_link(
        self,
        conn: Any,
        *,
        candidate_id: str,
        market_id: str | None,
        side: str | None,
        expected_token: str,
        snapshot_id: int | None,
        snapshot_ref: str | None,
        metrics: dict[str, Any],
    ) -> bool:
        spread = _float_or_none(metrics.get("spread"))
        liquidity = _float_or_none(metrics.get("liquidity_score"))
        trusted = (
            snapshot_id is not None
            and side in {"YES", "NO"}
            and str(metrics.get("snapshot_status") or "") == "OK"
            and spread is not None
            and spread <= MAX_SPREAD
            and (liquidity is None or liquidity >= MIN_LIQUIDITY_SCORE)
        )
        if not trusted:
            return False
        existing = conn.execute("SELECT 1 FROM trusted_orderbook_evidence_links WHERE candidate_id=%s", (candidate_id,)).fetchone()
        payload = {
            "link_id": f"trusted_orderbook_{candidate_id}",
            "candidate_id": candidate_id,
            "market_id": market_id,
            "side": side,
            "expected_token_id": expected_token,
            "orderbook_snapshot_id": snapshot_id,
            "orderbook_snapshot_ref": snapshot_ref,
            "orderbook_token_id": expected_token,
            "trusted": True,
            "trust_status": "TRUSTED",
            "trust_reason": "TRUSTED_ORDERBOOK",
            "best_bid": metrics.get("best_bid"),
            "best_ask": metrics.get("best_ask"),
            "mid_price": metrics.get("mid_price"),
            "spread": spread,
            "liquidity_score": liquidity,
            "age_seconds": 0,
            "freshness_threshold_seconds": FRESHNESS_SECONDS,
            "signal_market_link_id": None,
            "neuron_signal_binding_id": None,
            "evidence_json": Jsonb({"source": "polymarket_token_truth", "validated_asset_id": True, "validated_condition_id": True}),
        }
        conn.execute(
            """
            INSERT INTO trusted_orderbook_evidence_links (
                link_id, candidate_id, market_id, side, expected_token_id,
                orderbook_snapshot_id, orderbook_snapshot_ref, orderbook_token_id,
                trusted, trust_status, trust_reason, best_bid, best_ask, mid_price,
                spread, liquidity_score, age_seconds, freshness_threshold_seconds,
                signal_market_link_id, neuron_signal_binding_id, evidence_json,
                created_at, updated_at
            )
            VALUES (
                %(link_id)s, %(candidate_id)s, %(market_id)s, %(side)s, %(expected_token_id)s,
                %(orderbook_snapshot_id)s, %(orderbook_snapshot_ref)s, %(orderbook_token_id)s,
                %(trusted)s, %(trust_status)s, %(trust_reason)s, %(best_bid)s, %(best_ask)s,
                %(mid_price)s, %(spread)s, %(liquidity_score)s, %(age_seconds)s,
                %(freshness_threshold_seconds)s, %(signal_market_link_id)s,
                %(neuron_signal_binding_id)s, %(evidence_json)s, now(), now()
            )
            ON CONFLICT (candidate_id) DO UPDATE SET
                orderbook_snapshot_id=EXCLUDED.orderbook_snapshot_id,
                orderbook_snapshot_ref=EXCLUDED.orderbook_snapshot_ref,
                orderbook_token_id=EXCLUDED.orderbook_token_id,
                trusted=EXCLUDED.trusted,
                trust_status=EXCLUDED.trust_status,
                trust_reason=EXCLUDED.trust_reason,
                best_bid=EXCLUDED.best_bid,
                best_ask=EXCLUDED.best_ask,
                mid_price=EXCLUDED.mid_price,
                spread=EXCLUDED.spread,
                liquidity_score=EXCLUDED.liquidity_score,
                evidence_json=EXCLUDED.evidence_json,
                updated_at=now()
            """,
            payload,
        )
        return existing is None

    def _attach_trusted_orderbook(self, conn: Any, *, candidate_id: str, snapshot_id: int | None, expected_token: str) -> None:
        conn.execute(
            """
            UPDATE paper_eligibility_candidates
            SET orderbook_snapshot_id=%s,
                evidence=COALESCE(evidence,'{}'::jsonb) || %s,
                eligibility_blockers=_jsonb_without_codes(COALESCE(eligibility_blockers,'[]'::jsonb), ARRAY['MISSING_TRUSTED_ORDERBOOK','MISSING_FRESH_ORDERBOOK']),
                missing_requirements=_jsonb_without_codes(COALESCE(missing_requirements,'[]'::jsonb), ARRAY['MISSING_TRUSTED_ORDERBOOK','MISSING_FRESH_ORDERBOOK']),
                updated_at=now()
            WHERE eligibility_id=%s
            """,
            (snapshot_id, Jsonb({"trusted_orderbook": {"trusted": True, "source": "polymarket_token_truth", "expected_token_id": expected_token}}), candidate_id),
        )

    def _upsert_source_truth(self, conn: Any, *, market: dict[str, Any] | None, market_id: str, parsed: dict[str, Any], raw: dict[str, Any], row: dict[str, Any] | None) -> dict[str, Any]:
        tokens = parsed.get("tokens") or {}
        payload = {
            "market_id": market_id,
            "condition_id": _clean(parsed.get("condition_id")),
            "question": _clean(raw.get("question") or raw.get("title") or (market or {}).get("question")),
            "slug": _clean(raw.get("slug") or (market or {}).get("slug")),
            "yes_token_id": tokens.get("YES"),
            "no_token_id": tokens.get("NO"),
            "outcome_tokens_json": Jsonb(tokens),
            "accepting_orders": _bool_or_none(raw.get("acceptingOrders")),
            "closed": bool(raw.get("closed", False)),
            "archived": bool(raw.get("archived", False)),
            "active": bool(raw.get("active", True)),
            "raw_market_json": Jsonb(raw),
            "metadata_json": Jsonb({
                "token_source_truth": True,
                "token_source": parsed.get("token_source"),
                "gamma_field": parsed.get("gamma_field"),
                "seen_at": _iso((row or {}).get("seen_at")),
            }),
        }
        return dict(conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, condition_id, question, slug, yes_token_id, no_token_id,
                outcome_tokens_json, accepting_orders, closed, archived, active,
                raw_market_json, metadata_json, resolution_source, source
            )
            VALUES (
                %(market_id)s, %(condition_id)s, %(question)s, %(slug)s,
                %(yes_token_id)s, %(no_token_id)s, %(outcome_tokens_json)s,
                %(accepting_orders)s, %(closed)s, %(archived)s, %(active)s,
                %(raw_market_json)s, %(metadata_json)s, 'polymarket_gamma_token_truth', 'polymarket_gamma'
            )
            ON CONFLICT (market_id) DO UPDATE SET
                condition_id=COALESCE(EXCLUDED.condition_id, markets_v2.condition_id),
                question=COALESCE(EXCLUDED.question, markets_v2.question),
                slug=COALESCE(EXCLUDED.slug, markets_v2.slug),
                yes_token_id=EXCLUDED.yes_token_id,
                no_token_id=EXCLUDED.no_token_id,
                outcome_tokens_json=EXCLUDED.outcome_tokens_json,
                accepting_orders=COALESCE(EXCLUDED.accepting_orders, markets_v2.accepting_orders),
                closed=EXCLUDED.closed,
                archived=EXCLUDED.archived,
                active=EXCLUDED.active,
                raw_market_json=EXCLUDED.raw_market_json,
                metadata_json=COALESCE(markets_v2.metadata_json,'{}'::jsonb) || EXCLUDED.metadata_json,
                updated_at=now()
            RETURNING *
            """,
            payload,
        ).fetchone())

    def _upsert_token_binding(self, conn: Any, *, market_id: str | None, condition_id: str | None, raw: dict[str, Any], side: str, token_id: str, parsed: dict[str, Any], classification: str, clob: dict[str, Any]) -> None:
        binding_id = f"polymarket_token_{market_id}_{side}"
        conn.execute(
            """
            INSERT INTO polymarket_token_bindings (
                binding_id, market_id, condition_id, slug, question, outcome_label,
                side, token_id, token_source, gamma_field, confidence,
                accepting_orders, closed, active, verified_by_clob_book,
                clob_book_status, metadata_json, updated_at
            )
            VALUES (
                %(binding_id)s, %(market_id)s, %(condition_id)s, %(slug)s, %(question)s,
                %(outcome_label)s, %(side)s, %(token_id)s, %(token_source)s,
                %(gamma_field)s, %(confidence)s, %(accepting_orders)s, %(closed)s,
                %(active)s, %(verified_by_clob_book)s, %(clob_book_status)s,
                %(metadata_json)s, now()
            )
            ON CONFLICT (binding_id) DO UPDATE SET
                condition_id=EXCLUDED.condition_id,
                slug=EXCLUDED.slug,
                question=EXCLUDED.question,
                token_id=EXCLUDED.token_id,
                token_source=EXCLUDED.token_source,
                gamma_field=EXCLUDED.gamma_field,
                confidence=EXCLUDED.confidence,
                accepting_orders=EXCLUDED.accepting_orders,
                closed=EXCLUDED.closed,
                active=EXCLUDED.active,
                verified_by_clob_book=EXCLUDED.verified_by_clob_book,
                clob_book_status=EXCLUDED.clob_book_status,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            {
                "binding_id": binding_id,
                "market_id": market_id,
                "condition_id": condition_id,
                "slug": raw.get("slug"),
                "question": raw.get("question") or raw.get("title"),
                "outcome_label": side.title(),
                "side": side,
                "token_id": token_id,
                "token_source": parsed.get("token_source"),
                "gamma_field": parsed.get("gamma_field"),
                "confidence": parsed.get("confidence"),
                "accepting_orders": _bool_or_none(raw.get("acceptingOrders")),
                "closed": bool(raw.get("closed", False)),
                "active": bool(raw.get("active", True)),
                "verified_by_clob_book": classification == "VERIFIED_BY_CLOB_BOOK",
                "clob_book_status": clob.get("status"),
                "metadata_json": Jsonb({"classification": classification, "clob_latency_ms": clob.get("latency_ms")}),
            },
        )

    def _trace(self, **kwargs: Any) -> dict[str, Any]:
        parsed = kwargs["parsed"]
        raw = kwargs["raw"] or {}
        clob = kwargs["clob"]
        metrics = kwargs["metrics"]
        return {
            "run_id": kwargs["run_id"],
            "trace_type": kwargs["trace_type"],
            "candidate_id": kwargs["candidate_id"],
            "market_id": kwargs["market_id"],
            "slug": raw.get("slug") or (kwargs.get("market") or {}).get("slug"),
            "question": raw.get("question") or raw.get("title") or (kwargs.get("market") or {}).get("question"),
            "condition_id": kwargs["condition_id"],
            "side": kwargs["side"],
            "stored_yes_token_id": kwargs["stored_yes"],
            "stored_no_token_id": kwargs["stored_no"],
            "candidate_token_id": kwargs["candidate_token"],
            "expected_token_id": kwargs["expected_token"],
            "clob_attempted_token_id": kwargs["attempted_token"],
            "gamma_field": parsed.get("gamma_field"),
            "token_source": parsed.get("token_source"),
            "token_binding_confidence": parsed.get("confidence"),
            "accepting_orders": _bool_or_none(raw.get("acceptingOrders")),
            "closed": bool(raw.get("closed", False)),
            "active": bool(raw.get("active", True)),
            "enable_order_book": _bool_or_none(raw.get("enableOrderBook")),
            "clob_book_attempted": bool(kwargs["attempted_token"]),
            "clob_book_status": clob.get("status", "NOT_ATTEMPTED"),
            "clob_error_summary": redact_secrets(clob.get("error_summary") or "")[:240] or None,
            "best_bid": metrics.get("best_bid"),
            "best_ask": metrics.get("best_ask"),
            "spread": metrics.get("spread"),
            "snapshot_id": kwargs["snapshot_id"],
            "trust_link_id": kwargs["trust_link_id"],
            "classification": kwargs["classification"],
            "exact_fix_category": kwargs["classification"],
            "raw_gamma_fields_json": parsed.get("raw_fields") or {},
            "evidence_json": {
                "source": "polymarket_token_truth",
                "token_parse_status": parsed.get("status"),
                "condition_validated": kwargs["classification"] == "VERIFIED_BY_CLOB_BOOK",
                "asset_validated": kwargs["classification"] == "VERIFIED_BY_CLOB_BOOK",
            },
        }

    def _load_candidate_targets(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            WITH traced AS (
                SELECT DISTINCT candidate_id
                FROM polymarket_binding_candidate_traces
                WHERE exact_fix_category = 'TOKEN_NOT_FOUND'
                ORDER BY candidate_id
                LIMIT %s
            ), target AS (
                SELECT 0 AS priority, pec.*
                FROM paper_eligibility_candidates pec
                JOIN traced ON traced.candidate_id = pec.eligibility_id
                UNION ALL
                SELECT 1 AS priority, pec.*
                FROM paper_eligibility_candidates pec
                WHERE pec.eligibility_id NOT IN (SELECT candidate_id FROM traced)
                  AND (
                        pec.market_id IS NULL OR pec.market_id = ''
                        OR pec.side IS NULL OR pec.side NOT IN ('YES','NO')
                        OR COALESCE(pec.eligibility_blockers,'[]'::jsonb) ?| ARRAY['MISSING_FRESH_ORDERBOOK','MISSING_TRUSTED_ORDERBOOK','MISSING_MARKET_ID','MISSING_SIDE']
                      )
            )
            SELECT * FROM target
            ORDER BY priority, market_id NULLS LAST, updated_at DESC NULLS LAST
            LIMIT %s
            """,
            (min(limit, 31), limit),
        ).fetchall()
        return [{key: value for key, value in dict(row).items() if key != "priority"} for row in rows[:limit]]

    def _load_gamma_market_targets(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT market_id, raw_snapshot_json AS raw, snapshot_at AS seen_at
            FROM market_snapshots_v2
            WHERE raw_snapshot_json IS NOT NULL
              AND raw_snapshot_json <> '{}'::jsonb
              AND COALESCE((raw_snapshot_json->>'active')::boolean, true) = true
              AND COALESCE((raw_snapshot_json->>'closed')::boolean, false) = false
              AND COALESCE((raw_snapshot_json->>'acceptingOrders')::boolean, true) = true
              AND COALESCE((raw_snapshot_json->>'enableOrderBook')::boolean, true) = true
            ORDER BY snapshot_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _load_market(self, conn: Any, market_id: str | None) -> dict[str, Any] | None:
        if not market_id:
            return None
        row = conn.execute("SELECT * FROM markets_v2 WHERE market_id=%s", (market_id,)).fetchone()
        return dict(row) if row else None

    def _latest_gamma_payload(self, conn: Any, *, market_id: str | None) -> dict[str, Any] | None:
        if not market_id:
            return None
        row = conn.execute(
            """
            SELECT market_id, raw_snapshot_json AS raw, snapshot_at AS seen_at
            FROM market_snapshots_v2
            WHERE market_id=%s AND raw_snapshot_json IS NOT NULL AND raw_snapshot_json <> '{}'::jsonb
            ORDER BY snapshot_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()
        if row:
            return dict(row)
        row = conn.execute(
            """
            SELECT market_id, raw_payload AS raw, captured_at AS seen_at
            FROM market_snapshots
            WHERE market_id=%s AND raw_payload IS NOT NULL AND raw_payload <> '{}'::jsonb
            ORDER BY captured_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()
        return dict(row) if row else None

    def _record_traces(self, conn: Any, traces: list[dict[str, Any]]) -> None:
        for trace in traces:
            conn.execute(
                """
                INSERT INTO polymarket_token_truth_traces (
                    run_id, trace_type, candidate_id, market_id, slug, question,
                    condition_id, side, stored_yes_token_id, stored_no_token_id,
                    candidate_token_id, expected_token_id, clob_attempted_token_id,
                    gamma_field, token_source, token_binding_confidence,
                    accepting_orders, closed, active, enable_order_book,
                    clob_book_attempted, clob_book_status, clob_error_summary,
                    best_bid, best_ask, spread, snapshot_id, trust_link_id,
                    classification, exact_fix_category, raw_gamma_fields_json, evidence_json
                )
                VALUES (
                    %(run_id)s, %(trace_type)s, %(candidate_id)s, %(market_id)s,
                    %(slug)s, %(question)s, %(condition_id)s, %(side)s,
                    %(stored_yes_token_id)s, %(stored_no_token_id)s,
                    %(candidate_token_id)s, %(expected_token_id)s,
                    %(clob_attempted_token_id)s, %(gamma_field)s, %(token_source)s,
                    %(token_binding_confidence)s, %(accepting_orders)s, %(closed)s,
                    %(active)s, %(enable_order_book)s, %(clob_book_attempted)s,
                    %(clob_book_status)s, %(clob_error_summary)s, %(best_bid)s,
                    %(best_ask)s, %(spread)s, %(snapshot_id)s, %(trust_link_id)s,
                    %(classification)s, %(exact_fix_category)s,
                    %(raw_gamma_fields_json)s, %(evidence_json)s
                )
                """,
                {
                    **trace,
                    "raw_gamma_fields_json": Jsonb(_json_safe(trace.get("raw_gamma_fields_json") or {})),
                    "evidence_json": Jsonb(_json_safe(trace.get("evidence_json") or {})),
                },
            )

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "polymarket_token_truth_runs"):
                return
            conn.execute(
                """
                INSERT INTO polymarket_token_truth_runs (
                    run_id, cycle_id, system_power, started_at, finished_at, status,
                    candidates_checked, gamma_markets_checked, tokens_resolved,
                    clob_checks_attempted, verified_token_books, token_not_found_count,
                    token_parse_error_count, ambiguous_token_count,
                    trusted_links_created, trusted_links_refreshed,
                    orderbook_snapshots_created, blocker_counts_json,
                    live_orders_delta, real_orders_delta, metadata_json, error_message
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(system_power)s, %(started_at)s,
                    %(finished_at)s, %(status)s, %(candidates_checked)s,
                    %(gamma_markets_checked)s, %(tokens_resolved)s,
                    %(clob_checks_attempted)s, %(verified_token_books)s,
                    %(token_not_found_count)s, %(token_parse_error_count)s,
                    %(ambiguous_token_count)s, %(trusted_links_created)s,
                    %(trusted_links_refreshed)s, %(orderbook_snapshots_created)s,
                    %(blocker_counts_json)s, %(live_orders_delta)s,
                    %(real_orders_delta)s, %(metadata_json)s, %(error_message)s
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                {
                    **payload,
                    "blocker_counts_json": Jsonb(_json_safe(payload.get("blocker_counts") or {})),
                    "metadata_json": Jsonb(_json_safe(payload.get("metadata") or {})),
                },
            )

    def _blocked_payload(self, run_id: str, cycle_id: str | None, system_power: str, started_at: datetime, reason: str) -> dict[str, Any]:
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "BLOCKED",
            "candidates_checked": 0,
            "gamma_markets_checked": 0,
            "tokens_resolved": 0,
            "clob_checks_attempted": 0,
            "verified_token_books": 0,
            "token_not_found_count": 0,
            "token_parse_error_count": 0,
            "ambiguous_token_count": 0,
            "trusted_links_created": 0,
            "trusted_links_refreshed": 0,
            "orderbook_snapshots_created": 0,
            "blocker_counts": {reason: 1},
            "live_orders_delta": 0,
            "real_orders_delta": 0,
            "metadata": {"reason": reason, "counts": self._counts()},
            "error_message": reason,
        }

    def _latest_run(self) -> dict[str, Any] | None:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "polymarket_token_truth_runs"):
                return None
            row = conn.execute("SELECT * FROM polymarket_token_truth_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _latest_blockers(self) -> dict[str, int]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "polymarket_token_truth_runs"):
                return {}
            row = conn.execute("SELECT blocker_counts_json FROM polymarket_token_truth_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return dict(row["blocker_counts_json"] or {}) if row else {}

    def _sample_traces(self, classification: str, *, limit: int) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "polymarket_token_truth_traces"):
                return []
            rows = conn.execute(
                """
                SELECT *
                FROM polymarket_token_truth_traces
                WHERE classification=%s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (classification, limit),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _sample_failures(self, *, limit: int) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "polymarket_token_truth_traces"):
                return []
            rows = conn.execute(
                """
                SELECT *
                FROM polymarket_token_truth_traces
                WHERE classification <> 'VERIFIED_BY_CLOB_BOOK'
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _top_failure_causes(self) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "polymarket_token_truth_traces"):
                return []
            rows = conn.execute(
                """
                SELECT classification, COUNT(*) AS count
                FROM polymarket_token_truth_traces
                WHERE classification <> 'VERIFIED_BY_CLOB_BOOK'
                GROUP BY classification
                ORDER BY count DESC, classification
                LIMIT 20
                """
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _counts(self) -> dict[str, int]:
        with self._factory.connect() as conn:
            return {
                "total_markets": _count_table(conn, "markets_v2"),
                "markets_with_condition_id": _count_where(conn, "markets_v2", "condition_id IS NOT NULL AND condition_id<>''"),
                "markets_with_yes_no_tokens": _count_where(conn, "markets_v2", "yes_token_id IS NOT NULL AND yes_token_id<>'' AND no_token_id IS NOT NULL AND no_token_id<>''"),
                "candidates_with_expected_token": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec JOIN markets_v2 m ON m.market_id=pec.market_id WHERE (pec.side='YES' AND m.yes_token_id IS NOT NULL AND m.yes_token_id<>'') OR (pec.side='NO' AND m.no_token_id IS NOT NULL AND m.no_token_id<>'')"),
                "candidates_verified_by_clob": _scalar(conn, "SELECT COUNT(DISTINCT candidate_id) FROM polymarket_token_truth_traces WHERE classification='VERIFIED_BY_CLOB_BOOK' AND candidate_id IS NOT NULL") if _table_exists(conn, "polymarket_token_truth_traces") else 0,
                "token_not_found_count": _count_where(conn, "polymarket_token_truth_traces", "classification IN ('TOKEN_NOT_FOUND','CLOB_TOKEN_NOT_FOUND_DESPITE_GAMMA_TOKEN')"),
                "token_parse_error_count": _count_where(conn, "polymarket_token_truth_traces", "classification IN ('TOKEN_JSON_ARRAY_PARSE_BUG','TOKEN_OUTCOME_ORDER_MISMATCH')"),
                "ambiguous_token_count": _count_where(conn, "polymarket_token_truth_traces", "classification='AMBIGUOUS_TOKEN_MAPPING'"),
                "verified_token_book_count": _count_where(conn, "polymarket_token_bindings", "verified_by_clob_book=true"),
                "live_orders": _count_table(conn, "live_orders"),
                "paper_intents": _count_table(conn, "paper_intents"),
                "paper_orders": _count_table(conn, "paper_orders"),
                "paper_fills": _count_table(conn, "paper_fills"),
                "paper_positions": _count_table(conn, "paper_positions"),
                "paper_capital_ledger": _count_table(conn, "paper_capital_ledger"),
                "orders_v2": _count_table(conn, "orders_v2"),
                "fills_v2": _count_table(conn, "fills_v2"),
                "canonical_positions": _count_table(conn, "positions"),
                "trusted_orderbook_links": _count_where(conn, "trusted_orderbook_evidence_links", "trusted=true"),
                "fresh_orderbook_snapshots": _count_where(conn, "orderbook_snapshots", "snapshot_status='OK' AND COALESCE(is_stale,false)=false AND COALESCE(snapshot_at,collected_at,created_at) >= now() - interval '180 seconds'"),
                "NO_MARKET_ID": _count_where(conn, "paper_eligibility_candidates", "market_id IS NULL OR market_id=''"),
                "NO_SIDE": _count_where(conn, "paper_eligibility_candidates", "side IS NULL OR side NOT IN ('YES','NO')"),
                "NO_YES_NO_TOKEN_MAPPING": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec LEFT JOIN markets_v2 m ON m.market_id=pec.market_id WHERE pec.market_id IS NOT NULL AND pec.market_id<>'' AND (m.yes_token_id IS NULL OR m.no_token_id IS NULL OR m.yes_token_id='' OR m.no_token_id='' OR m.yes_token_id=m.no_token_id)"),
                "MISSING_FRESH_ORDERBOOK": _candidate_code_count(conn, "MISSING_FRESH_ORDERBOOK"),
            }

    def _safety_counts(self) -> dict[str, int]:
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


class _TokenTruthHttpClient:
    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[dict[str, object], int]:
        started = time.perf_counter()
        with httpx.Client(timeout=10.0, headers={"User-Agent": "POLYBOT-polymarket-token-truth/1.0"}) as client:
            response = client.get(url, params=params)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms


def parse_gamma_token_binding(raw: dict[str, Any]) -> dict[str, Any]:
    raw = raw or {}
    outcome_labels = _parse_jsonish_list(raw.get("outcomes"))
    labels = [str(label).strip().upper() for label in outcome_labels]
    for field in ("clobTokenIds", "clob_token_ids", "tokenIds", "outcomeTokens"):
        tokens, parse_error = _parse_token_field(raw.get(field))
        if parse_error:
            return _parsed("TOKEN_JSON_ARRAY_PARSE_BUG", field, raw, error=parse_error)
        if not tokens:
            continue
        mapping = _tokens_from_labels(labels, tokens)
        if mapping:
            return _parsed("OK", field, raw, tokens=mapping, confidence=1.0)
        if labels and (len(labels) != len(tokens) or {"YES", "NO"} - set(labels)):
            return _parsed("TOKEN_OUTCOME_ORDER_MISMATCH", field, raw, tokens={}, confidence=0.0)
        if len(tokens) == 2 and not labels:
            return _parsed("OK", field, raw, tokens={"YES": str(tokens[0]), "NO": str(tokens[1])}, confidence=0.75)
        if len(tokens) == 2:
            return _parsed("OK", field, raw, tokens={"YES": str(tokens[0]), "NO": str(tokens[1])}, confidence=0.8)
        return _parsed("AMBIGUOUS_TOKEN_MAPPING", field, raw, tokens={}, confidence=0.0)
    token_objects = raw.get("tokens")
    if isinstance(token_objects, list):
        mapping: dict[str, str] = {}
        for item in token_objects:
            if not isinstance(item, dict):
                continue
            label = str(item.get("outcome") or item.get("name") or item.get("label") or "").strip().upper()
            token = item.get("token_id") or item.get("tokenId") or item.get("asset_id") or item.get("id")
            if label in {"YES", "NO"} and token:
                mapping[label] = str(token)
        if mapping.get("YES") and mapping.get("NO"):
            return _parsed("OK", "tokens", raw, tokens=mapping, confidence=1.0)
        return _parsed("AMBIGUOUS_TOKEN_MAPPING", "tokens", raw, tokens=mapping, confidence=0.0)
    return _parsed("NO_YES_NO_TOKEN_MAPPING", None, raw, tokens={}, confidence=0.0)


def _parsed(status: str, field: str | None, raw: dict[str, Any], *, tokens: dict[str, str] | None = None, confidence: float = 0.0, error: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "tokens": tokens or {},
        "condition_id": _clean(raw.get("conditionId") or raw.get("condition_id")),
        "gamma_field": field,
        "token_source": "gamma_public_market",
        "confidence": confidence,
        "raw_fields": {
            "clobTokenIds_present": raw.get("clobTokenIds") is not None,
            "outcomes_present": raw.get("outcomes") is not None,
            "tokens_present": raw.get("tokens") is not None,
            "conditionId_present": raw.get("conditionId") is not None,
            "parse_error": error,
        },
    }


def _parse_token_field(value: Any) -> tuple[list[str], str | None]:
    if value is None:
        return [], None
    if isinstance(value, list):
        return [str(item) for item in value if item], None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return [], None
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                return [], str(exc)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item], None
            return [], "JSON token field was not an array"
        return [stripped], None
    return [], None


def _parse_jsonish_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _tokens_from_labels(labels: list[str], tokens: list[str]) -> dict[str, str] | None:
    if not labels or len(labels) != len(tokens):
        return None
    mapping: dict[str, str] = {}
    for label, token in zip(labels, tokens, strict=False):
        if label in {"YES", "NO"} and token:
            mapping[label] = str(token)
    return mapping if mapping.get("YES") and mapping.get("NO") else None


def _market_closed(market: dict[str, Any] | None, raw: dict[str, Any]) -> bool:
    return bool((market or {}).get("closed")) or bool((market or {}).get("archived")) or bool(raw.get("closed")) or bool(raw.get("archived")) or raw.get("active") is False or (market is not None and (market or {}).get("active") is False)


def _accepting_orders_false(market: dict[str, Any] | None, raw: dict[str, Any]) -> bool:
    return (market is not None and (market or {}).get("accepting_orders") is False) or raw.get("acceptingOrders") is False or raw.get("accepting_orders") is False


def _orderbook_disabled(raw: dict[str, Any]) -> bool:
    return raw.get("enableOrderBook") is False or raw.get("enable_orderbook") is False


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def _candidate_code_count(conn: Any, code: str) -> int:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return 0
    return int(conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM paper_eligibility_candidates
        WHERE COALESCE(eligibility_blockers,'[]'::jsonb) @> %s::jsonb
           OR COALESCE(missing_requirements,'[]'::jsonb) @> %s::jsonb
        """,
        (Jsonb([code]), Jsonb([code])),
    ).fetchone()["count"] or 0)


def _scalar(conn: Any, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row["count"] or 0)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _valid_side(value: Any) -> str | None:
    side = str(value or "").strip().upper()
    return side if side in {"YES", "NO"} else None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


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

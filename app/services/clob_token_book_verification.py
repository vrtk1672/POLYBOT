from __future__ import annotations

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
from app.services.fresh_market_identity import SECURITY_GOVERNANCE_STATUS
from app.services.polymarket_token_truth import parse_gamma_token_binding
from app.services.source_status import DEFAULT_CLOB_BASE_URL
from app.services.system_power import SystemPowerService
from app.services.trusted_orderbook import FRESHNESS_SECONDS, MAX_SPREAD, MIN_LIQUIDITY_SCORE


class ClobTokenBookVerificationService:
    """Verify CLOB books only for fresh identities or isolated fresh Gamma seeds."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        clob_client: Any | None = None,
        gamma_client: Any | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._clob = clob_client or _BookHttpClient(user_agent="POLYBOT-clob-token-book-verification/1.0")
        self._gamma = gamma_client or _BookHttpClient(user_agent="POLYBOT-fresh-candidate-seeder/1.0")
        self._snapshotter = OrderbookSnapshotter(connection_factory=self._factory)
        self._orderbooks = OrderbookSnapshotRepository()

    def run_verification(
        self,
        *,
        cycle_id: str | None = None,
        limit: int = 50,
        seed_threshold: int = 5,
        seed_limit: int = 20,
        verify_seeds: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"clob_token_book_verification_{uuid4().hex}"
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
        seeds_created = 0

        with self._factory.connect() as conn:
            with conn.transaction():
                stale_skipped = self._count_stale_skipped(conn)
                for stale in self._load_stale_samples(conn, limit=min(limit, 20)):
                    trace = self._skip_stale_trace(run_id, stale)
                    traces.append(trace)
                    blockers["STALE_MARKET"] += 1

                candidates = self._load_fresh_verified_candidates(conn, limit=limit)
                for candidate in candidates:
                    try:
                        trace, effects = self._verify_target(conn, run_id=run_id, target=candidate, trace_type="candidate")
                        traces.append(trace)
                        blockers[trace["rejection_reason"] or "VERIFIED"] += 1
                        snapshots_created += effects["snapshot_created"]
                        trusted_created += effects["trusted_created"]
                        trusted_refreshed += effects["trusted_refreshed"]
                    except Exception as exc:
                        errors.append(_error_summary(candidate.get("candidate_id"), exc))
                        blockers["CLOB_ENDPOINT_ERROR"] += 1

                if len(candidates) < seed_threshold and seed_limit > 0:
                    seeded = self._seed_current_gamma_markets(conn, run_id=run_id, limit=seed_limit)
                    seeds_created = len(seeded)
                    for seed in seeded:
                        seed_trace = self._seed_trace(run_id, seed)
                        traces.append(seed_trace)
                        blockers["SEEDED"] += 1

                if verify_seeds:
                    seeds = self._load_seed_targets(conn, limit=seed_limit)
                    for seed in seeds:
                        try:
                            trace, effects = self._verify_target(conn, run_id=run_id, target=seed, trace_type="seed")
                            traces.append(trace)
                            blockers[trace["rejection_reason"] or "VERIFIED"] += 1
                            snapshots_created += effects["snapshot_created"]
                            trusted_created += effects["trusted_created"]
                            trusted_refreshed += effects["trusted_refreshed"]
                        except Exception as exc:
                            errors.append(_error_summary(seed.get("seed_id"), exc))
                            blockers["CLOB_ENDPOINT_ERROR"] += 1

                self._record_traces(conn, traces)
            conn.commit()

        after = self._counts()
        safety_after = self._safety_counts()
        clob_attempted = sum(1 for trace in traces if trace.get("clob_book_attempted"))
        verified = sum(1 for trace in traces if not trace.get("rejection_reason") and trace.get("clob_book_status") == "OK")
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "DEGRADED" if errors else "OK",
            "fresh_verified_candidates": len(candidates),
            "stale_market_skipped": stale_skipped,
            "fresh_seeds_created": seeds_created,
            "seed_candidates_checked": sum(1 for trace in traces if trace["trace_type"] == "seed"),
            "clob_checks_attempted": clob_attempted,
            "clob_books_verified": verified,
            "snapshots_created": snapshots_created,
            "trusted_links_created": trusted_created,
            "trusted_links_refreshed": trusted_refreshed,
            "token_not_found_count": blockers["TOKEN_NOT_FOUND"],
            "clob_no_book_count": blockers["CLOB_NO_BOOK"],
            "asset_id_mismatch_count": blockers["ASSET_ID_MISMATCH"],
            "condition_id_mismatch_count": blockers["CONDITION_ID_MISMATCH"],
            "empty_bid_ask_count": blockers["EMPTY_BIDS"] + blockers["EMPTY_ASKS"] + blockers["BID_ASK_MISSING"],
            "spread_too_wide_count": blockers["SPREAD_TOO_WIDE"],
            "liquidity_too_low_count": blockers["LIQUIDITY_TOO_LOW"],
            "blocker_counts": dict(blockers),
            "safety_counts_before": safety_before,
            "safety_counts_after": safety_after,
            "live_orders_delta": max(0, safety_after["live_orders"] - safety_before["live_orders"]),
            "real_orders_delta": max(0, safety_after["orders_v2"] - safety_before["orders_v2"]),
            "metadata": {
                "phase": "clob_token_book_verification",
                "fresh_verified_only": True,
                "seed_threshold": seed_threshold,
                "seed_limit": seed_limit,
                "verify_seeds": verify_seeds,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "no_paper_candidate_seed": True,
                "read_only_clob_book_endpoint": True,
                "before": before,
                "after": after,
            },
            "error_message": "; ".join(errors[:10]) if errors else None,
            "before": before,
            "after": after,
            "sample_traces": traces[:25],
        }
        self._record_run(payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 100) -> dict[str, Any]:
        counts = self._counts()
        latest = self._latest_run()
        return {
            "mock_data": False,
            "status": "OK",
            "fresh_verified_candidates": counts["FRESH_VERIFIED"],
            "fresh_seeds_created": counts["fresh_candidate_seeds"],
            "clob_checks_attempted": int((latest or {}).get("clob_checks_attempted") or 0),
            "clob_books_verified": int((latest or {}).get("clob_books_verified") or 0),
            "snapshots_created": int((latest or {}).get("snapshots_created") or 0),
            "trusted_links_created": int((latest or {}).get("trusted_links_created") or 0),
            "token_not_found_count": counts["TOKEN_NOT_FOUND"],
            "clob_no_book_count": counts["CLOB_NO_BOOK"],
            "asset_id_mismatch_count": counts["ASSET_ID_MISMATCH"],
            "condition_id_mismatch_count": counts["CONDITION_ID_MISMATCH"],
            "empty_bid_ask_count": counts["EMPTY_BIDS"] + counts["EMPTY_ASKS"] + counts["BID_ASK_MISSING"],
            "spread_too_wide_count": counts["SPREAD_TOO_WIDE"],
            "liquidity_too_low_count": counts["LIQUIDITY_TOO_LOW"],
            "skipped_stale_market_count": counts["STALE_MARKET"],
            "blocker_counts": self._latest_blockers() or self._live_blocker_counts(),
            "sample_successes": self._sample_traces(success=True, limit=limit),
            "sample_rejections": self._sample_traces(success=False, limit=limit),
            "latest_run": latest,
            "security_governance_status": SECURITY_GOVERNANCE_STATUS,
            "safety_counts": self._safety_counts(),
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _verify_target(self, conn: Any, *, run_id: str, target: dict[str, Any], trace_type: str) -> tuple[dict[str, Any], dict[str, int]]:
        effects = {"snapshot_created": 0, "trusted_created": 0, "trusted_refreshed": 0}
        market_id = _clean(target.get("market_id"))
        side = _valid_side(target.get("side"))
        condition_id = _clean(target.get("condition_id"))
        expected_token = _clean(target.get("expected_token_id"))
        candidate_id = _clean(target.get("candidate_id"))
        seed_id = _clean(target.get("seed_id"))
        preflight = self._preflight_target(target)
        if preflight:
            return self._trace(run_id, target, trace_type=trace_type, attempted=False, clob={"status": "NOT_ATTEMPTED"}, reason=preflight), effects

        clob = self._fetch_book(expected_token or "")
        reason = self._classify_book(clob, expected_token=expected_token, condition_id=condition_id)
        metrics: dict[str, Any] = {}
        snapshot_id = None
        trust_link_id = None
        if reason is None and clob.get("raw"):
            snapshot_id, metrics = self._persist_snapshot(conn, raw=clob["raw"], market_id=market_id or "", token_id=expected_token or "", side=side, run_id=run_id)
            reason = self._classify_snapshot(metrics)
            if reason is None and snapshot_id:
                link_candidate_id = candidate_id if trace_type == "candidate" else seed_id
                if link_candidate_id:
                    created = self._upsert_trusted_link(
                        conn,
                        candidate_id=link_candidate_id,
                        market_id=market_id,
                        side=side,
                        expected_token=expected_token or "",
                        snapshot_id=snapshot_id,
                        snapshot_ref=metrics.get("snapshot_ref"),
                        metrics=metrics,
                        source=trace_type,
                    )
                    trust_link_id = f"trusted_orderbook_{link_candidate_id}"
                    effects["trusted_created"] = int(bool(created))
                    effects["trusted_refreshed"] = int(not created)
                effects["snapshot_created"] = 1
        if trace_type == "seed" and seed_id:
            self._update_seed_after_book(conn, seed_id=seed_id, status="BOOK_VERIFIED" if reason is None else "BOOK_REJECTED", snapshot_id=snapshot_id, trusted_link_id=trust_link_id, reason=reason)
        return self._trace(run_id, target, trace_type=trace_type, attempted=True, clob=clob, reason=reason, metrics=metrics, snapshot_id=snapshot_id, trust_link_id=trust_link_id), effects

    def _preflight_target(self, target: dict[str, Any]) -> str | None:
        if target.get("identity_status") not in {None, "FRESH_VERIFIED", "FRESH_SEED"}:
            return str(target.get("identity_status"))
        if not _clean(target.get("market_id")):
            return "NO_MARKET_ID"
        if not _clean(target.get("condition_id")):
            return "NO_CONDITION_ID"
        if _valid_side(target.get("side")) not in {"YES", "NO"}:
            return "NO_SIDE"
        if not _clean(target.get("expected_token_id")):
            return "EXPECTED_TOKEN_MISSING"
        if bool(target.get("closed")) or bool(target.get("archived")) or target.get("active") is False:
            return "MARKET_CLOSED"
        if target.get("accepting_orders") is False:
            return "ACCEPTING_ORDERS_FALSE"
        return None

    def _fetch_book(self, token_id: str) -> dict[str, Any]:
        endpoint = f"{(os.getenv('POLYMARKET_CLOB_HOST') or DEFAULT_CLOB_BASE_URL).rstrip('/')}/book"
        started = time.perf_counter()
        try:
            raw, latency_ms = self._clob.get_json(endpoint, params={"token_id": token_id})
        except httpx.HTTPStatusError as exc:
            body = redact_secrets(exc.response.text or "")[:240]
            status = "TOKEN_NOT_FOUND" if exc.response.status_code == 404 else "CLOB_ENDPOINT_ERROR"
            return {"status": status, "latency_ms": int((time.perf_counter() - started) * 1000), "error_summary": body}
        except Exception as exc:
            text = redact_secrets(str(exc))[:240]
            status = "TOKEN_NOT_FOUND" if "token" in text.lower() and "not" in text.lower() else "CLOB_ENDPOINT_ERROR"
            return {"status": status, "latency_ms": int((time.perf_counter() - started) * 1000), "error_summary": text}
        latency = latency_ms if latency_ms is not None else int((time.perf_counter() - started) * 1000)
        if not isinstance(raw, dict) or not raw:
            return {"status": "CLOB_NO_BOOK", "latency_ms": latency}
        return {"status": "OK", "latency_ms": latency, "raw": raw, "asset_id": raw.get("asset_id"), "market": raw.get("market")}

    def _classify_book(self, clob: dict[str, Any], *, expected_token: str | None, condition_id: str | None) -> str | None:
        status = str(clob.get("status") or "UNKNOWN")
        if status != "OK":
            return status
        raw = clob.get("raw") or {}
        if _clean(raw.get("asset_id") or clob.get("asset_id")) != expected_token:
            return "ASSET_ID_MISMATCH"
        if condition_id and _clean(raw.get("market") or clob.get("market")) != condition_id:
            return "CONDITION_ID_MISMATCH"
        bids = raw.get("bids") or raw.get("buy") or []
        asks = raw.get("asks") or raw.get("sell") or []
        if not bids:
            return "EMPTY_BIDS"
        if not asks:
            return "EMPTY_ASKS"
        return None

    def _classify_snapshot(self, metrics: dict[str, Any]) -> str | None:
        if str(metrics.get("snapshot_status") or "") != "OK":
            return "BID_ASK_MISSING"
        spread = _float_or_none(metrics.get("spread"))
        liquidity = _float_or_none(metrics.get("liquidity_score"))
        if spread is None:
            return "BID_ASK_MISSING"
        if spread > MAX_SPREAD:
            return "SPREAD_TOO_WIDE"
        if liquidity is not None and liquidity < MIN_LIQUIDITY_SCORE:
            return "LIQUIDITY_TOO_LOW"
        return None

    def _persist_snapshot(self, conn: Any, *, raw: dict[str, Any], market_id: str, token_id: str, side: str | None, run_id: str) -> tuple[int | None, dict[str, Any]]:
        snapshot = self._snapshotter.normalize_orderbook(
            raw,
            market_id=market_id,
            token_id=token_id,
            side=side,
            source="clob_token_book_verification",
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
        snapshot_id: int,
        snapshot_ref: str | None,
        metrics: dict[str, Any],
        source: str,
    ) -> bool:
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
            "spread": metrics.get("spread"),
            "liquidity_score": metrics.get("liquidity_score"),
            "age_seconds": 0,
            "freshness_threshold_seconds": FRESHNESS_SECONDS,
            "evidence_json": Jsonb({
                "source": "clob_token_book_verification",
                "target_source": source,
                "validated_asset_id": True,
                "validated_condition_id": True,
                "no_paper_candidate_seed": source == "seed",
            }),
        }
        conn.execute(
            """
            INSERT INTO trusted_orderbook_evidence_links (
                link_id, candidate_id, market_id, side, expected_token_id,
                orderbook_snapshot_id, orderbook_snapshot_ref, orderbook_token_id,
                trusted, trust_status, trust_reason, best_bid, best_ask, mid_price,
                spread, liquidity_score, age_seconds, freshness_threshold_seconds,
                evidence_json, created_at, updated_at
            )
            VALUES (
                %(link_id)s, %(candidate_id)s, %(market_id)s, %(side)s, %(expected_token_id)s,
                %(orderbook_snapshot_id)s, %(orderbook_snapshot_ref)s, %(orderbook_token_id)s,
                %(trusted)s, %(trust_status)s, %(trust_reason)s, %(best_bid)s, %(best_ask)s,
                %(mid_price)s, %(spread)s, %(liquidity_score)s, %(age_seconds)s,
                %(freshness_threshold_seconds)s, %(evidence_json)s, now(), now()
            )
            ON CONFLICT (candidate_id) DO UPDATE SET
                market_id=EXCLUDED.market_id,
                side=EXCLUDED.side,
                expected_token_id=EXCLUDED.expected_token_id,
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

    def _seed_current_gamma_markets(self, conn: Any, *, run_id: str, limit: int) -> list[dict[str, Any]]:
        markets = self._fetch_current_gamma_markets(limit=max(limit, 1))
        seeded: list[dict[str, Any]] = []
        for market in markets:
            if len(seeded) >= limit:
                break
            parsed = parse_gamma_token_binding(market)
            tokens = parsed.get("tokens") or {}
            market_id = _clean(market.get("id"))
            condition_id = _clean(parsed.get("condition_id"))
            if parsed.get("status") != "OK" or not market_id or not condition_id or not tokens.get("YES") or not tokens.get("NO"):
                continue
            if _market_closed(market) or _accepting_orders_false(market):
                continue
            self._upsert_market_truth(conn, market=market, parsed=parsed)
            for side in ("YES", "NO"):
                if len(seeded) >= limit:
                    break
                seed = {
                    "seed_id": f"fresh_seed_{market_id}_{side}",
                    "market_id": market_id,
                    "condition_id": condition_id,
                    "slug": _clean(market.get("slug")),
                    "question": _clean(market.get("question") or market.get("title")),
                    "side": side,
                    "expected_token_id": tokens[side],
                    "yes_token_id": tokens["YES"],
                    "no_token_id": tokens["NO"],
                    "source": "current_gamma",
                    "status": "SEEDED",
                    "metadata": {
                        "run_id": run_id,
                        "gamma_field": parsed.get("gamma_field"),
                        "token_source": parsed.get("token_source"),
                        "confidence": parsed.get("confidence"),
                    },
                }
                self._upsert_seed(conn, seed)
                seeded.append(seed)
        return seeded

    def _fetch_current_gamma_markets(self, *, limit: int) -> list[dict[str, Any]]:
        endpoint = f"{(os.getenv('GAMMA_API_BASE_URL') or 'https://gamma-api.polymarket.com').rstrip('/')}/events"
        raw, _ = self._gamma.get_json(endpoint, params={"active": "true", "closed": "false", "limit": max(20, limit)})
        events = raw if isinstance(raw, list) else raw.get("data", []) if isinstance(raw, dict) else []
        markets: list[dict[str, Any]] = []
        for item in events:
            if not isinstance(item, dict):
                continue
            event_markets = item.get("markets")
            if isinstance(event_markets, list):
                markets.extend([market for market in event_markets if isinstance(market, dict)])
            elif item.get("conditionId"):
                markets.append(item)
        return markets

    def _upsert_market_truth(self, conn: Any, *, market: dict[str, Any], parsed: dict[str, Any]) -> None:
        tokens = parsed.get("tokens") or {}
        conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, condition_id, question, slug, yes_token_id, no_token_id,
                outcome_tokens_json, accepting_orders, closed, archived, active,
                raw_market_json, metadata_json, resolution_source, source,
                first_seen_at, last_seen_at
            )
            VALUES (
                %(market_id)s, %(condition_id)s, %(question)s, %(slug)s,
                %(yes_token_id)s, %(no_token_id)s, %(outcome_tokens_json)s,
                %(accepting_orders)s, %(closed)s, %(archived)s, %(active)s,
                %(raw_market_json)s, %(metadata_json)s, 'clob_token_book_verification_seed',
                'polymarket_gamma', now(), now()
            )
            ON CONFLICT (market_id) DO UPDATE SET
                condition_id=COALESCE(EXCLUDED.condition_id, markets_v2.condition_id),
                question=COALESCE(EXCLUDED.question, markets_v2.question),
                slug=COALESCE(EXCLUDED.slug, markets_v2.slug),
                yes_token_id=EXCLUDED.yes_token_id,
                no_token_id=EXCLUDED.no_token_id,
                outcome_tokens_json=EXCLUDED.outcome_tokens_json,
                accepting_orders=EXCLUDED.accepting_orders,
                closed=EXCLUDED.closed,
                archived=EXCLUDED.archived,
                active=EXCLUDED.active,
                raw_market_json=EXCLUDED.raw_market_json,
                metadata_json=COALESCE(markets_v2.metadata_json, '{}'::jsonb) || EXCLUDED.metadata_json,
                last_seen_at=now(),
                updated_at=now()
            """,
            {
                "market_id": _clean(market.get("id")),
                "condition_id": _clean(parsed.get("condition_id")),
                "question": _clean(market.get("question") or market.get("title")),
                "slug": _clean(market.get("slug")),
                "yes_token_id": _clean(tokens.get("YES")),
                "no_token_id": _clean(tokens.get("NO")),
                "outcome_tokens_json": Jsonb(tokens),
                "accepting_orders": _accepting_orders(market),
                "closed": bool(market.get("closed", False)),
                "archived": bool(market.get("archived", False)),
                "active": _active(market),
                "raw_market_json": Jsonb(market),
                "metadata_json": Jsonb({
                    "fresh_candidate_seed_source": True,
                    "gamma_field": parsed.get("gamma_field"),
                    "token_source": parsed.get("token_source"),
                    "verified_at": datetime.now(UTC).isoformat(),
                }),
            },
        )

    def _upsert_seed(self, conn: Any, seed: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO fresh_candidate_seeds (
                seed_id, market_id, condition_id, slug, question, side,
                expected_token_id, yes_token_id, no_token_id, source, status,
                metadata_json, updated_at
            )
            VALUES (
                %(seed_id)s, %(market_id)s, %(condition_id)s, %(slug)s, %(question)s,
                %(side)s, %(expected_token_id)s, %(yes_token_id)s, %(no_token_id)s,
                %(source)s, %(status)s, %(metadata_json)s, now()
            )
            ON CONFLICT (seed_id) DO UPDATE SET
                condition_id=EXCLUDED.condition_id,
                slug=EXCLUDED.slug,
                question=EXCLUDED.question,
                expected_token_id=EXCLUDED.expected_token_id,
                yes_token_id=EXCLUDED.yes_token_id,
                no_token_id=EXCLUDED.no_token_id,
                source=EXCLUDED.source,
                status='SEEDED',
                rejection_reason=NULL,
                metadata_json=COALESCE(fresh_candidate_seeds.metadata_json,'{}'::jsonb) || EXCLUDED.metadata_json,
                updated_at=now()
            """,
            {**seed, "metadata_json": Jsonb(_json_safe(seed.get("metadata") or {}))},
        )

    def _update_seed_after_book(
        self,
        conn: Any,
        *,
        seed_id: str,
        status: str,
        snapshot_id: int | None,
        trusted_link_id: str | None,
        reason: str | None,
    ) -> None:
        conn.execute(
            """
            UPDATE fresh_candidate_seeds
            SET status=%s,
                orderbook_snapshot_id=%s,
                trusted_link_id=%s,
                rejection_reason=%s,
                updated_at=now()
            WHERE seed_id=%s
            """,
            (status, snapshot_id, trusted_link_id, reason, seed_id),
        )

    def _load_fresh_verified_candidates(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT
                pec.eligibility_id AS candidate_id,
                pec.market_id,
                pec.side,
                pec.expected_token_id,
                pec.identity_status,
                m.condition_id,
                m.slug,
                m.question,
                COALESCE(m.accepting_orders, true) AS accepting_orders,
                COALESCE(m.closed, false) AS closed,
                COALESCE(m.archived, false) AS archived,
                COALESCE(m.active, true) AS active
            FROM paper_eligibility_candidates pec
            JOIN markets_v2 m ON m.market_id = pec.market_id
            WHERE pec.identity_status = 'FRESH_VERIFIED'
              AND pec.side IN ('YES','NO')
              AND pec.expected_token_id IS NOT NULL
              AND pec.expected_token_id <> ''
              AND m.condition_id IS NOT NULL
              AND m.condition_id <> ''
              AND COALESCE(m.closed, false) = false
              AND COALESCE(m.archived, false) = false
              AND COALESCE(m.active, true) = true
              AND COALESCE(m.accepting_orders, true) = true
            ORDER BY pec.identity_verified_at DESC NULLS LAST, pec.updated_at DESC NULLS LAST, pec.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _load_seed_targets(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT
                seed_id,
                market_id,
                condition_id,
                slug,
                question,
                side,
                expected_token_id,
                'FRESH_SEED' AS identity_status,
                true AS accepting_orders,
                false AS closed,
                false AS archived,
                true AS active
            FROM fresh_candidate_seeds
            WHERE status IN ('SEEDED','BOOK_REJECTED')
              AND expected_token_id IS NOT NULL
              AND expected_token_id <> ''
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _count_stale_skipped(self, conn: Any) -> int:
        return _count_where(conn, "paper_eligibility_candidates", "identity_status='STALE_MARKET'")

    def _load_stale_samples(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT eligibility_id AS candidate_id, market_id, side, expected_token_id,
                   identity_status, identity_blocker_reason AS reason
            FROM paper_eligibility_candidates
            WHERE identity_status='STALE_MARKET'
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _skip_stale_trace(self, run_id: str, stale: dict[str, Any]) -> dict[str, Any]:
        return self._trace(
            run_id,
            stale,
            trace_type="skipped_candidate",
            attempted=False,
            clob={"status": "NOT_ATTEMPTED"},
            reason="STALE_MARKET",
        )

    def _seed_trace(self, run_id: str, seed: dict[str, Any]) -> dict[str, Any]:
        return self._trace(
            run_id,
            {**seed, "identity_status": "FRESH_SEED"},
            trace_type="fresh_seed",
            attempted=False,
            clob={"status": "NOT_ATTEMPTED"},
            reason=None,
        )

    def _trace(
        self,
        run_id: str,
        target: dict[str, Any],
        *,
        trace_type: str,
        attempted: bool,
        clob: dict[str, Any],
        reason: str | None,
        metrics: dict[str, Any] | None = None,
        snapshot_id: int | None = None,
        trust_link_id: str | None = None,
    ) -> dict[str, Any]:
        metrics = metrics or {}
        raw = clob.get("raw") or {}
        return {
            "run_id": run_id,
            "trace_type": trace_type,
            "candidate_id": _clean(target.get("candidate_id")),
            "seed_id": _clean(target.get("seed_id")),
            "market_id": _clean(target.get("market_id")),
            "slug": _clean(target.get("slug")),
            "question": _clean(target.get("question")),
            "condition_id": _clean(target.get("condition_id")),
            "side": _valid_side(target.get("side")),
            "identity_status": _clean(target.get("identity_status")),
            "expected_token_id": _clean(target.get("expected_token_id")),
            "clob_book_attempted": attempted,
            "clob_book_status": str(clob.get("status") or "NOT_ATTEMPTED"),
            "rejection_reason": reason,
            "asset_id": _clean(raw.get("asset_id") or clob.get("asset_id")),
            "response_market": _clean(raw.get("market") or clob.get("market")),
            "best_bid": metrics.get("best_bid"),
            "best_ask": metrics.get("best_ask"),
            "spread": metrics.get("spread"),
            "liquidity_score": metrics.get("liquidity_score"),
            "snapshot_id": snapshot_id,
            "trust_link_id": trust_link_id,
            "source_refs_json": {
                "source": "clob_token_book_verification",
                "target": trace_type,
                "read_only_clob_book": True,
            },
            "evidence_json": {
                "validated_asset_id": reason is None and attempted,
                "validated_condition_id": reason is None and attempted,
                "error_summary": redact_secrets(clob.get("error_summary") or "")[:240] or None,
            },
        }

    def _record_traces(self, conn: Any, traces: list[dict[str, Any]]) -> None:
        for trace in traces:
            conn.execute(
                """
                INSERT INTO clob_token_book_verification_traces (
                    run_id, trace_type, candidate_id, seed_id, market_id, slug, question,
                    condition_id, side, identity_status, expected_token_id,
                    clob_book_attempted, clob_book_status, rejection_reason,
                    asset_id, response_market, best_bid, best_ask, spread,
                    liquidity_score, snapshot_id, trust_link_id,
                    source_refs_json, evidence_json
                )
                VALUES (
                    %(run_id)s, %(trace_type)s, %(candidate_id)s, %(seed_id)s,
                    %(market_id)s, %(slug)s, %(question)s, %(condition_id)s,
                    %(side)s, %(identity_status)s, %(expected_token_id)s,
                    %(clob_book_attempted)s, %(clob_book_status)s,
                    %(rejection_reason)s, %(asset_id)s, %(response_market)s,
                    %(best_bid)s, %(best_ask)s, %(spread)s, %(liquidity_score)s,
                    %(snapshot_id)s, %(trust_link_id)s, %(source_refs_json)s,
                    %(evidence_json)s
                )
                """,
                {
                    **trace,
                    "source_refs_json": Jsonb(_json_safe(trace.get("source_refs_json") or {})),
                    "evidence_json": Jsonb(_json_safe(trace.get("evidence_json") or {})),
                },
            )

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "clob_token_book_verification_runs"):
                return
            conn.execute(
                """
                INSERT INTO clob_token_book_verification_runs (
                    run_id, cycle_id, system_power, started_at, finished_at, status,
                    fresh_verified_candidates, stale_market_skipped,
                    fresh_seeds_created, seed_candidates_checked,
                    clob_checks_attempted, clob_books_verified, snapshots_created,
                    trusted_links_created, trusted_links_refreshed,
                    token_not_found_count, clob_no_book_count,
                    asset_id_mismatch_count, condition_id_mismatch_count,
                    empty_bid_ask_count, spread_too_wide_count, liquidity_too_low_count,
                    blocker_counts_json, safety_counts_before_json, safety_counts_after_json,
                    live_orders_delta, real_orders_delta, metadata_json, error_message
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(system_power)s, %(started_at)s,
                    %(finished_at)s, %(status)s, %(fresh_verified_candidates)s,
                    %(stale_market_skipped)s, %(fresh_seeds_created)s,
                    %(seed_candidates_checked)s, %(clob_checks_attempted)s,
                    %(clob_books_verified)s, %(snapshots_created)s,
                    %(trusted_links_created)s, %(trusted_links_refreshed)s,
                    %(token_not_found_count)s, %(clob_no_book_count)s,
                    %(asset_id_mismatch_count)s, %(condition_id_mismatch_count)s,
                    %(empty_bid_ask_count)s, %(spread_too_wide_count)s,
                    %(liquidity_too_low_count)s, %(blocker_counts_json)s,
                    %(safety_counts_before_json)s, %(safety_counts_after_json)s,
                    %(live_orders_delta)s, %(real_orders_delta)s,
                    %(metadata_json)s, %(error_message)s
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                {
                    **payload,
                    "blocker_counts_json": Jsonb(_json_safe(payload.get("blocker_counts") or {})),
                    "safety_counts_before_json": Jsonb(_json_safe(payload.get("safety_counts_before") or {})),
                    "safety_counts_after_json": Jsonb(_json_safe(payload.get("safety_counts_after") or {})),
                    "metadata_json": Jsonb(_json_safe(payload.get("metadata") or {})),
                },
            )

    def _blocked_payload(self, run_id: str, cycle_id: str | None, system_power: str, started_at: datetime, reason: str) -> dict[str, Any]:
        counts = self._counts()
        safety = self._safety_counts()
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "BLOCKED",
            "fresh_verified_candidates": 0,
            "stale_market_skipped": counts["STALE_MARKET"],
            "fresh_seeds_created": 0,
            "seed_candidates_checked": 0,
            "clob_checks_attempted": 0,
            "clob_books_verified": 0,
            "snapshots_created": 0,
            "trusted_links_created": 0,
            "trusted_links_refreshed": 0,
            "token_not_found_count": 0,
            "clob_no_book_count": 0,
            "asset_id_mismatch_count": 0,
            "condition_id_mismatch_count": 0,
            "empty_bid_ask_count": 0,
            "spread_too_wide_count": 0,
            "liquidity_too_low_count": 0,
            "blocker_counts": {reason: 1},
            "safety_counts_before": safety,
            "safety_counts_after": safety,
            "live_orders_delta": 0,
            "real_orders_delta": 0,
            "metadata": {"reason": reason, "counts": counts, "security_governance_status": SECURITY_GOVERNANCE_STATUS},
            "error_message": reason,
            "before": counts,
            "after": counts,
            "sample_traces": [],
        }

    def _latest_run(self) -> dict[str, Any] | None:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "clob_token_book_verification_runs"):
                return None
            row = conn.execute("SELECT * FROM clob_token_book_verification_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _latest_blockers(self) -> dict[str, int]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "clob_token_book_verification_runs"):
                return {}
            row = conn.execute("SELECT blocker_counts_json FROM clob_token_book_verification_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return dict(row["blocker_counts_json"] or {}) if row else {}

    def _sample_traces(self, *, success: bool, limit: int) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "clob_token_book_verification_traces"):
                return []
            clause = "rejection_reason IS NULL AND clob_book_status='OK'" if success else "rejection_reason IS NOT NULL"
            rows = conn.execute(
                f"""
                SELECT *
                FROM clob_token_book_verification_traces
                WHERE {clause}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _counts(self) -> dict[str, int]:
        with self._factory.connect() as conn:
            return {
                "FRESH_VERIFIED": _count_where(conn, "paper_eligibility_candidates", "identity_status='FRESH_VERIFIED'"),
                "STALE_MARKET": _count_where(conn, "paper_eligibility_candidates", "identity_status='STALE_MARKET'"),
                "fresh_candidate_seeds": _count_table(conn, "fresh_candidate_seeds"),
                "clob_checks_attempted": _count_where(conn, "clob_token_book_verification_traces", "clob_book_attempted=true"),
                "clob_books_verified": _count_where(conn, "clob_token_book_verification_traces", "rejection_reason IS NULL AND clob_book_status='OK'"),
                "snapshots_created": _count_where(conn, "orderbook_snapshots", "source='clob_token_book_verification'"),
                "trusted_links_created": _count_where(conn, "trusted_orderbook_evidence_links", "trusted=true AND evidence_json->>'source'='clob_token_book_verification'"),
                "TOKEN_NOT_FOUND": _count_where(conn, "clob_token_book_verification_traces", "rejection_reason='TOKEN_NOT_FOUND'"),
                "CLOB_NO_BOOK": _count_where(conn, "clob_token_book_verification_traces", "rejection_reason='CLOB_NO_BOOK'"),
                "ASSET_ID_MISMATCH": _count_where(conn, "clob_token_book_verification_traces", "rejection_reason='ASSET_ID_MISMATCH'"),
                "CONDITION_ID_MISMATCH": _count_where(conn, "clob_token_book_verification_traces", "rejection_reason='CONDITION_ID_MISMATCH'"),
                "EMPTY_BIDS": _count_where(conn, "clob_token_book_verification_traces", "rejection_reason='EMPTY_BIDS'"),
                "EMPTY_ASKS": _count_where(conn, "clob_token_book_verification_traces", "rejection_reason='EMPTY_ASKS'"),
                "BID_ASK_MISSING": _count_where(conn, "clob_token_book_verification_traces", "rejection_reason='BID_ASK_MISSING'"),
                "SPREAD_TOO_WIDE": _count_where(conn, "clob_token_book_verification_traces", "rejection_reason='SPREAD_TOO_WIDE'"),
                "LIQUIDITY_TOO_LOW": _count_where(conn, "clob_token_book_verification_traces", "rejection_reason='LIQUIDITY_TOO_LOW'"),
                "MISSING_FRESH_ORDERBOOK": _candidate_code_count(conn, "MISSING_FRESH_ORDERBOOK"),
                **self._safety_counts(conn),
            }

    def _live_blocker_counts(self) -> dict[str, int]:
        counts = self._counts()
        return {key: counts[key] for key in ("STALE_MARKET", "TOKEN_NOT_FOUND", "CLOB_NO_BOOK", "ASSET_ID_MISMATCH", "CONDITION_ID_MISMATCH", "EMPTY_BIDS", "EMPTY_ASKS", "SPREAD_TOO_WIDE", "LIQUIDITY_TOO_LOW")}

    def _safety_counts(self, conn: Any | None = None) -> dict[str, int]:
        if conn is not None:
            return _safety_counts(conn)
        with self._factory.connect() as local:
            return _safety_counts(local)


class _BookHttpClient:
    def __init__(self, *, user_agent: str) -> None:
        self._user_agent = user_agent

    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[Any, int]:
        started = time.perf_counter()
        with httpx.Client(timeout=12.0, headers={"User-Agent": self._user_agent}) as client:
            response = client.get(url, params=params)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms


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


def _safety_counts(conn: Any) -> dict[str, int]:
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


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _valid_side(value: Any) -> str | None:
    side = str(value or "").strip().upper()
    return side if side in {"YES", "NO"} else None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _active(raw: dict[str, Any]) -> bool | None:
    value = raw.get("active")
    return value if isinstance(value, bool) else None if value is None else str(value).strip().lower() == "true"


def _accepting_orders(raw: dict[str, Any]) -> bool | None:
    value = raw.get("acceptingOrders", raw.get("accepting_orders"))
    return value if isinstance(value, bool) else None if value is None else str(value).strip().lower() == "true"


def _accepting_orders_false(raw: dict[str, Any]) -> bool:
    return _accepting_orders(raw) is False


def _market_closed(raw: dict[str, Any]) -> bool:
    return bool(raw.get("closed")) or bool(raw.get("archived")) or raw.get("active") is False


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


def _error_summary(identifier: Any, exc: Exception) -> str:
    return f"{identifier or 'unknown'}:{type(exc).__name__}:{redact_secrets(str(exc))[:160]}"

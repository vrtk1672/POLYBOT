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

from app.db.connection import DatabaseConnectionFactory
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.security.redaction import redact_secrets
from app.services.polymarket_token_truth import parse_gamma_token_binding
from app.services.system_power import SystemPowerService


SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"
TRUSTED_LINK_CONFIDENCE = 0.8


class FreshMarketIdentityGateService:
    """Verify current Polymarket identity before candidates can move toward Paper."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        gamma_client: Any | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._gamma = gamma_client or _GammaMarketIdentityClient()
        self._gamma_cache: dict[str, dict[str, Any]] = {}

    def run_recovery(
        self,
        *,
        cycle_id: str | None = None,
        limit: int = 100,
        dry_run: bool = True,
        include_stale: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"fresh_market_identity_{uuid4().hex}"
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        if not dry_run:
            if system_power != "ON" or not bool(power.get("runtime_work_allowed")):
                payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, "SYSTEM_POWER_OFF", dry_run=dry_run)
                self._record_run(payload)
                return _json_safe(payload)
            if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
                payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, "STATE_GOVERNOR_BLOCKED_INTELLIGENCE", dry_run=dry_run)
                self._record_run(payload)
                return _json_safe(payload)

        safety_before = self._safety_counts()
        before = self._counts()
        traces: list[dict[str, Any]] = []
        blockers: Counter[str] = Counter()
        errors: list[str] = []

        with self._factory.connect() as conn:
            candidates = self._load_candidates(conn, limit=limit, include_stale=include_stale)
            if dry_run:
                for candidate in candidates:
                    try:
                        trace = self._resolve_candidate(conn, candidate, run_id=run_id, apply_changes=False)
                        traces.append(trace)
                        blockers[trace["identity_status"]] += 1
                    except Exception as exc:
                        errors.append(_error_summary(candidate, exc))
                        blockers["UNRECOVERABLE"] += 1
            else:
                with conn.transaction():
                    for candidate in candidates:
                        try:
                            trace = self._resolve_candidate(conn, candidate, run_id=run_id, apply_changes=True)
                            traces.append(trace)
                            blockers[trace["identity_status"]] += 1
                        except Exception as exc:
                            errors.append(_error_summary(candidate, exc))
                            blockers["UNRECOVERABLE"] += 1
                    self._record_traces(conn, traces)
                conn.commit()

        safety_after = self._safety_counts()
        after = self._counts()
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "system_power": system_power,
            "status": "DEGRADED" if errors else "OK",
            "dry_run": dry_run,
            "candidates_checked": len(traces),
            "fresh_verified_count": blockers["FRESH_VERIFIED"],
            "stale_market_count": blockers["STALE_MARKET"],
            "missing_market_id_count": blockers["MISSING_MARKET_ID"],
            "missing_condition_id_count": blockers["MISSING_CONDITION_ID"],
            "missing_side_count": blockers["MISSING_SIDE"],
            "missing_token_mapping_count": blockers["MISSING_TOKEN_MAPPING"],
            "accepting_orders_false_count": blockers["ACCEPTING_ORDERS_FALSE"],
            "market_closed_count": blockers["CLOSED_MARKET"],
            "ambiguous_count": blockers["AMBIGUOUS_MATCH"],
            "unrecoverable_count": blockers["UNRECOVERABLE"],
            "blocker_counts": dict(blockers),
            "safety_counts_before": safety_before,
            "safety_counts_after": safety_after,
            "live_orders_delta": max(0, safety_after["live_orders"] - safety_before["live_orders"]),
            "real_orders_delta": max(0, safety_after["orders_v2"] - safety_before["orders_v2"]),
            "metadata": {
                "phase": "fresh_market_identity_gate",
                "include_stale": include_stale,
                "current_gamma_required": True,
                "clob_book_verification": False,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "before": before,
                "after": after,
            },
            "error_message": "; ".join(errors[:10]) if errors else None,
            "before": before,
            "after": after,
            "sample_traces": traces[:20],
        }
        if not dry_run:
            self._record_run(payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 100) -> dict[str, Any]:
        counts = self._counts()
        latest = self._latest_run()
        return {
            "mock_data": False,
            "status": "OK",
            **counts,
            "candidates_checked_latest": int((latest or {}).get("candidates_checked") or 0),
            "fresh_verified_count": int((latest or {}).get("fresh_verified_count") or 0),
            "stale_market_count": int((latest or {}).get("stale_market_count") or 0),
            "missing_market_id_count": int((latest or {}).get("missing_market_id_count") or counts.get("candidates_missing_market_id", 0)),
            "missing_condition_id_count": int((latest or {}).get("missing_condition_id_count") or 0),
            "missing_side_count": int((latest or {}).get("missing_side_count") or counts.get("candidates_missing_side", 0)),
            "missing_token_mapping_count": int((latest or {}).get("missing_token_mapping_count") or 0),
            "accepting_orders_false_count": int((latest or {}).get("accepting_orders_false_count") or 0),
            "market_closed_count": int((latest or {}).get("market_closed_count") or 0),
            "ambiguous_count": int((latest or {}).get("ambiguous_count") or 0),
            "unrecoverable_count": int((latest or {}).get("unrecoverable_count") or 0),
            "blocker_counts": self._latest_blockers() or self._live_blocker_counts(),
            "top_stale_markets": self._top_stale_markets(),
            "sample_traces": self._latest_traces(limit=limit),
            "latest_run": latest,
            "security_governance_status": SECURITY_GOVERNANCE_STATUS,
            "safety_counts": self._safety_counts(),
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _resolve_candidate(self, conn: Any, candidate: dict[str, Any], *, run_id: str, apply_changes: bool) -> dict[str, Any]:
        candidate_id = str(candidate["eligibility_id"])
        signal_ids = _json_list(candidate.get("signal_ids"))
        source_signal_id = signal_ids[0] if signal_ids else None
        link_options = self._link_options(conn, signal_ids=signal_ids)
        market_id = _clean(candidate.get("market_id"))
        side = _valid_side(candidate.get("side"))
        identity_source = "existing DB" if market_id else "unknown"
        source_refs: dict[str, Any] = {"signal_ids": signal_ids}

        if not market_id:
            linked_market = _single_value([_clean(row.get("market_id")) for row in link_options])
            if linked_market:
                market_id = linked_market
                identity_source = "signal_market_link"
                source_refs["signal_market_link_ids"] = [row.get("id") for row in link_options if _clean(row.get("market_id")) == market_id]
            elif link_options:
                return self._trace(
                    run_id=run_id,
                    candidate_id=candidate_id,
                    source_signal_id=source_signal_id,
                    market_id=None,
                    side=side,
                    identity_source="signal_market_link",
                    identity_status="AMBIGUOUS_MATCH",
                    reason="Multiple deterministic signal market links exist; market_id was not written.",
                    source_refs=source_refs,
                    gamma={"status": "NOT_ATTEMPTED"},
                )

        if not side:
            linked_side = _single_value([_valid_side(row.get("matched_side") or (row.get("link_evidence_json") or {}).get("matched_side")) for row in link_options])
            if linked_side:
                side = linked_side
                source_refs["side_source"] = "signal_market_link"

        if not market_id:
            trace = self._trace(
                run_id=run_id,
                candidate_id=candidate_id,
                source_signal_id=source_signal_id,
                market_id=None,
                side=side,
                identity_source=identity_source,
                identity_status="MISSING_MARKET_ID",
                reason="No deterministic market_id exists for candidate.",
                source_refs=source_refs,
                gamma={"status": "NOT_ATTEMPTED"},
            )
            if apply_changes:
                self._annotate_candidate(conn, candidate_id=candidate_id, trace=trace)
            return trace

        gamma = self._lookup_current_gamma(market_id)
        source_refs["gamma_lookup"] = {"status": gamma["status"], "latency_ms": gamma.get("latency_ms")}
        if gamma["status"] == "NOT_FOUND":
            trace = self._trace(
                run_id=run_id,
                candidate_id=candidate_id,
                source_signal_id=source_signal_id,
                market_id=market_id,
                side=side,
                identity_source=identity_source,
                identity_status="STALE_MARKET",
                reason=f"Current Gamma did not return market {market_id}.",
                source_refs=source_refs,
                gamma=gamma,
            )
            if apply_changes:
                self._annotate_candidate(conn, candidate_id=candidate_id, trace=trace)
            return trace
        if gamma["status"] == "AMBIGUOUS":
            trace = self._trace(
                run_id=run_id,
                candidate_id=candidate_id,
                source_signal_id=source_signal_id,
                market_id=market_id,
                side=side,
                identity_source=identity_source,
                identity_status="AMBIGUOUS_MATCH",
                reason=f"Current Gamma returned multiple matches for market {market_id}; identity not written.",
                source_refs=source_refs,
                gamma=gamma,
            )
            if apply_changes:
                self._annotate_candidate(conn, candidate_id=candidate_id, trace=trace)
            return trace
        if gamma["status"] == "ERROR":
            trace = self._trace(
                run_id=run_id,
                candidate_id=candidate_id,
                source_signal_id=source_signal_id,
                market_id=market_id,
                side=side,
                identity_source=identity_source,
                identity_status="UNRECOVERABLE",
                reason=gamma.get("error_summary") or "Current Gamma lookup failed.",
                source_refs=source_refs,
                gamma=gamma,
            )
            if apply_changes:
                self._annotate_candidate(conn, candidate_id=candidate_id, trace=trace)
            return trace

        raw = gamma.get("raw") or {}
        parsed = parse_gamma_token_binding(raw)
        condition_id = _clean(parsed.get("condition_id") or raw.get("conditionId") or raw.get("condition_id"))
        tokens = parsed.get("tokens") or {}
        yes_token = _clean(tokens.get("YES"))
        no_token = _clean(tokens.get("NO"))
        expected_token = yes_token if side == "YES" else no_token if side == "NO" else None
        closed = _market_closed(raw)
        accepting_orders = _accepting_orders(raw)
        active = _active(raw)

        if apply_changes and parsed.get("status") == "OK":
            self._upsert_current_market(conn, market_id=market_id, raw=raw, parsed=parsed)

        if not condition_id:
            status, reason = "MISSING_CONDITION_ID", "Current Gamma market has no condition_id."
        elif side not in {"YES", "NO"}:
            status, reason = "MISSING_SIDE", "Candidate has no deterministic YES/NO side."
        elif parsed.get("status") != "OK" or not yes_token or not no_token:
            status, reason = "MISSING_TOKEN_MAPPING", f"Current Gamma token mapping is not deterministic: {parsed.get('status')}."
        elif closed or active is False:
            status, reason = "CLOSED_MARKET", "Current Gamma marks market closed, archived, or inactive."
        elif accepting_orders is False:
            status, reason = "ACCEPTING_ORDERS_FALSE", "Current Gamma marks accepting_orders=false."
        elif not expected_token:
            status, reason = "MISSING_TOKEN_MAPPING", "Candidate side has no matching current Gamma token."
        else:
            status, reason = "FRESH_VERIFIED", "Current Gamma confirms market identity and side token mapping."

        trace = self._trace(
            run_id=run_id,
            candidate_id=candidate_id,
            source_signal_id=source_signal_id,
            market_id=market_id,
            slug=_clean(raw.get("slug")),
            question=_clean(raw.get("question") or raw.get("title")),
            condition_id=condition_id,
            side=side,
            yes_token_id=yes_token,
            no_token_id=no_token,
            expected_token_id=expected_token,
            market_active=active,
            market_closed=closed,
            accepting_orders=accepting_orders,
            identity_source="refreshed Gamma" if identity_source == "existing DB" else identity_source,
            identity_status=status,
            reason=reason,
            source_refs={**source_refs, "gamma_field": parsed.get("gamma_field"), "token_parse_status": parsed.get("status")},
            gamma=gamma,
            evidence={
                "token_binding_confidence": parsed.get("confidence"),
                "token_source": parsed.get("token_source"),
                "gamma_required_for_freshness": True,
                "clob_book_verification": False,
            },
        )
        if apply_changes:
            self._backfill_candidate(conn, candidate_id=candidate_id, market_id=market_id, side=side, trace=trace, original=candidate)
        return trace

    def _lookup_current_gamma(self, market_id: str) -> dict[str, Any]:
        if market_id in self._gamma_cache:
            return self._gamma_cache[market_id]
        endpoint = f"{(os.getenv('GAMMA_API_BASE_URL') or 'https://gamma-api.polymarket.com').rstrip('/')}/markets"
        try:
            raw, latency_ms = self._gamma.get_json(endpoint, params={"id": market_id})
        except Exception as exc:
            payload = {
                "status": "ERROR",
                "latency_ms": None,
                "error_type": type(exc).__name__,
                "error_summary": redact_secrets(str(exc))[:240],
                "attempted": True,
            }
            self._gamma_cache[market_id] = payload
            return payload
        matches = _normalize_gamma_market_response(raw, market_id=market_id)
        if len(matches) == 1:
            result = {"status": "FOUND", "latency_ms": latency_ms, "raw": matches[0], "attempted": True}
        elif len(matches) > 1:
            result = {"status": "AMBIGUOUS", "latency_ms": latency_ms, "attempted": True, "match_count": len(matches)}
        else:
            result = {"status": "NOT_FOUND", "latency_ms": latency_ms, "attempted": True}
        self._gamma_cache[market_id] = result
        return result

    def _load_candidates(self, conn: Any, *, limit: int, include_stale: bool) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM paper_eligibility_candidates
            WHERE is_runtime_generated = true
              AND COALESCE(is_dry_run_generated, false) = false
              AND (
                    (%s AND market_id = '824952')
                    OR market_id IS NULL
                    OR market_id = ''
                    OR side IS NULL
                    OR side NOT IN ('YES','NO')
                    OR identity_status IS NULL
                    OR identity_status <> 'FRESH_VERIFIED'
                    OR COALESCE(eligibility_blockers, '[]'::jsonb) ?| ARRAY[
                        'MISSING_MARKET_ID','MISSING_SIDE','MISSING_FRESH_ORDERBOOK','MISSING_TRUSTED_ORDERBOOK','MISSING_SIGNAL_MARKET_BINDING'
                    ]
                  )
            ORDER BY
                CASE WHEN market_id = '824952' THEN 0 ELSE 1 END,
                CASE WHEN market_id IS NULL OR market_id = '' THEN 1 ELSE 0 END,
                CASE WHEN side IS NULL OR side NOT IN ('YES','NO') THEN 1 ELSE 0 END,
                updated_at DESC NULLS LAST,
                id DESC
            LIMIT %s
            """,
            (include_stale, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _link_options(self, conn: Any, *, signal_ids: list[str]) -> list[dict[str, Any]]:
        if not signal_ids:
            return []
        rows = conn.execute(
            """
            SELECT *
            FROM signal_market_links
            WHERE signal_id = ANY(%s)
              AND market_id IS NOT NULL
              AND market_id <> ''
              AND link_status IN ('confirmed','suggested')
              AND COALESCE(is_review_required, false) = false
              AND COALESCE(link_confidence, confidence, 0) >= %s
            ORDER BY COALESCE(link_confidence, confidence, 0) DESC, id DESC
            """,
            (signal_ids, TRUSTED_LINK_CONFIDENCE),
        ).fetchall()
        return [dict(row) for row in rows]

    def _upsert_current_market(self, conn: Any, *, market_id: str, raw: dict[str, Any], parsed: dict[str, Any]) -> None:
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
                %(raw_market_json)s, %(metadata_json)s, 'fresh_market_identity_gate',
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
                "market_id": market_id,
                "condition_id": _clean(parsed.get("condition_id")),
                "question": _clean(raw.get("question") or raw.get("title")),
                "slug": _clean(raw.get("slug")),
                "yes_token_id": _clean(tokens.get("YES")),
                "no_token_id": _clean(tokens.get("NO")),
                "outcome_tokens_json": Jsonb(tokens),
                "accepting_orders": _accepting_orders(raw),
                "closed": bool(raw.get("closed", False)),
                "archived": bool(raw.get("archived", False)),
                "active": _active(raw),
                "raw_market_json": Jsonb(raw),
                "metadata_json": Jsonb({
                    "fresh_market_identity_gate": True,
                    "gamma_field": parsed.get("gamma_field"),
                    "token_source": parsed.get("token_source"),
                    "verified_at": datetime.now(UTC).isoformat(),
                }),
            },
        )

    def _backfill_candidate(self, conn: Any, *, candidate_id: str, market_id: str, side: str | None, trace: dict[str, Any], original: dict[str, Any]) -> None:
        set_side = side if not _valid_side(original.get("side")) and side in {"YES", "NO"} else original.get("side")
        conn.execute(
            """
            UPDATE paper_eligibility_candidates
            SET market_id = COALESCE(NULLIF(market_id, ''), %(market_id)s),
                side = %(side)s,
                identity_status = %(identity_status)s,
                identity_verified_at = CASE WHEN %(identity_status)s = 'FRESH_VERIFIED' THEN now() ELSE identity_verified_at END,
                identity_source = %(identity_source)s,
                expected_token_id = %(expected_token_id)s,
                identity_blocker_reason = %(reason)s,
                evidence = COALESCE(evidence, '{}'::jsonb) || %(evidence)s,
                updated_at = now()
            WHERE eligibility_id = %(candidate_id)s
            """,
            {
                "candidate_id": candidate_id,
                "market_id": market_id,
                "side": set_side,
                "identity_status": trace["identity_status"],
                "identity_source": trace["identity_source"],
                "expected_token_id": trace.get("expected_token_id"),
                "reason": trace["reason"],
                "evidence": Jsonb({
                    "fresh_market_identity": {
                        "status": trace["identity_status"],
                        "reason": trace["reason"],
                        "source": trace["identity_source"],
                        "expected_token_id": trace.get("expected_token_id"),
                        "gamma_lookup_status": trace["gamma_lookup_status"],
                    }
                }),
            },
        )

    def _annotate_candidate(self, conn: Any, *, candidate_id: str, trace: dict[str, Any]) -> None:
        conn.execute(
            """
            UPDATE paper_eligibility_candidates
            SET identity_status = %(identity_status)s,
                identity_source = %(identity_source)s,
                identity_blocker_reason = %(reason)s,
                expected_token_id = %(expected_token_id)s,
                evidence = COALESCE(evidence, '{}'::jsonb) || %(evidence)s,
                updated_at = now()
            WHERE eligibility_id = %(candidate_id)s
            """,
            {
                "candidate_id": candidate_id,
                "identity_status": trace["identity_status"],
                "identity_source": trace["identity_source"],
                "reason": trace["reason"],
                "expected_token_id": trace.get("expected_token_id"),
                "evidence": Jsonb({"fresh_market_identity": {"status": trace["identity_status"], "reason": trace["reason"]}}),
            },
        )

    def _trace(self, **kwargs: Any) -> dict[str, Any]:
        gamma = kwargs.get("gamma") or {}
        evidence = kwargs.get("evidence") or {}
        return {
            "run_id": kwargs["run_id"],
            "candidate_id": kwargs["candidate_id"],
            "source_signal_id": kwargs.get("source_signal_id"),
            "market_id": kwargs.get("market_id"),
            "slug": kwargs.get("slug"),
            "question": kwargs.get("question"),
            "condition_id": kwargs.get("condition_id"),
            "side": kwargs.get("side"),
            "yes_token_id": kwargs.get("yes_token_id"),
            "no_token_id": kwargs.get("no_token_id"),
            "expected_token_id": kwargs.get("expected_token_id"),
            "market_active": kwargs.get("market_active"),
            "market_closed": kwargs.get("market_closed"),
            "accepting_orders": kwargs.get("accepting_orders"),
            "gamma_lookup_attempted": bool(gamma.get("attempted")),
            "gamma_lookup_status": gamma.get("status", "NOT_ATTEMPTED"),
            "identity_source": kwargs.get("identity_source"),
            "identity_status": kwargs["identity_status"],
            "reason": kwargs["reason"],
            "source_refs_json": kwargs.get("source_refs") or {},
            "evidence_json": evidence,
        }

    def _record_traces(self, conn: Any, traces: list[dict[str, Any]]) -> None:
        if not _table_exists(conn, "fresh_market_identity_traces"):
            return
        for trace in traces:
            conn.execute(
                """
                INSERT INTO fresh_market_identity_traces (
                    run_id, candidate_id, source_signal_id, market_id, slug, question,
                    condition_id, side, yes_token_id, no_token_id, expected_token_id,
                    market_active, market_closed, accepting_orders,
                    gamma_lookup_attempted, gamma_lookup_status, identity_source,
                    identity_status, reason, source_refs_json, evidence_json
                )
                VALUES (
                    %(run_id)s, %(candidate_id)s, %(source_signal_id)s, %(market_id)s,
                    %(slug)s, %(question)s, %(condition_id)s, %(side)s,
                    %(yes_token_id)s, %(no_token_id)s, %(expected_token_id)s,
                    %(market_active)s, %(market_closed)s, %(accepting_orders)s,
                    %(gamma_lookup_attempted)s, %(gamma_lookup_status)s,
                    %(identity_source)s, %(identity_status)s, %(reason)s,
                    %(source_refs_json)s, %(evidence_json)s
                )
                ON CONFLICT (run_id, candidate_id) DO NOTHING
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
            if not _table_exists(conn, "fresh_market_identity_runs"):
                return
            conn.execute(
                """
                INSERT INTO fresh_market_identity_runs (
                    run_id, cycle_id, started_at, finished_at, system_power, status,
                    dry_run, candidates_checked, fresh_verified_count,
                    stale_market_count, missing_market_id_count,
                    missing_condition_id_count, missing_side_count,
                    missing_token_mapping_count, accepting_orders_false_count,
                    market_closed_count, ambiguous_count, unrecoverable_count,
                    blocker_counts_json, safety_counts_before_json,
                    safety_counts_after_json, live_orders_delta, real_orders_delta,
                    metadata_json, error_message
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(started_at)s, %(finished_at)s,
                    %(system_power)s, %(status)s, %(dry_run)s, %(candidates_checked)s,
                    %(fresh_verified_count)s, %(stale_market_count)s,
                    %(missing_market_id_count)s, %(missing_condition_id_count)s,
                    %(missing_side_count)s, %(missing_token_mapping_count)s,
                    %(accepting_orders_false_count)s, %(market_closed_count)s,
                    %(ambiguous_count)s, %(unrecoverable_count)s,
                    %(blocker_counts_json)s, %(safety_counts_before_json)s,
                    %(safety_counts_after_json)s, %(live_orders_delta)s,
                    %(real_orders_delta)s, %(metadata_json)s, %(error_message)s
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

    def _blocked_payload(self, run_id: str, cycle_id: str | None, system_power: str, started_at: datetime, reason: str, *, dry_run: bool) -> dict[str, Any]:
        counts = self._counts()
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "system_power": system_power,
            "status": "BLOCKED",
            "dry_run": dry_run,
            "candidates_checked": 0,
            "fresh_verified_count": 0,
            "stale_market_count": 0,
            "missing_market_id_count": 0,
            "missing_condition_id_count": 0,
            "missing_side_count": 0,
            "missing_token_mapping_count": 0,
            "accepting_orders_false_count": 0,
            "market_closed_count": 0,
            "ambiguous_count": 0,
            "unrecoverable_count": 0,
            "blocker_counts": {reason: 1},
            "safety_counts_before": self._safety_counts(),
            "safety_counts_after": self._safety_counts(),
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
            if not _table_exists(conn, "fresh_market_identity_runs"):
                return None
            row = conn.execute("SELECT * FROM fresh_market_identity_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _latest_traces(self, *, limit: int) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "fresh_market_identity_traces"):
                return []
            rows = conn.execute(
                """
                SELECT *
                FROM fresh_market_identity_traces
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _latest_blockers(self) -> dict[str, int]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "fresh_market_identity_runs"):
                return {}
            row = conn.execute("SELECT blocker_counts_json FROM fresh_market_identity_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return dict(row["blocker_counts_json"] or {}) if row else {}

    def _top_stale_markets(self) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "fresh_market_identity_traces"):
                return []
            rows = conn.execute(
                """
                SELECT market_id, COUNT(*) AS count, MAX(created_at) AS latest_at
                FROM fresh_market_identity_traces
                WHERE identity_status = 'STALE_MARKET'
                GROUP BY market_id
                ORDER BY count DESC, market_id
                LIMIT 20
                """
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _counts(self) -> dict[str, int]:
        with self._factory.connect() as conn:
            return {
                "total_candidates": _count_table(conn, "paper_eligibility_candidates"),
                "candidates_with_market_id": _count_where(conn, "paper_eligibility_candidates", "market_id IS NOT NULL AND market_id<>''"),
                "candidates_missing_market_id": _count_where(conn, "paper_eligibility_candidates", "market_id IS NULL OR market_id=''"),
                "candidates_with_condition_id": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec JOIN markets_v2 m ON m.market_id=pec.market_id WHERE m.condition_id IS NOT NULL AND m.condition_id<>''"),
                "candidates_missing_condition_id": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec LEFT JOIN markets_v2 m ON m.market_id=pec.market_id WHERE pec.market_id IS NOT NULL AND pec.market_id<>'' AND (m.condition_id IS NULL OR m.condition_id='')"),
                "candidates_with_side": _count_where(conn, "paper_eligibility_candidates", "side IN ('YES','NO')"),
                "candidates_missing_side": _count_where(conn, "paper_eligibility_candidates", "side IS NULL OR side NOT IN ('YES','NO')"),
                "candidates_with_yes_token_id": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec JOIN markets_v2 m ON m.market_id=pec.market_id WHERE m.yes_token_id IS NOT NULL AND m.yes_token_id<>''"),
                "candidates_with_no_token_id": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec JOIN markets_v2 m ON m.market_id=pec.market_id WHERE m.no_token_id IS NOT NULL AND m.no_token_id<>''"),
                "candidates_with_expected_token": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec JOIN markets_v2 m ON m.market_id=pec.market_id WHERE (pec.side='YES' AND m.yes_token_id IS NOT NULL AND m.yes_token_id<>'') OR (pec.side='NO' AND m.no_token_id IS NOT NULL AND m.no_token_id<>'')"),
                "FRESH_VERIFIED": _count_where(conn, "paper_eligibility_candidates", "identity_status='FRESH_VERIFIED'"),
                "STALE_MARKET": _count_where(conn, "paper_eligibility_candidates", "identity_status='STALE_MARKET'"),
                "MISSING_MARKET_ID": _count_where(conn, "paper_eligibility_candidates", "identity_status='MISSING_MARKET_ID'"),
                "MISSING_CONDITION_ID": _count_where(conn, "paper_eligibility_candidates", "identity_status='MISSING_CONDITION_ID'"),
                "MISSING_SIDE": _count_where(conn, "paper_eligibility_candidates", "identity_status='MISSING_SIDE'"),
                "MISSING_TOKEN_MAPPING": _count_where(conn, "paper_eligibility_candidates", "identity_status='MISSING_TOKEN_MAPPING'"),
                "AMBIGUOUS_MATCH": _count_where(conn, "paper_eligibility_candidates", "identity_status='AMBIGUOUS_MATCH'"),
                "MARKET_CLOSED": _count_where(conn, "paper_eligibility_candidates", "identity_status='CLOSED_MARKET'"),
                "ACCEPTING_ORDERS_FALSE": _count_where(conn, "paper_eligibility_candidates", "identity_status='ACCEPTING_ORDERS_FALSE'"),
                "UNRECOVERABLE": _count_where(conn, "paper_eligibility_candidates", "identity_status='UNRECOVERABLE'"),
                "candidates_tied_to_stale_market_824952": _count_where(conn, "paper_eligibility_candidates", "market_id='824952'"),
                "paper_intents": _count_table(conn, "paper_intents"),
                "paper_orders": _count_table(conn, "paper_orders"),
                "paper_fills": _count_table(conn, "paper_fills"),
                "paper_positions": _count_table(conn, "paper_positions"),
                "live_orders": _count_table(conn, "live_orders"),
                "orders_v2": _count_table(conn, "orders_v2"),
                "fills_v2": _count_table(conn, "fills_v2"),
                "canonical_positions": _count_table(conn, "positions"),
            }

    def _live_blocker_counts(self) -> dict[str, int]:
        counts = self._counts()
        return {
            "NO_MARKET_ID": counts["candidates_missing_market_id"],
            "NO_CONDITION_ID": counts["candidates_missing_condition_id"],
            "NO_SIDE": counts["candidates_missing_side"],
            "STALE_MARKET": counts["STALE_MARKET"],
            "MISSING_TOKEN_MAPPING": counts["MISSING_TOKEN_MAPPING"],
            "AMBIGUOUS_MATCH": counts["AMBIGUOUS_MATCH"],
            "MARKET_CLOSED": counts["MARKET_CLOSED"],
            "ACCEPTING_ORDERS_FALSE": counts["ACCEPTING_ORDERS_FALSE"],
            "UNRECOVERABLE": counts["UNRECOVERABLE"],
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


class _GammaMarketIdentityClient:
    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[Any, int]:
        started = time.perf_counter()
        with httpx.Client(timeout=10.0, headers={"User-Agent": "POLYBOT-fresh-market-identity/1.0"}) as client:
            response = client.get(url, params=params)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms


def _normalize_gamma_market_response(raw: Any, *, market_id: str) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        if isinstance(raw.get("data"), list):
            items = raw["data"]
        elif isinstance(raw.get("markets"), list):
            items = raw["markets"]
        elif str(raw.get("id") or raw.get("market_id") or "") == str(market_id):
            items = [raw]
        else:
            items = []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    return [dict(item) for item in items if isinstance(item, dict) and str(item.get("id") or item.get("market_id") or "") == str(market_id)]


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
    return bool(row and row["name"])


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    if table == "paper_eligibility_candidates" and not _column_exists(conn, table, "identity_status") and "identity_status" in where:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name=%s AND column_name=%s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return bool(row)


def _scalar(conn: Any, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row["count"] or 0)


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item is not None]
    return []


def _single_value(values: list[Any]) -> Any | None:
    clean = [value for value in values if value is not None and value != ""]
    unique = sorted(set(clean))
    return unique[0] if len(unique) == 1 else None


def _valid_side(value: Any) -> str | None:
    side = str(value or "").strip().upper()
    return side if side in {"YES", "NO"} else None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _active(raw: dict[str, Any]) -> bool | None:
    if "active" not in raw:
        return True
    return _bool_or_none(raw.get("active"))


def _market_closed(raw: dict[str, Any]) -> bool:
    return bool(raw.get("closed")) or bool(raw.get("archived")) or raw.get("active") is False


def _accepting_orders(raw: dict[str, Any]) -> bool | None:
    if "acceptingOrders" in raw:
        return _bool_or_none(raw.get("acceptingOrders"))
    if "accepting_orders" in raw:
        return _bool_or_none(raw.get("accepting_orders"))
    return True


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


def _error_summary(candidate: dict[str, Any], exc: Exception) -> str:
    return f"{candidate.get('eligibility_id') or 'unknown'}:{type(exc).__name__}:{redact_secrets(str(exc))[:160]}"


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

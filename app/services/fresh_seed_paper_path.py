from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.exit_foundation import ExitFoundationService
from app.services.paper_eligibility import PaperEligibilityService
from app.services.paper_intents import PaperIntentGateService
from app.services.payout_odds import PayoutOddsService
from app.services.risk_core import RiskCoreService
from app.services.system_power import SystemPowerService
from app.services.thesis_profiles import ThesisProfileService


SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"
MAX_SPREAD = 0.08
MIN_LIQUIDITY_SCORE = 0.25


class FreshSeedPaperCandidateService:
    """Bridge verified fresh seeds into the canonical non-live Paper decision path.

    This service deliberately stops at Paper Intent creation. It never creates
    paper orders, fills, positions, order intents, live orders, or real orders.
    """

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        thesis_service: ThesisProfileService | None = None,
        risk_service: RiskCoreService | None = None,
        exit_service: ExitFoundationService | None = None,
        eligibility_service: PaperEligibilityService | None = None,
        intent_service: PaperIntentGateService | None = None,
        payout_odds: PayoutOddsService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._thesis = thesis_service or ThesisProfileService(connection_factory=self._factory)
        self._risk = risk_service or RiskCoreService(connection_factory=self._factory)
        self._exit = exit_service or ExitFoundationService(connection_factory=self._factory)
        self._eligibility = eligibility_service or PaperEligibilityService(connection_factory=self._factory)
        self._intents = intent_service or PaperIntentGateService(connection_factory=self._factory)
        self._payout_odds = payout_odds or PayoutOddsService(connection_factory=self._factory)

    def run(
        self,
        *,
        cycle_id: str | None = None,
        limit: int = 25,
        dry_run: bool = False,
        max_seconds: int = 30,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"fresh_seed_paper_path_{uuid4().hex}"
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        if not dry_run and (system_power != "ON" or not bool(power.get("runtime_work_allowed"))):
            payload = self._run_payload(
                run_id=run_id,
                cycle_id=cycle_id,
                system_power=system_power,
                status="BLOCKED",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error_message="SYSTEM_POWER_OFF",
                blockers_by_stage={"SYSTEM_POWER_OFF": 1},
            )
            self._record_run(payload)
            return payload

        safety_before = self._safety_counts()
        seeds = self._select_seeds(limit=limit)
        blockers = Counter()
        converted = 0
        traces: list[dict[str, Any]] = []
        errors: list[str] = []

        if dry_run:
            for seed in seeds:
                reason = self._seed_blocker(seed)
                status = "READY_FOR_CANDIDATE" if reason is None else _status_for_seed_blocker(reason)
                if reason:
                    blockers[reason] += 1
                traces.append(self._conversion_preview(seed, status=status, blocker_reason=reason))
            payload = self._run_payload(
                run_id=run_id,
                cycle_id=cycle_id,
                system_power=system_power,
                status="DRY_RUN",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                seeds_checked=len(seeds),
                blockers_by_stage=dict(blockers),
                safety_counts_before=safety_before,
                safety_counts_after=self._safety_counts(),
                metadata={"dry_run": True, "max_seconds": max_seconds, "sample_traces": traces[:10]},
            )
            return payload

        for seed in seeds:
            reason = self._seed_blocker(seed)
            if reason:
                blockers[reason] += 1
                self._upsert_conversion(seed, status=_status_for_seed_blocker(reason), blocker_reason=reason)
                continue
            try:
                self._upsert_seed_lineage(seed)
                self._upsert_conversion(seed, status="CANDIDATE_CREATED", blocker_reason=None)
                converted += 1
            except Exception as exc:
                reason = f"{type(exc).__name__}:{exc}"
                blockers["BLOCKED_UNKNOWN"] += 1
                errors.append(f"{seed.get('seed_id')}:lineage:{reason}")
                self._upsert_conversion(seed, status="BLOCKED_UNKNOWN", blocker_reason=reason)

        downstream: dict[str, Any] = {}
        if converted:
            downstream = self._run_downstream(limit=max(limit * 4, 100))
            errors.extend(downstream.get("errors") or [])
            self._reconcile_conversions(limit=limit)
        else:
            downstream = {
                "thesis": {"thesis_profiles_created": 0, "thesis_profiles_updated": 0},
                "risk": {"risk_decisions_created": 0, "risk_decisions_updated": 0},
                "exit": {"exit_plans_created": 0, "exit_plans_updated": 0},
                "eligibility": {"candidates_created": 0, "candidates_updated": 0},
                "paper_intents": {"paper_intents_created": 0, "paper_intents_updated": 0},
                "errors": [],
            }

        summary = self._conversion_summary(limit=limit)
        blockers.update(summary.get("blockers_by_stage") or {})
        safety_after = self._safety_counts()
        status = "ERROR" if errors and not converted else "DEGRADED" if errors else "OK"
        payload = self._run_payload(
            run_id=run_id,
            cycle_id=cycle_id,
            system_power=system_power,
            status=status,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            seeds_checked=len(seeds),
            converted_candidates=summary["converted_candidates"],
            thesis_created=_int(downstream.get("thesis", {}).get("thesis_profiles_created")),
            risk_created=_int(downstream.get("risk", {}).get("risk_decisions_created")),
            exit_created=_int(downstream.get("exit", {}).get("exit_plans_created")),
            eligibility_created=_int(downstream.get("eligibility", {}).get("candidates_created")),
            paper_intents_created=_int(downstream.get("paper_intents", {}).get("paper_intents_created")),
            blockers_by_stage=dict(blockers),
            safety_counts_before=safety_before,
            safety_counts_after=safety_after,
            error_message="; ".join(errors) if errors else None,
            metadata={
                "dry_run": False,
                "max_seconds": max_seconds,
                "downstream": downstream,
                "latest_conversions": summary["latest_conversions"],
                "runner_invocation_status": "OK_OFFICIAL_SERVICE_ENTRYPOINTS",
            },
        )
        self._record_run(payload)
        return payload

    def get_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard()
        with self._factory.connect() as conn:
            latest_run = _fetch_one(conn, "SELECT * FROM fresh_seed_paper_path_runs ORDER BY created_at DESC, id DESC LIMIT 1") if _table_exists(conn, "fresh_seed_paper_path_runs") else None
            summary = self._conversion_summary(conn=conn, limit=limit)
            total_seeds = _count_table(conn, "fresh_candidate_seeds")
            book_verified = _count_where(conn, "fresh_candidate_seeds", "status='BOOK_VERIFIED'")
            trusted_seed_links = _count_seed_trusted_links(conn)
            mapped_to_candidates = _count_where(conn, "fresh_seed_candidate_conversions", "candidate_id IS NOT NULL") if _table_exists(conn, "fresh_seed_candidate_conversions") else 0
            runner_status = "OK_OFFICIAL_SERVICE_ENTRYPOINTS"
            return {
                "mock_data": False,
                "status": "OK",
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "total_seeds": total_seeds,
                "book_verified_seeds": book_verified,
                "seeds_with_trusted_orderbook_links": trusted_seed_links,
                "seeds_currently_mapped_to_paper_candidates": mapped_to_candidates,
                "converted_candidates": summary["converted_candidates"],
                "thesis_created": summary["thesis_created"],
                "risk_created": summary["risk_created"],
                "exit_created": summary["exit_created"],
                "eligibility_created": summary["eligibility_created"],
                "paper_intents_created": summary["paper_intents_created"],
                "blockers_by_stage": summary["blockers_by_stage"],
                "duplicate_count": summary["duplicate_count"],
                "already_executed_count": summary["already_executed_count"],
                "latest_conversions": summary["latest_conversions"],
                "sample_conversion_traces": summary["latest_conversions"],
                "latest_run": _json_safe(dict(latest_run)) if latest_run else None,
                "runner_invocation_status": runner_status,
                "paper_orders_created_by_converter": 0,
                "paper_fills_created_by_converter": 0,
                "paper_positions_created_by_converter": 0,
                "live_enabled": False,
                "shadow_enabled": False,
                "last_updated": datetime.now(UTC).isoformat(),
            }

    def _run_downstream(self, *, limit: int) -> dict[str, Any]:
        errors: list[str] = []
        thesis = risk = exit_plan = eligibility = paper_intents = {}
        try:
            thesis = self._thesis.build_profiles(limit=limit, include_incomplete=True, include_blocked=True, write_profiles=True)
        except Exception as exc:
            errors.append(f"thesis_profiles:{type(exc).__name__}:{exc}")
        try:
            risk = self._risk.evaluate_risk(limit=limit, include_blocked=True, write_decisions=True)
        except Exception as exc:
            errors.append(f"risk_core:{type(exc).__name__}:{exc}")
        try:
            exit_plan = self._exit.build_exit_plans(limit=limit, include_blocked=True, write_plans=True)
        except Exception as exc:
            errors.append(f"exit_foundation:{type(exc).__name__}:{exc}")
        try:
            eligibility = self._eligibility.evaluate_candidates(limit=limit, include_blocked=True, write_candidates=True)
        except Exception as exc:
            errors.append(f"paper_eligibility:{type(exc).__name__}:{exc}")
        try:
            paper_intents = self._intents.build_intents(limit=limit, write_intents=True, write_no_trade=True)
        except Exception as exc:
            errors.append(f"paper_intents:{type(exc).__name__}:{exc}")
        try:
            payout_odds = self._payout_odds.evaluate_recent(limit=limit, dry_run=False)
        except Exception as exc:
            payout_odds = {}
            errors.append(f"payout_odds:{type(exc).__name__}:{exc}")
        return {
            "thesis": thesis,
            "risk": risk,
            "exit": exit_plan,
            "eligibility": eligibility,
            "paper_intents": paper_intents,
            "payout_odds": payout_odds,
            "errors": errors,
        }

    def _select_seeds(self, *, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "fresh_candidate_seeds"):
                return []
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT
                        fcs.*,
                        tol.id AS trusted_row_id,
                        tol.trusted,
                        tol.trust_status,
                        tol.trust_reason,
                        tol.orderbook_snapshot_id AS trusted_snapshot_id,
                        tol.spread AS trusted_spread,
                        tol.liquidity_score AS trusted_liquidity_score,
                        obs.snapshot_status,
                        obs.is_stale,
                        obs.best_bid,
                        obs.best_ask,
                        obs.mid_price,
                        obs.spread AS orderbook_spread,
                        obs.liquidity_score AS orderbook_liquidity_score
                    FROM fresh_candidate_seeds fcs
                    LEFT JOIN trusted_orderbook_evidence_links tol
                        ON tol.link_id = fcs.trusted_link_id
                    LEFT JOIN orderbook_snapshots obs
                        ON obs.id = COALESCE(fcs.orderbook_snapshot_id, tol.orderbook_snapshot_id)
                    WHERE fcs.status IN ('BOOK_VERIFIED', 'BOOK_REJECTED', 'NOT_TRADABLE', 'AMBIGUOUS')
                    ORDER BY
                        CASE WHEN fcs.status = 'BOOK_VERIFIED' THEN 0 ELSE 1 END,
                        fcs.updated_at DESC,
                        fcs.id DESC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            ]

    def _seed_blocker(self, seed: dict[str, Any]) -> str | None:
        if str(seed.get("status") or "") != "BOOK_VERIFIED":
            rejection = str(seed.get("rejection_reason") or "").upper()
            if "STALE" in rejection or "CLOSED" in rejection:
                return "BLOCKED_STALE_MARKET"
            return "BLOCKED_NO_TRUSTED_ORDERBOOK"
        for key in ("market_id", "condition_id", "side", "expected_token_id"):
            if not seed.get(key):
                return f"MISSING_{key.upper()}"
        if seed.get("orderbook_snapshot_id") is None or seed.get("trusted_link_id") is None:
            return "BLOCKED_NO_TRUSTED_ORDERBOOK"
        if not bool(seed.get("trusted")) or str(seed.get("trust_status") or "") != "TRUSTED":
            return "BLOCKED_NO_TRUSTED_ORDERBOOK"
        if seed.get("trusted_snapshot_id") is None:
            return "BLOCKED_NO_TRUSTED_ORDERBOOK"
        if bool(seed.get("is_stale")) or str(seed.get("snapshot_status") or "").upper() != "OK":
            return "BLOCKED_NO_TRUSTED_ORDERBOOK"
        spread = _float(seed.get("orderbook_spread") if seed.get("orderbook_spread") is not None else seed.get("trusted_spread"))
        if spread is not None and spread > MAX_SPREAD:
            return "SPREAD_TOO_WIDE"
        liquidity = _float(seed.get("orderbook_liquidity_score") if seed.get("orderbook_liquidity_score") is not None else seed.get("trusted_liquidity_score"))
        if liquidity is not None and liquidity < MIN_LIQUIDITY_SCORE:
            return "LIQUIDITY_TOO_LOW"
        return None

    def _upsert_seed_lineage(self, seed: dict[str, Any]) -> None:
        ids = _ids_for_seed(seed)
        side = str(seed["side"]).upper()
        raw_direction = "yes_up" if side == "YES" else "no_up"
        evidence = {
            "fresh_seed_id": seed["seed_id"],
            "market_id": seed["market_id"],
            "condition_id": seed["condition_id"],
            "side": side,
            "expected_token_id": seed["expected_token_id"],
            "orderbook_snapshot_id": seed.get("orderbook_snapshot_id"),
            "trusted_link_id": seed.get("trusted_link_id"),
            "book_status": "BOOK_VERIFIED",
            "source": "fresh_candidate_seeds",
            "non_executing_bridge": True,
        }
        with self._factory.connect() as conn, conn.transaction():
            conn.execute(
                """
                INSERT INTO neuron_signals (
                    signal_id, neuron, event_type, source_name, market_id,
                    correlation_id, raw_direction, strength, confidence,
                    source_reliability, freshness_seconds, status, evidence_json,
                    raw_payload_ref, entity_count, evidence_count, processed_by_brain,
                    ttl_seconds, stale_after_seconds, created_at, updated_at
                )
                VALUES (
                    %(signal_id)s, 'Fresh Seed Paper Path', 'FRESH_SEED_BOOK_VERIFIED',
                    'fresh_candidate_seeds', %(market_id)s, %(conversion_id)s,
                    %(raw_direction)s, 0.7, 0.72, 0.95, 0, 'ACTIVE',
                    %(evidence)s, %(raw_payload_ref)s, 1, 3, true, 3600, 300,
                    now(), now()
                )
                ON CONFLICT (signal_id) DO UPDATE SET
                    market_id = EXCLUDED.market_id,
                    correlation_id = EXCLUDED.correlation_id,
                    raw_direction = EXCLUDED.raw_direction,
                    confidence = EXCLUDED.confidence,
                    evidence_json = EXCLUDED.evidence_json,
                    status = 'ACTIVE',
                    updated_at = now()
                """,
                {
                    **ids,
                    "market_id": seed["market_id"],
                    "raw_direction": raw_direction,
                    "evidence": Jsonb(evidence),
                    "raw_payload_ref": f"fresh_candidate_seeds:{seed['seed_id']}",
                },
            )
            conn.execute(
                """
                INSERT INTO signal_market_links (
                    signal_id, market_id, link_type, link_status, confidence,
                    reason, created_by, link_confidence, link_reason,
                    link_evidence_json, link_method, linked_by, is_auto_linked,
                    is_review_required, is_runtime_link, source_signal_id,
                    matched_side, side_source, side_source_id, side_confidence,
                    side_evidence_json, side_resolved_at, updated_at
                )
                SELECT
                    %(signal_id)s, %(market_id)s, 'fresh_seed_current_market',
                    'confirmed', 0.95, 'Fresh seed has verified current Gamma/CLOB identity.',
                    'fresh_seed_paper_path', 0.95,
                    'Fresh seed has verified current Gamma/CLOB identity.',
                    %(evidence)s, 'fresh_seed_verified_orderbook',
                    'fresh_seed_paper_path', true, false, true, %(signal_id)s,
                    %(side)s, 'fresh_candidate_seed', %(seed_id)s, 0.95,
                    %(evidence)s, now(), now()
                WHERE NOT EXISTS (
                    SELECT 1 FROM signal_market_links
                    WHERE signal_id=%(signal_id)s
                      AND market_id=%(market_id)s
                      AND link_method='fresh_seed_verified_orderbook'
                )
                """,
                {
                    **ids,
                    "market_id": seed["market_id"],
                    "side": side,
                    "seed_id": seed["seed_id"],
                    "evidence": Jsonb(evidence),
                },
            )
            conn.execute(
                """
                INSERT INTO brain_outputs (
                    brain_output_id, brain, output_type, market_id,
                    recommendation, confidence, urgency, risk_flags_json,
                    reasoning_summary, status, ttl_seconds, correlation_id,
                    generated_by, model_name, model_version, prompt_version,
                    raw_payload_ref, metadata_json, created_at, updated_at
                )
                VALUES (
                    %(brain_output_id)s, 'fresh_seed_context_brain', 'WATCH',
                    %(market_id)s, 'WATCH', 0.72, 0.35, '[]'::jsonb,
                    %(reasoning_summary)s, 'ACTIVE', 3600, %(conversion_id)s,
                    'runtime', 'source_backed_bridge', '1', 'fresh_seed_paper_path_v1',
                    %(raw_payload_ref)s, %(metadata)s, now(), now()
                )
                ON CONFLICT (brain_output_id) DO UPDATE SET
                    market_id = EXCLUDED.market_id,
                    confidence = EXCLUDED.confidence,
                    reasoning_summary = EXCLUDED.reasoning_summary,
                    status = 'ACTIVE',
                    metadata_json = EXCLUDED.metadata_json,
                    updated_at = now()
                """,
                {
                    **ids,
                    "market_id": seed["market_id"],
                    "reasoning_summary": f"Fresh verified seed {seed['seed_id']} has current identity and a trusted CLOB orderbook; Risk, Exit, Eligibility, and Capital remain required.",
                    "raw_payload_ref": f"fresh_candidate_seeds:{seed['seed_id']}",
                    "metadata": Jsonb({**evidence, "source_signal_ids": [ids["signal_id"]]}),
                },
            )
            conn.execute("DELETE FROM brain_output_dependencies WHERE brain_output_id=%s", (ids["brain_output_id"],))
            conn.execute(
                """
                INSERT INTO brain_output_dependencies (
                    brain_output_id, dependency_type, dependency_id,
                    dependency_role, confidence, created_at
                )
                VALUES (%s, 'signal', %s, 'primary_fresh_seed_signal', 0.95, now())
                """,
                (ids["brain_output_id"], ids["signal_id"]),
            )
            conn.execute(
                """
                INSERT INTO coordinator_decisions (
                    coordinator_decision_id, market_id, final_state,
                    primary_reason, confidence, urgency, conflicts_detected,
                    governor_required, execution_allowed, approved_actions_json,
                    blocked_actions_json, required_reviews_json, risk_flags_json,
                    source_brain_count, input_output_count, conflict_count,
                    correlation_id, ttl_seconds, status, metadata_json,
                    created_at, updated_at
                )
                VALUES (
                    %(coordinator_decision_id)s, %(market_id)s, 'WATCH',
                    %(primary_reason)s, 0.72, 0.35, false, true, false,
                    '[]'::jsonb, '[]'::jsonb, '["risk","exit","eligibility","capital"]'::jsonb,
                    '[]'::jsonb, 1, 1, 0, %(conversion_id)s, 3600, 'ACTIVE',
                    %(metadata)s, now(), now()
                )
                ON CONFLICT (coordinator_decision_id) DO UPDATE SET
                    market_id = EXCLUDED.market_id,
                    final_state = 'WATCH',
                    primary_reason = EXCLUDED.primary_reason,
                    confidence = EXCLUDED.confidence,
                    execution_allowed = false,
                    metadata_json = EXCLUDED.metadata_json,
                    status = 'ACTIVE',
                    updated_at = now()
                """,
                {
                    **ids,
                    "market_id": seed["market_id"],
                    "primary_reason": "Fresh verified seed is ready for canonical Risk/Exit/Eligibility review.",
                    "metadata": Jsonb(
                        {
                            **evidence,
                            "generated_by": "runtime",
                            "producer_name": "runtime_coordinator_adapter",
                            "is_runtime_generated": True,
                            "is_dry_run_generated": False,
                            "source_signal_ids": [ids["signal_id"]],
                            "source_brain_output_ids": [ids["brain_output_id"]],
                            "side": side,
                            "expected_move": side,
                            "fresh_seed_paper_path": True,
                        }
                    ),
                },
            )
            conn.execute("DELETE FROM coordinator_decision_inputs WHERE coordinator_decision_id=%s", (ids["coordinator_decision_id"],))
            conn.execute(
                """
                INSERT INTO coordinator_decision_inputs (
                    coordinator_decision_id, brain_output_id, brain,
                    input_role, input_recommendation, input_confidence, created_at
                )
                VALUES (%s, %s, 'fresh_seed_context_brain', 'primary', 'WATCH', 0.72, now())
                """,
                (ids["coordinator_decision_id"], ids["brain_output_id"]),
            )

    def _upsert_conversion(self, seed: dict[str, Any], *, status: str, blocker_reason: str | None) -> None:
        ids = _ids_for_seed(seed)
        blockers = [] if blocker_reason is None else [blocker_reason]
        with self._factory.connect() as conn, conn.transaction():
            conn.execute(
                """
                INSERT INTO fresh_seed_candidate_conversions (
                    conversion_id, seed_id, market_id, condition_id, side,
                    expected_token_id, orderbook_snapshot_id,
                    trusted_orderbook_link_id, signal_id, brain_output_id,
                    coordinator_decision_id, status, blocker_reason,
                    blockers_json, source_refs_json, metadata_json, created_at, updated_at
                )
                VALUES (
                    %(conversion_id)s, %(seed_id)s, %(market_id)s,
                    %(condition_id)s, %(side)s, %(expected_token_id)s,
                    %(orderbook_snapshot_id)s, %(trusted_link_id)s,
                    %(signal_id)s, %(brain_output_id)s,
                    %(coordinator_decision_id)s, %(status)s,
                    %(blocker_reason)s, %(blockers)s, %(source_refs)s,
                    %(metadata)s, now(), now()
                )
                ON CONFLICT (seed_id) DO UPDATE SET
                    market_id = EXCLUDED.market_id,
                    condition_id = EXCLUDED.condition_id,
                    side = EXCLUDED.side,
                    expected_token_id = EXCLUDED.expected_token_id,
                    orderbook_snapshot_id = EXCLUDED.orderbook_snapshot_id,
                    trusted_orderbook_link_id = EXCLUDED.trusted_orderbook_link_id,
                    signal_id = EXCLUDED.signal_id,
                    brain_output_id = EXCLUDED.brain_output_id,
                    coordinator_decision_id = EXCLUDED.coordinator_decision_id,
                    status = EXCLUDED.status,
                    blocker_reason = EXCLUDED.blocker_reason,
                    blockers_json = EXCLUDED.blockers_json,
                    source_refs_json = EXCLUDED.source_refs_json,
                    metadata_json = fresh_seed_candidate_conversions.metadata_json || EXCLUDED.metadata_json,
                    updated_at = now()
                """,
                {
                    **ids,
                    "market_id": seed.get("market_id"),
                    "condition_id": seed.get("condition_id"),
                    "side": seed.get("side"),
                    "expected_token_id": seed.get("expected_token_id"),
                    "orderbook_snapshot_id": seed.get("orderbook_snapshot_id"),
                    "trusted_link_id": seed.get("trusted_link_id"),
                    "status": status,
                    "blocker_reason": blocker_reason,
                    "blockers": Jsonb(blockers),
                    "source_refs": Jsonb(
                        {
                            "fresh_candidate_seeds": seed.get("seed_id"),
                            "orderbook_snapshots": seed.get("orderbook_snapshot_id"),
                            "trusted_orderbook_evidence_links": seed.get("trusted_link_id"),
                        }
                    ),
                    "metadata": Jsonb({"fresh_seed_paper_path": True}),
                },
            )

    def _reconcile_conversions(self, *, limit: int) -> None:
        with self._factory.connect() as conn, conn.transaction():
            rows = conn.execute(
                """
                SELECT *
                FROM fresh_seed_candidate_conversions
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            for row in rows:
                seed_id = row["seed_id"]
                ids = _ids_for_seed({"seed_id": seed_id})
                thesis_id = f"thesis_{ids['coordinator_decision_id']}"
                risk_id = f"risk_{thesis_id}"
                exit_id = f"exit_{risk_id}"
                eligibility_id = f"eligibility_{exit_id}"
                intent_id = f"paper_intent_{eligibility_id}"
                thesis = _fetch_one(conn, "SELECT * FROM thesis_profiles WHERE thesis_id=%s", (thesis_id,))
                risk = _fetch_one(conn, "SELECT * FROM risk_decisions WHERE risk_decision_id=%s", (risk_id,))
                exit_plan = _fetch_one(conn, "SELECT * FROM exit_plans WHERE exit_plan_id=%s", (exit_id,))
                eligibility = _fetch_one(conn, "SELECT * FROM paper_eligibility_candidates WHERE eligibility_id=%s", (eligibility_id,))
                intent = _fetch_one(conn, "SELECT * FROM paper_intents WHERE paper_intent_id=%s", (intent_id,))
                no_trade = _fetch_one(conn, "SELECT * FROM no_trade_log WHERE eligibility_id=%s", (eligibility_id,)) if _table_exists(conn, "no_trade_log") else None
                status, reason = _derive_status(thesis, risk, exit_plan, eligibility, intent, no_trade)
                conn.execute(
                    """
                    UPDATE fresh_seed_candidate_conversions
                    SET
                        candidate_id=%s,
                        thesis_id=%s,
                        risk_decision_id=%s,
                        exit_plan_id=%s,
                        eligibility_id=%s,
                        paper_intent_id=%s,
                        status=%s,
                        blocker_reason=%s,
                        blockers_json=%s,
                        updated_at=now()
                    WHERE seed_id=%s
                    """,
                    (
                        eligibility_id if eligibility else None,
                        thesis_id if thesis else None,
                        risk_id if risk else None,
                        exit_id if exit_plan else None,
                        eligibility_id if eligibility else None,
                        intent_id if intent else None,
                        status,
                        reason,
                        Jsonb([] if reason is None else [reason]),
                        seed_id,
                    ),
                )

    def _conversion_preview(self, seed: dict[str, Any], *, status: str, blocker_reason: str | None) -> dict[str, Any]:
        ids = _ids_for_seed(seed)
        return {
            "conversion_id": ids["conversion_id"],
            "seed_id": seed.get("seed_id"),
            "market_id": seed.get("market_id"),
            "side": seed.get("side"),
            "expected_token_id": seed.get("expected_token_id"),
            "status": status,
            "blocker_reason": blocker_reason,
        }

    def _conversion_summary(self, *, limit: int, conn: Any | None = None) -> dict[str, Any]:
        owns_conn = conn is None
        if owns_conn:
            if not self._factory.enabled:
                return _empty_conversion_summary()
            conn_ctx = self._factory.connect()
            conn = conn_ctx.__enter__()
        try:
            if not _table_exists(conn, "fresh_seed_candidate_conversions"):
                return _empty_conversion_summary()
            rows = [dict(row) for row in conn.execute(
                """
                SELECT *
                FROM fresh_seed_candidate_conversions
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()]
            blockers = Counter()
            for row in rows:
                if row.get("blocker_reason"):
                    blockers[str(row["blocker_reason"])] += 1
            return {
                "converted_candidates": _count_where(conn, "fresh_seed_candidate_conversions", "candidate_id IS NOT NULL"),
                "thesis_created": _count_where(conn, "fresh_seed_candidate_conversions", "thesis_id IS NOT NULL"),
                "risk_created": _count_where(conn, "fresh_seed_candidate_conversions", "risk_decision_id IS NOT NULL"),
                "exit_created": _count_where(conn, "fresh_seed_candidate_conversions", "exit_plan_id IS NOT NULL"),
                "eligibility_created": _count_where(conn, "fresh_seed_candidate_conversions", "eligibility_id IS NOT NULL"),
                "paper_intents_created": _count_where(conn, "fresh_seed_candidate_conversions", "paper_intent_id IS NOT NULL"),
                "duplicate_count": _count_where(conn, "fresh_seed_candidate_conversions", "status='BLOCKED_DUPLICATE'"),
                "already_executed_count": _count_where(conn, "fresh_seed_candidate_conversions", "status='BLOCKED_ALREADY_EXECUTED'"),
                "blockers_by_stage": dict(blockers),
                "latest_conversions": [_json_safe(row) for row in rows],
            }
        finally:
            if owns_conn:
                conn_ctx.__exit__(None, None, None)

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "fresh_seed_paper_path_runs"):
                return
            conn.execute(
                """
                INSERT INTO fresh_seed_paper_path_runs (
                    run_id, cycle_id, system_power, status, started_at, finished_at,
                    seeds_checked, converted_candidates, thesis_created,
                    risk_created, exit_created, eligibility_created,
                    paper_intents_created, blockers_by_stage_json,
                    safety_counts_before_json, safety_counts_after_json,
                    live_orders_delta, real_orders_delta, paper_orders_delta,
                    paper_fills_delta, paper_positions_delta, error_message,
                    metadata_json, created_at
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(system_power)s, %(status)s,
                    %(started_at)s, %(finished_at)s, %(seeds_checked)s,
                    %(converted_candidates)s, %(thesis_created)s,
                    %(risk_created)s, %(exit_created)s, %(eligibility_created)s,
                    %(paper_intents_created)s, %(blockers_by_stage_json)s,
                    %(safety_counts_before_json)s, %(safety_counts_after_json)s,
                    %(live_orders_delta)s, %(real_orders_delta)s,
                    %(paper_orders_delta)s, %(paper_fills_delta)s,
                    %(paper_positions_delta)s, %(error_message)s,
                    %(metadata_json)s, now()
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                _run_params(payload),
            )

    def _run_payload(
        self,
        *,
        run_id: str,
        cycle_id: str | None,
        system_power: str,
        status: str,
        started_at: datetime,
        finished_at: datetime,
        seeds_checked: int = 0,
        converted_candidates: int = 0,
        thesis_created: int = 0,
        risk_created: int = 0,
        exit_created: int = 0,
        eligibility_created: int = 0,
        paper_intents_created: int = 0,
        blockers_by_stage: dict[str, int] | None = None,
        safety_counts_before: dict[str, int] | None = None,
        safety_counts_after: dict[str, int] | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        before = safety_counts_before or {}
        after = safety_counts_after or before or {}
        return _json_safe(
            {
                "mock_data": False,
                "run_id": run_id,
                "cycle_id": cycle_id,
                "system_power": system_power,
                "status": status,
                "started_at": started_at,
                "finished_at": finished_at,
                "seeds_checked": seeds_checked,
                "converted_candidates": converted_candidates,
                "thesis_created": thesis_created,
                "risk_created": risk_created,
                "exit_created": exit_created,
                "eligibility_created": eligibility_created,
                "paper_intents_created": paper_intents_created,
                "blockers_by_stage": blockers_by_stage or {},
                "safety_counts_before": before,
                "safety_counts_after": after,
                "live_orders_delta": max(0, _int(after.get("live_orders")) - _int(before.get("live_orders"))),
                "real_orders_delta": max(0, _int(after.get("orders_v2")) - _int(before.get("orders_v2"))),
                "paper_orders_delta": max(0, _int(after.get("paper_orders")) - _int(before.get("paper_orders"))),
                "paper_fills_delta": max(0, _int(after.get("paper_fills")) - _int(before.get("paper_fills"))),
                "paper_positions_delta": max(0, _int(after.get("paper_positions")) - _int(before.get("paper_positions"))),
                "error_message": error_message,
                "metadata": metadata or {},
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "runner_invocation_status": "OK_OFFICIAL_SERVICE_ENTRYPOINTS",
            }
        )

    def _safety_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {}
        with self._factory.connect() as conn:
            return {
                "paper_intents": _count_table(conn, "paper_intents"),
                "paper_orders": _count_table(conn, "paper_orders"),
                "paper_fills": _count_table(conn, "paper_fills"),
                "paper_positions": _count_table(conn, "paper_positions"),
                "paper_capital_ledger": _count_table(conn, "paper_capital_ledger"),
                "live_orders": _count_table(conn, "live_orders"),
                "orders_v2": _count_table(conn, "orders_v2"),
                "fills_v2": _count_table(conn, "fills_v2"),
                "canonical_positions": _count_table(conn, "positions"),
            }


def _ids_for_seed(seed: dict[str, Any]) -> dict[str, str]:
    seed_id = str(seed["seed_id"])
    safe_id = seed_id.replace(":", "_").replace("/", "_")
    return {
        "seed_id": seed_id,
        "conversion_id": f"fresh_seed_conversion_{safe_id}",
        "signal_id": f"fresh_seed_signal_{safe_id}",
        "brain_output_id": f"fresh_seed_brain_{safe_id}",
        "coordinator_decision_id": f"fresh_seed_coord_{safe_id}",
    }


def _derive_status(
    thesis: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    exit_plan: dict[str, Any] | None,
    eligibility: dict[str, Any] | None,
    intent: dict[str, Any] | None,
    no_trade: dict[str, Any] | None,
) -> tuple[str, str | None]:
    if intent:
        return "PAPER_INTENT_CREATED", None
    if eligibility:
        if str(eligibility.get("status") or "").upper() == "ELIGIBLE":
            reason = (no_trade or {}).get("no_trade_reason") or "OTHER_EXACT_REASON"
            return "ELIGIBILITY_CREATED", reason
        return "BLOCKED_ELIGIBILITY", _first_code(eligibility.get("eligibility_blockers"), eligibility.get("missing_requirements")) or "ELIGIBILITY_BLOCKED"
    if exit_plan:
        if str(exit_plan.get("status") or "").upper() == "COMPLETE" and bool(exit_plan.get("paper_exit_ready")):
            return "EXIT_CREATED", "ELIGIBILITY_NOT_CREATED"
        return "BLOCKED_EXIT", _first_code(exit_plan.get("blockers"), exit_plan.get("missing_exit_evidence")) or "EXIT_NOT_READY"
    if risk:
        if bool(risk.get("risk_approved")):
            return "RISK_CREATED", "EXIT_NOT_CREATED"
        return "BLOCKED_RISK", _first_code(risk.get("blockers"), risk.get("required_missing_evidence")) or "RISK_NOT_APPROVED"
    if thesis:
        if str(thesis.get("status") or "").upper() == "COMPLETE":
            return "THESIS_CREATED", "RISK_NOT_CREATED"
        return "BLOCKED_NO_THESIS", _first_code(thesis.get("missing_evidence")) or "THESIS_NOT_COMPLETE"
    return "BLOCKED_NO_THESIS", "NO_THESIS"


def _first_code(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, str) and value:
            return value
    return None


def _status_for_seed_blocker(reason: str) -> str:
    if reason in {"BLOCKED_STALE_MARKET", "STALE_MARKET"}:
        return "BLOCKED_STALE_MARKET"
    if reason in {"SPREAD_TOO_WIDE", "LIQUIDITY_TOO_LOW"}:
        return "BLOCKED_RISK"
    return "BLOCKED_NO_TRUSTED_ORDERBOOK"


def _run_params(payload: dict[str, Any]) -> dict[str, Any]:
    before = payload.get("safety_counts_before") or {}
    after = payload.get("safety_counts_after") or {}
    return {
        "run_id": payload["run_id"],
        "cycle_id": payload.get("cycle_id"),
        "system_power": payload.get("system_power"),
        "status": payload.get("status"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "seeds_checked": _int(payload.get("seeds_checked")),
        "converted_candidates": _int(payload.get("converted_candidates")),
        "thesis_created": _int(payload.get("thesis_created")),
        "risk_created": _int(payload.get("risk_created")),
        "exit_created": _int(payload.get("exit_created")),
        "eligibility_created": _int(payload.get("eligibility_created")),
        "paper_intents_created": _int(payload.get("paper_intents_created")),
        "blockers_by_stage_json": Jsonb(payload.get("blockers_by_stage") or {}),
        "safety_counts_before_json": Jsonb(before),
        "safety_counts_after_json": Jsonb(after),
        "live_orders_delta": _int(payload.get("live_orders_delta")),
        "real_orders_delta": _int(payload.get("real_orders_delta")),
        "paper_orders_delta": _int(payload.get("paper_orders_delta")),
        "paper_fills_delta": _int(payload.get("paper_fills_delta")),
        "paper_positions_delta": _int(payload.get("paper_positions_delta")),
        "error_message": payload.get("error_message"),
        "metadata_json": Jsonb(payload.get("metadata") or {}),
    }


def _empty_dashboard() -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": "OK",
        "security_governance_status": SECURITY_GOVERNANCE_STATUS,
        "total_seeds": 0,
        "book_verified_seeds": 0,
        "converted_candidates": 0,
        "thesis_created": 0,
        "risk_created": 0,
        "exit_created": 0,
        "eligibility_created": 0,
        "paper_intents_created": 0,
        "blockers_by_stage": {},
        "latest_conversions": [],
        "runner_invocation_status": "OK_OFFICIAL_SERVICE_ENTRYPOINTS",
    }


def _empty_conversion_summary() -> dict[str, Any]:
    return {
        "converted_candidates": 0,
        "thesis_created": 0,
        "risk_created": 0,
        "exit_created": 0,
        "eligibility_created": 0,
        "paper_intents_created": 0,
        "duplicate_count": 0,
        "already_executed_count": 0,
        "blockers_by_stage": {},
        "latest_conversions": [],
    }


def _count_seed_trusted_links(conn: Any) -> int:
    if not _table_exists(conn, "fresh_candidate_seeds") or not _table_exists(conn, "trusted_orderbook_evidence_links"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM fresh_candidate_seeds fcs
        JOIN trusted_orderbook_evidence_links tol
          ON tol.link_id = fcs.trusted_link_id
        WHERE fcs.status='BOOK_VERIFIED'
          AND tol.trusted = true
          AND tol.trust_status = 'TRUSTED'
        """
    ).fetchone()
    return _int(row["count"] if row else 0)


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"])


def _fetch_one(conn: Any, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value.__class__.__name__ == "Decimal":
        return float(value)
    return value

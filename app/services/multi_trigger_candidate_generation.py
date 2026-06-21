from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.proactive_candidate_generation import MESH_HANDOFF_SKIPPED_REASON
from app.services.proactive_seed_mesh_inquiry import _safety_counts, _table_exists, _trading_mutation


DEFAULT_LIMIT = 100
TRIGGER_THRESHOLD = 60.0
WATCH_THRESHOLD = 35.0
SIDE_THRESHOLD = 0.60
ACTIVE_MARKET_STATES = {"ACTIVE"}
ALLOWED_PRIORITIES = {"HIGH", "MEDIUM"}

TRIGGER_SEED_TYPES = {
    "MARKET_MOVEMENT": "MARKET_MOVEMENT_TRIGGER",
    "PAYOUT_DISCREPANCY": "PAYOUT_DISCREPANCY_TRIGGER",
    "ORDERBOOK_PRESSURE": "ORDERBOOK_PRESSURE_TRIGGER",
    "WHALE": "WHALE_TRIGGER",
    "EVENT_WINDOW": "EVENT_WINDOW_TRIGGER",
    "SIGNAL_QUALITY": "SIGNAL_QUALITY_TRIGGER",
    "SIGNAL_PROCESSING": "SIGNAL_PROCESSING_TRIGGER",
}


class MultiTriggerProactiveCandidateGeneratorService:
    """DATA_ONLY multi-trigger candidate hypothesis generator.

    The service writes trigger truth and research-only proactive seeds. It does
    not create execution candidates, paper artifacts, live artifacts, or Mesh
    approvals.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def refresh(self, *, limit: int = DEFAULT_LIMIT, force: bool = False) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"multi_trigger_candidate_generation_{uuid4().hex}"
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "trigger_run_id": run_id, "triggers_detected": 0}
        limit = max(1, min(int(limit or DEFAULT_LIMIT), 500))
        errors: list[str] = []
        with self._factory.connect() as conn, conn.transaction():
            self._ensure_tables(conn)
            safety_before = _safety_counts(conn)
            triggers = self._detect_triggers(conn, limit=limit)
            stats = {
                "triggers_detected": len(triggers),
                "eligible_triggers": 0,
                "watch_only_triggers": 0,
                "blocked_triggers": 0,
                "duplicate_triggers": 0,
                "seeds_generated": 0,
                "yes_seeds": 0,
                "no_seeds": 0,
                "side_unknown_seeds": 0,
            }
            for trigger in triggers:
                try:
                    trigger["trigger_run_id"] = run_id
                    verdict = evaluate_trigger(trigger)
                    trigger.update(verdict)
                    existed = self._trigger_exists(conn, trigger["multi_trigger_id"])
                    seed = build_seed_from_trigger(trigger) if verdict["seed_generation_state"] in {"ELIGIBLE", "WATCH_ONLY"} else None
                    if seed:
                        trigger["proactive_candidate_seed_id"] = seed["proactive_candidate_seed_id"]
                    self._upsert_trigger(conn, trigger)
                    if seed:
                        seed_existed = self._seed_exists(conn, seed["proactive_candidate_seed_id"])
                        self._upsert_seed(conn, seed)
                        stats["duplicate_triggers"] += int(seed_existed or existed)
                        stats["seeds_generated"] += int(seed["seed_state"] == "GENERATED")
                        stats["yes_seeds"] += int(seed["side"] == "YES" and seed["seed_state"] == "GENERATED")
                        stats["no_seeds"] += int(seed["side"] == "NO" and seed["seed_state"] == "GENERATED")
                        stats["side_unknown_seeds"] += int(seed["side"] == "SIDE_UNKNOWN")
                    stats["eligible_triggers"] += int(verdict["seed_generation_state"] == "ELIGIBLE")
                    stats["watch_only_triggers"] += int(verdict["seed_generation_state"] == "WATCH_ONLY")
                    stats["blocked_triggers"] += int(verdict["seed_generation_state"] == "BLOCKED")
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    stats["blocked_triggers"] += 1
            safety_after = _safety_counts(conn)
            completed_at = datetime.now(UTC)
            status = "OK" if not errors else "PARTIAL" if triggers else "ERROR"
            self._insert_run(
                conn,
                trigger_run_id=run_id,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                latest_error=errors[0] if errors else None,
                metadata={
                    "limit": limit,
                    "force": force,
                    "safety_before": safety_before,
                    "safety_after": safety_after,
                    "trading_mutation": _trading_mutation(safety_before, safety_after),
                    "paper_artifacts_created": False,
                    "execution_candidates_created": False,
                    "errors": errors[:5],
                },
                **stats,
            )
        return {"status": status, "trigger_run_id": run_id, "started_at": started_at.isoformat(), "completed_at": completed_at.isoformat(), **stats, "errors": errors[:5]}

    def summary(self, *, limit: int = 10) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return _empty_summary("DATABASE_UNAVAILABLE", now)
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            counts = self._counts(conn)
            latest = self._latest_run(conn)
            top_triggers = self._sample_triggers(conn, "true", limit=limit)
            generated = self._sample_triggers(conn, "seed_generation_state='ELIGIBLE'", limit=limit)
            blocked = self._sample_triggers(conn, "seed_generation_state='BLOCKED'", limit=limit)
        return {
            "status": "REAL" if counts["total_triggers_detected"] else "MISSING",
            "source": "multi_trigger_candidate_triggers + proactive_candidate_seeds",
            "last_updated": (latest or {}).get("completed_at") or now.isoformat(),
            "freshness_state": "FRESH" if latest and counts["total_triggers_detected"] else "MISSING",
            "readiness_state": "READY" if counts["total_triggers_detected"] else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if counts["total_triggers_detected"] else "UNKNOWN",
            "counts": counts,
            "latest_run_status": (latest or {}).get("status"),
            "latest_error": (latest or {}).get("latest_error"),
            "latest_generation_run": latest,
            "top_trigger_examples": top_triggers,
            "top_generated_seeds": generated,
            "top_blocked_triggers": blocked,
            "warnings": [] if counts["total_triggers_detected"] else ["No multi-trigger candidate triggers have been detected yet."],
            "errors": [],
            "generated_at": now.isoformat(),
        }

    def by_market(self, *, market_id: str, limit: int = 20) -> dict[str, Any]:
        return self._by_field("market_id", market_id, limit=limit)

    def by_trigger(self, *, multi_trigger_id: str) -> dict[str, Any]:
        result = self._by_field("multi_trigger_id", multi_trigger_id, limit=1)
        return {"status": result["status"], "trigger": (result.get("results") or [None])[0]}

    def fields_for_market(self, *, market_id: str | None) -> dict[str, Any]:
        if not market_id or not self._factory.enabled:
            return {"multi_trigger_count": 0, "strongest_trigger_type": None, "strongest_trigger_score": None, "latest_trigger_at": None}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                """
                SELECT COUNT(*) AS multi_trigger_count,
                       (ARRAY_AGG(trigger_type ORDER BY trigger_score DESC, updated_at DESC))[1] AS strongest_trigger_type,
                       MAX(trigger_score) AS strongest_trigger_score,
                       MAX(updated_at) AS latest_trigger_at
                FROM multi_trigger_candidate_triggers
                WHERE market_id=%s
                """,
                (market_id,),
            ).fetchone()
        return {
            "multi_trigger_count": int((row or {}).get("multi_trigger_count") or 0),
            "strongest_trigger_type": (row or {}).get("strongest_trigger_type"),
            "strongest_trigger_score": _float((row or {}).get("strongest_trigger_score")),
            "latest_trigger_at": _iso((row or {}).get("latest_trigger_at")),
        }

    def _detect_triggers(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        triggers: list[dict[str, Any]] = []
        per_family = max(1, limit // 6)
        triggers.extend(self._market_movement_triggers(conn, per_family))
        triggers.extend(self._orderbook_pressure_triggers(conn, per_family))
        triggers.extend(self._payout_triggers(conn, per_family))
        triggers.extend(self._whale_triggers(conn, per_family))
        triggers.extend(self._event_window_triggers(conn, per_family))
        triggers.extend(self._signal_quality_triggers(conn, per_family))
        triggers.sort(key=lambda item: (item.get("research_priority_score") or 0, item.get("trigger_score") or 0), reverse=True)
        return triggers[:limit]

    def _market_movement_triggers(self, conn: Any, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "market_technical_signals"):
            return []
        rows = conn.execute(
            """
            SELECT mts.*, mum.market_memory_id, mum.condition_id, mum.status AS market_status,
                   mum.yes_token_id, mum.no_token_id, mum.token_verification_state,
                   rpw.priority_band, rpw.priority_score
            FROM market_technical_signals mts
            JOIN market_universe_memory mum ON mum.market_id=mts.market_id
            LEFT JOIN research_priority_watchlist rpw ON rpw.market_id=mts.market_id
            WHERE mts.ts >= now() - interval '24 hours'
              AND COALESCE(mts.stale,false) IS FALSE
              AND (abs(mts.price_change_15m) >= 0.02 OR mts.momentum_score >= 0.60 OR mts.trend_strength >= 0.60)
            ORDER BY mts.technical_score DESC, mts.ts DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            direction = str(item.get("trend_direction") or "UNKNOWN").upper()
            side = "YES" if direction in {"UP", "YES", "BULLISH"} or _float(item.get("price_change_15m"), 0) > 0 else "NO" if direction in {"DOWN", "NO", "BEARISH"} or _float(item.get("price_change_15m"), 0) < 0 else "SIDE_UNKNOWN"
            move_strength = min(1.0, max(abs(_float(item.get("price_change_15m"), 0)) * 5, _float(item.get("momentum_score"), 0), _float(item.get("trend_strength"), 0)))
            out.append(_trigger(item, "MARKET_MOVEMENT", side, move_strength, _float(item.get("data_completeness_score"), 0.5), "market_movement_id", str(item.get("id")), ["RECENT_MARKET_MOVEMENT", "MOMENTUM_OR_TREND_SIGNAL"]))
        return out

    def _orderbook_pressure_triggers(self, conn: Any, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "orderbook_signals"):
            return []
        rows = conn.execute(
            """
            SELECT obs.*, mum.market_memory_id, mum.condition_id, mum.status AS market_status,
                   mum.yes_token_id, mum.no_token_id, mum.token_verification_state,
                   rpw.priority_band, rpw.priority_score
            FROM orderbook_signals obs
            JOIN market_universe_memory mum ON mum.market_id=obs.market_id
            LEFT JOIN research_priority_watchlist rpw ON rpw.market_id=obs.market_id
            WHERE obs.ts >= now() - interval '24 hours'
              AND COALESCE(obs.stale,false) IS FALSE
              AND obs.has_bid_ask IS TRUE
              AND (obs.imbalance_score >= 0.65 OR obs.imbalance_score <= 0.35 OR obs.orderbook_quality_score >= 0.60)
            ORDER BY obs.orderbook_quality_score DESC, obs.ts DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            side = str(item.get("side") or "SIDE_UNKNOWN").upper()
            if side not in {"YES", "NO"}:
                side = "YES" if _float(item.get("imbalance_score"), 0.5) >= 0.65 else "NO" if _float(item.get("imbalance_score"), 0.5) <= 0.35 else "SIDE_UNKNOWN"
            out.append(_trigger(item, "ORDERBOOK_PRESSURE", side, abs(_float(item.get("imbalance_score"), 0.5) - 0.5) * 2, _float(item.get("orderbook_quality_score"), 0.5), "orderbook_signal_id", str(item.get("id")), ["ORDERBOOK_PRESSURE", "BID_ASK_IMBALANCE"]))
        return out

    def _payout_triggers(self, conn: Any, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "payout_odds_evaluations"):
            return []
        rows = conn.execute(
            """
            SELECT poe.*, mum.market_memory_id, mum.status AS market_status,
                   mum.yes_token_id, mum.no_token_id, mum.token_verification_state,
                   rpw.priority_band, rpw.priority_score
            FROM payout_odds_evaluations poe
            JOIN market_universe_memory mum ON mum.market_id=poe.market_id
            LEFT JOIN research_priority_watchlist rpw ON rpw.market_id=poe.market_id
            WHERE poe.created_at >= now() - interval '24 hours'
              AND poe.settlement_value_status='OK'
              AND (poe.risk_reward >= 1.0 OR abs(COALESCE(poe.expected_value,0)) >= 0.02)
            ORDER BY poe.risk_reward DESC NULLS LAST, poe.expected_value DESC NULLS LAST, poe.created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            side = str(item.get("side") or "SIDE_UNKNOWN").upper()
            if side not in {"YES", "NO"}:
                side = "SIDE_UNKNOWN"
            strength = min(1.0, max(_float(item.get("risk_reward"), 0) - 1.0, abs(_float(item.get("expected_value"), 0))) )
            confidence = 0.70 if item.get("fair_probability") is not None or item.get("expected_value") is not None else 0.65 if _float(item.get("risk_reward"), 0) >= 1.0 else 0.45
            out.append(_trigger(item, "PAYOUT_DISCREPANCY", side, strength, confidence, "payout_odds_evaluation_id", str(item.get("evaluation_id")), ["PAYOUT_ODDS_DISCREPANCY", "MISPRICING_REVIEW"]))
        return out

    def _whale_triggers(self, conn: Any, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "whale_market_scores"):
            return []
        rows = conn.execute(
            """
            SELECT wms.*, mum.market_memory_id, mum.condition_id, mum.status AS market_status,
                   mum.yes_token_id, mum.no_token_id, mum.token_verification_state,
                   rpw.priority_band, rpw.priority_score
            FROM whale_market_scores wms
            JOIN market_universe_memory mum ON mum.market_id=wms.market_id
            LEFT JOIN research_priority_watchlist rpw ON rpw.market_id=wms.market_id
            WHERE wms.created_at >= now() - interval '72 hours'
              AND (wms.whale_presence_score >= 0.60 OR wms.whale_conviction_score >= 0.60)
            ORDER BY wms.whale_presence_score DESC, wms.created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_trigger(dict(row), "WHALE", "SIDE_UNKNOWN", _float(row["whale_presence_score"], 0), _float(row["whale_conviction_score"], 0.5), "whale_event_id", str(row["id"]), ["WHALE_ACTIVITY_MARKET_LEVEL"]) for row in rows]

    def _event_window_triggers(self, conn: Any, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "market_universe_memory"):
            return []
        rows = conn.execute(
            """
            SELECT mum.*, rpw.priority_band, rpw.priority_score
            FROM market_universe_memory mum
            LEFT JOIN research_priority_watchlist rpw ON rpw.market_id=mum.market_id
            WHERE mum.active IS TRUE
              AND mum.close_time IS NOT NULL
              AND mum.close_time BETWEEN now() AND now() + interval '48 hours'
            ORDER BY mum.close_time ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_trigger(dict(row), "EVENT_WINDOW", "SIDE_UNKNOWN", 0.55, 0.60, "market_memory_id", str(row["market_memory_id"]), ["CLOSING_SOON_EVENT_WINDOW"]) for row in rows]

    def _signal_quality_triggers(self, conn: Any, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "signal_quality_evaluations") or not _table_exists(conn, "neuron_signals"):
            return []
        rows = conn.execute(
            """
            SELECT sqe.*, ns.market_id, ns.raw_direction AS signal_direction,
                   mum.market_memory_id, mum.condition_id, mum.status AS market_status,
                   mum.yes_token_id, mum.no_token_id, mum.token_verification_state,
                   rpw.priority_band, rpw.priority_score
            FROM signal_quality_evaluations sqe
            JOIN neuron_signals ns ON ns.signal_id=sqe.signal_id
            JOIN market_universe_memory mum ON mum.market_id=ns.market_id
            LEFT JOIN research_priority_watchlist rpw ON rpw.market_id=ns.market_id
            WHERE sqe.evaluated_at >= now() - interval '24 hours'
              AND sqe.linked_to_market IS TRUE
              AND sqe.quality_score >= 0.60
            ORDER BY sqe.quality_score DESC, sqe.evaluated_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            side = str(item.get("signal_direction") or "SIDE_UNKNOWN").upper()
            if side not in {"YES", "NO"}:
                side = "SIDE_UNKNOWN"
            out.append(_trigger(item, "SIGNAL_QUALITY", side, _float(item.get("quality_score"), 0), 0.70, "signal_quality_id", str(item.get("id")), ["SIGNAL_QUALITY_IMPROVED"]))
        return out

    def _upsert_trigger(self, conn: Any, record: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO multi_trigger_candidate_triggers (
                multi_trigger_id, trigger_run_id, trigger_type, market_memory_id, market_id, condition_id,
                source_event_id, targeted_revalidation_id, orderbook_snapshot_id, payout_odds_evaluation_id,
                market_movement_id, orderbook_signal_id, technical_signal_id, whale_event_id,
                signal_quality_id, signal_processing_id, side_hint, side_confidence, trigger_strength,
                trigger_confidence, trigger_score, freshness_seconds, evidence_summary, trigger_reasons_json,
                guardrail_blockers_json, watch_reasons_json, research_priority_band, research_priority_score,
                seed_generation_state, proactive_candidate_seed_id, metadata_json
            ) VALUES (
                %(multi_trigger_id)s, %(trigger_run_id)s, %(trigger_type)s, %(market_memory_id)s, %(market_id)s, %(condition_id)s,
                %(source_event_id)s, %(targeted_revalidation_id)s, %(orderbook_snapshot_id)s, %(payout_odds_evaluation_id)s,
                %(market_movement_id)s, %(orderbook_signal_id)s, %(technical_signal_id)s, %(whale_event_id)s,
                %(signal_quality_id)s, %(signal_processing_id)s, %(side_hint)s, %(side_confidence)s, %(trigger_strength)s,
                %(trigger_confidence)s, %(trigger_score)s, %(freshness_seconds)s, %(evidence_summary)s, %(trigger_reasons_json)s,
                %(guardrail_blockers_json)s, %(watch_reasons_json)s, %(research_priority_band)s, %(research_priority_score)s,
                %(seed_generation_state)s, %(proactive_candidate_seed_id)s, %(metadata_json)s
            )
            ON CONFLICT (multi_trigger_id) DO UPDATE SET
                trigger_run_id=EXCLUDED.trigger_run_id,
                trigger_strength=EXCLUDED.trigger_strength,
                trigger_confidence=EXCLUDED.trigger_confidence,
                trigger_score=EXCLUDED.trigger_score,
                side_hint=EXCLUDED.side_hint,
                side_confidence=EXCLUDED.side_confidence,
                evidence_summary=EXCLUDED.evidence_summary,
                research_priority_band=EXCLUDED.research_priority_band,
                research_priority_score=EXCLUDED.research_priority_score,
                seed_generation_state=EXCLUDED.seed_generation_state,
                proactive_candidate_seed_id=EXCLUDED.proactive_candidate_seed_id,
                trigger_reasons_json=EXCLUDED.trigger_reasons_json,
                guardrail_blockers_json=EXCLUDED.guardrail_blockers_json,
                watch_reasons_json=EXCLUDED.watch_reasons_json,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            _json_params(record),
        )

    def _upsert_seed(self, conn: Any, seed: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO proactive_candidate_seeds (
                proactive_candidate_seed_id, generation_run_id, source_event_id, targeted_revalidation_id,
                market_memory_id, market_id, condition_id, side, token_id, seed_state, seed_type,
                research_only, execution_allowed, paper_allowed, shadow_allowed, live_allowed,
                link_type, link_confidence, direction_for_market, direction_confidence, orderbook_snapshot_id,
                orderbook_refresh_state, liquidity_state, spread_state, payout_odds_state, movement_state,
                already_priced_in_state, candidate_event_scope_state, token_side_resolution_state,
                mesh_handoff_state, blockers_json, soft_warnings_json, required_to_pass_json, reason,
                metadata_json, multi_trigger_id, trigger_type, trigger_score, trigger_reasons_json, seed_generation_source
            ) VALUES (
                %(proactive_candidate_seed_id)s, %(generation_run_id)s, %(source_event_id)s, %(targeted_revalidation_id)s,
                %(market_memory_id)s, %(market_id)s, %(condition_id)s, %(side)s, %(token_id)s, %(seed_state)s, %(seed_type)s,
                %(research_only)s, %(execution_allowed)s, %(paper_allowed)s, %(shadow_allowed)s, %(live_allowed)s,
                %(link_type)s, %(link_confidence)s, %(direction_for_market)s, %(direction_confidence)s, %(orderbook_snapshot_id)s,
                %(orderbook_refresh_state)s, %(liquidity_state)s, %(spread_state)s, %(payout_odds_state)s, %(movement_state)s,
                %(already_priced_in_state)s, %(candidate_event_scope_state)s, %(token_side_resolution_state)s,
                %(mesh_handoff_state)s, %(blockers_json)s, %(soft_warnings_json)s, %(required_to_pass_json)s, %(reason)s,
                %(metadata_json)s, %(multi_trigger_id)s, %(trigger_type)s, %(trigger_score)s, %(trigger_reasons_json)s, %(seed_generation_source)s
            )
            ON CONFLICT (proactive_candidate_seed_id) DO UPDATE SET
                generation_run_id=EXCLUDED.generation_run_id,
                seed_state=EXCLUDED.seed_state,
                token_id=EXCLUDED.token_id,
                trigger_score=EXCLUDED.trigger_score,
                trigger_reasons_json=EXCLUDED.trigger_reasons_json,
                blockers_json=EXCLUDED.blockers_json,
                soft_warnings_json=EXCLUDED.soft_warnings_json,
                required_to_pass_json=EXCLUDED.required_to_pass_json,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            _json_params(seed),
        )

    def _counts(self, conn: Any) -> dict[str, Any]:
        trigger_rows = conn.execute("SELECT trigger_type, seed_generation_state, COUNT(*) AS count FROM multi_trigger_candidate_triggers GROUP BY trigger_type, seed_generation_state").fetchall()
        seed_rows = conn.execute("SELECT trigger_type, side, seed_state, COUNT(*) AS count FROM proactive_candidate_seeds WHERE seed_generation_source='MULTI_TRIGGER' GROUP BY trigger_type, side, seed_state").fetchall()
        result = {
            "total_triggers_detected": 0,
            "eligible_trigger_count": 0,
            "watch_only_trigger_count": 0,
            "blocked_trigger_count": 0,
            "duplicate_trigger_count": 0,
            "seeds_generated_count": 0,
            "yes_seed_count": 0,
            "no_seed_count": 0,
            "side_unknown_seed_count": 0,
            "triggers_by_type": {},
            "seeds_by_trigger_type": {},
            "blocked_skipped_reasons": {},
        }
        for row in trigger_rows:
            count = int(row["count"] or 0)
            state = str(row["seed_generation_state"])
            trig_type = str(row["trigger_type"])
            result["total_triggers_detected"] += count
            result["triggers_by_type"][trig_type] = result["triggers_by_type"].get(trig_type, 0) + count
            result["eligible_trigger_count"] += count if state == "ELIGIBLE" else 0
            result["watch_only_trigger_count"] += count if state == "WATCH_ONLY" else 0
            result["blocked_trigger_count"] += count if state == "BLOCKED" else 0
        for row in seed_rows:
            count = int(row["count"] or 0)
            trig_type = str(row["trigger_type"])
            result["seeds_by_trigger_type"][trig_type] = result["seeds_by_trigger_type"].get(trig_type, 0) + count
            result["seeds_generated_count"] += count if row["seed_state"] == "GENERATED" else 0
            result["yes_seed_count"] += count if row["side"] == "YES" and row["seed_state"] == "GENERATED" else 0
            result["no_seed_count"] += count if row["side"] == "NO" and row["seed_state"] == "GENERATED" else 0
            result["side_unknown_seed_count"] += count if row["side"] == "SIDE_UNKNOWN" else 0
        blockers = conn.execute(
            """
            SELECT blocker, COUNT(*) AS count
            FROM multi_trigger_candidate_triggers,
                 LATERAL jsonb_array_elements_text(guardrail_blockers_json) AS blocker
            GROUP BY blocker ORDER BY count DESC, blocker
            """
        ).fetchall()
        result["blocked_skipped_reasons"] = {str(row["blocker"]): int(row["count"] or 0) for row in blockers}
        result["mesh_handoff_count"] = 0
        result["mesh_reviewed_count"] = int(conn.execute("SELECT COUNT(*) AS count FROM proactive_seed_mesh_results psr JOIN proactive_seed_mesh_inquiries psi ON psi.seed_mesh_inquiry_id=psr.seed_mesh_inquiry_id JOIN proactive_candidate_seeds pcs ON pcs.proactive_candidate_seed_id=psi.proactive_candidate_seed_id WHERE pcs.seed_generation_source='MULTI_TRIGGER'").fetchone()["count"] or 0)
        result["paper_observation_classification_count"] = int(conn.execute("SELECT COUNT(*) AS count FROM proactive_seed_mesh_results psr JOIN proactive_seed_mesh_inquiries psi ON psi.seed_mesh_inquiry_id=psr.seed_mesh_inquiry_id JOIN proactive_candidate_seeds pcs ON pcs.proactive_candidate_seed_id=psi.proactive_candidate_seed_id WHERE pcs.seed_generation_source='MULTI_TRIGGER' AND psr.paper_observation_eligible IS TRUE").fetchone()["count"] or 0)
        result["full_paper_ready_count"] = int(conn.execute("SELECT COUNT(*) AS count FROM proactive_seed_mesh_results psr JOIN proactive_seed_mesh_inquiries psi ON psi.seed_mesh_inquiry_id=psr.seed_mesh_inquiry_id JOIN proactive_candidate_seeds pcs ON pcs.proactive_candidate_seed_id=psi.proactive_candidate_seed_id WHERE pcs.seed_generation_source='MULTI_TRIGGER' AND psr.full_paper_ready IS TRUE").fetchone()["count"] or 0)
        if _table_exists(conn, "paper_observation_policy_reviews"):
            policy = conn.execute(
                """
                SELECT observation_policy_state, COUNT(*) AS count
                FROM paper_observation_policy_reviews popr
                JOIN proactive_candidate_seeds pcs ON pcs.proactive_candidate_seed_id=popr.proactive_candidate_seed_id
                WHERE pcs.seed_generation_source='MULTI_TRIGGER'
                GROUP BY observation_policy_state
                """
            ).fetchall()
            result["downstream_observation_policy_counts"] = {str(row["observation_policy_state"]): int(row["count"] or 0) for row in policy}
            result["downstream_observation_policy_eligible"] = int(result["downstream_observation_policy_counts"].get("OBSERVATION_POLICY_ELIGIBLE", 0))
        else:
            result["downstream_observation_policy_counts"] = {}
            result["downstream_observation_policy_eligible"] = 0
        return result

    def _sample_triggers(self, conn: Any, where: str, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"SELECT * FROM multi_trigger_candidate_triggers WHERE {where} ORDER BY trigger_score DESC, updated_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _by_field(self, field: str, value: str, *, limit: int) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "results": []}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            rows = conn.execute(f"SELECT * FROM multi_trigger_candidate_triggers WHERE {field}=%s ORDER BY updated_at DESC LIMIT %s", (value, limit)).fetchall()
        return {"status": "REAL" if rows else "MISSING", "results": [_jsonable(dict(row)) for row in rows]}

    def _latest_run(self, conn: Any) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM multi_trigger_candidate_generation_runs ORDER BY completed_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
        return _jsonable(dict(row)) if row else None

    def _insert_run(self, conn: Any, *, trigger_run_id: str, status: str, started_at: datetime, completed_at: datetime, latest_error: str | None, metadata: dict[str, Any], **stats: Any) -> None:
        conn.execute(
            """
            INSERT INTO multi_trigger_candidate_generation_runs (
                trigger_run_id, status, started_at, completed_at, triggers_detected, eligible_triggers,
                watch_only_triggers, blocked_triggers, duplicate_triggers, seeds_generated, yes_seeds,
                no_seeds, side_unknown_seeds, latest_error, metadata_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (trigger_run_id) DO UPDATE SET status=EXCLUDED.status, completed_at=EXCLUDED.completed_at, metadata_json=EXCLUDED.metadata_json, updated_at=now()
            """,
            (trigger_run_id, status, started_at, completed_at, stats["triggers_detected"], stats["eligible_triggers"], stats["watch_only_triggers"], stats["blocked_triggers"], stats["duplicate_triggers"], stats["seeds_generated"], stats["yes_seeds"], stats["no_seeds"], stats["side_unknown_seeds"], latest_error, Jsonb(_jsonable(metadata))),
        )

    def _ensure_tables(self, conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS multi_trigger_candidate_triggers (
                id BIGSERIAL PRIMARY KEY,
                multi_trigger_id TEXT NOT NULL UNIQUE,
                trigger_run_id TEXT,
                trigger_type TEXT NOT NULL,
                market_memory_id TEXT,
                market_id TEXT,
                condition_id TEXT,
                source_event_id TEXT,
                targeted_revalidation_id TEXT,
                orderbook_snapshot_id TEXT,
                payout_odds_evaluation_id TEXT,
                market_movement_id TEXT,
                orderbook_signal_id TEXT,
                technical_signal_id TEXT,
                whale_event_id TEXT,
                signal_quality_id TEXT,
                signal_processing_id TEXT,
                side_hint TEXT NOT NULL DEFAULT 'SIDE_UNKNOWN',
                side_confidence NUMERIC NOT NULL DEFAULT 0,
                trigger_strength NUMERIC NOT NULL DEFAULT 0,
                trigger_confidence NUMERIC NOT NULL DEFAULT 0,
                trigger_score NUMERIC NOT NULL DEFAULT 0,
                freshness_seconds INTEGER,
                evidence_summary TEXT,
                trigger_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                guardrail_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                watch_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                research_priority_band TEXT,
                research_priority_score NUMERIC NOT NULL DEFAULT 0,
                seed_generation_state TEXT NOT NULL DEFAULT 'SKIPPED',
                proactive_candidate_seed_id TEXT,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS multi_trigger_candidate_generation_runs (
                id BIGSERIAL PRIMARY KEY,
                trigger_run_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                triggers_detected INTEGER NOT NULL DEFAULT 0,
                eligible_triggers INTEGER NOT NULL DEFAULT 0,
                watch_only_triggers INTEGER NOT NULL DEFAULT 0,
                blocked_triggers INTEGER NOT NULL DEFAULT 0,
                duplicate_triggers INTEGER NOT NULL DEFAULT 0,
                seeds_generated INTEGER NOT NULL DEFAULT 0,
                yes_seeds INTEGER NOT NULL DEFAULT 0,
                no_seeds INTEGER NOT NULL DEFAULT 0,
                side_unknown_seeds INTEGER NOT NULL DEFAULT 0,
                latest_error TEXT,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_multi_trigger_candidate_triggers_market ON multi_trigger_candidate_triggers (market_id, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_multi_trigger_candidate_triggers_type ON multi_trigger_candidate_triggers (trigger_type, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_multi_trigger_candidate_triggers_state ON multi_trigger_candidate_triggers (seed_generation_state, updated_at DESC)")
        conn.execute("ALTER TABLE proactive_candidate_seeds ADD COLUMN IF NOT EXISTS multi_trigger_id TEXT")
        conn.execute("ALTER TABLE proactive_candidate_seeds ADD COLUMN IF NOT EXISTS trigger_type TEXT")
        conn.execute("ALTER TABLE proactive_candidate_seeds ADD COLUMN IF NOT EXISTS trigger_score NUMERIC")
        conn.execute("ALTER TABLE proactive_candidate_seeds ADD COLUMN IF NOT EXISTS trigger_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb")
        conn.execute("ALTER TABLE proactive_candidate_seeds ADD COLUMN IF NOT EXISTS seed_generation_source TEXT NOT NULL DEFAULT 'EVENT_DRIVEN'")

    def _trigger_exists(self, conn: Any, trigger_id: str) -> bool:
        return bool(conn.execute("SELECT 1 FROM multi_trigger_candidate_triggers WHERE multi_trigger_id=%s LIMIT 1", (trigger_id,)).fetchone())

    def _seed_exists(self, conn: Any, seed_id: str) -> bool:
        return bool(conn.execute("SELECT 1 FROM proactive_candidate_seeds WHERE proactive_candidate_seed_id=%s LIMIT 1", (seed_id,)).fetchone())


def evaluate_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    watch: list[str] = []
    if trigger.get("market_status") not in ACTIVE_MARKET_STATES:
        blockers.append("MARKET_NOT_ACTIVE")
    if trigger.get("token_verification_state") != "TOKENS_VERIFIED":
        blockers.append("TOKENS_NOT_VERIFIED")
    if trigger.get("research_priority_band") not in ALLOWED_PRIORITIES:
        blockers.append("PRIORITY_NOT_SELECTED")
    if trigger.get("trigger_score", 0) < WATCH_THRESHOLD:
        blockers.append("TRIGGER_CONFIDENCE_TOO_LOW")
    side = trigger.get("side_hint")
    if side not in {"YES", "NO"}:
        watch.append("SIDE_UNKNOWN_NOT_ACTIONABLE")
    elif trigger.get("side_confidence", 0) < SIDE_THRESHOLD:
        watch.append("SIDE_CONFIDENCE_BELOW_ACTIONABLE_THRESHOLD")
    token = _token_for_side(trigger, side)
    if side in {"YES", "NO"} and not token:
        blockers.append("SIDE_TOKEN_MISSING")
    if blockers:
        state = "BLOCKED"
    elif side in {"YES", "NO"} and trigger.get("trigger_score", 0) >= TRIGGER_THRESHOLD and not watch:
        state = "ELIGIBLE"
    else:
        state = "WATCH_ONLY"
    return {
        "seed_generation_state": state,
        "guardrail_blockers_json": _dedupe(blockers),
        "watch_reasons_json": _dedupe(watch),
    }


def build_seed_from_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
    side = trigger.get("side_hint") if trigger.get("seed_generation_state") == "ELIGIBLE" else "SIDE_UNKNOWN"
    token = _token_for_side(trigger, side)
    seed_state = "GENERATED" if side in {"YES", "NO"} else "WATCH_ONLY"
    seed_id = _seed_id(trigger["multi_trigger_id"], side)
    return {
        "proactive_candidate_seed_id": seed_id,
        "generation_run_id": trigger.get("trigger_run_id"),
        "source_event_id": trigger.get("source_event_id"),
        "targeted_revalidation_id": trigger.get("targeted_revalidation_id"),
        "market_memory_id": trigger.get("market_memory_id"),
        "market_id": trigger.get("market_id"),
        "condition_id": trigger.get("condition_id"),
        "side": side,
        "token_id": token,
        "seed_state": seed_state,
        "seed_type": TRIGGER_SEED_TYPES.get(trigger.get("trigger_type"), "UNKNOWN_TRIGGER"),
        "research_only": True,
        "execution_allowed": False,
        "paper_allowed": False,
        "shadow_allowed": False,
        "live_allowed": False,
        "link_type": "MULTI_TRIGGER",
        "link_confidence": trigger.get("trigger_confidence") or 0.0,
        "direction_for_market": side if side in {"YES", "NO"} else "UNKNOWN",
        "direction_confidence": trigger.get("side_confidence") or 0.0,
        "orderbook_snapshot_id": trigger.get("orderbook_snapshot_id"),
        "orderbook_refresh_state": "FRESH",
        "liquidity_state": "MEDIUM",
        "spread_state": "MEDIUM",
        "payout_odds_state": "AVAILABLE" if trigger.get("payout_odds_evaluation_id") else "UNKNOWN",
        "movement_state": "ACTIVE" if trigger.get("market_movement_id") or trigger.get("orderbook_signal_id") else "UNKNOWN",
        "already_priced_in_state": "UNKNOWN",
        "candidate_event_scope_state": "CANDIDATE_SCOPED" if side in {"YES", "NO"} else "MARKET_LEVEL_ONLY",
        "token_side_resolution_state": f"SIDE_DIRECTIONAL_{side}" if side in {"YES", "NO"} else "TOKEN_SIDE_UNKNOWN",
        "mesh_handoff_state": "SKIPPED",
        "blockers_json": trigger.get("guardrail_blockers_json") or [],
        "soft_warnings_json": trigger.get("watch_reasons_json") or [],
        "required_to_pass_json": trigger.get("guardrail_blockers_json") or trigger.get("watch_reasons_json") or [],
        "reason": trigger.get("evidence_summary"),
        "metadata_json": {"stage": "MONEY_MACHINE_STAGE6", "mesh_handoff_policy": MESH_HANDOFF_SKIPPED_REASON, "trigger_lineage": trigger},
        "multi_trigger_id": trigger.get("multi_trigger_id"),
        "trigger_type": trigger.get("trigger_type"),
        "trigger_score": trigger.get("trigger_score"),
        "trigger_reasons_json": trigger.get("trigger_reasons_json") or [],
        "seed_generation_source": "MULTI_TRIGGER",
    }


def _trigger(row: dict[str, Any], trigger_type: str, side: str, strength: float, confidence: float, source_key: str, source_id: str, reasons: list[str]) -> dict[str, Any]:
    priority_score = _float(row.get("priority_score"), 0)
    trigger_score = _score(strength, confidence, priority_score)
    market_id = str(row.get("market_id") or "")
    key = "|".join([trigger_type, market_id, side, source_id])
    return {
        "multi_trigger_id": f"multi_trigger_{hashlib.sha256(key.encode()).hexdigest()[:28]}",
        "trigger_type": trigger_type,
        "market_memory_id": row.get("market_memory_id"),
        "market_id": market_id,
        "condition_id": row.get("condition_id"),
        "side_hint": side if side in {"YES", "NO"} else "SIDE_UNKNOWN",
        "side_confidence": min(1.0, max(0.0, confidence)),
        "trigger_strength": min(1.0, max(0.0, strength)),
        "trigger_confidence": min(1.0, max(0.0, confidence)),
        "trigger_score": trigger_score,
        "freshness_seconds": None,
        "evidence_summary": f"{trigger_type} trigger from {source_key}={source_id}; score={trigger_score}.",
        "trigger_reasons_json": reasons,
        "research_priority_band": row.get("priority_band") or "LOW",
        "research_priority_score": priority_score,
        "market_status": row.get("market_status") or row.get("status"),
        "token_verification_state": row.get("token_verification_state"),
        "yes_token_id": row.get("yes_token_id"),
        "no_token_id": row.get("no_token_id"),
        "source_event_id": None,
        "targeted_revalidation_id": None,
        "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
        "payout_odds_evaluation_id": row.get("evaluation_id") if source_key == "payout_odds_evaluation_id" else None,
        "market_movement_id": source_id if source_key == "market_movement_id" else None,
        "orderbook_signal_id": source_id if source_key == "orderbook_signal_id" else None,
        "technical_signal_id": None,
        "whale_event_id": source_id if source_key == "whale_event_id" else None,
        "signal_quality_id": source_id if source_key == "signal_quality_id" else None,
        "signal_processing_id": None,
        "metadata_json": {"source_row": _jsonable(row)},
    }


def _score(strength: float, confidence: float, priority_score: float) -> float:
    return round(max(0.0, min(100.0, 45 * strength + 35 * confidence + 20 * (priority_score / 100))), 2)


def _token_for_side(trigger: dict[str, Any], side: str | None) -> str | None:
    if side == "YES":
        return trigger.get("yes_token_id")
    if side == "NO":
        return trigger.get("no_token_id")
    return None


def _seed_id(trigger_id: str, side: str) -> str:
    key = f"{trigger_id}|{side}"
    return f"multi_trigger_seed_{hashlib.sha256(key.encode()).hexdigest()[:30]}"


def _json_params(record: dict[str, Any]) -> dict[str, Any]:
    out = dict(record)
    out.setdefault("proactive_candidate_seed_id", None)
    list_keys = {
        "trigger_reasons_json",
        "guardrail_blockers_json",
        "watch_reasons_json",
        "blockers_json",
        "soft_warnings_json",
        "required_to_pass_json",
    }
    dict_keys = {"metadata_json"}
    for key in list_keys:
        out[key] = Jsonb(_jsonable(out.get(key) or []))
    for key in dict_keys:
        out[key] = Jsonb(_jsonable(out.get(key) or {}))
    return out


def _float(value: Any, default: float | None = None) -> float:
    if value is None:
        return 0.0 if default is None else default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0 if default is None else default


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(part) for key, part in value.items()}
    if isinstance(value, list):
        return [_jsonable(part) for part in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def _empty_summary(status: str, now: datetime) -> dict[str, Any]:
    return {"status": status, "source": "multi_trigger_candidate_generation", "last_updated": now.isoformat(), "freshness_state": "MISSING", "readiness_state": "UNKNOWN", "truth_state": "UNKNOWN", "counts": {}, "warnings": ["Multi-trigger generator unavailable."], "errors": []}

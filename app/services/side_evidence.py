from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.logging import get_logger
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.system_power import SystemPowerService

logger = get_logger(__name__)

TRUSTED_LINK_CONFIDENCE = 0.8
VALID_SIDE = {"YES", "NO"}
TOKEN_KEYS = {
    "token_id",
    "sample_token_id",
    "asset_id",
    "clob_token_id",
    "clobTokenId",
    "outcome_token_id",
    "outcomeTokenId",
}
TOKEN_LIST_KEYS = {
    "token_ids",
    "clob_token_ids",
    "clobTokenIds",
    "outcome_token_ids",
    "outcomeTokens",
    "tokens",
}


@dataclass(frozen=True)
class SideResolution:
    side: str | None
    source: str | None
    source_id: str | None
    confidence: float
    evidence: dict[str, Any]
    rejected_reason: str | None = None


@dataclass(frozen=True)
class ArbitrationSideEvidence:
    market_id: str | None
    side: str
    side_evidence_score: Decimal
    direction_confidence: Decimal
    evidence_quality: str
    source_support: dict[str, Decimal]
    positive_reasons: list[str]
    negative_reasons: list[str]
    missing_reasons: list[str]
    side_unknown_penalty: Decimal
    already_priced_in_penalty: Decimal

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "market_id": self.market_id,
                "side": self.side,
                "side_evidence_score": self.side_evidence_score,
                "direction_confidence": self.direction_confidence,
                "evidence_quality": self.evidence_quality,
                "source_support": self.source_support,
                "positive_reasons": self.positive_reasons,
                "negative_reasons": self.negative_reasons,
                "missing_reasons": self.missing_reasons,
                "side_unknown_penalty": self.side_unknown_penalty,
                "already_priced_in_penalty": self.already_priced_in_penalty,
            }
        )


class SideEvidenceScorer:
    """Build a side-specific arbitration view without inventing evidence."""

    def score_decision(self, decision: dict[str, Any], *, conn: Any | None = None) -> ArbitrationSideEvidence:
        market_id = _clean(decision.get("market_id"))
        side = str(decision.get("side") or "SIDE_UNKNOWN").upper()
        evidence = decision.get("evidence") if isinstance(decision.get("evidence"), dict) else {}
        source = evidence.get("source_evidence") if isinstance(evidence.get("source_evidence"), dict) else {}
        runtime_side = evidence.get("side_evidence") if isinstance(evidence.get("side_evidence"), dict) else {}
        support: dict[str, Decimal] = {
            "news": Decimal("0"),
            "event": Decimal("0"),
            "ai": Decimal("0"),
            "orderbook": Decimal("0"),
            "liquidity": Decimal("0"),
            "thesis": Decimal("0"),
            "edge": Decimal("0"),
            "exit": Decimal("0"),
            "memory": Decimal("0"),
        }
        positive: list[str] = []
        negative: list[str] = []
        missing: list[str] = []
        confidence = Decimal("0")
        side_unknown_penalty = Decimal("0")
        already_priced_in_penalty = Decimal("0")

        if side not in {"YES", "NO"}:
            negative.append("side is unknown")
            side_unknown_penalty += Decimal("8")
            missing.append("valid YES/NO side")
            return ArbitrationSideEvidence(market_id, side, Decimal("-8"), confidence, "UNKNOWN", support, positive, negative, missing, side_unknown_penalty, already_priced_in_penalty)

        direction = _direction_side(
            runtime_side.get("direction_hint")
            or runtime_side.get("direction_for_market")
            or source.get("direction_hint")
            or source.get("direction_for_market")
            or evidence.get("direction_hint")
            or evidence.get("direction_for_market")
            or ""
        )
        direction_conf = _decimal(
            runtime_side.get("direction_confidence")
            or source.get("direction_confidence")
            or evidence.get("direction_confidence")
            or 0
        )
        if direction == side:
            bonus = Decimal("8") * max(direction_conf, Decimal("0.50"))
            support["event"] += bonus
            confidence = max(confidence, direction_conf)
            positive.append(f"explicit runtime direction supports {side}")
        elif direction in {"YES", "NO"}:
            penalty = Decimal("6") * max(direction_conf, Decimal("0.50"))
            support["event"] -= penalty
            confidence = max(confidence, direction_conf)
            negative.append(f"explicit runtime direction supports {direction}")
        else:
            side_unknown_penalty += Decimal("2")
            missing.append("explicit event/source direction")

        link_support = self._link_side_support(conn, market_id=market_id, side=side) if conn is not None and market_id else {}
        if link_support:
            link_score = _decimal(link_support.get("score"))
            support["memory"] += link_score
            confidence = max(confidence, _decimal(link_support.get("confidence")))
            if link_score > 0:
                positive.append(str(link_support.get("reason") or "side-resolved link supports side"))
            elif link_score < 0:
                negative.append(str(link_support.get("reason") or "opposite side-resolved link is stronger"))
        elif conn is not None:
            missing.append("side-resolved signal/market link")

        ai_support = self._ai_side_support(conn, market_id=market_id, side=side) if conn is not None and market_id else {}
        if ai_support:
            ai_score = _decimal(ai_support.get("score"))
            support["ai"] += ai_score
            confidence = max(confidence, _decimal(ai_support.get("confidence")))
            if ai_score > 0:
                positive.append(str(ai_support.get("reason") or "AI direction hint supports side"))
            elif ai_score < 0:
                negative.append(str(ai_support.get("reason") or "AI direction hint supports opposite side"))
        elif conn is not None:
            missing.append("directional AI insight")

        thesis_side = str(source.get("thesis_side") or runtime_side.get("thesis_side") or "").upper()
        if thesis_side == side:
            support["thesis"] += Decimal("5")
            positive.append("thesis explicitly supports side")
        elif thesis_side in {"YES", "NO"}:
            support["thesis"] -= Decimal("4")
            negative.append(f"thesis explicitly supports {thesis_side}")
        elif str(decision.get("thesis_state") or "").upper() in {"THESIS_SUPPORTED", "VALID", "COMPLETE"}:
            support["thesis"] += Decimal("1")
            missing.append("side-specific thesis direction")
        else:
            missing.append("supported side-specific thesis")

        edge_side = str(source.get("edge_side") or runtime_side.get("edge_side") or "").upper()
        if edge_side == side:
            support["edge"] += Decimal("5")
            positive.append("edge explicitly supports side")
        elif edge_side in {"YES", "NO"}:
            support["edge"] -= Decimal("4")
            negative.append(f"edge explicitly supports {edge_side}")
        elif str(decision.get("edge_state") or "").upper() == "EDGE_SUPPORTED":
            support["edge"] += Decimal("1")
            missing.append("side-specific edge direction")
        else:
            missing.append("supported side-specific edge")

        if str(decision.get("exit_state") or "").upper() in {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}:
            support["exit"] += Decimal("1")
        elif str((evidence.get("paper_defense") or {}).get("exit_plan_type") or "").upper() == "FALLBACK_LEARNING":
            support["exit"] += Decimal("0.5")
        else:
            missing.append("side-specific exit readiness")

        spread = _spread_from_evidence(evidence)
        liquidity = _liquidity_from_evidence(evidence, spread)
        if spread is not None:
            if spread <= Decimal("0.02"):
                support["orderbook"] += Decimal("2")
                positive.append("tight side orderbook spread")
            elif spread <= Decimal("0.05"):
                support["orderbook"] += Decimal("1")
            else:
                support["orderbook"] -= Decimal("1")
                negative.append("wide side orderbook spread")
        else:
            missing.append("side orderbook spread")
        if liquidity is not None:
            if liquidity >= Decimal("0.70"):
                support["liquidity"] += Decimal("2")
                positive.append("good side liquidity")
            elif liquidity < Decimal("0.35"):
                support["liquidity"] -= Decimal("1")
                negative.append("weak side liquidity")
        else:
            missing.append("side liquidity")

        priced_state = str(runtime_side.get("already_priced_in_state") or source.get("already_priced_in_state") or "").upper()
        if priced_state == "YES":
            already_priced_in_penalty += Decimal("2")
            negative.append("side may already be priced in")

        raw_score = sum(support.values()) - side_unknown_penalty - already_priced_in_penalty
        quality = _quality(confidence=confidence, positive=positive, missing=missing, side_unknown_penalty=side_unknown_penalty)
        return ArbitrationSideEvidence(
            market_id=market_id,
            side=side,
            side_evidence_score=raw_score,
            direction_confidence=confidence,
            evidence_quality=quality,
            source_support=support,
            positive_reasons=_dedupe(positive),
            negative_reasons=_dedupe(negative),
            missing_reasons=_dedupe(missing),
            side_unknown_penalty=side_unknown_penalty,
            already_priced_in_penalty=already_priced_in_penalty,
        )

    def _link_side_support(self, conn: Any, *, market_id: str | None, side: str) -> dict[str, Any]:
        if not market_id or not _table_exists(conn, "signal_market_links"):
            return {}
        rows = conn.execute(
            """
            SELECT matched_side, side_confidence, side_evidence_json
            FROM signal_market_links
            WHERE market_id=%s
              AND matched_side IN ('YES','NO')
            ORDER BY side_resolved_at DESC NULLS LAST, updated_at DESC NULLS LAST, id DESC
            LIMIT 12
            """,
            (market_id,),
        ).fetchall()
        if not rows:
            return {}
        same = [_decimal(row.get("side_confidence") or 0) for row in rows if str(row.get("matched_side") or "").upper() == side]
        opposite = [_decimal(row.get("side_confidence") or 0) for row in rows if str(row.get("matched_side") or "").upper() in {"YES", "NO"} and str(row.get("matched_side") or "").upper() != side]
        if same and (not opposite or max(same) >= max(opposite)):
            confidence = max(same)
            return {"score": Decimal("6") * confidence, "confidence": confidence, "reason": f"side-resolved signal link supports {side}"}
        if opposite:
            confidence = max(opposite)
            return {"score": Decimal("-4") * confidence, "confidence": confidence, "reason": "side-resolved signal link favors opposite side"}
        return {}

    def _ai_side_support(self, conn: Any, *, market_id: str | None, side: str) -> dict[str, Any]:
        if not market_id or not _table_exists(conn, "ai_mesh_insights"):
            return {}
        rows = conn.execute(
            """
            SELECT direction_hint, direction_confidence, insight_type
            FROM ai_mesh_insights
            WHERE market_id=%s
              AND direction_hint IN ('YES','NO','NEUTRAL','MIXED','UNKNOWN')
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            (market_id,),
        ).fetchall()
        same: list[Decimal] = []
        opposite: list[Decimal] = []
        unknown = 0
        for row in rows:
            hint = str(row.get("direction_hint") or "UNKNOWN").upper()
            confidence = _decimal(row.get("direction_confidence") or 0)
            if hint == side and confidence > 0:
                same.append(confidence)
            elif hint in {"YES", "NO"} and hint != side and confidence > 0:
                opposite.append(confidence)
            elif hint in {"UNKNOWN", "NEUTRAL", "MIXED"}:
                unknown += 1
        if same and (not opposite or max(same) >= max(opposite)):
            confidence = max(same)
            return {"score": Decimal("3") * confidence, "confidence": confidence, "reason": f"AI direction hint supports {side}"}
        if opposite:
            confidence = max(opposite)
            return {"score": Decimal("-2") * confidence, "confidence": confidence, "reason": "AI direction hint favors opposite side"}
        if unknown:
            return {"score": Decimal("0"), "confidence": Decimal("0"), "reason": "AI insights are SIDE_UNKNOWN/WATCH_ONLY"}
        return {}


class DeterministicSideEvidenceService:
    """Persist auditable YES/NO side only from deterministic token-side evidence."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)

    def run_recovery(self, *, cycle_id: str | None = None, limit: int = 200) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"side_evidence_{uuid4().hex}"
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
        links = self._load_links(limit=limit)
        rejected = Counter()
        token_mappings_checked = 0
        sides_recovered = 0
        side_conflicts = 0
        errors: list[str] = []

        for row in links:
            try:
                resolution = self.resolve_row(row)
                token_mappings_checked += int(resolution.evidence.get("token_mappings_checked") or 0)
                if resolution.side:
                    changed = self._persist_side(row, resolution)
                    sides_recovered += 1 if changed else 0
                else:
                    rejected[resolution.rejected_reason or "UNKNOWN_REJECTED"] += 1
                    self._persist_rejection(row, resolution.rejected_reason or "UNKNOWN_REJECTED", resolution.evidence)
                    if resolution.rejected_reason == "SIDE_CONFLICT":
                        side_conflicts += 1
            except Exception as exc:
                errors.append(f"{row.get('signal_id')}:{type(exc).__name__}:{exc}")
                rejected["ERROR"] += 1
                logger.exception("side_evidence_row_failed signal_id=%s", row.get("signal_id"))

        self._propagate_candidate_sides(limit=limit)
        after = self._counts()
        safety_after = self._safety_counts()
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "DEGRADED" if errors else "OK",
            "links_checked": len(links),
            "candidates_checked": before["candidate_total"],
            "token_mappings_checked": token_mappings_checked,
            "sides_recovered": sides_recovered,
            "sides_rejected": sum(rejected.values()),
            "ambiguous_side_count": rejected.get("AMBIGUOUS_TOKEN_SIDE", 0),
            "missing_token_mapping_count": rejected.get("MISSING_TOKEN_MAPPING", 0),
            "side_conflict_count": side_conflicts,
            "candidates_with_side_before": before["candidates_with_side"],
            "candidates_with_side_after": after["candidates_with_side"],
            "eligible_before": before["eligible_candidates"],
            "eligible_after": after["eligible_candidates"],
            "paper_intents_before": before["paper_intents"],
            "paper_intents_after": after["paper_intents"],
            "paper_positions_delta": max(0, safety_after["paper_positions"] - safety_before["paper_positions"]),
            "live_orders_delta": max(0, safety_after["live_orders"] - safety_before["live_orders"]),
            "real_orders_delta": max(0, safety_after["real_orders"] - safety_before["real_orders"]),
            "top_rejected_reasons": [{"reason": key, "count": count} for key, count in rejected.most_common(10)],
            "error_message": "; ".join(errors) if errors else None,
            "metadata": {
                "deterministic_sources": ["token_id_equals_yes_token_id", "token_id_equals_no_token_id"],
                "invalid_sources_rejected": ["title_sentiment", "fuzzy_text", "default_yes", "default_no", "ambiguous_mapping", "weak_binding", "stale_binding"],
                "candidate_trace": self.candidate_trace(limit=10),
            },
        }
        self._record_run(payload)
        return _json_safe(payload)

    def resolve_row(self, row: dict[str, Any]) -> SideResolution:
        confidence = _float(row.get("link_confidence") or row.get("confidence"))
        if str(row.get("link_status") or "").lower() not in {"confirmed", "suggested"}:
            return _rejected("WEAK_OR_UNTRUSTED_BINDING", confidence, row, [])
        if bool(row.get("is_review_required")) or confidence < TRUSTED_LINK_CONFIDENCE:
            return _rejected("WEAK_OR_UNTRUSTED_BINDING", confidence, row, [])
        if _is_stale(row):
            return _rejected("STALE_BINDING", confidence, row, [])

        yes_token = _clean(row.get("yes_token_id"))
        no_token = _clean(row.get("no_token_id"))
        if not yes_token or not no_token:
            return _rejected("MISSING_TOKEN_MAPPING", confidence, row, [])
        if yes_token == no_token:
            return _rejected("AMBIGUOUS_TOKEN_SIDE", confidence, row, [yes_token])

        tokens = _extract_token_ids(
            row.get("link_evidence_json"),
            row.get("signal_evidence_json"),
            row.get("lineage_json"),
        )
        if not tokens:
            return _rejected("MISSING_TOKEN_EVIDENCE", confidence, row, [])

        matched_sides: dict[str, str] = {}
        for token in tokens:
            if token == yes_token:
                matched_sides[token] = "YES"
            elif token == no_token:
                matched_sides[token] = "NO"
        unique_sides = set(matched_sides.values())
        if len(unique_sides) == 1:
            token = next(iter(matched_sides.keys()))
            side = next(iter(unique_sides))
            evidence = _base_side_evidence(row, tokens)
            evidence.update({
                "matched_token_id": token,
                "matched_side": side,
                "yes_token_id": yes_token,
                "no_token_id": no_token,
                "token_mappings_checked": len(tokens),
                "reason": "token_id_matches_market_yes_no_token",
            })
            return SideResolution(side=side, source="token_id", source_id=token, confidence=max(confidence, TRUSTED_LINK_CONFIDENCE), evidence=evidence)
        if len(unique_sides) > 1:
            return _rejected("AMBIGUOUS_TOKEN_SIDE", confidence, row, tokens)
        return _rejected("TOKEN_NOT_IN_MARKET_YES_NO_MAPPING", confidence, row, tokens)

    def get_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        latest = self._latest_run()
        counts = self._counts()
        power = self._system_power.get_power_state()
        blockers = self._blocker_counts()
        return {
            "mock_data": False,
            "status": "OK" if latest else "EMPTY",
            "side_recovery_allowed": bool(power.get("runtime_work_allowed")),
            "latest_side_recovery_run_at": latest.get("finished_at") if latest else None,
            "latest_side_recovery_status": latest.get("status") if latest else None,
            "latest_run": latest,
            "links_checked": _int((latest or {}).get("links_checked")),
            "token_mappings_checked": _int((latest or {}).get("token_mappings_checked")),
            "sides_recovered": _int((latest or {}).get("sides_recovered")),
            "sides_rejected": _int((latest or {}).get("sides_rejected")),
            "candidates_with_side_before": _int((latest or {}).get("candidates_with_side_before")),
            "candidates_with_side_after": counts["candidates_with_side"],
            "trusted_links_with_matched_side": counts["links_with_matched_side"],
            "bindings_with_matched_side": counts["bindings_with_matched_side"],
            "coordinator_explicit_side_count": counts["coordinator_explicit_side"],
            "brain_output_explicit_side_count": counts["brain_explicit_side"],
            "side_conflicts": _int((latest or {}).get("side_conflict_count")),
            "top_side_rejected_reasons": latest.get("top_rejected_reasons_json") if latest else [],
            "missing_token_mapping_count": _int((latest or {}).get("missing_token_mapping_count")),
            "ambiguous_side_count": _int((latest or {}).get("ambiguous_side_count")),
            "eligible_candidates": counts["eligible_candidates"],
            "paper_intents": counts["paper_intents"],
            "executable_paper_intents": counts["executable_paper_intents"],
            "paper_orders": counts["paper_orders"],
            "paper_fills": counts["paper_fills"],
            "paper_positions": counts["paper_positions"],
            "live_orders": counts["live_orders"],
            "real_orders": counts["real_orders"],
            "no_live_execution": counts["live_orders"] == 0,
            "top_blockers": blockers,
            "candidate_trace": self.candidate_trace(limit=limit),
            "arbitration_side_evidence": self.arbitration_side_evidence(limit=limit),
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def arbitration_side_evidence(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "same_market_side_arbitrations"):
                return []
            rows = conn.execute(
                """
                SELECT
                    market_id,
                    defense_level,
                    yes_side_evidence_score,
                    no_side_evidence_score,
                    yes_evidence_quality,
                    no_evidence_quality,
                    selected_side,
                    rejected_side,
                    outcome,
                    tie_breaker_used,
                    side_unknown_count,
                    missing_side_evidence_json,
                    yes_evidence_json,
                    no_evidence_json,
                    created_at
                FROM same_market_side_arbitrations
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (max(1, min(int(limit or 20), 100)),),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def candidate_trace(self, *, limit: int = 10) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "paper_eligibility_candidates"):
                return []
            rows = conn.execute(
                """
                SELECT
                    pec.eligibility_id AS candidate_id,
                    pec.market_id,
                    m.condition_id,
                    token_side.token_id,
                    m.yes_token_id,
                    m.no_token_id,
                    pec.orderbook_snapshot_id,
                    link.signal_market_link_id,
                    nsb.id AS neuron_signal_binding_id,
                    pec.coordinator_decision_id,
                    pec.brain_output_ids->>0 AS brain_output_id,
                    pec.side AS existing_side,
                    COALESCE(link.matched_side, link.link_matched_side) AS matched_side,
                    link.side_source,
                    link.side_confidence,
                    CASE
                        WHEN pec.side IN ('YES','NO') THEN NULL
                        WHEN COALESCE(link.matched_side, link.link_matched_side) IN ('YES','NO') THEN 'side_available_waiting_for_candidate_recompute'
                        WHEN token_side.token_id IS NULL THEN 'missing_token_evidence'
                        WHEN m.yes_token_id IS NULL OR m.no_token_id IS NULL THEN 'missing_market_yes_no_token_mapping'
                        ELSE 'token_side_not_persisted_or_ambiguous'
                    END AS why_side_is_missing,
                    (token_side.side IN ('YES','NO')) AS deterministic_mapping_exists,
                    CASE
                        WHEN token_side.side IN ('YES','NO') AND COALESCE(link.matched_side, link.link_matched_side) IS NULL THEN 'side_recovery_has_not_persisted_mapping_for_this_link_yet'
                        ELSE NULL
                    END AS why_mapping_not_persisted,
                    rd.risk_status,
                    ep.status AS exit_status,
                    pec.status AS eligibility_status,
                    pi.paper_intent_id,
                    pec.eligibility_blockers,
                    CASE
                        WHEN pec.side IS NULL THEN 'MISSING_SIDE'
                        WHEN NOT COALESCE(pec.risk_approved, false) THEN 'RISK_NOT_APPROVED'
                        WHEN NOT COALESCE(pec.exit_ready, false) THEN 'EXIT_NOT_READY'
                        ELSE 'PAPER_INTENT_GATE'
                    END AS exact_next_blocker
                FROM paper_eligibility_candidates pec
                LEFT JOIN markets_v2 m ON m.market_id = pec.market_id
                LEFT JOIN risk_decisions rd ON rd.risk_decision_id = pec.risk_decision_id
                LEFT JOIN exit_plans ep ON ep.exit_plan_id = pec.exit_plan_id
                LEFT JOIN paper_intents pi ON pi.eligibility_id = pec.eligibility_id
                LEFT JOIN LATERAL (
                    SELECT
                        sml.id AS signal_market_link_id,
                        sml.matched_side,
                        sml.link_evidence_json->>'matched_side' AS link_matched_side,
                        sml.side_source,
                        sml.side_confidence,
                        sml.signal_id
                    FROM signal_market_links sml
                    WHERE sml.market_id = pec.market_id
                      AND sml.signal_id IN (SELECT jsonb_array_elements_text(COALESCE(pec.signal_ids, '[]'::jsonb)))
                      AND sml.link_status IN ('confirmed','suggested')
                      AND COALESCE(sml.is_review_required, false) = false
                      AND COALESCE(sml.link_confidence, sml.confidence, 0) >= %s
                    ORDER BY COALESCE(sml.side_resolved_at, sml.updated_at, sml.created_at) DESC, sml.id DESC
                    LIMIT 1
                ) link ON true
                LEFT JOIN neuron_signal_bindings nsb ON nsb.signal_id = link.signal_id
                LEFT JOIN neuron_signals nsig ON nsig.signal_id = link.signal_id
                LEFT JOIN LATERAL (
                    SELECT
                        token AS token_id,
                        CASE
                            WHEN token = m.yes_token_id THEN 'YES'
                            WHEN token = m.no_token_id THEN 'NO'
                            ELSE NULL
                        END AS side
                    FROM (
                        SELECT jsonb_array_elements_text(
                            COALESCE(
                                jsonb_path_query_array(COALESCE(nsig.evidence_json, '{}'::jsonb), '$.**.sample_token_id'),
                                '[]'::jsonb
                            )
                        ) AS token
                    ) tokens
                    WHERE token IN (m.yes_token_id, m.no_token_id)
                    LIMIT 1
                ) token_side ON true
                ORDER BY pec.updated_at DESC NULLS LAST, pec.created_at DESC, pec.id DESC
                LIMIT %s
                """,
                (TRUSTED_LINK_CONFIDENCE, limit),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _load_links(self, *, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "signal_market_links"):
                return []
            rows = conn.execute(
                """
                SELECT
                    sml.*,
                    m.yes_token_id,
                    m.no_token_id,
                    m.condition_id,
                    m.outcome_tokens_json,
                    ns.evidence_json AS signal_evidence_json,
                    ns.status AS signal_status,
                    ns.expires_at AS signal_expires_at,
                    ns.raw_payload_ref AS signal_raw_payload_ref,
                    nsb.lineage_json,
                    nsb.raw_payload_ref AS binding_raw_payload_ref,
                    nsb.id AS neuron_signal_binding_id,
                    NULL::text AS orderbook_token_id
                FROM signal_market_links sml
                JOIN markets_v2 m ON m.market_id = sml.market_id
                LEFT JOIN neuron_signals ns ON ns.signal_id = sml.signal_id
                LEFT JOIN neuron_signal_bindings nsb ON nsb.signal_id = sml.signal_id
                WHERE sml.link_status IN ('confirmed','suggested')
                  AND COALESCE(sml.is_review_required, false) = false
                  AND COALESCE(sml.link_confidence, sml.confidence, 0) >= %s
                  AND (
                      sml.matched_side IS NULL
                      OR sml.link_evidence_json->>'matched_side' IS NULL
                      OR sml.side_resolved_at IS NULL
                  )
                ORDER BY sml.updated_at DESC NULLS LAST, sml.created_at DESC, sml.id DESC
                LIMIT %s
                """,
                (TRUSTED_LINK_CONFIDENCE, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def _persist_side(self, row: dict[str, Any], resolution: SideResolution) -> bool:
        if not self._factory.enabled or not resolution.side:
            return False
        with self._factory.connect() as conn, conn.transaction():
            updated = conn.execute(
                """
                UPDATE signal_market_links
                SET matched_side = %s,
                    side_source = %s,
                    side_source_id = %s,
                    side_confidence = %s,
                    side_evidence_json = %s,
                    side_resolved_at = now(),
                    side_rejected_reason = NULL,
                    link_evidence_json = COALESCE(link_evidence_json, '{}'::jsonb) || %s::jsonb,
                    updated_at = now()
                WHERE id = %s
                  AND (
                      matched_side IS NULL
                      OR matched_side = %s
                  )
                RETURNING id
                """,
                (
                    resolution.side,
                    resolution.source,
                    resolution.source_id,
                    resolution.confidence,
                    Jsonb(_json_safe(resolution.evidence)),
                    Jsonb({
                        "matched_side": resolution.side,
                        "side_source": resolution.source,
                        "side_source_id": resolution.source_id,
                        "side_confidence": resolution.confidence,
                        "side_evidence": _json_safe(resolution.evidence),
                    }),
                    row["id"],
                    resolution.side,
                ),
            ).fetchone()
            if _table_exists(conn, "neuron_signal_bindings"):
                conn.execute(
                    """
                    UPDATE neuron_signal_bindings
                    SET matched_side = %s,
                        side_source = %s,
                        side_source_id = %s,
                        side_confidence = %s,
                        side_evidence_json = %s,
                        side_resolved_at = now(),
                        side_rejected_reason = NULL
                    WHERE signal_id = %s
                      AND (matched_side IS NULL OR matched_side = %s)
                    """,
                    (
                        resolution.side,
                        resolution.source,
                        resolution.source_id,
                        resolution.confidence,
                        Jsonb(_json_safe(resolution.evidence)),
                        row["signal_id"],
                        resolution.side,
                    ),
                )
        return bool(updated)

    def _persist_rejection(self, row: dict[str, Any], reason: str, evidence: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            conn.execute(
                """
                UPDATE signal_market_links
                SET side_rejected_reason = %s,
                    side_evidence_json = %s,
                    updated_at = now()
                WHERE id = %s
                  AND matched_side IS NULL
                """,
                (reason, Jsonb(_json_safe(evidence)), row["id"]),
            )
            if _table_exists(conn, "neuron_signal_bindings"):
                conn.execute(
                    """
                    UPDATE neuron_signal_bindings
                    SET side_rejected_reason = %s,
                        side_evidence_json = %s
                    WHERE signal_id = %s
                      AND matched_side IS NULL
                    """,
                    (reason, Jsonb(_json_safe(evidence)), row["signal_id"]),
                )

    def _propagate_candidate_sides(self, *, limit: int) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "paper_eligibility_candidates"):
                return 0
            conflicts = conn.execute(
                """
                WITH side_options AS (
                    SELECT
                        pec.eligibility_id,
                        COUNT(DISTINCT sml.matched_side) AS side_count
                    FROM paper_eligibility_candidates pec
                    JOIN LATERAL jsonb_array_elements_text(COALESCE(pec.signal_ids, '[]'::jsonb)) sig(signal_id) ON true
                    JOIN signal_market_links sml
                      ON sml.signal_id = sig.signal_id
                     AND sml.market_id = pec.market_id
                    WHERE sml.matched_side IN ('YES','NO')
                      AND pec.side IS NOT NULL
                      AND pec.side NOT IN ('YES','NO')
                    GROUP BY pec.eligibility_id
                )
                UPDATE paper_eligibility_candidates pec
                SET eligibility_blockers = (
                        SELECT COALESCE(jsonb_agg(DISTINCT item), '[]'::jsonb)
                        FROM (
                            SELECT jsonb_array_elements_text(COALESCE(pec.eligibility_blockers, '[]'::jsonb)) AS item
                            UNION ALL
                            SELECT 'SIDE_CONFLICT'
                        ) blockers
                    ),
                    evidence = COALESCE(pec.evidence, '{}'::jsonb) || jsonb_build_object('side_conflict', true),
                    updated_at = now()
                FROM side_options so
                WHERE pec.eligibility_id = so.eligibility_id
                  AND so.side_count > 1
                RETURNING pec.eligibility_id
                """
            ).fetchall()
            rows = conn.execute(
                """
                WITH side_options AS (
                    SELECT
                        pec.eligibility_id,
                        MAX(sml.matched_side) AS matched_side,
                        COUNT(DISTINCT sml.matched_side) AS side_count,
                        MAX(sml.side_confidence) AS side_confidence,
                        MAX(sml.signal_id) AS source_signal_id
                    FROM paper_eligibility_candidates pec
                    JOIN LATERAL jsonb_array_elements_text(COALESCE(pec.signal_ids, '[]'::jsonb)) sig(signal_id) ON true
                    JOIN signal_market_links sml
                      ON sml.signal_id = sig.signal_id
                     AND sml.market_id = pec.market_id
                    WHERE sml.matched_side IN ('YES','NO')
                      AND (pec.side IS NULL OR pec.side NOT IN ('YES','NO'))
                    GROUP BY pec.eligibility_id
                    HAVING COUNT(DISTINCT sml.matched_side) = 1
                    LIMIT %s
                )
                UPDATE paper_eligibility_candidates pec
                SET side = so.matched_side,
                    evidence = COALESCE(pec.evidence, '{}'::jsonb) || jsonb_build_object(
                        'side_recovery',
                        jsonb_build_object(
                            'side', so.matched_side,
                            'source_component', 'side_evidence_recovery',
                            'source_signal_id', so.source_signal_id,
                            'confidence', so.side_confidence,
                            'recovered_at', now()
                        )
                    ),
                    updated_at = now()
                FROM side_options so
                WHERE pec.eligibility_id = so.eligibility_id
                RETURNING pec.eligibility_id
                """,
                (limit,),
            ).fetchall()
        return len(rows) + len(conflicts)

    def _counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return _zero_counts()
        with self._factory.connect() as conn:
            return {
                "signal_market_links": _count_table(conn, "signal_market_links"),
                "links_with_matched_side": _count_where(conn, "signal_market_links", "matched_side IN ('YES','NO') OR UPPER(COALESCE(link_evidence_json->>'matched_side','')) IN ('YES','NO')"),
                "neuron_signal_bindings": _count_table(conn, "neuron_signal_bindings"),
                "bindings_with_matched_side": _count_where(conn, "neuron_signal_bindings", "matched_side IN ('YES','NO')"),
                "coordinator_explicit_side": _count_where(conn, "coordinator_decisions", "UPPER(COALESCE(metadata_json->>'side', metadata_json->>'expected_move','')) IN ('YES','NO')"),
                "brain_explicit_side": _count_where(conn, "brain_outputs", "UPPER(COALESCE(metadata_json->>'side', metadata_json->>'expected_move','')) IN ('YES','NO')"),
                "candidate_total": _count_table(conn, "paper_eligibility_candidates"),
                "candidates_with_side": _count_where(conn, "paper_eligibility_candidates", "side IN ('YES','NO')"),
                "eligible_candidates": _count_where(conn, "paper_eligibility_candidates", "status = 'ELIGIBLE'"),
                "paper_intents": _count_table(conn, "paper_intents"),
                "executable_paper_intents": _count_where(conn, "paper_intents", "intent_status = 'CREATED' AND intent_type = 'PAPER_ENTRY_INTENT'"),
                "paper_orders": _count_table(conn, "paper_orders"),
                "paper_fills": _count_table(conn, "paper_fills"),
                "paper_positions": _count_table(conn, "paper_positions"),
                "live_orders": _count_table(conn, "live_orders"),
                "real_orders": _count_table(conn, "orders_v2"),
            }

    def _blocker_counts(self) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "paper_eligibility_candidates"):
                return []
            rows = conn.execute(
                """
                SELECT item AS blocker, COUNT(*) AS count
                FROM paper_eligibility_candidates, jsonb_array_elements_text(COALESCE(eligibility_blockers, '[]'::jsonb)) AS item
                GROUP BY item
                ORDER BY count DESC, item ASC
                LIMIT 20
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def _safety_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {"paper_positions": 0, "live_orders": 0, "real_orders": 0}
        with self._factory.connect() as conn:
            return {
                "paper_positions": _count_table(conn, "paper_positions"),
                "live_orders": _count_table(conn, "live_orders"),
                "real_orders": _count_table(conn, "orders_v2"),
            }

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "side_evidence_recovery_runs"):
                return
            conn.execute(
                """
                INSERT INTO side_evidence_recovery_runs (
                    run_id, cycle_id, system_power, started_at, finished_at, status,
                    links_checked, candidates_checked, token_mappings_checked,
                    sides_recovered, sides_rejected, ambiguous_side_count,
                    missing_token_mapping_count, side_conflict_count,
                    candidates_with_side_before, candidates_with_side_after,
                    eligible_before, eligible_after, paper_intents_before,
                    paper_intents_after, paper_positions_delta, live_orders_delta,
                    real_orders_delta, top_rejected_reasons_json, error_message,
                    metadata_json
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(system_power)s, %(started_at)s,
                    %(finished_at)s, %(status)s, %(links_checked)s,
                    %(candidates_checked)s, %(token_mappings_checked)s,
                    %(sides_recovered)s, %(sides_rejected)s,
                    %(ambiguous_side_count)s, %(missing_token_mapping_count)s,
                    %(side_conflict_count)s, %(candidates_with_side_before)s,
                    %(candidates_with_side_after)s, %(eligible_before)s,
                    %(eligible_after)s, %(paper_intents_before)s,
                    %(paper_intents_after)s, %(paper_positions_delta)s,
                    %(live_orders_delta)s, %(real_orders_delta)s,
                    %(top_rejected_reasons_json)s, %(error_message)s,
                    %(metadata_json)s
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                {
                    **payload,
                    "top_rejected_reasons_json": Jsonb(_json_safe(payload.get("top_rejected_reasons") or [])),
                    "metadata_json": Jsonb(_json_safe(payload.get("metadata") or {})),
                },
            )

    def _existing_for_cycle(self, cycle_id: str | None) -> dict[str, Any] | None:
        if not cycle_id or not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "side_evidence_recovery_runs"):
                return None
            row = conn.execute(
                "SELECT * FROM side_evidence_recovery_runs WHERE cycle_id = %s ORDER BY id DESC LIMIT 1",
                (cycle_id,),
            ).fetchone()
            return dict(row) if row else None

    def _latest_run(self) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "side_evidence_recovery_runs"):
                return None
            row = conn.execute("SELECT * FROM side_evidence_recovery_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _blocked_payload(self, run_id: str, cycle_id: str | None, system_power: str, started_at: datetime, reason: str) -> dict[str, Any]:
        counts = self._counts()
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "BLOCKED",
            "links_checked": 0,
            "candidates_checked": 0,
            "token_mappings_checked": 0,
            "sides_recovered": 0,
            "sides_rejected": 0,
            "ambiguous_side_count": 0,
            "missing_token_mapping_count": 0,
            "side_conflict_count": 0,
            "candidates_with_side_before": counts["candidates_with_side"],
            "candidates_with_side_after": counts["candidates_with_side"],
            "eligible_before": counts["eligible_candidates"],
            "eligible_after": counts["eligible_candidates"],
            "paper_intents_before": counts["paper_intents"],
            "paper_intents_after": counts["paper_intents"],
            "paper_positions_delta": 0,
            "live_orders_delta": 0,
            "real_orders_delta": 0,
            "top_rejected_reasons": [{"reason": reason, "count": 1}],
            "error_message": reason,
            "metadata": {"blocked_reason": reason},
        }


def _extract_token_ids(*sources: Any) -> list[str]:
    found: list[str] = []
    for source in sources:
        _extract_recursive(source, found)
    deduped: list[str] = []
    for token in found:
        clean = _clean(token)
        if clean and clean not in deduped:
            deduped.append(clean)
    return deduped


def _extract_recursive(value: Any, found: list[str], key: str | None = None) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _extract_recursive(child_value, found, str(child_key))
        return
    if isinstance(value, list):
        for item in value:
            _extract_recursive(item, found, key)
        return
    if key in TOKEN_KEYS or key in TOKEN_LIST_KEYS:
        found.append(str(value))


def _is_stale(row: dict[str, Any]) -> bool:
    if str(row.get("signal_status") or "").upper() == "STALE":
        return True
    expires_at = row.get("signal_expires_at")
    if isinstance(expires_at, datetime):
        expires = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        return expires <= datetime.now(UTC)
    return False


def _rejected(reason: str, confidence: float, row: dict[str, Any], tokens: list[str]) -> SideResolution:
    evidence = _base_side_evidence(row, tokens)
    evidence.update({"rejected_reason": reason, "token_mappings_checked": len(tokens)})
    return SideResolution(side=None, source=None, source_id=None, confidence=confidence, evidence=evidence, rejected_reason=reason)


def _base_side_evidence(row: dict[str, Any], tokens: list[str]) -> dict[str, Any]:
    return {
        "signal_id": row.get("signal_id"),
        "market_id": row.get("market_id"),
        "condition_id": row.get("condition_id"),
        "token_ids_observed": tokens,
        "link_id": row.get("id"),
        "link_method": row.get("link_method"),
        "link_status": row.get("link_status"),
        "source": "deterministic_side_evidence_recovery",
        "resolved_from": "market_yes_no_token_mapping",
    }


def _zero_counts() -> dict[str, int]:
    return {
        "signal_market_links": 0,
        "links_with_matched_side": 0,
        "neuron_signal_bindings": 0,
        "bindings_with_matched_side": 0,
        "coordinator_explicit_side": 0,
        "brain_explicit_side": 0,
        "candidate_total": 0,
        "candidates_with_side": 0,
        "eligible_candidates": 0,
        "paper_intents": 0,
        "executable_paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "live_orders": 0,
        "real_orders": 0,
    }


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"])


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _direction_side(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"YES", "NO"}:
        return text
    if text == "SIDE_DIRECTIONAL_YES":
        return "YES"
    if text == "SIDE_DIRECTIONAL_NO":
        return "NO"
    return "UNKNOWN"


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _spread_from_evidence(evidence: dict[str, Any]) -> Decimal | None:
    explicit = _decimal_or_none(evidence.get("orderbook_spread"))
    if explicit is not None:
        return explicit
    bid = _decimal_or_none(evidence.get("orderbook_best_bid"))
    ask = _decimal_or_none(evidence.get("orderbook_best_ask"))
    if bid is None or ask is None:
        return None
    return abs(ask - bid)


def _liquidity_from_evidence(evidence: dict[str, Any], spread: Decimal | None) -> Decimal | None:
    source = evidence.get("source_evidence") if isinstance(evidence.get("source_evidence"), dict) else {}
    raw = _decimal_or_none(evidence.get("orderbook_liquidity_score") or source.get("orderbook_liquidity_score"))
    if raw is not None:
        return max(Decimal("0"), min(Decimal("1"), raw))
    if spread is None:
        return None
    return max(Decimal("0"), min(Decimal("1"), Decimal("1") - (spread / Decimal("0.20"))))


def _quality(*, confidence: Decimal, positive: list[str], missing: list[str], side_unknown_penalty: Decimal) -> str:
    if confidence >= Decimal("0.75") and positive:
        return "DIRECT"
    if positive and side_unknown_penalty <= Decimal("2"):
        return "INDIRECT"
    if positive or len(missing) <= 2:
        return "WEAK"
    return "UNKNOWN"


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value.__class__.__name__ == "Decimal":
        return float(value)
    return value

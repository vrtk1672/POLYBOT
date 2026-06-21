from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.data_foundation.market_rules_store import MarketRulesStore
from app.db.connection import DatabaseConnectionFactory
from app.rules_neuron.service import RulesNeuronService
from app.services.neuron_signals import NeuronSignalService


PRIORITY_MARKET_FAMILIES = ("POLITICS_MACRO", "SPORTS")
PRIORITY_FAMILY_MATCH_TERMS = ("politics", "political", "election", "macro", "economy", "fed", "sports")


class RulesResolutionTruthService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def refresh_rules_truth(
        self,
        *,
        limit: int = 50,
        market_families: tuple[str, ...] | None = PRIORITY_MARKET_FAMILIES,
        allow_ai: bool = False,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DISABLED", "refreshed_rules": 0, "analyzed": 0, "failed": 0, "items": []}
        families = tuple(market_families or ())
        store = MarketRulesStore(connection_factory=self._factory)
        analyzer = RulesNeuronService(connection_factory=self._factory)
        refreshed = 0
        analyzed = 0
        failed = 0
        items: list[dict[str, Any]] = []
        with self._factory.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    m.market_id,
                    m.question,
                    m.category,
                    m.market_family,
                    m.raw_market_json,
                    mr.rules_text,
                    mr.resolution_source_url,
                    mr.settlement_method,
                    mr.deadline_at
                FROM markets_v2 m
                LEFT JOIN market_rules mr ON mr.market_id = m.market_id
                WHERE active = true
                  AND (
                    %(families_empty)s
                    OR UPPER(COALESCE(m.market_family, '')) = ANY(%(families)s)
                    OR LOWER(COALESCE(m.market_family, '')) LIKE ANY(%(family_patterns)s)
                    OR LOWER(COALESCE(m.category, '')) LIKE ANY(%(family_patterns)s)
                    OR LOWER(COALESCE(m.question, '')) LIKE ANY(%(family_patterns)s)
                  )
                ORDER BY m.last_seen_at DESC, m.id DESC
                LIMIT %(limit)s
                """,
                {
                    "families_empty": not families,
                    "families": list(families),
                    "family_patterns": [f"%{term}%" for term in PRIORITY_FAMILY_MATCH_TERMS],
                    "limit": limit,
                },
            ).fetchall()
        for row in rows:
            raw = dict(row.get("raw_market_json") or {})
            raw.setdefault("question", row.get("question"))
            raw.setdefault("category", row.get("category"))
            raw.setdefault("market_family", row.get("market_family"))
            if row.get("rules_text"):
                raw.setdefault("description", row.get("rules_text"))
            if row.get("resolution_source_url"):
                raw.setdefault("resolutionSourceUrl", row.get("resolution_source_url"))
            if row.get("settlement_method"):
                raw.setdefault("settlementMethod", row.get("settlement_method"))
            if row.get("deadline_at"):
                raw.setdefault("deadline", row.get("deadline_at"))
            try:
                record = store.extract_rules(raw, market_id=row["market_id"])
                _rule_row, changed = store.upsert_rules(record)
                refreshed += int(bool(changed))
                result = analyzer.analyze_market_rules(
                    row["market_id"],
                    allow_ai=allow_ai,
                    log_no_trade_block=record.resolution_source_hard_block,
                )
                analyzed += 1
                items.append(
                    {
                        "market_id": row["market_id"],
                        "resolution_source_status": record.resolution_source_status,
                        "resolution_source_type": record.resolution_source_type,
                        "recommendation": result.recommendation,
                        "changed": changed,
                    }
                )
            except Exception as exc:
                failed += 1
                items.append({"market_id": row["market_id"], "error": str(exc)})
        return {
            "status": "OK" if failed == 0 else "DEGRADED",
            "selected_market_families": list(families),
            "candidate_count": len(rows),
            "refreshed_rules": refreshed,
            "analyzed": analyzed,
            "failed": failed,
            "items": items,
        }

    def get_dashboard_rules_status(self, *, limit: int = 25) -> dict[str, Any]:
        updated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return {
                "status": "NO_DATA",
                "mock_data": False,
                "stale": False,
                "updated_at": updated_at,
                "selected_market_families": list(PRIORITY_MARKET_FAMILIES),
                "coverage": _empty_coverage(),
                "markets": [],
                "warnings": ["database persistence disabled"],
            }
        try:
            with self._factory.connect() as conn:
                coverage = _coverage(conn)
                rows = conn.execute(
                    """
                    WITH latest_rules AS (
                        SELECT DISTINCT ON (market_id) *
                        FROM rules_analysis
                        ORDER BY market_id, created_at DESC, id DESC
                    ),
                    latest_wording AS (
                        SELECT DISTINCT ON (market_id) *
                        FROM wording_risk_scores
                        ORDER BY market_id, created_at DESC, id DESC
                    ),
                    block_counts AS (
                        SELECT
                            market_id,
                            COUNT(*) FILTER (WHERE active = true) AS active_block_count,
                            COUNT(*) FILTER (WHERE active = true AND severity = 'BLOCKING') AS blocking_count,
                            jsonb_agg(
                                jsonb_build_object('block_type', block_type, 'severity', severity, 'reason', reason)
                                ORDER BY created_at DESC
                            ) FILTER (WHERE active = true) AS active_blocks_json
                        FROM compliance_blocks
                        GROUP BY market_id
                    )
                    SELECT
                        m.market_id,
                        m.question,
                        m.category,
                        m.market_family,
                        m.resolution_source AS market_resolution_source,
                        m.close_time,
                        mr.rules_text IS NOT NULL AND mr.rules_text <> '' AS rules_text_present,
                        COALESCE(mr.resolution_source, m.resolution_source) AS resolution_source,
                        mr.resolution_source_url,
                        mr.resolution_source_status,
                        mr.resolution_source_type,
                        mr.resolution_source_evidence,
                        mr.resolution_source_confidence,
                        mr.resolution_source_penalty,
                        mr.resolution_source_hard_block,
                        mr.deadline_at,
                        lr.rules_analysis_id,
                        lr.recommendation,
                        lr.compliance_status,
                        lr.wording_risk,
                        lr.dispute_risk,
                        lr.resolution_clarity,
                        lr.source_verification_status,
                        lr.cannot_trade_reason,
                        lw.total_wording_risk,
                        lw.risk_terms_json,
                        COALESCE(bc.active_block_count, 0) AS active_block_count,
                        COALESCE(bc.blocking_count, 0) AS blocking_count,
                        COALESCE(bc.active_blocks_json, '[]'::jsonb) AS active_blocks_json,
                        lr.created_at AS analyzed_at
                    FROM markets_v2 m
                    LEFT JOIN market_rules mr ON mr.market_id = m.market_id
                    LEFT JOIN latest_rules lr ON lr.market_id = m.market_id
                    LEFT JOIN latest_wording lw ON lw.market_id = m.market_id
                    LEFT JOIN block_counts bc ON bc.market_id = m.market_id
                    WHERE m.active = true
                    ORDER BY
                        CASE
                            WHEN lr.recommendation = 'NO_TRADE' THEN 0
                            WHEN lr.compliance_status = 'WARNING' THEN 1
                            WHEN lr.rules_analysis_id IS NULL THEN 2
                            ELSE 3
                        END,
                        GREATEST(COALESCE(lr.wording_risk, 0), COALESCE(lr.dispute_risk, 0)) DESC,
                        m.last_seen_at DESC NULLS LAST
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
        except Exception as exc:
            return {
                "status": "ERROR",
                "mock_data": False,
                "stale": False,
                "updated_at": updated_at,
                "selected_market_families": list(PRIORITY_MARKET_FAMILIES),
                "coverage": _empty_coverage(),
                "markets": [],
                "warnings": [str(exc)],
            }

        warnings = _warnings(coverage)
        status = "DEGRADED" if warnings else "OK"
        serialized_markets = [_serialize_market(row) for row in rows]
        _record_rules_signals_safely(self._factory, serialized_markets)
        return {
            "status": status,
            "mock_data": False,
            "stale": False,
            "updated_at": updated_at,
            "selected_market_families": list(PRIORITY_MARKET_FAMILIES),
            "coverage": coverage,
            "markets": serialized_markets,
            "warnings": warnings,
        }


def _record_rules_signals_safely(
    factory: DatabaseConnectionFactory,
    markets: list[dict[str, Any]],
) -> None:
    if not factory.enabled:
        return
    try:
        NeuronSignalService(connection_factory=factory).record_rules_status_signals(markets)
    except Exception:
        return


def _coverage(conn) -> dict[str, Any]:  # noqa: ANN001
    row = conn.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE m.active = true) AS active_markets,
            COUNT(*) FILTER (WHERE m.active = true AND (mr.rules_text IS NOT NULL AND mr.rules_text <> '')) AS with_rules,
            COUNT(*) FILTER (WHERE m.active = true AND (mr.rules_text IS NULL OR mr.rules_text = '')) AS missing_rules,
            COUNT(*) FILTER (WHERE m.active = true AND COALESCE(mr.resolution_source_status, 'MISSING') = 'EXPLICIT') AS explicit_resolution_source,
            COUNT(*) FILTER (WHERE m.active = true AND COALESCE(mr.resolution_source_status, 'MISSING') = 'RULES_DERIVED') AS rules_derived_resolution_source,
            COUNT(*) FILTER (WHERE m.active = true AND COALESCE(mr.resolution_source_status, 'MISSING') = 'FAMILY_DERIVED') AS family_derived_resolution_source,
            COUNT(*) FILTER (WHERE m.active = true AND COALESCE(mr.resolution_source_status, 'MISSING') = 'AMBIGUOUS') AS ambiguous_resolution_source,
            COUNT(*) FILTER (WHERE m.active = true AND COALESCE(mr.resolution_source_status, 'MISSING') = 'MISSING') AS missing_resolution_source,
            COUNT(DISTINCT lr.market_id) FILTER (WHERE m.active = true) AS analyzed_markets,
            COUNT(*) FILTER (WHERE lr.recommendation = 'NO_TRADE') AS no_trade_rule_blocks,
            COUNT(*) FILTER (WHERE lr.recommendation = 'PENALIZE_HEAVILY') AS penalize_heavily_count,
            COUNT(*) FILTER (WHERE lr.wording_risk >= 0.75) AS high_wording_risk,
            COUNT(*) FILTER (WHERE lr.dispute_risk >= 0.75) AS high_dispute_risk,
            MAX(lr.created_at) AS latest_rules_analysis_at
        FROM markets_v2 m
        LEFT JOIN market_rules mr ON mr.market_id = m.market_id
        LEFT JOIN (
            SELECT DISTINCT ON (market_id) *
            FROM rules_analysis
            ORDER BY market_id, created_at DESC, id DESC
        ) lr ON lr.market_id = m.market_id
        """
    ).fetchone()
    active = int(row["active_markets"] or 0)
    analyzed = int(row["analyzed_markets"] or 0)
    return {
        "active_markets": active,
        "with_rules": int(row["with_rules"] or 0),
        "missing_rules": int(row["missing_rules"] or 0),
        "explicit_resolution_source_count": int(row["explicit_resolution_source"] or 0),
        "rules_derived_resolution_source_count": int(row["rules_derived_resolution_source"] or 0),
        "family_derived_resolution_source_count": int(row["family_derived_resolution_source"] or 0),
        "derived_resolution_source_count": int(row["rules_derived_resolution_source"] or 0)
        + int(row["family_derived_resolution_source"] or 0),
        "ambiguous_resolution_source_count": int(row["ambiguous_resolution_source"] or 0),
        "missing_resolution_source": int(row["missing_resolution_source"] or 0),
        "missing_resolution_source_count": int(row["missing_resolution_source"] or 0),
        "analyzed_markets": analyzed,
        "coverage_pct": round((analyzed / active) * 100, 2) if active else 0.0,
        "analysis_coverage_pct": round((analyzed / active) * 100, 2) if active else 0.0,
        "no_trade_rule_blocks": int(row["no_trade_rule_blocks"] or 0),
        "hard_no_trade_count": int(row["no_trade_rule_blocks"] or 0),
        "penalize_heavily_count": int(row["penalize_heavily_count"] or 0),
        "high_wording_risk": int(row["high_wording_risk"] or 0),
        "high_dispute_risk": int(row["high_dispute_risk"] or 0),
        "latest_rules_analysis_at": _iso(row["latest_rules_analysis_at"]),
    }


def _warnings(coverage: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if coverage["active_markets"] and coverage["analyzed_markets"] < coverage["active_markets"]:
        warnings.append("some active markets do not have rules/resolution analysis yet")
    if coverage["missing_rules"]:
        warnings.append("one or more active markets are missing rules text")
    if coverage["missing_resolution_source"]:
        warnings.append("one or more active markets are missing resolution source")
    if coverage["ambiguous_resolution_source_count"]:
        warnings.append("one or more active markets have ambiguous resolution source")
    return warnings


def _serialize_market(row: dict[str, Any]) -> dict[str, Any]:
    rules_present = bool(row.get("rules_text_present"))
    resolution_present = bool(row.get("resolution_source") or row.get("resolution_source_url"))
    source_status = row.get("resolution_source_status") or ("EXPLICIT" if resolution_present else "MISSING")
    resolution_present = source_status in {"EXPLICIT", "RULES_DERIVED", "FAMILY_DERIVED", "AMBIGUOUS"}
    analysis_present = bool(row.get("rules_analysis_id"))
    no_trade_blocked = row.get("recommendation") == "NO_TRADE" or int(row.get("blocking_count") or 0) > 0
    return {
        "market_id": row.get("market_id"),
        "question": row.get("question"),
        "category": row.get("category"),
        "market_family": row.get("market_family"),
        "rules_text_present": rules_present,
        "resolution_source_present": resolution_present,
        "resolution_source_status": source_status,
        "resolution_source_type": row.get("resolution_source_type") or source_status,
        "resolution_source_name": row.get("resolution_source"),
        "resolution_source_url": row.get("resolution_source_url"),
        "resolution_source_evidence": row.get("resolution_source_evidence"),
        "resolution_source_confidence": _float(row.get("resolution_source_confidence")) or 0.0,
        "resolution_source_penalty": _float(row.get("resolution_source_penalty")) or 0.0,
        "resolution_source_hard_block": bool(row.get("resolution_source_hard_block")),
        "evidence": row.get("resolution_source_evidence"),
        "penalty": _float(row.get("resolution_source_penalty")) or 0.0,
        "hard_block": bool(row.get("resolution_source_hard_block")) or no_trade_blocked,
        "deadline_present": row.get("deadline_at") is not None or row.get("close_time") is not None,
        "rules_analysis_present": analysis_present,
        "rules_analysis_id": row.get("rules_analysis_id"),
        "recommendation": row.get("recommendation") or ("REVIEW_REQUIRED" if not analysis_present else None),
        "compliance_status": row.get("compliance_status") or "UNKNOWN",
        "wording_risk": _float(row.get("wording_risk") or row.get("total_wording_risk")),
        "dispute_risk": _float(row.get("dispute_risk")),
        "resolution_clarity": _float(row.get("resolution_clarity")),
        "source_verification_status": row.get("source_verification_status") or "UNKNOWN",
        "risk_terms": row.get("risk_terms_json") or [],
        "active_blocks": row.get("active_blocks_json") or [],
        "no_trade_blocked": no_trade_blocked,
        "cannot_trade_reason": row.get("cannot_trade_reason"),
        "analyzed_at": _iso(row.get("analyzed_at")),
    }


def _empty_coverage() -> dict[str, Any]:
    return {
        "active_markets": 0,
        "with_rules": 0,
        "missing_rules": 0,
        "explicit_resolution_source_count": 0,
        "rules_derived_resolution_source_count": 0,
        "family_derived_resolution_source_count": 0,
        "derived_resolution_source_count": 0,
        "ambiguous_resolution_source_count": 0,
        "missing_resolution_source": 0,
        "missing_resolution_source_count": 0,
        "analyzed_markets": 0,
        "coverage_pct": 0.0,
        "analysis_coverage_pct": 0.0,
        "no_trade_rule_blocks": 0,
        "hard_no_trade_count": 0,
        "penalize_heavily_count": 0,
        "high_wording_risk": 0,
        "high_dispute_risk": 0,
        "latest_rules_analysis_at": None,
    }


def _float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value

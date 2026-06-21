from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.link_coverage import SignalLinkCoverageAnalysis, SuggestedMarketLink, link_coverage_from_row, suggested_market_link_from_row
from app.repositories.link_coverage_repository import LinkCoverageRepository


class LinkCoverageService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: LinkCoverageRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or LinkCoverageRepository()

    def analyze_signal(
        self,
        signal_id: str,
        *,
        create_suggestions: bool = True,
        apply_safe_links: bool = False,
    ) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn, conn.transaction():
            context = self._repository.get_signal_context(conn, signal_id)
            if not context:
                return None
            analysis = self._analyze_context(conn, context)
            row = self._repository.upsert_analysis(conn, analysis)
            suggestions = []
            applied = False
            if create_suggestions and analysis.suggested_market_id:
                suggestion = _suggestion_from_analysis(analysis)
                suggestions.append(self._repository.upsert_suggestion(conn, suggestion))
            if apply_safe_links and _can_apply_safe_link(analysis):
                applied = self._repository.apply_safe_signal_market_link(
                    conn,
                    signal_id=analysis.signal_id,
                    market_id=str(analysis.suggested_market_id),
                    reason=analysis.suggested_market_reason or "explicit existing market_id link coverage safe apply",
                )
                if applied:
                    context = self._repository.get_signal_context(conn, signal_id)
                    if context:
                        analysis = self._analyze_context(conn, context)
                        row = self._repository.upsert_analysis(conn, analysis)
        return _analysis_response(row, suggestions, applied=applied)

    def analyze_recent_signals(
        self,
        *,
        limit: int = 100,
        create_suggestions: bool = True,
        apply_safe_links: bool = False,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "OK", "mock_data": False, "analyzed": 0, "created_or_updated": 0, "applied_links": 0, "summary": _empty_summary()}
        with self._factory.connect() as conn, conn.transaction():
            signal_ids = self._repository.list_recent_signal_ids(conn, limit=limit)
            updated = 0
            applied_links = 0
            for signal_id in signal_ids:
                context = self._repository.get_signal_context(conn, signal_id)
                if not context:
                    continue
                analysis = self._analyze_context(conn, context)
                self._repository.upsert_analysis(conn, analysis)
                if create_suggestions and analysis.suggested_market_id:
                    self._repository.upsert_suggestion(conn, _suggestion_from_analysis(analysis))
                if apply_safe_links and _can_apply_safe_link(analysis):
                    applied = self._repository.apply_safe_signal_market_link(
                        conn,
                        signal_id=analysis.signal_id,
                        market_id=str(analysis.suggested_market_id),
                        reason=analysis.suggested_market_reason or "explicit existing market_id link coverage safe apply",
                    )
                    applied_links += 1 if applied else 0
                updated += 1
            summary = self._repository.summary(conn, limit=20)
            status = "OK" if updated == len(signal_ids) else "PARTIAL"
            self._repository.record_run(conn, requested_limit=limit, summary={**summary, "analyzed_count": updated}, status=status)
        return {
            "status": status,
            "mock_data": False,
            "analyzed": len(signal_ids),
            "created_or_updated": updated,
            "applied_links": applied_links,
            "summary": _summary_response(summary),
        }

    def get_link_coverage(self, signal_id: str, *, include_suggestions: bool = True) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_analysis(conn, signal_id)
            suggestions = self._repository.list_suggestions(conn, signal_id) if row and include_suggestions else []
        return _analysis_response(row, suggestions) if row else None

    def list_link_coverage(
        self,
        *,
        limit: int = 50,
        linkability_status: str | None = None,
        reason: str | None = None,
        include_suggestions: bool = False,
    ) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_analyses(conn, limit=limit, linkability_status=linkability_status, reason=reason)
            suggestions_by_signal: dict[str, list[dict[str, Any]]] = {}
            if include_suggestions:
                for row in rows:
                    suggestions_by_signal[str(row["signal_id"])] = self._repository.list_suggestions(conn, str(row["signal_id"]))
        return [_analysis_response(row, suggestions_by_signal.get(str(row["signal_id"]), [])) for row in rows]

    def get_link_coverage_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        return _summary_response(summary)

    def _analyze_context(self, conn, row: dict[str, Any]) -> SignalLinkCoverageAnalysis:
        signal_id = str(row["signal_id"])
        linked_to_market = bool(row.get("linked_to_market"))
        linked_to_position = bool(row.get("linked_to_position"))
        has_market_id = bool(row.get("market_id"))
        has_entity = bool(row.get("has_signal_entity")) or bool(row.get("has_event_entity")) or int(row.get("entity_count") or 0) > 0
        has_source = bool(row.get("binding_source_name") or row.get("source_name"))
        has_rules_context = _has_rules_context(row)
        has_producer = bool(row.get("producer_name"))
        has_raw_payload_ref = bool(row.get("binding_raw_payload_ref") or row.get("raw_payload_ref"))
        is_dry_run = bool(row.get("quality_is_dry_run_generated")) or str(row.get("producer_name") or "").lower() == "mesh_dry_run" or str(row.get("generated_from") or "").lower() == "mesh_dry_run"
        is_runtime = bool(row.get("quality_is_runtime_generated")) or (bool(row.get("signal_created_at")) and not is_dry_run)
        is_stale = bool(row.get("quality_is_stale")) or _is_stale(row)
        missing = _missing_fields(
            has_market_id=has_market_id,
            has_entity=has_entity,
            has_source=has_source,
            has_rules_context=has_rules_context,
            has_producer=has_producer,
            has_raw_payload_ref=has_raw_payload_ref,
        )
        reasons = list(missing)
        suggested_market_id = None
        suggested_confidence = None
        suggested_reason = None
        has_matcher_evidence = False
        can_auto_link = False

        if linked_to_market or linked_to_position:
            status = "LINKED"
            primary = "ALREADY_LINKED"
            action = "NONE"
            reasons = ["ALREADY_LINKED"]
        elif is_stale:
            status = "STALE"
            primary = "STALE_SIGNAL"
            action = "BLOCKED_STALE"
            reasons = _prepend_reason(reasons, primary)
        elif is_dry_run:
            status = "DRY_RUN_ONLY"
            primary = "DRY_RUN_ONLY"
            action = "BLOCKED_DRY_RUN_ONLY"
            reasons = _prepend_reason(reasons, primary)
        elif has_market_id and self._repository.market_exists(conn, str(row["market_id"])):
            status = "LINKABLE"
            primary = "MISSING_MARKET_LINK"
            action = "SAFE_TO_LINK_EXISTING_MARKET_ID"
            suggested_market_id = str(row["market_id"])
            suggested_confidence = 0.95
            suggested_reason = "Signal has explicit market_id that exists in local market truth."
            has_matcher_evidence = True
            can_auto_link = True
            reasons = _prepend_reason(reasons, primary)
        elif not has_market_id:
            candidate = self._repository.find_entity_market_candidate(conn, signal_id) if has_entity else None
            if candidate:
                confidence = float(candidate["confidence"] or 0.0)
                has_matcher_evidence = True
                suggested_market_id = str(candidate["market_id"])
                suggested_confidence = confidence
                suggested_reason = f"Entity-market local link candidate via {candidate.get('entity_id') or 'entity'}."
                if confidence >= 0.70:
                    status = "LINKABLE"
                    primary = "MISSING_MARKET_ID"
                    action = "REVIEW_ONLY"
                else:
                    status = "NEEDS_MORE_EVIDENCE"
                    primary = "WEAK_MATCHER_EVIDENCE"
                    action = "BLOCKED_WEAK_EVIDENCE"
                reasons = _prepend_reason(reasons, primary)
            elif not has_entity:
                status = "NOT_LINKABLE"
                primary = "MISSING_ENTITY"
                action = "BLOCKED_MISSING_ENTITY"
                reasons = _prepend_reason(reasons, primary)
            else:
                status = "NEEDS_MORE_EVIDENCE"
                primary = "NO_MATCHER_AVAILABLE"
                action = "BLOCKED_NO_MATCHER"
                reasons = _prepend_reason(reasons, primary)
        elif not has_source:
            status = "NOT_LINKABLE"
            primary = "MISSING_SOURCE"
            action = "BLOCKED_MISSING_SOURCE"
            reasons = _prepend_reason(reasons, primary)
        else:
            status = "NEEDS_MORE_EVIDENCE"
            primary = "NO_MATCHER_AVAILABLE"
            action = "BLOCKED_NO_MATCHER"
            reasons = _prepend_reason(reasons, primary)

        if not linked_to_position:
            reasons = _append_unique(reasons, "POSITION_LINK_MISSING")

        return SignalLinkCoverageAnalysis(
            signal_id=signal_id,
            is_linked_to_market=linked_to_market,
            is_linked_to_position=linked_to_position,
            is_unlinked=not (linked_to_market or linked_to_position),
            linkability_status=status,
            primary_unlinked_reason=primary,
            unlinked_reasons=reasons or ["UNKNOWN"],
            missing_fields=missing,
            has_market_id=has_market_id,
            has_entity=has_entity,
            has_source=has_source,
            has_rules_context=has_rules_context,
            has_producer=has_producer,
            has_matcher_evidence=has_matcher_evidence,
            has_raw_payload_ref=has_raw_payload_ref,
            is_dry_run_generated=is_dry_run,
            is_runtime_generated=is_runtime,
            is_stale=is_stale,
            suggested_market_id=suggested_market_id,
            suggested_market_confidence=suggested_confidence,
            suggested_market_reason=suggested_reason,
            suggested_link_action=action,
            can_auto_link=can_auto_link,
            can_feed_brain_after_link=bool(row.get("quality_can_feed_brain")) or status in {"LINKABLE", "LINKED"},
            can_feed_paper_after_link=False,
            analysis_status="OK",
            analyzed_at=datetime.now(UTC),
        )


def _suggestion_from_analysis(analysis: SignalLinkCoverageAnalysis) -> SuggestedMarketLink:
    if analysis.suggested_link_action == "SAFE_TO_LINK_EXISTING_MARKET_ID":
        status = "SAFE_CANDIDATE"
    elif analysis.suggested_link_action == "BLOCKED_WEAK_EVIDENCE":
        status = "REJECTED_WEAK_EVIDENCE"
    elif analysis.suggested_link_action == "BLOCKED_DRY_RUN_ONLY":
        status = "REJECTED_DRY_RUN_ONLY"
    elif analysis.suggested_link_action == "BLOCKED_STALE":
        status = "REJECTED_STALE"
    else:
        status = "REVIEW_ONLY"
    return SuggestedMarketLink(
        signal_id=analysis.signal_id,
        suggested_market_id=str(analysis.suggested_market_id),
        confidence=float(analysis.suggested_market_confidence or 0.0),
        evidence={
            "suggested_link_action": analysis.suggested_link_action,
            "primary_unlinked_reason": analysis.primary_unlinked_reason,
            "unlinked_reasons": analysis.unlinked_reasons,
        },
        reason=analysis.suggested_market_reason or analysis.primary_unlinked_reason,
        suggestion_status=status,
        created_by="link_coverage_analyzer",
    )


def _can_apply_safe_link(analysis: SignalLinkCoverageAnalysis) -> bool:
    return (
        analysis.can_auto_link
        and analysis.suggested_link_action == "SAFE_TO_LINK_EXISTING_MARKET_ID"
        and bool(analysis.suggested_market_id)
        and not analysis.is_stale
        and not analysis.is_dry_run_generated
        and analysis.suggested_market_confidence is not None
        and analysis.suggested_market_confidence >= 0.95
    )


def _summary_response(summary: dict[str, Any]) -> dict[str, Any]:
    total = int(summary.get("total_analyzed") or 0)
    total_signals = int(summary.get("total_signals") or 0)
    linked = int(summary.get("linked_signals") or 0)
    unlinked = int(summary.get("unlinked_signals") or 0)
    status = "EMPTY"
    if total:
        status = "DEGRADED" if unlinked or int(summary.get("needs_more_evidence") or 0) or int(summary.get("stale_unlinked") or 0) else "OK"
    return {
        "status": status,
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "total_signals": total_signals,
        "total_analyzed": total,
        "linked_signals": linked,
        "unlinked_signals": unlinked,
        "link_coverage_ratio": round(linked / total_signals, 4) if total_signals else 0.0,
        "coverage_pct": round(linked / total_signals * 100, 2) if total_signals else 0.0,
        "linkable_signals": int(summary.get("linkable_signals") or 0),
        "non_linkable_signals": int(summary.get("non_linkable_signals") or 0),
        "needs_more_evidence": int(summary.get("needs_more_evidence") or 0),
        "stale_unlinked": int(summary.get("stale_unlinked") or 0),
        "dry_run_only_unlinked": int(summary.get("dry_run_only_unlinked") or 0),
        "unlinked_by_reason": [_json_safe(row) for row in summary.get("unlinked_by_reason", [])],
        "suggested_market_links_count": int(summary.get("suggested_market_links_count") or 0),
        "safe_to_link_count": int(summary.get("safe_to_link_count") or 0),
        "applied_suggestions_count": int(summary.get("applied_suggestions_count") or 0),
        "weak_suggestions_count": int(summary.get("weak_suggestions_count") or 0),
        "last_analysis_at": _json_safe(summary.get("last_analysis_at")),
        "analysis_status": "ERROR" if int(summary.get("error_count") or 0) else status,
        "latest_analyses": [_json_safe(link_coverage_from_row(row).to_api_dict()) for row in summary.get("latest_analyses", [])],
        "paper_ready": False,
    }


def _analysis_response(row: dict[str, Any], suggestions: list[dict[str, Any]], *, applied: bool = False) -> dict[str, Any]:
    item = link_coverage_from_row(dict(row)).to_api_dict()
    item["suggestions"] = [_json_safe(suggested_market_link_from_row(dict(suggestion)).to_api_dict()) for suggestion in suggestions]
    item["applied_link"] = applied
    return item


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "OK",
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "total_signals": 0,
        "total_analyzed": 0,
        "linked_signals": 0,
        "unlinked_signals": 0,
        "link_coverage_ratio": 0.0,
        "coverage_pct": 0.0,
        "linkable_signals": 0,
        "non_linkable_signals": 0,
        "needs_more_evidence": 0,
        "stale_unlinked": 0,
        "dry_run_only_unlinked": 0,
        "unlinked_by_reason": [],
        "suggested_market_links_count": 0,
        "safe_to_link_count": 0,
        "applied_suggestions_count": 0,
        "weak_suggestions_count": 0,
        "last_analysis_at": None,
        "analysis_status": "OK",
        "latest_analyses": [],
        "paper_ready": False,
    }


def _has_rules_context(row: dict[str, Any]) -> bool:
    text = " ".join(str(row.get(field) or "").lower() for field in ("neuron", "event_type", "source_name", "binding_source_name", "generated_from"))
    evidence = row.get("evidence_json") if isinstance(row.get("evidence_json"), dict) else {}
    return "rules" in text or "resolution" in text or bool({"rules", "resolution", "resolution_status"}.intersection(evidence))


def _missing_fields(**flags: bool) -> list[str]:
    mapping = {
        "has_market_id": "MISSING_MARKET_ID",
        "has_entity": "MISSING_ENTITY",
        "has_source": "MISSING_SOURCE",
        "has_rules_context": "MISSING_RULES_CONTEXT",
        "has_producer": "MISSING_PRODUCER",
        "has_raw_payload_ref": "MISSING_RAW_PAYLOAD_REF",
    }
    return [reason for field, reason in mapping.items() if not flags.get(field)]


def _is_stale(row: dict[str, Any]) -> bool:
    if str(row.get("signal_status") or "").upper() == "STALE":
        return True
    now = datetime.now(UTC)
    expires_at = row.get("expires_at")
    if isinstance(expires_at, datetime):
        expires = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        if expires <= now:
            return True
    created_at = row.get("signal_created_at")
    stale_after = row.get("stale_after_seconds")
    if isinstance(created_at, datetime) and stale_after is not None:
        created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
        return (now - created).total_seconds() >= int(stale_after)
    return False


def _prepend_reason(reasons: list[str], reason: str) -> list[str]:
    return [reason, *[item for item in reasons if item != reason]]


def _append_unique(reasons: list[str], reason: str) -> list[str]:
    return reasons if reason in reasons else [*reasons, reason]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value

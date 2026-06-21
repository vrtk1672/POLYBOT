from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.signal_market_binding import SignalMarketBindingCandidate, SignalMarketBindingRun
from app.repositories.signal_market_binding_repository import SignalMarketBindingRepository
from app.services.link_coverage import LinkCoverageService
from app.services.mesh_blockers import MeshBlockersService
from app.services.signal_processing import SignalProcessingService
from app.services.signal_quality import SignalQualityService


class SignalMarketBindingRecoveryService:
    """Evidence-only market binding recovery for Signals."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: SignalMarketBindingRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or SignalMarketBindingRepository()

    def recover_market_bindings(
        self,
        *,
        limit: int = 200,
        apply_safe_links: bool = True,
        create_suggestions: bool = True,
        include_stale: bool = False,
        include_dry_run: bool = False,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"market_binding_{uuid4().hex}"
        safety_before = _safety_counts(self._factory)
        links_before = _count_table(self._factory, "signal_market_links")
        candidates: list[SignalMarketBindingCandidate] = []
        linked_signal_ids: list[str] = []
        errors: list[str] = []

        counters = {
            "signals_checked": 0,
            "runtime_signals_checked": 0,
            "already_linked": 0,
            "safe_links_created": 0,
            "suggestions_created": 0,
            "remained_unlinked": 0,
            "stale_skipped": 0,
            "dry_run_skipped": 0,
            "weak_evidence_skipped": 0,
            "ambiguous_candidates": 0,
        }

        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                rows = self._repository.list_unlinked_signal_contexts(conn, limit=limit)
                counters["signals_checked"] = len(rows)
                for row in rows:
                    signal_id = str(row["signal_id"])
                    is_runtime = _is_runtime_signal(row)
                    is_dry_run = _is_dry_run_signal(row)
                    is_stale = _is_stale_signal(row)
                    counters["runtime_signals_checked"] += 1 if is_runtime else 0
                    try:
                        if is_stale and not include_stale:
                            candidate = _candidate(signal_id, None, 0.0, "Signal is stale; skipped from auto-linking.", "BLOCKED_STALE", row)
                            counters["stale_skipped"] += 1
                            counters["remained_unlinked"] += 1
                        elif is_dry_run and not include_dry_run:
                            candidate = _candidate(signal_id, None, 0.0, "Signal is dry-run generated; skipped from production link recovery.", "BLOCKED_DRY_RUN", row)
                            counters["dry_run_skipped"] += 1
                            counters["remained_unlinked"] += 1
                        else:
                            candidate = self._classify_candidate(conn, row)
                            if candidate.action == "AUTO_LINKED":
                                if apply_safe_links:
                                    created = self._repository.apply_link(
                                        conn,
                                        signal_id=signal_id,
                                        market_id=str(candidate.candidate_market_id),
                                        confidence=candidate.confidence,
                                        reason=candidate.reason,
                                        evidence=candidate.evidence,
                                        method=str(candidate.evidence.get("method") or "deterministic"),
                                        runtime_link=is_runtime,
                                    )
                                    if created:
                                        counters["safe_links_created"] += 1
                                        linked_signal_ids.append(signal_id)
                                    else:
                                        counters["already_linked"] += 1
                                    candidate.action = "AUTO_LINKED"
                                else:
                                    candidate.action = "REVIEW_ONLY"
                                    counters["suggestions_created"] += 1
                                    counters["remained_unlinked"] += 1
                                    if create_suggestions and candidate.candidate_market_id:
                                        self._repository.upsert_suggestion(
                                            conn,
                                            signal_id=signal_id,
                                            market_id=str(candidate.candidate_market_id),
                                            confidence=candidate.confidence,
                                            reason=candidate.reason,
                                            evidence=candidate.evidence,
                                            status="SAFE_CANDIDATE",
                                        )
                            elif candidate.action == "REVIEW_ONLY":
                                counters["suggestions_created"] += 1
                                counters["remained_unlinked"] += 1
                                if create_suggestions and candidate.candidate_market_id:
                                    self._repository.upsert_suggestion(
                                        conn,
                                        signal_id=signal_id,
                                        market_id=str(candidate.candidate_market_id),
                                        confidence=candidate.confidence,
                                        reason=candidate.reason,
                                        evidence=candidate.evidence,
                                        status="REVIEW_ONLY",
                                    )
                            else:
                                counters["remained_unlinked"] += 1
                                if candidate.action == "BLOCKED_WEAK_EVIDENCE":
                                    counters["weak_evidence_skipped"] += 1
                                if candidate.action == "BLOCKED_AMBIGUOUS":
                                    counters["ambiguous_candidates"] += 1
                        candidates.append(candidate)
                        self._repository.record_candidate(conn, run_id=run_id, candidate=candidate)
                    except Exception as exc:
                        errors.append(f"{signal_id}:{type(exc).__name__}:{exc}")
                        candidate = _candidate(signal_id, None, 0.0, f"Binding analysis error: {type(exc).__name__}", "ERROR", row)
                        candidates.append(candidate)
                        self._repository.record_candidate(conn, run_id=run_id, candidate=candidate)

        for signal_id in linked_signal_ids:
            SignalQualityService(connection_factory=self._factory).evaluate_signal_quality(signal_id)
            SignalProcessingService(connection_factory=self._factory).evaluate_signal_processing(signal_id, refresh_quality=False)
            LinkCoverageService(connection_factory=self._factory).analyze_signal(signal_id, create_suggestions=True, apply_safe_links=False)

        links_after = _count_table(self._factory, "signal_market_links")
        safety_after = _safety_counts(self._factory)
        status = "ERROR" if errors and not candidates else "PARTIAL" if errors else "OK"
        run = SignalMarketBindingRun(
            run_id=run_id,
            status=status,
            **counters,
            signal_market_links_before=links_before,
            signal_market_links_after=links_after,
            paper_ready_before=False,
            paper_ready_after=False,
            orders_created=max(0, safety_after["orders"] - safety_before["orders"]),
            order_intents_created=max(0, safety_after["order_intents"] - safety_before["order_intents"]),
            fills_created=max(0, safety_after["fills"] - safety_before["fills"]),
            positions_created=max(0, safety_after["positions"] - safety_before["positions"]),
            live_actions_created=max(0, safety_after["live_actions"] - safety_before["live_actions"]),
            candidates=candidates,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error_summary="; ".join(errors) if errors else None,
        )

        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.record_run(conn, run)

        return _with_blockers(run.to_api_dict(), self._factory)

    def get_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        total = int(summary.get("total_signals") or 0)
        links = int(summary.get("signal_market_links") or 0)
        latest = summary.get("latest_run") or {}
        by_action = {str(row.get("action")): int(row.get("count") or 0) for row in summary.get("by_action", [])}
        blockers = MeshBlockersService(connection_factory=self._factory).get_mesh_blockers(limit=limit)
        return {
            "mock_data": False,
            "status": "OK" if latest else "EMPTY",
            "latest_run": _json_safe(latest) if latest else None,
            "total_signals": total,
            "runtime_signals": int(summary.get("runtime_signals") or 0),
            "signal_market_links": links,
            "linked_runtime_signals": int(summary.get("linked_runtime_signals") or 0),
            "unlinked_runtime_signals": int(summary.get("unlinked_runtime_signals") or 0),
            "safe_links_created_last_run": int(latest.get("safe_links_created") or 0) if latest else 0,
            "suggestions_created_last_run": int(latest.get("suggestions_created") or 0) if latest else 0,
            "review_only_candidates": by_action.get("REVIEW_ONLY", 0),
            "blocked_weak_evidence": by_action.get("BLOCKED_WEAK_EVIDENCE", 0),
            "blocked_stale": by_action.get("BLOCKED_STALE", 0),
            "blocked_dry_run": by_action.get("BLOCKED_DRY_RUN", 0),
            "ambiguous_candidates": by_action.get("BLOCKED_AMBIGUOUS", 0),
            "link_coverage_ratio": round(links / total, 4) if total else 0.0,
            "latest_candidates": [_json_safe(row) for row in summary.get("latest_candidates", [])],
            "paper_ready": False,
            "orders_created": int(latest.get("orders_created") or 0) if latest else 0,
            "order_intents_created": int(latest.get("order_intents_created") or 0) if latest else 0,
            "fills_created": int(latest.get("fills_created") or 0) if latest else 0,
            "positions_created": int(latest.get("positions_created") or 0) if latest else 0,
            "live_actions_created": int(latest.get("live_actions_created") or 0) if latest else 0,
            "remaining_blockers": blockers.get("blocked_by", []),
            "analysis_status": "OK" if latest else "EMPTY",
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _classify_candidate(self, conn: Any, row: dict[str, Any]) -> SignalMarketBindingCandidate:
        signal_id = str(row["signal_id"])
        signal_market_id = _clean(row.get("market_id"))
        base_evidence = _base_evidence(row)

        if signal_market_id:
            market = self._repository.market_by_id(conn, signal_market_id)
            if market:
                evidence = {**base_evidence, "method": "explicit_market_id", "market_id": signal_market_id}
                return SignalMarketBindingCandidate(
                    signal_id=signal_id,
                    candidate_market_id=signal_market_id,
                    confidence=0.95,
                    evidence=evidence,
                    reason="Signal has explicit market_id that exists in local markets_v2 truth.",
                    action="AUTO_LINKED",
                )

        token_ids = _extract_values(row, {"token_id", "sample_token_id", "asset_id"})
        token_matches: list[dict[str, Any]] = []
        for token_id in token_ids:
            token_matches.extend(self._repository.markets_by_token_id(conn, token_id))
        unique_token_markets = _unique_markets(token_matches)
        if len(unique_token_markets) == 1:
            market = unique_token_markets[0]
            evidence = {**base_evidence, "method": "unique_token_id", "token_ids": token_ids, "matched_side": market.get("matched_side")}
            return SignalMarketBindingCandidate(
                signal_id=signal_id,
                candidate_market_id=str(market["market_id"]),
                confidence=0.90,
                evidence=evidence,
                reason="Signal token_id uniquely maps to one local markets_v2 market.",
                action="AUTO_LINKED",
            )
        if len(unique_token_markets) > 1:
            return _candidate(signal_id, None, 0.0, "Token evidence matched multiple local markets.", "BLOCKED_AMBIGUOUS", row, {"token_ids": token_ids})

        condition_ids = _extract_values(row, {"condition_id"})
        condition_matches: list[dict[str, Any]] = []
        for condition_id in condition_ids:
            condition_matches.extend(self._repository.markets_by_condition_id(conn, condition_id))
        unique_condition_markets = _unique_markets(condition_matches)
        if len(unique_condition_markets) == 1:
            market = unique_condition_markets[0]
            evidence = {**base_evidence, "method": "unique_condition_id", "condition_ids": condition_ids}
            return SignalMarketBindingCandidate(
                signal_id=signal_id,
                candidate_market_id=str(market["market_id"]),
                confidence=0.85,
                evidence=evidence,
                reason="Signal condition_id uniquely maps to one local markets_v2 market.",
                action="AUTO_LINKED",
            )
        if len(unique_condition_markets) > 1:
            return _candidate(signal_id, None, 0.0, "Condition evidence matched multiple local markets.", "BLOCKED_AMBIGUOUS", row, {"condition_ids": condition_ids})

        slugs = _extract_values(row, {"slug", "market_slug", "market_ref"})
        slug_matches: list[dict[str, Any]] = []
        for slug in slugs:
            slug_matches.extend(self._repository.markets_by_slug(conn, slug))
        unique_slug_markets = _unique_markets(slug_matches)
        if len(unique_slug_markets) == 1:
            market = unique_slug_markets[0]
            evidence = {**base_evidence, "method": "exact_slug", "slugs": slugs}
            return SignalMarketBindingCandidate(
                signal_id=signal_id,
                candidate_market_id=str(market["market_id"]),
                confidence=0.80,
                evidence=evidence,
                reason="Signal slug/ref exactly matches one local markets_v2 slug.",
                action="AUTO_LINKED",
            )
        if len(unique_slug_markets) > 1:
            return _candidate(signal_id, None, 0.0, "Slug evidence matched multiple local markets.", "BLOCKED_AMBIGUOUS", row, {"slugs": slugs})

        if signal_market_id:
            return _candidate(signal_id, signal_market_id, 0.0, "Signal market_id is not present in local markets_v2 truth.", "BLOCKED_MISSING_MARKET", row)
        return _candidate(signal_id, None, 0.0, "Signal lacks deterministic local market, token, condition, or exact slug evidence.", "BLOCKED_WEAK_EVIDENCE", row)


def _candidate(
    signal_id: str,
    market_id: str | None,
    confidence: float,
    reason: str,
    action: str,
    row: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> SignalMarketBindingCandidate:
    return SignalMarketBindingCandidate(
        signal_id=signal_id,
        candidate_market_id=market_id,
        confidence=confidence,
        evidence={**_base_evidence(row), **(extra or {})},
        reason=reason,
        action=action,
    )


def _base_evidence(row: dict[str, Any]) -> dict[str, Any]:
    evidence = row.get("evidence_json") if isinstance(row.get("evidence_json"), dict) else {}
    return {
        "signal_id": row.get("signal_id"),
        "neuron": row.get("neuron"),
        "source_name": row.get("source_name"),
        "producer_name": row.get("producer_name"),
        "raw_payload_ref": row.get("binding_raw_payload_ref") or row.get("raw_payload_ref"),
        "generated_from": row.get("generated_from"),
        "signal_market_id": row.get("market_id"),
        "runtime_generated": _is_runtime_signal(row),
        "dry_run_generated": _is_dry_run_signal(row),
        "source_details": evidence.get("details") if isinstance(evidence.get("details"), dict) else {},
    }


def _extract_values(row: dict[str, Any], keys: set[str]) -> list[str]:
    values: list[str] = []
    for source in (row.get("evidence_json"), row.get("lineage_json")):
        _extract_recursive(source, keys, values)
    for key in keys:
        value = row.get(key)
        if value is not None:
            values.append(str(value))
    deduped: list[str] = []
    for value in values:
        normalized = _clean(value)
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _extract_recursive(value: Any, keys: set[str], values: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in keys and item not in (None, ""):
                values.append(str(item))
            _extract_recursive(item, keys, values)
    elif isinstance(value, list):
        for item in value:
            _extract_recursive(item, keys, values)


def _unique_markets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        seen.setdefault(str(row["market_id"]), row)
    return list(seen.values())


def _is_runtime_signal(row: dict[str, Any]) -> bool:
    evidence = row.get("evidence_json") if isinstance(row.get("evidence_json"), dict) else {}
    return str(evidence.get("generated_by") or "").lower() == "runtime" or evidence.get("is_runtime_generated") is True


def _is_dry_run_signal(row: dict[str, Any]) -> bool:
    evidence = row.get("evidence_json") if isinstance(row.get("evidence_json"), dict) else {}
    return bool(row.get("quality_is_dry_run_generated")) or str(evidence.get("generated_by") or "").lower() in {"dry_run", "mesh_dry_run"} or evidence.get("is_dry_run_generated") is True


def _is_stale_signal(row: dict[str, Any]) -> bool:
    if bool(row.get("quality_is_stale")) or bool(row.get("link_coverage_is_stale")):
        return True
    if str(row.get("signal_status") or "").upper() == "STALE":
        return True
    if str(row.get("processing_state") or "").upper() == "STALE":
        return True
    now = datetime.now(UTC)
    expires_at = row.get("expires_at")
    if isinstance(expires_at, datetime):
        expires = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        if expires <= now:
            return True
    created_at = row.get("created_at")
    stale_after = row.get("stale_after_seconds")
    if isinstance(created_at, datetime) and stale_after is not None:
        created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
        return (now - created).total_seconds() >= int(stale_after)
    return False


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _count_table(factory: DatabaseConnectionFactory, table: str) -> int:
    if not factory.enabled:
        return 0
    try:
        with factory.connect() as conn:
            row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
            if not row or not row["table_name"]:
                return 0
            return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
    except Exception:
        return 0


def _safety_counts(factory: DatabaseConnectionFactory) -> dict[str, int]:
    return {
        "orders": _count_table(factory, "paper_orders") + _count_table(factory, "shadow_orders") + _count_table(factory, "live_orders"),
        "order_intents": _count_table(factory, "order_intents"),
        "fills": _count_table(factory, "fills_v2"),
        "positions": _count_table(factory, "positions"),
        "live_actions": _count_table(factory, "live_orders"),
    }


def _with_blockers(payload: dict[str, Any], factory: DatabaseConnectionFactory) -> dict[str, Any]:
    blockers = MeshBlockersService(connection_factory=factory).get_mesh_blockers(limit=50)
    payload["remaining_blockers"] = blockers.get("blocked_by", [])
    return payload


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value.__class__.__name__ == "Decimal":
        return float(value)
    return value


def _empty_summary() -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": "OK",
        "latest_run": None,
        "total_signals": 0,
        "runtime_signals": 0,
        "signal_market_links": 0,
        "linked_runtime_signals": 0,
        "unlinked_runtime_signals": 0,
        "safe_links_created_last_run": 0,
        "suggestions_created_last_run": 0,
        "review_only_candidates": 0,
        "blocked_weak_evidence": 0,
        "blocked_stale": 0,
        "blocked_dry_run": 0,
        "ambiguous_candidates": 0,
        "link_coverage_ratio": 0.0,
        "paper_ready": False,
        "orders_created": 0,
        "order_intents_created": 0,
        "fills_created": 0,
        "positions_created": 0,
        "live_actions_created": 0,
        "remaining_blockers": [],
        "analysis_status": "OK",
        "last_updated": datetime.now(UTC).isoformat(),
    }

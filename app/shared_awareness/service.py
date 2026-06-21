from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.services.system_power import SystemPowerService
from app.shared_awareness.repository import SharedAwarenessRepository, table_columns, table_exists
from app.shared_awareness.types import (
    ALL_DOMAINS,
    DOMAIN_STATE_COLUMNS,
    EVENT_DOMAIN_MAP,
    FRESHNESS_WINDOWS,
    NEURON_DOMAIN_MAP,
    AwarenessDomain,
    DomainStatus,
)


class SharedAwarenessBlocked(RuntimeError):
    pass


class SharedAwarenessService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: SharedAwarenessRepository | None = None,
        system_power: SystemPowerService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or SharedAwarenessRepository()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)

    def refresh_session(self, session_id: str) -> dict[str, Any]:
        self._assert_system_on()
        with self._factory.connect() as conn, conn.transaction():
            return self.refresh_session_with_conn(conn, session_id)

    def refresh_sessions(self, session_ids: list[str]) -> dict[str, Any]:
        self._assert_system_on()
        refreshed: list[str] = []
        with self._factory.connect() as conn, conn.transaction():
            for session_id in dict.fromkeys(session_ids):
                result = self.refresh_session_with_conn(conn, session_id)
                if result.get("status") == "OK":
                    refreshed.append(session_id)
        return {"mock_data": False, "status": "OK", "sessions_refreshed": len(refreshed), "session_ids": refreshed}

    def refresh_session_with_conn(self, conn: Any, session_id: str) -> dict[str, Any]:
        if not table_exists(conn, "mesh_shared_awareness"):
            return {"mock_data": False, "status": "MISSING_TABLES", "session_id": session_id}
        session = self._repository.get_session(conn, session_id)
        if not session:
            return {"mock_data": False, "status": "SESSION_NOT_FOUND", "session_id": session_id}
        awareness, sources = self._build_awareness(conn, session)
        row = self._repository.upsert_awareness(conn, awareness=awareness, sources=sources)
        try:
            from app.capital_brain.service import CapitalBrainService

            CapitalBrainService(connection_factory=self._factory).evaluate_session_with_conn(conn, session_id)
        except Exception:
            if table_exists(conn, "capital_brain_evaluations"):
                raise
        try:
            from app.position_awareness.service import PositionAwarenessService

            PositionAwarenessService(connection_factory=self._factory).refresh_session_with_conn(conn, session_id)
        except Exception:
            if table_exists(conn, "position_awareness"):
                raise
        try:
            from app.multi_brain_consumption.service import MultiBrainConsumptionService

            MultiBrainConsumptionService(connection_factory=self._factory).consume_session_with_conn(conn, session_id)
        except Exception:
            if table_exists(conn, "mesh_brain_opinions"):
                raise
        try:
            from app.position_awareness.service import PositionAwarenessService

            PositionAwarenessService(connection_factory=self._factory).refresh_session_with_conn(conn, session_id)
        except Exception:
            if table_exists(conn, "position_awareness"):
                raise
        return {
            "mock_data": False,
            "status": "OK",
            "session_id": session_id,
            "awareness_id": row["awareness_id"],
            "domains_present": len([domain for domain in ALL_DOMAINS if awareness[DOMAIN_STATE_COLUMNS[domain]]["status"] in {DomainStatus.PRESENT.value, DomainStatus.PARTIAL.value}]),
            "domains_missing": len(awareness["missing_domains_json"]),
            "domains_stale": len(awareness["stale_domains_json"]),
        }

    def process_active_sessions(self, *, limit: int = 100) -> dict[str, Any]:
        self._assert_system_on()
        with self._factory.connect() as conn, conn.transaction():
            sessions = self._repository.list_sessions(conn, limit=limit)
            refreshed = 0
            for session in sessions:
                result = self.refresh_session_with_conn(conn, session["session_id"])
                refreshed += int(result.get("status") == "OK")
        return {"mock_data": False, "status": "OK", "sessions_checked": len(sessions), "sessions_refreshed": refreshed}

    def dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard("DB_UNAVAILABLE")
        with self._factory.connect() as conn:
            if not table_exists(conn, "mesh_shared_awareness"):
                return _empty_dashboard("MISSING_TABLES")
            rows = self._repository.all_awareness_rows(conn)
            latest = self._repository.dashboard_rows(conn, limit=limit)
        total = len(rows)
        active = len([row for row in rows if row.get("status") in {"ACTIVE", "PARTIAL"}])
        avg_completeness = round(sum(float(row.get("completeness_score") or 0) for row in rows) / total, 4) if total else 0.0
        missing_counts = _domain_counter(rows, "missing_domains_json")
        stale_counts = _domain_counter(rows, "stale_domains_json")
        return {
            "mock_data": False,
            "status": "OK",
            "generated_at": datetime.now(UTC).isoformat(),
            "total_awareness_records": total,
            "active_awareness_records": active,
            "avg_completeness_score": avg_completeness,
            "sessions_with_news": _sessions_with_domain(rows, AwarenessDomain.NEWS),
            "sessions_with_liquidity": _sessions_with_domain(rows, AwarenessDomain.LIQUIDITY),
            "sessions_with_rules": _sessions_with_domain(rows, AwarenessDomain.RULES),
            "sessions_with_risk": _sessions_with_domain(rows, AwarenessDomain.RISK),
            "sessions_with_exit": _sessions_with_domain(rows, AwarenessDomain.EXIT),
            "sessions_with_capital": _sessions_with_domain(rows, AwarenessDomain.CAPITAL),
            "missing_domain_counts": missing_counts,
            "stale_domain_counts": stale_counts,
            "latest_awareness": [_json_safe(row) for row in latest],
        }

    def detail(self, session_id: str, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DB_UNAVAILABLE", "session_id": session_id}
        with self._factory.connect() as conn:
            if not table_exists(conn, "mesh_shared_awareness"):
                return {"mock_data": False, "status": "MISSING_TABLES", "session_id": session_id}
            payload = self._repository.detail(conn, session_id, limit=limit)
        if payload is None:
            return {"mock_data": False, "status": "NOT_FOUND", "session_id": session_id}
        payload.update({"mock_data": False, "status": "OK", "generated_at": datetime.now(UTC).isoformat()})
        return _json_safe(payload)

    def _build_awareness(self, conn: Any, session: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        buckets: dict[AwarenessDomain, list[dict[str, Any]]] = {domain: [] for domain in ALL_DOMAINS}
        sources: list[dict[str, Any]] = []

        for event in self._repository.linked_events(conn, session["session_id"], limit=500):
            for domain in EVENT_DOMAIN_MAP.get(str(event.get("event_type") or ""), ()):
                self._add_source(
                    buckets,
                    domain=domain,
                    source_table=str(event.get("source_table") or "neural_events"),
                    source_record_id=str(event.get("source_record_id") or event.get("event_id")),
                    source_component=str(event.get("source_component") or "Neural Event"),
                    source_created_at=_as_aware(event.get("created_at")),
                    summary=f"{event.get('event_type')} from {event.get('source_component')}",
                    confidence=_confidence(event, default=0.65),
                    payload=event.get("payload_json") or {},
                )

        self._collect_neuron_intelligence(conn, session, buckets)
        self._collect_market_sources(conn, session, buckets)
        self._collect_candidate_sources(conn, session, buckets)
        self._collect_position_sources(conn, session, buckets)
        self._collect_global_capital(conn, session, buckets)

        domain_states: dict[AwarenessDomain, dict[str, Any]] = {}
        for domain in ALL_DOMAINS:
            state = self._domain_state(domain, buckets[domain])
            domain_states[domain] = state
            for ref in state["source_refs"]:
                sources.append(
                    {
                        "source_domain": domain.value,
                        "source_table": ref["source_table"],
                        "source_record_id": ref["source_record_id"],
                        "source_component": ref.get("source_component"),
                        "source_created_at": ref.get("source_created_at"),
                        "freshness_status": ref["freshness_status"],
                        "contribution_summary": ref["summary"],
                    }
                )

        missing = [domain.value for domain, state in domain_states.items() if state["status"] == DomainStatus.MISSING.value]
        stale = [domain.value for domain, state in domain_states.items() if state["status"] == DomainStatus.STALE.value]
        non_missing = [state for state in domain_states.values() if state["status"] != DomainStatus.MISSING.value]
        confidence_values = [float(state["confidence"] or 0) for state in non_missing]
        completeness = round(len(non_missing) / len(ALL_DOMAINS), 4)
        confidence = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0.0
        freshness_status = _overall_freshness(domain_states)
        status = "EMPTY" if not non_missing else "PARTIAL" if missing else "ACTIVE"
        awareness_id = f"shared_awareness_{session['session_id']}"
        awareness = {
            "awareness_id": awareness_id,
            "session_id": session["session_id"],
            "session_type": session["session_type"],
            "market_id": session.get("market_id"),
            "candidate_id": session.get("candidate_id"),
            "position_id": session.get("position_id"),
            "status": status,
            "freshness_status": freshness_status,
            "completeness_score": completeness,
            "confidence_score": confidence,
            "missing_domains_json": missing,
            "stale_domains_json": stale,
            "source_counts_json": {domain.value: domain_states[domain]["source_count"] for domain in ALL_DOMAINS},
        }
        for domain, column in DOMAIN_STATE_COLUMNS.items():
            awareness[column] = domain_states[domain]
        return awareness, _dedupe_sources(sources)

    def _collect_neuron_intelligence(self, conn: Any, session: dict[str, Any], buckets: dict[AwarenessDomain, list[dict[str, Any]]]) -> None:
        rows = self._fetch_entity_rows(
            conn,
            "neuron_intelligence_evidence",
            session,
            timestamp_column="created_at",
            limit=25,
        )
        for row in rows:
            domain = NEURON_DOMAIN_MAP.get(str(row.get("neuron_name") or "").lower())
            if not domain:
                continue
            self._add_source(
                buckets,
                domain=domain,
                source_table="neuron_intelligence_evidence",
                source_record_id=str(row.get("evidence_id") or row.get("id")),
                source_component=f"{row.get('neuron_name')} Neuron",
                source_created_at=_as_aware(row.get("created_at")),
                summary=str(row.get("human_message") or f"{row.get('neuron_name')} evidence {row.get('status') or row.get('decision')}"),
                confidence=_confidence(row, default=0.7),
                payload=row,
            )

    def _collect_market_sources(self, conn: Any, session: dict[str, Any], buckets: dict[AwarenessDomain, list[dict[str, Any]]]) -> None:
        market_id = session.get("market_id")
        if not market_id:
            return
        for row in self._fetch_rows(conn, "orderbook_snapshots", "market_id = %s", [market_id], "snapshot_at", limit=3):
            status = "STALE" if row.get("is_stale") else None
            self._add_source(buckets, domain=AwarenessDomain.ORDERBOOK, source_table="orderbook_snapshots", source_record_id=str(row.get("orderbook_snapshot_id") or row.get("id")), source_component="Orderbook", source_created_at=_as_aware(row.get("snapshot_at") or row.get("created_at")), summary=f"orderbook snapshot status={row.get('snapshot_status')}", confidence=0.8, payload=row, freshness_override=status)
        for row in self._fetch_rows(conn, "trusted_orderbook_evidence_links", "market_id = %s", [market_id], "updated_at", limit=5):
            confidence = 0.85 if row.get("trusted") else 0.45
            status = "PARTIAL" if not row.get("trusted") else None
            for domain in (AwarenessDomain.ORDERBOOK, AwarenessDomain.LIQUIDITY):
                self._add_source(buckets, domain=domain, source_table="trusted_orderbook_evidence_links", source_record_id=str(row.get("link_id") or row.get("id")), source_component="Orderbook", source_created_at=_as_aware(row.get("updated_at") or row.get("created_at")), summary=f"trusted orderbook {row.get('trust_status') or row.get('trust_reason')}", confidence=confidence, payload=row, freshness_override=status)
        for row in self._fetch_rows(conn, "rules_analysis", "market_id = %s", [market_id], "created_at", limit=3):
            self._add_source(buckets, domain=AwarenessDomain.RULES, source_table="rules_analysis", source_record_id=str(row.get("rules_analysis_id") or row.get("id")), source_component="Rules", source_created_at=_as_aware(row.get("created_at")), summary=f"rules recommendation={row.get('recommendation')}", confidence=_confidence(row, key="resolution_clarity", default=0.7), payload=row)
        for row in self._fetch_rows(conn, "fee_snapshots", "market_id = %s", [market_id], "snapshot_at", limit=3):
            self._add_source(buckets, domain=AwarenessDomain.FEES, source_table="fee_snapshots", source_record_id=str(row.get("fee_snapshot_id") or row.get("id")), source_component="Fees", source_created_at=_as_aware(row.get("snapshot_at")), summary="fee snapshot available", confidence=0.75, payload=row)
        for row in self._fetch_rows(conn, "news_impact_scores", "market_id = %s", [market_id], "created_at", limit=5):
            override = "STALE" if _is_news_stale(row) else None
            self._add_source(buckets, domain=AwarenessDomain.NEWS, source_table="news_impact_scores", source_record_id=str(row.get("impact_id") or row.get("id")), source_component="News", source_created_at=_as_aware(row.get("created_at")), summary=str(row.get("reason") or "news impact score"), confidence=_confidence(row, default=0.7), payload=row, freshness_override=override)
        for row in self._fetch_rows(conn, "whale_events", "market_id = %s", [market_id], "event_time", limit=5):
            self._add_source(buckets, domain=AwarenessDomain.WHALE, source_table="whale_events", source_record_id=str(row.get("whale_event_id") or row.get("id")), source_component="Whale", source_created_at=_as_aware(row.get("event_time") or row.get("created_at")), summary=f"whale event {row.get('event_classification') or row.get('action_type')}", confidence=_confidence(row, default=0.7), payload=row)
        for row in self._fetch_rows(conn, "market_memory_v2", "market_id = %s", [market_id], "updated_at", limit=3):
            self._add_source(buckets, domain=AwarenessDomain.MEMORY, source_table="market_memory_v2", source_record_id=str(row.get("id")), source_component="Market Memory", source_created_at=_as_aware(row.get("updated_at") or row.get("last_updated_at")), summary=f"memory status={row.get('memory_status')}", confidence=_confidence(row, key="memory_confidence", default=0.7), payload=row)
        for row in self._fetch_rows(conn, "risk_decisions", "market_id = %s", [market_id], "created_at", limit=5):
            self._add_source(buckets, domain=AwarenessDomain.RISK, source_table="risk_decisions", source_record_id=str(row.get("risk_decision_id") or row.get("id")), source_component="Risk", source_created_at=_as_aware(row.get("created_at")), summary=f"risk decision={row.get('decision') or row.get('risk_status')}", confidence=_confidence(row, default=0.7), payload=row)
        for row in self._fetch_rows(conn, "exit_plans", "market_id = %s", [market_id], "updated_at", limit=5):
            self._add_source(buckets, domain=AwarenessDomain.EXIT, source_table="exit_plans", source_record_id=str(row.get("exit_plan_id") or row.get("id")), source_component="Exit", source_created_at=_as_aware(row.get("updated_at") or row.get("created_at")), summary=f"exit status={row.get('status') or row.get('plan_status')}", confidence=_confidence(row, key="data_confidence", default=0.7), payload=row)
        for row in self._fetch_rows(conn, "paper_eligibility_candidates", "market_id = %s", [market_id], "updated_at", limit=5):
            self._add_source(buckets, domain=AwarenessDomain.CANDIDATE, source_table="paper_eligibility_candidates", source_record_id=str(row.get("eligibility_id") or row.get("id")), source_component="Eligibility", source_created_at=_as_aware(row.get("updated_at") or row.get("created_at")), summary=f"eligibility status={row.get('status')}", confidence=_confidence(row, key="eligibility_score", default=0.7), payload=row)

    def _collect_candidate_sources(self, conn: Any, session: dict[str, Any], buckets: dict[AwarenessDomain, list[dict[str, Any]]]) -> None:
        candidate_id = session.get("candidate_id")
        if not candidate_id:
            return
        for row in self._fetch_rows(conn, "neuron_intelligence_evidence", "(candidate_id = %s)", [candidate_id], "created_at", limit=10):
            domain = NEURON_DOMAIN_MAP.get(str(row.get("neuron_name") or "").lower())
            if domain:
                self._add_source(buckets, domain=domain, source_table="neuron_intelligence_evidence", source_record_id=str(row.get("evidence_id") or row.get("id")), source_component=f"{row.get('neuron_name')} Neuron", source_created_at=_as_aware(row.get("created_at")), summary=str(row.get("human_message") or "candidate neuron evidence"), confidence=_confidence(row, default=0.7), payload=row)
        for row in self._fetch_rows(conn, "trusted_orderbook_evidence_links", "candidate_id = %s", [candidate_id], "updated_at", limit=5):
            self._add_source(buckets, domain=AwarenessDomain.ORDERBOOK, source_table="trusted_orderbook_evidence_links", source_record_id=str(row.get("link_id") or row.get("id")), source_component="Orderbook", source_created_at=_as_aware(row.get("updated_at") or row.get("created_at")), summary=f"candidate trusted orderbook {row.get('trust_status')}", confidence=0.85 if row.get("trusted") else 0.45, payload=row)
        for row in self._fetch_rows(conn, "paper_eligibility_candidates", "eligibility_id = %s", [candidate_id], "updated_at", limit=5):
            self._add_source(buckets, domain=AwarenessDomain.CANDIDATE, source_table="paper_eligibility_candidates", source_record_id=str(row.get("eligibility_id") or row.get("id")), source_component="Eligibility", source_created_at=_as_aware(row.get("updated_at") or row.get("created_at")), summary=f"candidate eligibility status={row.get('status')}", confidence=_confidence(row, key="eligibility_score", default=0.7), payload=row)

    def _collect_position_sources(self, conn: Any, session: dict[str, Any], buckets: dict[AwarenessDomain, list[dict[str, Any]]]) -> None:
        position_id = session.get("position_id")
        if not position_id:
            return
        for row in self._fetch_rows(conn, "paper_positions", "id::text = %s", [position_id], "updated_at", limit=3):
            self._add_source(buckets, domain=AwarenessDomain.POSITION, source_table="paper_positions", source_record_id=str(row.get("id")), source_component="Position", source_created_at=_as_aware(row.get("updated_at") or row.get("opened_at")), summary=f"paper position status={row.get('current_status')}", confidence=0.8, payload=row)
        for row in self._fetch_rows(conn, "paper_trade_ledger", "position_id::text = %s", [position_id], "created_at", limit=10):
            self._add_source(buckets, domain=AwarenessDomain.POSITION, source_table="paper_trade_ledger", source_record_id=str(row.get("ledger_id") or row.get("id")), source_component="Position", source_created_at=_as_aware(row.get("created_at")), summary=f"position ledger event={row.get('event_type')}", confidence=0.75, payload=row)
            if row.get("realized_pnl") is not None or row.get("unrealized_pnl") is not None:
                self._add_source(buckets, domain=AwarenessDomain.PNL, source_table="paper_trade_ledger", source_record_id=str(row.get("ledger_id") or row.get("id")), source_component="PnL", source_created_at=_as_aware(row.get("created_at")), summary="position PnL ledger available", confidence=0.75, payload=row)
        for row in self._fetch_rows(conn, "exit_plans", "position_ref = %s", [position_id], "updated_at", limit=5):
            self._add_source(buckets, domain=AwarenessDomain.EXIT, source_table="exit_plans", source_record_id=str(row.get("exit_plan_id") or row.get("id")), source_component="Exit", source_created_at=_as_aware(row.get("updated_at") or row.get("created_at")), summary=f"position exit status={row.get('status') or row.get('plan_status')}", confidence=_confidence(row, key="data_confidence", default=0.7), payload=row)
        for row in self._fetch_rows(conn, "paper_daily_pnl", "TRUE", [], "updated_at", limit=1):
            self._add_source(buckets, domain=AwarenessDomain.PNL, source_table="paper_daily_pnl", source_record_id=str(row.get("id")), source_component="PnL", source_created_at=_as_aware(row.get("updated_at")), summary=f"daily pnl net={row.get('net_pnl')}", confidence=0.75, payload=row)

    def _collect_global_capital(self, conn: Any, session: dict[str, Any], buckets: dict[AwarenessDomain, list[dict[str, Any]]]) -> None:
        if session.get("session_type") not in {"POSITION_SESSION", "CANDIDATE_SESSION", "MARKET_SESSION", "THREAT_SESSION", "OPPORTUNITY_SESSION"}:
            return
        for row in self._fetch_rows(conn, "paper_accounts", "TRUE", [], "updated_at", limit=1):
            self._add_source(buckets, domain=AwarenessDomain.CAPITAL, source_table="paper_accounts", source_record_id=str(row.get("account_id") or row.get("id")), source_component="Capital", source_created_at=_as_aware(row.get("updated_at") or row.get("created_at")), summary=f"paper capital available={row.get('available_balance')} locked={row.get('locked_balance')}", confidence=0.85, payload=row)
        for row in self._fetch_rows(conn, "paper_capital_ledger", "TRUE", [], "created_at", limit=3):
            self._add_source(buckets, domain=AwarenessDomain.CAPITAL, source_table="paper_capital_ledger", source_record_id=str(row.get("ledger_id") or row.get("id")), source_component="Capital", source_created_at=_as_aware(row.get("created_at")), summary=f"capital ledger event={row.get('event_type')}", confidence=0.75, payload=row)

    def _fetch_entity_rows(self, conn: Any, table: str, session: dict[str, Any], *, timestamp_column: str, limit: int) -> list[dict[str, Any]]:
        if not table_exists(conn, table):
            return []
        clauses: list[str] = []
        params: list[Any] = []
        cols = table_columns(conn, table)
        if session.get("market_id") and "market_id" in cols:
            clauses.append("market_id = %s")
            params.append(session["market_id"])
        if session.get("candidate_id") and "candidate_id" in cols:
            clauses.append("candidate_id = %s")
            params.append(session["candidate_id"])
        if session.get("position_id") and "position_id" in cols:
            clauses.append("position_id::text = %s")
            params.append(session["position_id"])
        if not clauses:
            return []
        return self._fetch_rows(conn, table, "(" + " OR ".join(clauses) + ")", params, timestamp_column, limit=limit)

    def _fetch_rows(self, conn: Any, table: str, where: str, params: list[Any], timestamp_column: str, *, limit: int) -> list[dict[str, Any]]:
        if not table_exists(conn, table):
            return []
        cols = table_columns(conn, table)
        if timestamp_column not in cols:
            timestamp_column = "id"
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM {table}
                WHERE {where}
                ORDER BY {timestamp_column} DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                [*params, limit],
            ).fetchall()
        ]

    def _add_source(
        self,
        buckets: dict[AwarenessDomain, list[dict[str, Any]]],
        *,
        domain: AwarenessDomain,
        source_table: str,
        source_record_id: str,
        source_component: str,
        source_created_at: datetime | None,
        summary: str,
        confidence: float,
        payload: dict[str, Any],
        freshness_override: str | None = None,
    ) -> None:
        freshness_status = freshness_override or _source_freshness(domain, source_created_at)
        buckets[domain].append(
            {
                "source_table": source_table,
                "source_record_id": source_record_id,
                "source_component": source_component,
                "source_created_at": source_created_at,
                "summary": summary,
                "confidence": max(0.0, min(float(confidence or 0), 1.0)),
                "freshness_status": freshness_status,
                "payload": _json_safe(payload),
            }
        )

    def _domain_state(self, domain: AwarenessDomain, refs: list[dict[str, Any]]) -> dict[str, Any]:
        if not refs:
            return {
                "status": DomainStatus.MISSING.value,
                "summary": f"{domain.value} evidence missing for session.",
                "confidence": 0.0,
                "source_count": 0,
                "latest_source_at": None,
                "source_refs": [],
            }
        refs = sorted(refs, key=lambda item: item.get("source_created_at") or datetime.min.replace(tzinfo=UTC), reverse=True)
        fresh = [ref for ref in refs if ref["freshness_status"] == "FRESH"]
        stale = [ref for ref in refs if ref["freshness_status"] == "STALE"]
        partial = [ref for ref in refs if ref["freshness_status"] == "PARTIAL"]
        if fresh and (stale or partial):
            status = DomainStatus.PARTIAL.value
        elif fresh:
            status = DomainStatus.PRESENT.value
        elif partial:
            status = DomainStatus.PARTIAL.value
        else:
            status = DomainStatus.STALE.value
        latest = refs[0]
        confidence = round(sum(float(ref.get("confidence") or 0) for ref in refs) / len(refs), 4)
        return {
            "status": status,
            "summary": latest["summary"],
            "confidence": confidence,
            "source_count": len(refs),
            "latest_source_at": latest.get("source_created_at").isoformat() if latest.get("source_created_at") else None,
            "source_refs": [
                {
                    "source_table": ref["source_table"],
                    "source_record_id": ref["source_record_id"],
                    "source_component": ref["source_component"],
                    "source_created_at": ref["source_created_at"].isoformat() if ref.get("source_created_at") else None,
                    "freshness_status": ref["freshness_status"],
                    "summary": ref["summary"],
                }
                for ref in refs[:10]
            ],
        }

    def _assert_system_on(self) -> None:
        power = self._system_power.get_power_state()
        if str(power.get("power") or "OFF").upper() != "ON" or not power.get("runtime_work_allowed"):
            raise SharedAwarenessBlocked("SYSTEM_POWER_OFF")


def _source_freshness(domain: AwarenessDomain, source_created_at: datetime | None) -> str:
    if source_created_at is None:
        return "FRESH"
    window = FRESHNESS_WINDOWS[domain]
    return "STALE" if datetime.now(UTC) - _as_aware(source_created_at) > window else "FRESH"


def _overall_freshness(domain_states: dict[AwarenessDomain, dict[str, Any]]) -> str:
    statuses = {state["status"] for state in domain_states.values()}
    if statuses == {DomainStatus.MISSING.value}:
        return "MISSING"
    if DomainStatus.ERROR.value in statuses:
        return "ERROR"
    if DomainStatus.STALE.value in statuses and not (DomainStatus.PRESENT.value in statuses or DomainStatus.PARTIAL.value in statuses):
        return "STALE"
    if DomainStatus.MISSING.value in statuses or DomainStatus.STALE.value in statuses or DomainStatus.PARTIAL.value in statuses:
        return "PARTIAL"
    return "FRESH"


def _sessions_with_domain(rows: list[dict[str, Any]], domain: AwarenessDomain) -> int:
    column = DOMAIN_STATE_COLUMNS[domain]
    return len([row for row in rows if (row.get(column) or {}).get("source_count", 0) > 0])


def _domain_counter(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = {domain.value: 0 for domain in ALL_DOMAINS}
    for row in rows:
        for domain in row.get(key) or []:
            if domain in counts:
                counts[domain] += 1
    return counts


def _confidence(row: dict[str, Any], *, key: str = "confidence", default: float) -> float:
    value = row.get(key)
    try:
        if value is None:
            return default
        numeric = float(value)
        if numeric > 1:
            numeric = numeric / 100
        return max(0.0, min(numeric, 1.0))
    except (TypeError, ValueError):
        return default


def _is_news_stale(row: dict[str, Any]) -> bool:
    created_at = _as_aware(row.get("created_at"))
    ttl = row.get("ttl_seconds")
    if created_at is None or ttl is None:
        return False
    try:
        return datetime.now(UTC) - created_at > timedelta(seconds=int(ttl))
    except (TypeError, ValueError):
        return False


def _as_aware(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for source in sources:
        key = (source["source_domain"], source["source_table"], source["source_record_id"])
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _empty_dashboard(status: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "total_awareness_records": 0,
        "active_awareness_records": 0,
        "avg_completeness_score": 0.0,
        "sessions_with_news": 0,
        "sessions_with_liquidity": 0,
        "sessions_with_rules": 0,
        "sessions_with_risk": 0,
        "sessions_with_exit": 0,
        "sessions_with_capital": 0,
        "missing_domain_counts": {domain.value: 0 for domain in ALL_DOMAINS},
        "stale_domain_counts": {domain.value: 0 for domain in ALL_DOMAINS},
        "latest_awareness": [],
    }

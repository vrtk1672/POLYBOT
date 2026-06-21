from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.full_mesh_inquiry import FullMeshInquiryOrchestrator
from app.services.proactive_seed_mesh_inquiry import (
    SAFE_MESH_CONTRACT_MISSING,
    _result_id,
    _safety_counts,
    _table_exists,
    _trading_mutation,
)
from app.services.trade_opportunity_score import score_actionability_item
from app.services.trade_thesis_engine import build_trade_thesis


DEFAULT_ADAPTER_LIMIT = 25
MESH_DATA_ONLY_COMPLETED = "MESH_DATA_ONLY_COMPLETED"
FAILED_SAFETY_BOUNDARY = "FAILED_SAFETY_BOUNDARY"
PAYLOAD_TYPE = "PROACTIVE_SEED_RESEARCH_CANDIDATE"
ALLOWED_REQUEST_STATES = {"SKIPPED", "PENDING"}
ALLOWED_SIDES = {"YES", "NO"}
ALLOWED_TOKEN_SIDE_STATES = {"TOKEN_SIDE_DIRECT", "SIDE_DIRECTIONAL_YES", "SIDE_DIRECTIONAL_NO"}
ALLOWED_PRIORITIES = {"HIGH", "MEDIUM"}


class ProactiveSeedDataOnlyMeshAdapter:
    """DATA_ONLY adapter from proactive research seeds into read-only Mesh review."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def run(self, *, limit: int = DEFAULT_ADAPTER_LIMIT, force: bool = False) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        adapter_run_id = f"proactive_seed_mesh_adapter_{uuid4().hex}"
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "adapter_run_id": adapter_run_id, "eligible_requests": 0}
        limit = max(1, min(int(limit or DEFAULT_ADAPTER_LIMIT), 250))
        errors: list[str] = []
        with self._factory.connect() as conn, conn.transaction():
            self._ensure_tables(conn)
            safety_before = _safety_counts(conn)
            rows = self._eligible_rows(conn, limit=limit, force=force)
            stats = {
                "eligible_requests": len(rows),
                "processed_count": 0,
                "completed_count": 0,
                "partial_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "blocked_count": 0,
            }
            for row in rows:
                try:
                    result = self.process_row(conn, row, adapter_run_id=adapter_run_id)
                    stats["processed_count"] += 1
                    state = result.get("result_state")
                    stats["completed_count"] += int(state == MESH_DATA_ONLY_COMPLETED)
                    stats["partial_count"] += int(state == "PARTIAL")
                    stats["skipped_count"] += int(state == "SKIPPED")
                    stats["failed_count"] += int(state in {"FAILED", FAILED_SAFETY_BOUNDARY})
                    stats["blocked_count"] += int(state == "BLOCKED")
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    stats["failed_count"] += 1
            safety_after = _safety_counts(conn)
            completed_at = datetime.now(UTC)
            status = "OK" if not errors else "PARTIAL" if rows else "ERROR"
            if _trading_mutation(safety_before, safety_after):
                status = FAILED_SAFETY_BOUNDARY
                errors.insert(0, "Adapter safety boundary failed: trading artifact counts changed.")
            self._insert_run(
                conn,
                adapter_run_id=adapter_run_id,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                latest_error=errors[0] if errors else None,
                metadata={
                    "limit": limit,
                    "force": force,
                    "mesh_handoff_mode": "DATA_ONLY",
                    "adapter_available": True,
                    "full_mesh_path_found": True,
                    "source_backed_edge_path_found": True,
                    "thesis_path_found": True,
                    "score_path_found": True,
                    "execution_isolation_verified": not _trading_mutation(safety_before, safety_after),
                    "safety_before": safety_before,
                    "safety_after": safety_after,
                    "trading_mutation": _trading_mutation(safety_before, safety_after),
                    "errors": errors[:5],
                },
                **stats,
            )
        return {
            "status": status,
            "adapter_run_id": adapter_run_id,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            **stats,
            "errors": errors[:5],
        }

    def diagnostics(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return {
                "status": "DATABASE_UNAVAILABLE",
                "adapter_available": False,
                "generated_at": now.isoformat(),
            }
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            latest = self._latest_run(conn)
            counts = self._adapter_counts(conn)
        return {
            "status": "REAL",
            "adapter_available": True,
            "full_mesh_path_found": True,
            "source_backed_edge_path_found": True,
            "thesis_path_found": True,
            "score_path_found": True,
            "execution_isolation_verified": True,
            "latest_adapter_run": latest,
            "latest_errors": [latest.get("latest_error")] if latest and latest.get("latest_error") else [],
            "counts": counts,
            "generated_at": now.isoformat(),
        }

    def process_row(self, conn: Any, row: dict[str, Any], *, adapter_run_id: str) -> dict[str, Any]:
        verdict = evaluate_adapter_request(row)
        if not verdict["selected"]:
            result = build_blocked_adapter_result(row, verdict)
            self._upsert_stage5_result(conn, result)
            self._update_request_state(conn, row["seed_mesh_inquiry_id"], "BLOCKED", None, verdict["blockers"], verdict["warnings"], None, None, None, None)
            return result

        payload = build_adapter_payload(row, adapter_run_id=adapter_run_id)
        self._upsert_payload(conn, payload)
        mesh_bundle = build_mesh_bundle_from_payload(payload)
        try:
            session = FullMeshInquiryOrchestrator(connection_factory=self._factory).build_session(mesh_bundle)
            result = build_adapter_result(row, payload=payload, session=session)
            self._upsert_stage5_result(conn, result)
            self._update_request_state(
                conn,
                row["seed_mesh_inquiry_id"],
                result["result_state"],
                session.get("mesh_session_id"),
                [],
                result.get("soft_blockers_json") or [],
                session.get("edge_thesis_id"),
                result.get("trade_thesis_id"),
                result.get("opportunity_score_id"),
                payload["adapter_payload_id"],
            )
            return result
        except Exception as exc:
            result = build_failed_adapter_result(row, payload=payload, reason=f"{type(exc).__name__}: {exc}")
            self._upsert_stage5_result(conn, result)
            self._update_request_state(conn, row["seed_mesh_inquiry_id"], "FAILED", None, result["hard_blockers_json"], [], None, None, None, payload["adapter_payload_id"])
            return result

    def _eligible_rows(self, conn: Any, *, limit: int, force: bool) -> list[dict[str, Any]]:
        if not _table_exists(conn, "proactive_seed_mesh_inquiries") or not _table_exists(conn, "proactive_candidate_seeds"):
            return []
        recent_filter = "" if force else """
            AND NOT EXISTS (
                SELECT 1
                FROM proactive_seed_mesh_adapter_payloads p
                WHERE p.seed_mesh_inquiry_id=psi.seed_mesh_inquiry_id
                  AND p.updated_at >= now() - interval '24 hours'
            )
            AND COALESCE(psr.result_state, '') <> 'MESH_DATA_ONLY_COMPLETED'
        """
        rows = conn.execute(
            f"""
            SELECT
                psi.seed_mesh_inquiry_id,
                psi.proactive_candidate_seed_id,
                psi.source_event_id,
                psi.event_to_market_link_id,
                psi.targeted_revalidation_id,
                psi.market_memory_id,
                psi.research_watchlist_id,
                psi.market_id,
                psi.condition_id,
                psi.side,
                psi.token_id,
                psi.priority_band,
                psi.priority_score,
                psi.request_state,
                psi.research_only AS inquiry_research_only,
                psi.execution_allowed AS inquiry_execution_allowed,
                psi.paper_allowed AS inquiry_paper_allowed,
                psi.shadow_allowed AS inquiry_shadow_allowed,
                psi.live_allowed AS inquiry_live_allowed,
                psi.blockers_json AS inquiry_blockers_json,
                pcs.seed_state,
                pcs.seed_type,
                pcs.research_only,
                pcs.execution_allowed,
                pcs.paper_allowed,
                pcs.shadow_allowed,
                pcs.live_allowed,
                pcs.link_type,
                pcs.link_confidence,
                pcs.direction_for_market,
                pcs.direction_confidence,
                pcs.orderbook_snapshot_id,
                pcs.orderbook_refresh_state,
                pcs.liquidity_state,
                pcs.spread_state,
                pcs.payout_odds_state,
                pcs.movement_state,
                pcs.already_priced_in_state,
                pcs.candidate_event_scope_state,
                pcs.token_side_resolution_state,
                pcs.blockers_json,
                pcs.soft_warnings_json,
                pcs.required_to_pass_json,
                pcs.reason,
                pcs.metadata_json,
                psr.result_state AS current_result_state
            FROM proactive_seed_mesh_inquiries psi
            JOIN proactive_candidate_seeds pcs ON pcs.proactive_candidate_seed_id=psi.proactive_candidate_seed_id
            LEFT JOIN proactive_seed_mesh_results psr ON psr.seed_mesh_inquiry_id=psi.seed_mesh_inquiry_id
            WHERE psi.request_state IN ('SKIPPED','PENDING')
              AND psi.research_only IS TRUE
              AND COALESCE(psi.execution_allowed, false) IS FALSE
              AND COALESCE(psi.paper_allowed, false) IS FALSE
              AND COALESCE(psi.shadow_allowed, false) IS FALSE
              AND COALESCE(psi.live_allowed, false) IS FALSE
              AND (
                    psi.blockers_json ? %s
                    OR psi.blockers_json ? 'ADAPTER_PENDING'
                  )
              {recent_filter}
            ORDER BY
                CASE psi.priority_band WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 WHEN 'LOW' THEN 2 ELSE 3 END,
                psi.priority_score DESC NULLS LAST,
                pcs.link_confidence DESC,
                psi.updated_at DESC,
                psi.id DESC
            LIMIT %s
            """,
            (SAFE_MESH_CONTRACT_MISSING, limit),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _upsert_payload(self, conn: Any, payload: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO proactive_seed_mesh_adapter_payloads (
                adapter_payload_id, adapter_run_id, seed_mesh_inquiry_id, proactive_candidate_seed_id,
                synthetic_candidate_id, payload_type, source_event_id, event_to_market_link_id,
                targeted_revalidation_id, market_memory_id, research_watchlist_id, market_id, condition_id,
                side, token_id, orderbook_snapshot_id, link_confidence, direction_confidence, priority_score,
                research_only, execution_allowed, paper_allowed, shadow_allowed, live_allowed,
                lineage_json, safety_flags_json, payload_json
            )
            VALUES (
                %(adapter_payload_id)s, %(adapter_run_id)s, %(seed_mesh_inquiry_id)s, %(proactive_candidate_seed_id)s,
                %(synthetic_candidate_id)s, %(payload_type)s, %(source_event_id)s, %(event_to_market_link_id)s,
                %(targeted_revalidation_id)s, %(market_memory_id)s, %(research_watchlist_id)s, %(market_id)s, %(condition_id)s,
                %(side)s, %(token_id)s, %(orderbook_snapshot_id)s, %(link_confidence)s, %(direction_confidence)s, %(priority_score)s,
                %(research_only)s, %(execution_allowed)s, %(paper_allowed)s, %(shadow_allowed)s, %(live_allowed)s,
                %(lineage_json)s, %(safety_flags_json)s, %(payload_json)s
            )
            ON CONFLICT (adapter_payload_id) DO UPDATE SET
                adapter_run_id=EXCLUDED.adapter_run_id,
                lineage_json=EXCLUDED.lineage_json,
                safety_flags_json=EXCLUDED.safety_flags_json,
                payload_json=EXCLUDED.payload_json,
                updated_at=now()
            """,
            {
                **payload,
                "lineage_json": Jsonb(payload.get("lineage_json") or {}),
                "safety_flags_json": Jsonb(payload.get("safety_flags_json") or {}),
                "payload_json": Jsonb(payload.get("payload_json") or {}),
            },
        )

    def _upsert_stage5_result(self, conn: Any, result: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO proactive_seed_mesh_results (
                seed_mesh_result_id, seed_mesh_inquiry_id, proactive_candidate_seed_id,
                result_state, edge_state, trade_thesis_state, opportunity_score,
                opportunity_decision_band, risk_state, capital_state, exit_state, lifecycle_state,
                paper_observation_eligible, full_paper_ready, hard_blockers_json, soft_blockers_json,
                required_to_improve_json, mesh_summary, metadata_json
            )
            VALUES (
                %(seed_mesh_result_id)s, %(seed_mesh_inquiry_id)s, %(proactive_candidate_seed_id)s,
                %(result_state)s, %(edge_state)s, %(trade_thesis_state)s, %(opportunity_score)s,
                %(opportunity_decision_band)s, %(risk_state)s, %(capital_state)s, %(exit_state)s, %(lifecycle_state)s,
                %(paper_observation_eligible)s, %(full_paper_ready)s, %(hard_blockers_json)s, %(soft_blockers_json)s,
                %(required_to_improve_json)s, %(mesh_summary)s, %(metadata_json)s
            )
            ON CONFLICT (seed_mesh_result_id) DO UPDATE SET
                result_state=EXCLUDED.result_state,
                edge_state=EXCLUDED.edge_state,
                trade_thesis_state=EXCLUDED.trade_thesis_state,
                opportunity_score=EXCLUDED.opportunity_score,
                opportunity_decision_band=EXCLUDED.opportunity_decision_band,
                risk_state=EXCLUDED.risk_state,
                capital_state=EXCLUDED.capital_state,
                exit_state=EXCLUDED.exit_state,
                lifecycle_state=EXCLUDED.lifecycle_state,
                paper_observation_eligible=EXCLUDED.paper_observation_eligible,
                full_paper_ready=EXCLUDED.full_paper_ready,
                hard_blockers_json=EXCLUDED.hard_blockers_json,
                soft_blockers_json=EXCLUDED.soft_blockers_json,
                required_to_improve_json=EXCLUDED.required_to_improve_json,
                mesh_summary=EXCLUDED.mesh_summary,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            {
                **result,
                "hard_blockers_json": Jsonb(result.get("hard_blockers_json") or []),
                "soft_blockers_json": Jsonb(result.get("soft_blockers_json") or []),
                "required_to_improve_json": Jsonb(result.get("required_to_improve_json") or []),
                "metadata_json": Jsonb(_jsonable(result.get("metadata_json") or {})),
            },
        )

    def _update_request_state(
        self,
        conn: Any,
        inquiry_id: str,
        state: str,
        mesh_session_id: str | None,
        blockers: list[str],
        warnings: list[str],
        edge_result_id: str | None,
        trade_thesis_id: str | None,
        opportunity_score_id: str | None,
        adapter_payload_id: str | None,
    ) -> None:
        conn.execute(
            """
            UPDATE proactive_seed_mesh_inquiries
            SET request_state=%s,
                mesh_inquiry_session_id=COALESCE(%s, mesh_inquiry_session_id),
                edge_result_id=COALESCE(%s, edge_result_id),
                trade_thesis_id=COALESCE(%s, trade_thesis_id),
                opportunity_score_id=COALESCE(%s, opportunity_score_id),
                blockers_json=%s,
                warnings_json=%s,
                metadata_json=metadata_json || %s,
                updated_at=now()
            WHERE seed_mesh_inquiry_id=%s
            """,
            (
                state,
                mesh_session_id,
                edge_result_id,
                trade_thesis_id,
                opportunity_score_id,
                Jsonb(blockers or []),
                Jsonb(warnings or []),
                Jsonb({"stage5_5_adapter_payload_id": adapter_payload_id, "stage5_5_adapter_state": state}),
                inquiry_id,
            ),
        )

    def _insert_run(self, conn: Any, *, adapter_run_id: str, status: str, started_at: datetime, completed_at: datetime, latest_error: str | None, metadata: dict[str, Any], **stats: Any) -> None:
        conn.execute(
            """
            INSERT INTO proactive_seed_mesh_adapter_runs (
                adapter_run_id, status, started_at, completed_at, eligible_requests, processed_count,
                completed_count, partial_count, skipped_count, failed_count, blocked_count, latest_error, metadata_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (adapter_run_id) DO UPDATE SET
                status=EXCLUDED.status,
                completed_at=EXCLUDED.completed_at,
                eligible_requests=EXCLUDED.eligible_requests,
                processed_count=EXCLUDED.processed_count,
                completed_count=EXCLUDED.completed_count,
                partial_count=EXCLUDED.partial_count,
                skipped_count=EXCLUDED.skipped_count,
                failed_count=EXCLUDED.failed_count,
                blocked_count=EXCLUDED.blocked_count,
                latest_error=EXCLUDED.latest_error,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            (
                adapter_run_id,
                status,
                started_at,
                completed_at,
                int(stats.get("eligible_requests") or 0),
                int(stats.get("processed_count") or 0),
                int(stats.get("completed_count") or 0),
                int(stats.get("partial_count") or 0),
                int(stats.get("skipped_count") or 0),
                int(stats.get("failed_count") or 0),
                int(stats.get("blocked_count") or 0),
                latest_error,
                Jsonb(_jsonable(metadata)),
            ),
        )

    def _adapter_counts(self, conn: Any) -> dict[str, Any]:
        payloads = conn.execute("SELECT COUNT(*) AS count FROM proactive_seed_mesh_adapter_payloads").fetchone()
        runs = conn.execute(
            """
            SELECT
                COUNT(*) AS adapter_run_count,
                COALESCE(SUM(processed_count),0) AS adapter_processed_count,
                COALESCE(SUM(completed_count),0) AS adapter_completed_count,
                COALESCE(SUM(partial_count),0) AS adapter_partial_count,
                COALESCE(SUM(skipped_count),0) AS adapter_skipped_count,
                COALESCE(SUM(failed_count),0) AS adapter_failed_count,
                COALESCE(SUM(blocked_count),0) AS adapter_blocked_count
            FROM proactive_seed_mesh_adapter_runs
            """
        ).fetchone()
        missing = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM proactive_seed_mesh_inquiries
            WHERE blockers_json ? %s
              AND request_state IN ('SKIPPED','PENDING')
            """,
            (SAFE_MESH_CONTRACT_MISSING,),
        ).fetchone()
        completed = conn.execute(
            "SELECT COUNT(*) AS count FROM proactive_seed_mesh_results WHERE result_state=%s",
            (MESH_DATA_ONLY_COMPLETED,),
        ).fetchone()
        out = {key: int(value or 0) for key, value in dict(runs or {}).items()}
        out["adapter_payload_count"] = int((payloads or {}).get("count") or 0)
        out["safe_mesh_contract_missing_remaining_count"] = int((missing or {}).get("count") or 0)
        out["mesh_data_only_completed_count"] = int((completed or {}).get("count") or 0)
        result_counts = conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE result_state='MESH_DATA_ONLY_COMPLETED') AS completed,
                COUNT(*) FILTER (WHERE result_state='PARTIAL') AS partial,
                COUNT(*) FILTER (WHERE result_state='FAILED') AS failed,
                COUNT(*) FILTER (WHERE result_state='BLOCKED') AS blocked
            FROM proactive_seed_mesh_results
            WHERE metadata_json->>'stage'='MONEY_MACHINE_STAGE5_5'
            """
        ).fetchone()
        out["adapter_completed_count"] = int((result_counts or {}).get("completed") or 0)
        out["adapter_partial_count"] = int((result_counts or {}).get("partial") or 0)
        out["adapter_failed_count"] = int((result_counts or {}).get("failed") or 0)
        out["adapter_blocked_count"] = int((result_counts or {}).get("blocked") or 0)
        return out

    def _latest_run(self, conn: Any) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM proactive_seed_mesh_adapter_runs
            ORDER BY completed_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ).fetchone()
        return _jsonable(dict(row)) if row else None

    def _ensure_tables(self, conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proactive_seed_mesh_adapter_payloads (
                id BIGSERIAL PRIMARY KEY,
                adapter_payload_id TEXT NOT NULL UNIQUE,
                adapter_run_id TEXT,
                seed_mesh_inquiry_id TEXT NOT NULL,
                proactive_candidate_seed_id TEXT NOT NULL,
                synthetic_candidate_id TEXT NOT NULL,
                payload_type TEXT NOT NULL DEFAULT 'PROACTIVE_SEED_RESEARCH_CANDIDATE',
                source_event_id TEXT,
                event_to_market_link_id TEXT,
                targeted_revalidation_id TEXT,
                market_memory_id TEXT,
                research_watchlist_id TEXT,
                market_id TEXT,
                condition_id TEXT,
                side TEXT NOT NULL,
                token_id TEXT NOT NULL,
                orderbook_snapshot_id TEXT,
                link_confidence NUMERIC NOT NULL DEFAULT 0,
                direction_confidence NUMERIC NOT NULL DEFAULT 0,
                priority_score NUMERIC NOT NULL DEFAULT 0,
                research_only BOOLEAN NOT NULL DEFAULT TRUE,
                execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                paper_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                shadow_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                live_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                lineage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                safety_flags_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proactive_seed_mesh_adapter_runs (
                id BIGSERIAL PRIMARY KEY,
                adapter_run_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                eligible_requests INTEGER NOT NULL DEFAULT 0,
                processed_count INTEGER NOT NULL DEFAULT 0,
                completed_count INTEGER NOT NULL DEFAULT 0,
                partial_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                blocked_count INTEGER NOT NULL DEFAULT 0,
                latest_error TEXT,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def evaluate_adapter_request(row: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if str(row.get("request_state") or "") not in ALLOWED_REQUEST_STATES:
        blockers.append("REQUEST_STATE_NOT_ADAPTER_ELIGIBLE")
    inquiry_blockers = [str(item) for item in _as_list(row.get("inquiry_blockers_json"))]
    if SAFE_MESH_CONTRACT_MISSING not in inquiry_blockers and "ADAPTER_PENDING" not in inquiry_blockers:
        blockers.append("SAFE_MESH_CONTRACT_MISSING_NOT_PRESENT")
    if row.get("seed_state") != "GENERATED":
        blockers.append("SEED_STATE_NOT_GENERATED")
    if row.get("research_only") is not True or row.get("inquiry_research_only") is not True:
        blockers.append("SEED_NOT_RESEARCH_ONLY")
    for flag in ("execution_allowed", "paper_allowed", "shadow_allowed", "live_allowed", "inquiry_execution_allowed", "inquiry_paper_allowed", "inquiry_shadow_allowed", "inquiry_live_allowed"):
        if row.get(flag) is True:
            blockers.append(f"{flag.upper()}_MUST_BE_FALSE")
    if str(row.get("side") or "") not in ALLOWED_SIDES:
        blockers.append("SIDE_NOT_ADAPTER_ELIGIBLE")
    if not row.get("token_id"):
        blockers.append("TOKEN_ID_MISSING")
    if not row.get("market_id"):
        blockers.append("MARKET_ID_MISSING")
    if row.get("orderbook_refresh_state") != "FRESH":
        blockers.append("ORDERBOOK_NOT_FRESH")
    if str(row.get("token_side_resolution_state") or "") not in ALLOWED_TOKEN_SIDE_STATES:
        blockers.append("TOKEN_SIDE_NOT_DIRECT")
    if str(row.get("candidate_event_scope_state") or "") != "CANDIDATE_SCOPED":
        blockers.append("CANDIDATE_EVENT_SCOPE_NOT_CANDIDATE_SCOPED")
    if str(row.get("priority_band") or "") not in ALLOWED_PRIORITIES:
        blockers.append("PRIORITY_NOT_SELECTED")
    seed_blockers = [str(item) for item in _as_list(row.get("blockers_json")) if item]
    blockers.extend(seed_blockers)
    if str(row.get("already_priced_in_state") or "UNKNOWN") == "YES":
        warnings.append("EVENT_ALREADY_PRICED_IN_RESEARCH_ONLY")
    selected = not blockers
    return {"selected": selected, "blockers": _dedupe(blockers), "warnings": _dedupe(warnings)}


def build_adapter_payload(row: dict[str, Any], *, adapter_run_id: str) -> dict[str, Any]:
    seed_id = str(row.get("proactive_candidate_seed_id"))
    inquiry_id = str(row.get("seed_mesh_inquiry_id"))
    synthetic_candidate_id = f"research_seed_candidate_{seed_id}"
    adapter_payload_id = f"seed_mesh_adapter_payload_{hashlib.sha256(inquiry_id.encode('utf-8')).hexdigest()[:28]}"
    lineage = {
        "source_event_id": row.get("source_event_id"),
        "event_to_market_link_id": row.get("event_to_market_link_id"),
        "targeted_revalidation_id": row.get("targeted_revalidation_id"),
        "proactive_candidate_seed_id": seed_id,
        "seed_mesh_inquiry_id": inquiry_id,
        "market_memory_id": row.get("market_memory_id"),
        "research_watchlist_id": row.get("research_watchlist_id"),
    }
    safety_flags = {
        "research_only": True,
        "execution_allowed": False,
        "paper_allowed": False,
        "shadow_allowed": False,
        "live_allowed": False,
        "data_only": True,
    }
    payload_json = {
        "adapter_payload_id": adapter_payload_id,
        "payload_type": PAYLOAD_TYPE,
        "synthetic_candidate_id": synthetic_candidate_id,
        "market_id": row.get("market_id"),
        "condition_id": row.get("condition_id"),
        "side": row.get("side"),
        "token_id": row.get("token_id"),
        "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
        "lineage": lineage,
        "safety_flags": safety_flags,
    }
    return {
        "adapter_payload_id": adapter_payload_id,
        "adapter_run_id": adapter_run_id,
        "seed_mesh_inquiry_id": inquiry_id,
        "proactive_candidate_seed_id": seed_id,
        "synthetic_candidate_id": synthetic_candidate_id,
        "payload_type": PAYLOAD_TYPE,
        "source_event_id": row.get("source_event_id"),
        "event_to_market_link_id": row.get("event_to_market_link_id"),
        "targeted_revalidation_id": row.get("targeted_revalidation_id"),
        "market_memory_id": row.get("market_memory_id"),
        "research_watchlist_id": row.get("research_watchlist_id"),
        "market_id": row.get("market_id"),
        "condition_id": row.get("condition_id"),
        "side": row.get("side"),
        "token_id": row.get("token_id"),
        "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
        "link_confidence": _float(row.get("link_confidence")) or 0.0,
        "direction_confidence": _float(row.get("direction_confidence")) or 0.0,
        "priority_score": _float(row.get("priority_score")) or 0.0,
        "research_only": True,
        "execution_allowed": False,
        "paper_allowed": False,
        "shadow_allowed": False,
        "live_allowed": False,
        "lineage_json": lineage,
        "safety_flags_json": safety_flags,
        "payload_json": payload_json,
    }


def build_mesh_bundle_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle_id": f"seed_mesh_bundle_{payload['seed_mesh_inquiry_id']}",
        "payload_type": payload["payload_type"],
        "candidate_id": payload["synthetic_candidate_id"],
        "market_id": payload.get("market_id"),
        "condition_id": payload.get("condition_id"),
        "side": payload.get("side"),
        "token_id": payload.get("token_id"),
        "correlation_id": payload.get("event_to_market_link_id"),
        "event_id": payload.get("source_event_id"),
        "candidate_event_link_state": "LINKED_TO_CANDIDATE",
        "candidate_event_actionability_scope": "CANDIDATE_SCOPED",
        "correlation_confidence": "HIGH",
        "research_only": True,
        "execution_allowed": False,
        "paper_allowed": False,
        "shadow_allowed": False,
        "live_allowed": False,
        "orderbook": {
            "orderbook_snapshot_id": payload.get("orderbook_snapshot_id"),
            "snapshot_id": payload.get("orderbook_snapshot_id"),
            "trusted_state": "TRUSTED_FRESH",
            "freshness_state": "FRESH",
            "candidate_scoped": True,
        },
        "opinions": {
            "lifecycle": {"lifecycle_opinion_state": "DATA_ONLY_RESEARCH"},
            "risk": {"state": "RISK_REVIEW"},
            "capital": {"capital_opinion_state": "CAPITAL_WATCH"},
            "exit": {"state": "UNKNOWN"},
        },
        "coordinator": {
            "decision": "NO_ACTION",
            "reason": "DATA_ONLY proactive seed Mesh review only.",
        },
        "lineage": payload.get("lineage_json") or {},
        "safety_flags": payload.get("safety_flags_json") or {},
    }


def build_adapter_result(row: dict[str, Any], *, payload: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    edge = session.get("inquiry_edge_thesis") or {}
    thesis = build_trade_thesis(
        {
            "subject_type": "PROACTIVE_RESEARCH_SEED",
            "subject_id": payload["synthetic_candidate_id"],
            "candidate_id": payload["synthetic_candidate_id"],
            "market_id": payload.get("market_id"),
            "condition_id": payload.get("condition_id"),
            "side": payload.get("side"),
            "token_id": payload.get("token_id"),
        },
        {
            "edge": edge,
            "orderbook": {
                "orderbook_snapshot_id": payload.get("orderbook_snapshot_id"),
                "spread": _spread_decimal(row.get("spread_state")),
                "best_bid": None,
                "best_ask": None,
            },
            "payout": {"market_id": payload.get("market_id")},
            "exit_hold": {"liquidity_exit_quality": _liquidity_quality(row.get("liquidity_state"))},
            "market_movement": {"state": row.get("movement_state")} if row.get("movement_state") not in {None, "UNKNOWN"} else {},
        },
    )
    score_input = build_score_input(row, payload=payload, session=session, edge=edge, thesis=thesis)
    score = score_actionability_item(score_input)
    result_state = MESH_DATA_ONLY_COMPLETED
    if session.get("inquiry_state") == "ERROR":
        result_state = "PARTIAL"
    elif score.get("decision_band") == "UNKNOWN":
        result_state = "PARTIAL"
    return {
        "seed_mesh_result_id": _result_id(row.get("seed_mesh_inquiry_id")),
        "seed_mesh_inquiry_id": row.get("seed_mesh_inquiry_id"),
        "proactive_candidate_seed_id": row.get("proactive_candidate_seed_id"),
        "result_state": result_state,
        "edge_state": edge.get("edge_state") or session.get("edge_state") or "UNKNOWN",
        "trade_thesis_state": thesis.get("status") or "UNKNOWN",
        "trade_thesis_id": thesis.get("thesis_id"),
        "opportunity_score": score.get("overall_score"),
        "opportunity_score_id": score.get("opportunity_score_id"),
        "opportunity_decision_band": score.get("decision_band") or "UNKNOWN",
        "risk_state": score_input.get("risk_gate_state") or "UNKNOWN",
        "capital_state": score_input.get("capital_gate_state") or "UNKNOWN",
        "exit_state": score_input.get("exit_gate_state") or "UNKNOWN",
        "lifecycle_state": score_input.get("lifecycle_state") or "DATA_ONLY_RESEARCH",
        "paper_observation_eligible": bool(score.get("paper_observation_eligible")),
        "full_paper_ready": bool(score.get("full_paper_certification_ready")),
        "hard_blockers_json": score.get("hard_blockers") or [],
        "soft_blockers_json": score.get("soft_blockers") or [],
        "required_to_improve_json": score.get("required_to_improve") or [],
        "mesh_summary": _mesh_summary(session, edge, thesis, score),
        "metadata_json": {
            "stage": "MONEY_MACHINE_STAGE5_5",
            "adapter_payload_id": payload.get("adapter_payload_id"),
            "mesh_inquiry_session_id": session.get("mesh_session_id"),
            "edge_thesis_id": edge.get("edge_thesis_id") or session.get("edge_thesis_id"),
            "trade_thesis_id": thesis.get("thesis_id"),
            "opportunity_score_id": score.get("opportunity_score_id"),
            "research_only": True,
            "execution_allowed": False,
            "paper_allowed": False,
            "shadow_allowed": False,
            "live_allowed": False,
            "paper_observation_classification_only": True,
            "full_mesh_data_only": True,
            "lineage": payload.get("lineage_json") or {},
            "score": score,
            "thesis": thesis,
        },
    }


def build_score_input(row: dict[str, Any], *, payload: dict[str, Any], session: dict[str, Any], edge: dict[str, Any], thesis: dict[str, Any]) -> dict[str, Any]:
    edge_state = edge.get("edge_state") or session.get("edge_state") or "UNKNOWN"
    risk_state = "RISK_OK" if edge.get("risk_usable") is True and edge_state == "EDGE_SUPPORTED" else "RISK_REVIEW"
    exit_state = "EXIT_READY" if thesis.get("exit_intent") and thesis.get("exit_intent") != "UNKNOWN_EXIT" and thesis.get("status") in {"THESIS_SUPPORTED", "THESIS_WATCH"} else "EXIT_NOT_READY"
    return {
        "candidate_id": payload["synthetic_candidate_id"],
        "market_id": payload.get("market_id"),
        "condition_id": payload.get("condition_id"),
        "side": payload.get("side"),
        "token_id": payload.get("token_id"),
        "edge_state": edge_state,
        "edge_score": edge.get("edge_score") or session.get("edge_score") or 0.0,
        "source_backed": edge.get("source_backed") is True or session.get("source_backed") is True,
        "risk_usable": edge.get("risk_usable") is True or session.get("risk_usable") is True,
        "edge_thesis_id": edge.get("edge_thesis_id") or session.get("edge_thesis_id"),
        "edge_thesis": edge,
        "joined_trade_thesis": thesis,
        "thesis_id": thesis.get("thesis_id") if thesis.get("status") != "THESIS_MISSING" else None,
        "trade_thesis_type": thesis.get("trade_thesis_type"),
        "exit_intent": thesis.get("exit_intent"),
        "expected_hold_time_hours": thesis.get("expected_hold_time_hours"),
        "expected_reward": thesis.get("expected_reward"),
        "expected_price_move": thesis.get("expected_price_move"),
        "profit_if_win": thesis.get("expected_reward"),
        "risk_gate_state": risk_state,
        "capital_gate_state": "CAPITAL_WATCH",
        "exit_gate_state": exit_state,
        "lifecycle_state": "DATA_ONLY_RESEARCH",
        "candidate_event_scope": "CANDIDATE_SCOPED",
        "candidate_event_actionability_scope": "CANDIDATE_SCOPED",
        "candidate_event_link_state": "LINKED_TO_CANDIDATE",
        "token_side_resolution_state": row.get("token_side_resolution_state") or "TOKEN_SIDE_DIRECT",
        "candidate_trusted_orderbook_state": "FRESH",
        "candidate_price_path_state": "FRESH",
        "orderbook_snapshot_id": payload.get("orderbook_snapshot_id"),
        "selected_orderbook_snapshot_id": payload.get("orderbook_snapshot_id"),
        "selected_candidate_event_id": payload.get("source_event_id"),
        "event_id": payload.get("source_event_id"),
        "targeted_revalidation_id": payload.get("targeted_revalidation_id"),
        "proactive_seed_id": payload.get("proactive_candidate_seed_id"),
        "seed_type": "EVENT_RECALL_REVALIDATED_MARKET",
        "research_only": True,
        "seed_execution_allowed": False,
        "seed_paper_allowed": False,
        "seed_shadow_allowed": False,
        "seed_live_allowed": False,
        "seed_mesh_inquiry_id": payload.get("seed_mesh_inquiry_id"),
        "adapter_payload_id": payload.get("adapter_payload_id"),
        "seed_mesh_result_state": MESH_DATA_ONLY_COMPLETED,
        "seed_mesh_research_only": True,
        "operational_paper_execution_state": "DATA_ONLY",
        "propagation_context": {"mesh_inquiry_session_id": session.get("mesh_session_id")},
        "research_watchlist_id": payload.get("research_watchlist_id"),
        "research_priority_band": row.get("priority_band"),
        "research_priority_score": _float(row.get("priority_score")) or 0.0,
    }


def build_blocked_adapter_result(row: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    return {
        "seed_mesh_result_id": _result_id(row.get("seed_mesh_inquiry_id")),
        "seed_mesh_inquiry_id": row.get("seed_mesh_inquiry_id"),
        "proactive_candidate_seed_id": row.get("proactive_candidate_seed_id"),
        "result_state": "BLOCKED",
        "edge_state": "UNKNOWN",
        "trade_thesis_state": "UNKNOWN",
        "opportunity_score": None,
        "opportunity_decision_band": "UNKNOWN",
        "risk_state": "UNKNOWN",
        "capital_state": "UNKNOWN",
        "exit_state": "UNKNOWN",
        "lifecycle_state": "UNKNOWN",
        "paper_observation_eligible": False,
        "full_paper_ready": False,
        "hard_blockers_json": verdict.get("blockers") or [],
        "soft_blockers_json": verdict.get("warnings") or [],
        "required_to_improve_json": verdict.get("blockers") or [],
        "mesh_summary": "Adapter blocked unsafe or incomplete proactive seed before Mesh invocation.",
        "metadata_json": {"stage": "MONEY_MACHINE_STAGE5_5", "adapter_blocked": True, "fake_mesh_result": False},
    }


def build_failed_adapter_result(row: dict[str, Any], *, payload: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "seed_mesh_result_id": _result_id(row.get("seed_mesh_inquiry_id")),
        "seed_mesh_inquiry_id": row.get("seed_mesh_inquiry_id"),
        "proactive_candidate_seed_id": row.get("proactive_candidate_seed_id"),
        "result_state": "FAILED",
        "edge_state": "UNKNOWN",
        "trade_thesis_state": "UNKNOWN",
        "opportunity_score": None,
        "opportunity_decision_band": "UNKNOWN",
        "risk_state": "UNKNOWN",
        "capital_state": "UNKNOWN",
        "exit_state": "UNKNOWN",
        "lifecycle_state": "UNKNOWN",
        "paper_observation_eligible": False,
        "full_paper_ready": False,
        "hard_blockers_json": ["ADAPTER_MESH_INVOCATION_FAILED"],
        "soft_blockers_json": [],
        "required_to_improve_json": [reason],
        "mesh_summary": f"Adapter failed before completing DATA_ONLY Mesh review: {reason}",
        "metadata_json": {"stage": "MONEY_MACHINE_STAGE5_5", "adapter_payload_id": payload.get("adapter_payload_id"), "error": reason},
    }


def _mesh_summary(session: dict[str, Any], edge: dict[str, Any], thesis: dict[str, Any], score: dict[str, Any]) -> str:
    return (
        f"DATA_ONLY Mesh review completed for proactive research seed. "
        f"Mesh={session.get('inquiry_state')}; Edge={edge.get('edge_state') or session.get('edge_state')}; "
        f"Thesis={thesis.get('status')}; Band={score.get('decision_band')}; "
        "no execution or paper authority granted."
    )


def _spread_decimal(spread_state: Any) -> Decimal | None:
    state = str(spread_state or "").upper()
    if state == "TIGHT":
        return Decimal("0.02")
    if state == "MEDIUM":
        return Decimal("0.05")
    if state == "WIDE":
        return Decimal("0.12")
    return None


def _liquidity_quality(value: Any) -> str:
    state = str(value or "").upper()
    if state == "GOOD":
        return "GOOD"
    if state == "MEDIUM":
        return "FAIR"
    if state == "POOR":
        return "POOR"
    return "UNKNOWN"


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(part) for key, part in value.items()}
    if isinstance(value, list):
        return [_jsonable(part) for part in value]
    if isinstance(value, tuple):
        return [_jsonable(part) for part in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory


DEFAULT_REFRESH_LIMIT = 50
DEFAULT_RECENT_TTL_HOURS = 24
SAFE_MESH_CONTRACT_MISSING = "SAFE_MESH_CONTRACT_MISSING"
DATA_ONLY_MESH_HANDOFF = "DATA_ONLY"
ALLOWED_PRIORITY_BANDS = {"HIGH", "MEDIUM"}
ALLOWED_SIDES = {"YES", "NO"}
ALLOWED_TOKEN_SIDE_STATES = {"TOKEN_SIDE_DIRECT", "SIDE_DIRECTIONAL_YES", "SIDE_DIRECTIONAL_NO"}


class ProactiveSeedMeshInquiryService:
    """Persisted DATA_ONLY Mesh inquiry contract for proactive research seeds.

    Stage 5 creates auditable handoff requests/results for clean proactive
    candidate seeds. It does not create execution candidates, paper artifacts,
    orders, capital allocation, or synthetic Mesh approvals.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def refresh(self, *, limit: int = DEFAULT_REFRESH_LIMIT, force: bool = False) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"proactive_seed_mesh_inquiry_{uuid4().hex}"
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "mesh_inquiry_run_id": run_id, "seeds_available": 0}
        limit = max(1, min(int(limit or DEFAULT_REFRESH_LIMIT), 500))
        with self._factory.connect() as conn, conn.transaction():
            self._ensure_tables(conn)
            safety_before = _safety_counts(conn)
            rows = self._candidate_seed_rows(conn, limit=limit, force=force)
            stats = {
                "seeds_available": len(rows),
                "seeds_selected": 0,
                "requests_created": 0,
                "requests_skipped": 0,
                "requests_blocked": 0,
                "requests_failed": 0,
                "results_created": 0,
            }
            errors: list[str] = []
            for row in rows:
                try:
                    verdict = evaluate_seed_mesh_selection(row)
                    stats["seeds_selected"] += int(verdict["selected"])
                    inquiry = build_seed_mesh_inquiry_request(row, verdict=verdict, run_id=run_id)
                    existed = self._inquiry_exists(conn, inquiry["seed_mesh_inquiry_id"])
                    self._upsert_inquiry(conn, inquiry)
                    result = build_seed_mesh_result(inquiry)
                    self._upsert_result(conn, result)
                    stats["results_created"] += 0 if existed and not force else 1
                    state = str(inquiry["request_state"])
                    stats["requests_created"] += int(verdict["selected"])
                    stats["requests_skipped"] += int(state == "SKIPPED")
                    stats["requests_blocked"] += int(state == "BLOCKED")
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    stats["requests_failed"] += 1
            safety_after = _safety_counts(conn)
            completed_at = datetime.now(UTC)
            status = "OK" if not errors else "PARTIAL" if rows else "ERROR"
            self._insert_run(
                conn,
                mesh_inquiry_run_id=run_id,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                latest_error=errors[0] if errors else None,
                metadata={
                    "limit": limit,
                    "force": force,
                    "mesh_handoff_mode": DATA_ONLY_MESH_HANDOFF,
                    "safe_mesh_contract": "PERSISTED_REQUEST_ONLY",
                    "mesh_invocation": SAFE_MESH_CONTRACT_MISSING,
                    "safety_before": safety_before,
                    "safety_after": safety_after,
                    "trading_mutation": _trading_mutation(safety_before, safety_after),
                    "execution_candidates_created": False,
                    "paper_artifacts_created": False,
                    "errors": errors[:5],
                },
                **stats,
            )
        return {
            "status": status,
            "mesh_inquiry_run_id": run_id,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            **stats,
            "errors": errors[:5],
        }

    def summary(self, *, limit: int = 10) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return _empty_summary("DATABASE_UNAVAILABLE", now)
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            counts = self._counts(conn)
            latest = self._latest_run(conn)
            completed = self._sample(conn, "psi.request_state IN ('COMPLETED','MESH_DATA_ONLY_COMPLETED')", limit=limit)
            skipped = self._sample(conn, "psi.request_state='SKIPPED'", limit=limit)
            blocked = self._sample(conn, "psi.request_state='BLOCKED'", limit=limit)
        return {
            "status": "REAL" if counts["total_inquiry_requests"] else "MISSING",
            "source": "proactive_seed_mesh_inquiries + proactive_seed_mesh_results",
            "last_updated": (latest or {}).get("completed_at") or now.isoformat(),
            "freshness_state": "FRESH" if latest and counts["total_inquiry_requests"] else "MISSING",
            "readiness_state": "READY" if counts["total_inquiry_requests"] else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if counts["total_inquiry_requests"] else "UNKNOWN",
            "counts": counts,
            "latest_run_status": (latest or {}).get("status"),
            "latest_error": (latest or {}).get("latest_error"),
            "latest_mesh_inquiry_run": latest,
            "sample_completed_results": completed,
            "sample_skipped_requests": skipped,
            "sample_blocked_requests": blocked,
            "warnings": [] if counts["total_inquiry_requests"] else ["No proactive seed Mesh inquiry requests have been persisted yet."],
            "errors": [],
            "generated_at": now.isoformat(),
        }

    def by_seed(self, *, proactive_candidate_seed_id: str, limit: int = 20) -> dict[str, Any]:
        return self._by_field("proactive_candidate_seed_id", proactive_candidate_seed_id, limit=limit)

    def by_market(self, *, market_id: str, limit: int = 20) -> dict[str, Any]:
        return self._by_field("market_id", market_id, limit=limit)

    def by_event(self, *, source_event_id: str, limit: int = 50) -> dict[str, Any]:
        return self._by_field("source_event_id", source_event_id, limit=limit)

    def fields_for_seed(self, *, proactive_candidate_seed_id: str | None) -> dict[str, Any]:
        if not proactive_candidate_seed_id or not self._factory.enabled:
            return _empty_seed_fields()
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                """
                SELECT psi.*, psr.result_state, psr.edge_state, psr.trade_thesis_state,
                       psr.opportunity_score, psr.opportunity_decision_band,
                       psr.paper_observation_eligible, psr.full_paper_ready,
                       pap.adapter_payload_id
                FROM proactive_seed_mesh_inquiries psi
                LEFT JOIN proactive_seed_mesh_results psr ON psr.seed_mesh_inquiry_id=psi.seed_mesh_inquiry_id
                LEFT JOIN proactive_seed_mesh_adapter_payloads pap ON pap.seed_mesh_inquiry_id=psi.seed_mesh_inquiry_id
                WHERE psi.proactive_candidate_seed_id=%s
                ORDER BY psi.updated_at DESC, pap.updated_at DESC NULLS LAST, psi.id DESC
                LIMIT 1
                """,
                (proactive_candidate_seed_id,),
            ).fetchone()
        if not row:
            return _empty_seed_fields()
        item = _jsonable(dict(row))
        return {
            "seed_mesh_inquiry_id": item.get("seed_mesh_inquiry_id"),
            "seed_mesh_adapter_payload_id": item.get("adapter_payload_id"),
            "seed_mesh_adapter_result_state": item.get("result_state"),
            "mesh_inquiry_request_count": 1,
            "mesh_completed_count": 1 if item.get("request_state") in {"COMPLETED", "MESH_DATA_ONLY_COMPLETED"} else 0,
            "seed_mesh_result_state": item.get("result_state"),
            "seed_mesh_edge_state": item.get("edge_state"),
            "seed_mesh_trade_thesis_state": item.get("trade_thesis_state"),
            "seed_mesh_opportunity_score": item.get("opportunity_score"),
            "seed_mesh_opportunity_decision_band": item.get("opportunity_decision_band"),
            "paper_observation_eligible_from_seed_mesh": bool(item.get("paper_observation_eligible")),
            "full_paper_ready_from_seed_mesh": bool(item.get("full_paper_ready")),
            "seed_mesh_research_only": bool(item.get("research_only")),
            "seed_mesh_execution_allowed": bool(item.get("execution_allowed")),
            **_observation_policy_fields(conn, proactive_candidate_seed_id),
        }

    def fields_for_market(self, *, market_id: str | None) -> dict[str, Any]:
        if not market_id or not self._factory.enabled:
            return _empty_market_fields()
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS seed_mesh_inquiry_count,
                    COUNT(*) FILTER (WHERE psi.request_state IN ('COMPLETED','MESH_DATA_ONLY_COMPLETED')) AS mesh_completed_count,
                    MAX(psr.opportunity_score) AS seed_mesh_best_score,
                    (ARRAY_AGG(psr.opportunity_decision_band ORDER BY psr.opportunity_score DESC NULLS LAST, psr.updated_at DESC NULLS LAST))[1] AS seed_mesh_best_decision_band,
                    COUNT(*) FILTER (WHERE psr.paper_observation_eligible IS TRUE) AS paper_observation_interest_from_seed_mesh,
                    COUNT(*) FILTER (WHERE psr.edge_state='EDGE_SUPPORTED') AS downstream_edge_supported_count
                FROM proactive_seed_mesh_inquiries psi
                LEFT JOIN proactive_seed_mesh_results psr ON psr.seed_mesh_inquiry_id=psi.seed_mesh_inquiry_id
                WHERE psi.market_id=%s
                """,
                (market_id,),
            ).fetchone()
        item = dict(row or {})
        out = {
            "seed_mesh_inquiry_count": int(item.get("seed_mesh_inquiry_count") or 0),
            "mesh_completed_count": int(item.get("mesh_completed_count") or 0),
            "seed_mesh_best_score": _float(item.get("seed_mesh_best_score")),
            "seed_mesh_best_decision_band": item.get("seed_mesh_best_decision_band"),
            "paper_observation_interest_from_seed_mesh": int(item.get("paper_observation_interest_from_seed_mesh") or 0),
            "downstream_edge_supported_count": int(item.get("downstream_edge_supported_count") or 0),
        }
        out.update(_observation_policy_market_fields(conn, market_id))
        return out

    def fields_for_event(self, *, source_event_id: str | None) -> dict[str, Any]:
        if not source_event_id or not self._factory.enabled:
            return {"downstream_seed_mesh_count": 0, "downstream_edge_supported_count": 0}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                """
                SELECT COUNT(*) AS downstream_seed_mesh_count,
                       COUNT(*) FILTER (WHERE psr.edge_state='EDGE_SUPPORTED') AS downstream_edge_supported_count
                FROM proactive_seed_mesh_inquiries psi
                LEFT JOIN proactive_seed_mesh_results psr ON psr.seed_mesh_inquiry_id=psi.seed_mesh_inquiry_id
                WHERE psi.source_event_id=%s
                """,
                (source_event_id,),
            ).fetchone()
        return {
            "downstream_seed_mesh_count": int((row or {}).get("downstream_seed_mesh_count") or 0),
            "downstream_edge_supported_count": int((row or {}).get("downstream_edge_supported_count") or 0),
        }

    def _candidate_seed_rows(self, conn: Any, *, limit: int, force: bool) -> list[dict[str, Any]]:
        if not _table_exists(conn, "proactive_candidate_seeds"):
            return []
        priority_join = """
            LEFT JOIN LATERAL (
                SELECT research_watchlist_id, priority_band, priority_score
                FROM research_priority_watchlist rpw
                WHERE rpw.market_id=pcs.market_id
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
            ) rpw ON true
        """ if _table_exists(conn, "research_priority_watchlist") else """
            LEFT JOIN LATERAL (
                SELECT NULL::text AS research_watchlist_id, NULL::text AS priority_band, NULL::numeric AS priority_score
            ) rpw ON true
        """
        recent_filter = "" if force else """
            AND NOT EXISTS (
                SELECT 1
                FROM proactive_seed_mesh_inquiries psi
                WHERE psi.proactive_candidate_seed_id=pcs.proactive_candidate_seed_id
                  AND psi.updated_at >= now() - interval '24 hours'
            )
        """
        rows = conn.execute(
            f"""
            SELECT pcs.*, rpw.research_watchlist_id, rpw.priority_band, rpw.priority_score
            FROM proactive_candidate_seeds pcs
            {priority_join}
            WHERE pcs.updated_at >= now() - interval '7 days'
              {recent_filter}
            ORDER BY
                CASE
                    WHEN pcs.seed_state = 'GENERATED'
                     AND pcs.research_only IS TRUE
                     AND COALESCE(pcs.execution_allowed, false) IS FALSE
                     AND COALESCE(pcs.paper_allowed, false) IS FALSE
                     AND COALESCE(pcs.shadow_allowed, false) IS FALSE
                     AND COALESCE(pcs.live_allowed, false) IS FALSE
                     AND pcs.side IN ('YES', 'NO')
                     AND pcs.token_id IS NOT NULL
                     AND pcs.market_id IS NOT NULL
                     AND pcs.orderbook_refresh_state = 'FRESH'
                     AND pcs.token_side_resolution_state IN ('TOKEN_SIDE_DIRECT', 'SIDE_DIRECTIONAL_YES', 'SIDE_DIRECTIONAL_NO')
                     AND rpw.priority_band IN ('HIGH', 'MEDIUM')
                    THEN 0 ELSE 1
                END,
                CASE rpw.priority_band WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 WHEN 'LOW' THEN 2 ELSE 3 END,
                rpw.priority_score DESC NULLS LAST,
                pcs.link_confidence DESC,
                pcs.updated_at DESC,
                pcs.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _by_field(self, field: str, value: str, *, limit: int) -> dict[str, Any]:
        if not value:
            return {"status": "BLOCKED", "blocker": f"{field.upper()}_REQUIRED", "results": []}
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "results": []}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            rows = conn.execute(
                f"""
                SELECT psi.*, psr.*
                FROM proactive_seed_mesh_inquiries psi
                LEFT JOIN proactive_seed_mesh_results psr ON psr.seed_mesh_inquiry_id=psi.seed_mesh_inquiry_id
                WHERE psi.{field}=%s
                ORDER BY psi.updated_at DESC, psi.id DESC
                LIMIT %s
                """,
                (value, limit),
            ).fetchall()
        return {"status": "REAL" if rows else "MISSING", field: value, "results": [_jsonable(dict(row)) for row in rows]}

    def _inquiry_exists(self, conn: Any, inquiry_id: str) -> bool:
        return bool(conn.execute("SELECT 1 FROM proactive_seed_mesh_inquiries WHERE seed_mesh_inquiry_id=%s LIMIT 1", (inquiry_id,)).fetchone())

    def _upsert_inquiry(self, conn: Any, record: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO proactive_seed_mesh_inquiries (
                seed_mesh_inquiry_id, mesh_inquiry_run_id, proactive_candidate_seed_id,
                source_event_id, event_to_market_link_id, targeted_revalidation_id, market_memory_id,
                research_watchlist_id, market_id, condition_id, side, token_id, priority_band, priority_score,
                request_state, mesh_handoff_mode, research_only, execution_allowed, paper_allowed,
                shadow_allowed, live_allowed, mesh_inquiry_session_id, edge_result_id, trade_thesis_id,
                opportunity_score_id, risk_evidence_id, capital_evidence_id, exit_evidence_id,
                lifecycle_evidence_id, blockers_json, warnings_json, required_to_pass_json, metadata_json
            )
            VALUES (
                %(seed_mesh_inquiry_id)s, %(mesh_inquiry_run_id)s, %(proactive_candidate_seed_id)s,
                %(source_event_id)s, %(event_to_market_link_id)s, %(targeted_revalidation_id)s, %(market_memory_id)s,
                %(research_watchlist_id)s, %(market_id)s, %(condition_id)s, %(side)s, %(token_id)s, %(priority_band)s, %(priority_score)s,
                %(request_state)s, %(mesh_handoff_mode)s, %(research_only)s, %(execution_allowed)s, %(paper_allowed)s,
                %(shadow_allowed)s, %(live_allowed)s, %(mesh_inquiry_session_id)s, %(edge_result_id)s, %(trade_thesis_id)s,
                %(opportunity_score_id)s, %(risk_evidence_id)s, %(capital_evidence_id)s, %(exit_evidence_id)s,
                %(lifecycle_evidence_id)s, %(blockers_json)s, %(warnings_json)s, %(required_to_pass_json)s, %(metadata_json)s
            )
            ON CONFLICT (seed_mesh_inquiry_id) DO UPDATE SET
                mesh_inquiry_run_id=EXCLUDED.mesh_inquiry_run_id,
                request_state=EXCLUDED.request_state,
                priority_band=EXCLUDED.priority_band,
                priority_score=EXCLUDED.priority_score,
                blockers_json=EXCLUDED.blockers_json,
                warnings_json=EXCLUDED.warnings_json,
                required_to_pass_json=EXCLUDED.required_to_pass_json,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            {
                **record,
                "blockers_json": Jsonb(record.get("blockers_json") or []),
                "warnings_json": Jsonb(record.get("warnings_json") or []),
                "required_to_pass_json": Jsonb(record.get("required_to_pass_json") or []),
                "metadata_json": Jsonb(_jsonable(record.get("metadata_json") or {})),
            },
        )

    def _upsert_result(self, conn: Any, record: dict[str, Any]) -> None:
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
                **record,
                "hard_blockers_json": Jsonb(record.get("hard_blockers_json") or []),
                "soft_blockers_json": Jsonb(record.get("soft_blockers_json") or []),
                "required_to_improve_json": Jsonb(record.get("required_to_improve_json") or []),
                "metadata_json": Jsonb(_jsonable(record.get("metadata_json") or {})),
            },
        )

    def _insert_run(self, conn: Any, *, mesh_inquiry_run_id: str, status: str, started_at: datetime, completed_at: datetime, latest_error: str | None, metadata: dict[str, Any], **stats: Any) -> None:
        conn.execute(
            """
            INSERT INTO proactive_seed_mesh_inquiry_runs (
                mesh_inquiry_run_id, status, started_at, completed_at, seeds_available, seeds_selected,
                requests_created, requests_skipped, requests_blocked, requests_failed, results_created,
                latest_error, metadata_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (mesh_inquiry_run_id) DO UPDATE SET
                status=EXCLUDED.status,
                completed_at=EXCLUDED.completed_at,
                seeds_available=EXCLUDED.seeds_available,
                seeds_selected=EXCLUDED.seeds_selected,
                requests_created=EXCLUDED.requests_created,
                requests_skipped=EXCLUDED.requests_skipped,
                requests_blocked=EXCLUDED.requests_blocked,
                requests_failed=EXCLUDED.requests_failed,
                results_created=EXCLUDED.results_created,
                latest_error=EXCLUDED.latest_error,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            (
                mesh_inquiry_run_id,
                status,
                started_at,
                completed_at,
                int(stats.get("seeds_available") or 0),
                int(stats.get("seeds_selected") or 0),
                int(stats.get("requests_created") or 0),
                int(stats.get("requests_skipped") or 0),
                int(stats.get("requests_blocked") or 0),
                int(stats.get("requests_failed") or 0),
                int(stats.get("results_created") or 0),
                latest_error,
                Jsonb(_jsonable(metadata)),
            ),
        )

    def _counts(self, conn: Any) -> dict[str, Any]:
        requests = conn.execute(
            """
            SELECT
                COUNT(*) AS total_inquiry_requests,
                COUNT(*) FILTER (WHERE request_state='PENDING') AS pending_count,
                COUNT(*) FILTER (WHERE request_state='SENT') AS sent_count,
                COUNT(*) FILTER (WHERE request_state='COMPLETED') AS completed_count,
                COUNT(*) FILTER (WHERE request_state='MESH_DATA_ONLY_COMPLETED') AS mesh_data_only_completed_request_count,
                COUNT(*) FILTER (WHERE request_state='PARTIAL') AS partial_count,
                COUNT(*) FILTER (WHERE request_state='SKIPPED') AS skipped_count,
                COUNT(*) FILTER (WHERE request_state='BLOCKED') AS blocked_count,
                COUNT(*) FILTER (WHERE request_state='FAILED') AS failed_count,
                COUNT(*) FILTER (WHERE priority_band='HIGH') AS high_seed_count,
                COUNT(*) FILTER (WHERE priority_band='MEDIUM') AS medium_seed_count,
                COUNT(*) FILTER (WHERE priority_band='LOW') AS low_seed_count
            FROM proactive_seed_mesh_inquiries
            """
        ).fetchone()
        results = conn.execute(
            """
            SELECT
                COUNT(*) AS results_count,
                COUNT(*) FILTER (WHERE result_state='MESH_DATA_ONLY_COMPLETED') AS mesh_data_only_completed_count,
                COUNT(*) FILTER (WHERE result_state='PARTIAL') AS adapter_partial_count,
                COUNT(*) FILTER (WHERE result_state='FAILED') AS adapter_failed_result_count,
                COUNT(*) FILTER (WHERE paper_observation_eligible IS TRUE) AS paper_observation_eligible_count,
                COUNT(*) FILTER (WHERE full_paper_ready IS TRUE) AS full_paper_ready_count
            FROM proactive_seed_mesh_results
            """
        ).fetchone()
        edge = conn.execute("SELECT edge_state, COUNT(*) AS count FROM proactive_seed_mesh_results GROUP BY edge_state").fetchall()
        thesis = conn.execute("SELECT trade_thesis_state, COUNT(*) AS count FROM proactive_seed_mesh_results GROUP BY trade_thesis_state").fetchall()
        bands = conn.execute("SELECT opportunity_decision_band, COUNT(*) AS count FROM proactive_seed_mesh_results GROUP BY opportunity_decision_band").fetchall()
        blockers = conn.execute(
            """
            SELECT blocker, COUNT(*) AS count
            FROM proactive_seed_mesh_inquiries,
                 LATERAL jsonb_array_elements_text(blockers_json) AS blocker
            GROUP BY blocker
            ORDER BY count DESC, blocker
            """
        ).fetchall()
        warnings = conn.execute(
            """
            SELECT warning, COUNT(*) AS count
            FROM proactive_seed_mesh_inquiries,
                 LATERAL jsonb_array_elements_text(warnings_json) AS warning
            GROUP BY warning
            ORDER BY count DESC, warning
            """
        ).fetchall()
        out = {key: int(value or 0) for key, value in dict(requests or {}).items()}
        out.update({key: int(value or 0) for key, value in dict(results or {}).items()})
        out["seeds_selected_count"] = out.get("skipped_count", 0) + out.get("completed_count", 0) + out.get("sent_count", 0)
        out["edge_state_counts"] = {str(row["edge_state"]): int(row["count"] or 0) for row in edge}
        out["trade_thesis_state_counts"] = {str(row["trade_thesis_state"]): int(row["count"] or 0) for row in thesis}
        out["opportunity_decision_band_counts"] = {str(row["opportunity_decision_band"]): int(row["count"] or 0) for row in bands}
        out["hard_blocker_counts"] = {str(row["blocker"]): int(row["count"] or 0) for row in blockers}
        out["soft_blocker_counts"] = {str(row["warning"]): int(row["count"] or 0) for row in warnings}
        out["seeds_skipped_by_reason"] = dict(out["hard_blocker_counts"])
        out["adapter_available"] = True
        out["safe_mesh_contract_missing_remaining_count"] = int(out["hard_blocker_counts"].get(SAFE_MESH_CONTRACT_MISSING, 0))
        out["adapter_payload_count"] = 0
        out["adapter_processed_count"] = 0
        out["adapter_completed_count"] = int(out.get("mesh_data_only_completed_count") or 0)
        out["adapter_partial_count"] = int(out.get("adapter_partial_count") or 0)
        out["adapter_failed_count"] = int(out.get("adapter_failed_result_count") or 0)
        out["adapter_skipped_count"] = int(out.get("skipped_count") or 0)
        if _table_exists(conn, "proactive_seed_mesh_adapter_payloads"):
            row = conn.execute("SELECT COUNT(*) AS count FROM proactive_seed_mesh_adapter_payloads").fetchone()
            out["adapter_payload_count"] = int((row or {}).get("count") or 0)
        if _table_exists(conn, "proactive_seed_mesh_adapter_runs"):
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(processed_count),0) AS adapter_processed_count,
                    COALESCE(SUM(skipped_count),0) AS adapter_skipped_count
                FROM proactive_seed_mesh_adapter_runs
                """
            ).fetchone()
            for key, value in dict(row or {}).items():
                out[key] = int(value or 0)
        adapter_results = conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE result_state='MESH_DATA_ONLY_COMPLETED') AS adapter_completed_count,
                COUNT(*) FILTER (WHERE result_state='PARTIAL') AS adapter_partial_count,
                COUNT(*) FILTER (WHERE result_state='FAILED') AS adapter_failed_count
            FROM proactive_seed_mesh_results
            WHERE metadata_json->>'stage'='MONEY_MACHINE_STAGE5_5'
            """
        ).fetchone()
        for key, value in dict(adapter_results or {}).items():
            out[key] = int(value or 0)
        return out

    def _sample(self, conn: Any, where: str, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"""
            SELECT psi.*, psr.result_state, psr.edge_state, psr.trade_thesis_state,
                   psr.opportunity_score, psr.opportunity_decision_band,
                   psr.paper_observation_eligible, psr.full_paper_ready, psr.mesh_summary
            FROM proactive_seed_mesh_inquiries psi
            LEFT JOIN proactive_seed_mesh_results psr ON psr.seed_mesh_inquiry_id=psi.seed_mesh_inquiry_id
            WHERE {where}
            ORDER BY psi.priority_score DESC, psi.updated_at DESC, psi.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _latest_run(self, conn: Any) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM proactive_seed_mesh_inquiry_runs
            ORDER BY completed_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ).fetchone()
        return _jsonable(dict(row)) if row else None

    def _ensure_tables(self, conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proactive_seed_mesh_inquiries (
                id BIGSERIAL PRIMARY KEY,
                seed_mesh_inquiry_id TEXT NOT NULL UNIQUE,
                mesh_inquiry_run_id TEXT,
                proactive_candidate_seed_id TEXT NOT NULL,
                source_event_id TEXT,
                event_to_market_link_id TEXT,
                targeted_revalidation_id TEXT,
                market_memory_id TEXT,
                research_watchlist_id TEXT,
                market_id TEXT,
                condition_id TEXT,
                side TEXT NOT NULL,
                token_id TEXT,
                priority_band TEXT,
                priority_score NUMERIC NOT NULL DEFAULT 0,
                request_state TEXT NOT NULL DEFAULT 'PENDING',
                mesh_handoff_mode TEXT NOT NULL DEFAULT 'DATA_ONLY',
                research_only BOOLEAN NOT NULL DEFAULT TRUE,
                execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                paper_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                shadow_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                live_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                mesh_inquiry_session_id TEXT,
                edge_result_id TEXT,
                trade_thesis_id TEXT,
                opportunity_score_id TEXT,
                risk_evidence_id TEXT,
                capital_evidence_id TEXT,
                exit_evidence_id TEXT,
                lifecycle_evidence_id TEXT,
                blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proactive_seed_mesh_results (
                id BIGSERIAL PRIMARY KEY,
                seed_mesh_result_id TEXT NOT NULL UNIQUE,
                seed_mesh_inquiry_id TEXT NOT NULL,
                proactive_candidate_seed_id TEXT NOT NULL,
                result_state TEXT NOT NULL DEFAULT 'SKIPPED',
                edge_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                trade_thesis_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                opportunity_score NUMERIC,
                opportunity_decision_band TEXT NOT NULL DEFAULT 'UNKNOWN',
                risk_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                capital_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                exit_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                lifecycle_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                paper_observation_eligible BOOLEAN NOT NULL DEFAULT FALSE,
                full_paper_ready BOOLEAN NOT NULL DEFAULT FALSE,
                hard_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                soft_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                required_to_improve_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                mesh_summary TEXT,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proactive_seed_mesh_inquiry_runs (
                id BIGSERIAL PRIMARY KEY,
                mesh_inquiry_run_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                seeds_available INTEGER NOT NULL DEFAULT 0,
                seeds_selected INTEGER NOT NULL DEFAULT 0,
                requests_created INTEGER NOT NULL DEFAULT 0,
                requests_skipped INTEGER NOT NULL DEFAULT 0,
                requests_blocked INTEGER NOT NULL DEFAULT 0,
                requests_failed INTEGER NOT NULL DEFAULT 0,
                results_created INTEGER NOT NULL DEFAULT 0,
                latest_error TEXT,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def evaluate_seed_mesh_selection(seed: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if seed.get("seed_state") != "GENERATED":
        blockers.append(f"SEED_STATE_NOT_GENERATED_{seed.get('seed_state') or 'UNKNOWN'}")
    if seed.get("research_only") is not True:
        blockers.append("SEED_NOT_RESEARCH_ONLY")
    for flag in ("execution_allowed", "paper_allowed", "shadow_allowed", "live_allowed"):
        if seed.get(flag) is True:
            blockers.append(f"{flag.upper()}_MUST_BE_FALSE")
    if str(seed.get("side") or "") not in ALLOWED_SIDES:
        blockers.append("SIDE_NOT_MESH_ELIGIBLE")
    if not seed.get("token_id"):
        blockers.append("TOKEN_ID_MISSING")
    if not seed.get("market_id"):
        blockers.append("MARKET_ID_MISSING")
    if not seed.get("condition_id"):
        warnings.append("CONDITION_ID_MISSING")
    if seed.get("orderbook_refresh_state") != "FRESH":
        blockers.append("ORDERBOOK_NOT_FRESH")
    if str(seed.get("token_side_resolution_state") or "") not in ALLOWED_TOKEN_SIDE_STATES:
        blockers.append("TOKEN_SIDE_NOT_DIRECT")
    if str(seed.get("token_side_resolution_state") or "") == "TOKEN_SIDE_CONFLICT":
        blockers.append("TOKEN_SIDE_CONFLICT")
    if seed.get("blockers_json"):
        blockers.extend(str(item) for item in _as_list(seed.get("blockers_json")) if item)
    priority = str(seed.get("priority_band") or "UNKNOWN")
    if priority not in ALLOWED_PRIORITY_BANDS:
        blockers.append(f"PRIORITY_NOT_SELECTED_{priority}")
    selected = not blockers
    if selected:
        blockers.append(SAFE_MESH_CONTRACT_MISSING)
        warnings.append("MESH_INVOCATION_SKIPPED_DATA_ONLY_CONTRACT_CREATED")
    state = "SKIPPED" if selected else "BLOCKED"
    required = _required_to_pass(blockers, warnings)
    return {
        "selected": selected,
        "request_state": state,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "required_to_pass": required,
    }


def build_seed_mesh_inquiry_request(seed: dict[str, Any], *, verdict: dict[str, Any], run_id: str) -> dict[str, Any]:
    return {
        "seed_mesh_inquiry_id": _inquiry_id(seed.get("proactive_candidate_seed_id")),
        "mesh_inquiry_run_id": run_id,
        "proactive_candidate_seed_id": seed.get("proactive_candidate_seed_id"),
        "source_event_id": seed.get("source_event_id"),
        "event_to_market_link_id": seed.get("event_to_market_link_id"),
        "targeted_revalidation_id": seed.get("targeted_revalidation_id"),
        "market_memory_id": seed.get("market_memory_id"),
        "research_watchlist_id": seed.get("research_watchlist_id"),
        "market_id": seed.get("market_id"),
        "condition_id": seed.get("condition_id"),
        "side": seed.get("side") or "SIDE_UNKNOWN",
        "token_id": seed.get("token_id"),
        "priority_band": seed.get("priority_band"),
        "priority_score": _float(seed.get("priority_score")) or 0.0,
        "request_state": verdict["request_state"],
        "mesh_handoff_mode": DATA_ONLY_MESH_HANDOFF,
        "research_only": True,
        "execution_allowed": False,
        "paper_allowed": False,
        "shadow_allowed": False,
        "live_allowed": False,
        "mesh_inquiry_session_id": None,
        "edge_result_id": None,
        "trade_thesis_id": None,
        "opportunity_score_id": None,
        "risk_evidence_id": None,
        "capital_evidence_id": None,
        "exit_evidence_id": None,
        "lifecycle_evidence_id": None,
        "blockers_json": verdict.get("blockers") or [],
        "warnings_json": verdict.get("warnings") or [],
        "required_to_pass_json": verdict.get("required_to_pass") or [],
        "metadata_json": {
            "stage": "MONEY_MACHINE_STAGE5",
            "safe_mesh_contract": "PERSISTED_DATA_ONLY_REQUEST",
            "mesh_invocation": SAFE_MESH_CONTRACT_MISSING,
            "source_seed_state": seed.get("seed_state"),
            "source_mesh_handoff_state": seed.get("mesh_handoff_state"),
            "lineage": {
                "source_event_id": seed.get("source_event_id"),
                "event_to_market_link_id": seed.get("event_to_market_link_id"),
                "targeted_revalidation_id": seed.get("targeted_revalidation_id"),
                "proactive_candidate_seed_id": seed.get("proactive_candidate_seed_id"),
                "research_watchlist_id": seed.get("research_watchlist_id"),
            },
        },
    }


def build_seed_mesh_result(inquiry: dict[str, Any]) -> dict[str, Any]:
    blockers = list(inquiry.get("blockers_json") or [])
    result_state = "SKIPPED" if SAFE_MESH_CONTRACT_MISSING in blockers else "BLOCKED"
    return {
        "seed_mesh_result_id": _result_id(inquiry.get("seed_mesh_inquiry_id")),
        "seed_mesh_inquiry_id": inquiry.get("seed_mesh_inquiry_id"),
        "proactive_candidate_seed_id": inquiry.get("proactive_candidate_seed_id"),
        "result_state": result_state,
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
        "hard_blockers_json": blockers,
        "soft_blockers_json": inquiry.get("warnings_json") or [],
        "required_to_improve_json": inquiry.get("required_to_pass_json") or [],
        "mesh_summary": "Mesh invocation skipped: no persisted proactive-seed DATA_ONLY Mesh input adapter exists yet.",
        "metadata_json": {
            "fake_mesh_result": False,
            "edge_created": False,
            "thesis_created": False,
            "score_created": False,
            "paper_intent_created": False,
            "execution_candidate_created": False,
        },
    }


def _required_to_pass(blockers: list[str], warnings: list[str]) -> list[str]:
    mapping = {
        SAFE_MESH_CONTRACT_MISSING: "Create and review a persisted proactive-seed DATA_ONLY Mesh input adapter before invoking Full Mesh.",
        "SEED_NOT_RESEARCH_ONLY": "Only research_only proactive seeds may enter Stage 5 Mesh inquiry.",
        "EXECUTION_ALLOWED_MUST_BE_FALSE": "Execution flags must remain false.",
        "PAPER_ALLOWED_MUST_BE_FALSE": "Paper permission must remain false for Stage 5.",
        "SHADOW_ALLOWED_MUST_BE_FALSE": "Shadow permission must remain false.",
        "LIVE_ALLOWED_MUST_BE_FALSE": "Live permission must remain false.",
        "SIDE_NOT_MESH_ELIGIBLE": "Resolve seed side to YES or NO before Mesh inquiry.",
        "TOKEN_ID_MISSING": "Resolve the side token id before Mesh inquiry.",
        "MARKET_ID_MISSING": "Resolve market id before Mesh inquiry.",
        "ORDERBOOK_NOT_FRESH": "Refresh exact candidate orderbook before Mesh inquiry.",
        "TOKEN_SIDE_NOT_DIRECT": "Resolve direct token-side mapping before Mesh inquiry.",
        "TOKEN_SIDE_CONFLICT": "Resolve token-side conflict without guessing.",
    }
    return _dedupe([mapping.get(item, item) for item in [*blockers, *warnings] if item])


def _inquiry_id(seed_id: Any) -> str:
    key = str(seed_id or uuid4().hex)
    return f"seed_mesh_inquiry_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:28]}"


def _result_id(inquiry_id: Any) -> str:
    key = str(inquiry_id or uuid4().hex)
    return f"seed_mesh_result_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:30]}"


def _empty_summary(status: str, now: datetime) -> dict[str, Any]:
    return {
        "status": status,
        "source": "proactive_seed_mesh_inquiry",
        "last_updated": now.isoformat(),
        "freshness_state": "MISSING",
        "readiness_state": "UNKNOWN",
        "truth_state": "UNKNOWN",
        "counts": {},
        "warnings": ["Proactive seed Mesh inquiry service is unavailable."],
        "errors": [],
    }


def _empty_seed_fields() -> dict[str, Any]:
    return {
        "seed_mesh_inquiry_id": None,
        "seed_mesh_adapter_payload_id": None,
        "seed_mesh_adapter_result_state": None,
        "mesh_inquiry_request_count": 0,
        "mesh_completed_count": 0,
        "seed_mesh_result_state": None,
        "seed_mesh_edge_state": None,
        "seed_mesh_trade_thesis_state": None,
        "seed_mesh_opportunity_score": None,
        "seed_mesh_opportunity_decision_band": None,
        "paper_observation_eligible_from_seed_mesh": False,
        "full_paper_ready_from_seed_mesh": False,
        "seed_mesh_research_only": None,
        "seed_mesh_execution_allowed": False,
        "paper_observation_policy_review_id": None,
        "paper_observation_policy_state": "NOT_REVIEWED",
        "observation_allowed_by_policy": False,
        "observation_policy_blockers": [],
    }


def _empty_market_fields() -> dict[str, Any]:
    return {
        "seed_mesh_inquiry_count": 0,
        "mesh_completed_count": 0,
        "seed_mesh_best_score": None,
        "seed_mesh_best_decision_band": None,
        "paper_observation_interest_from_seed_mesh": 0,
        "downstream_edge_supported_count": 0,
        "paper_observation_policy_review_count": 0,
        "paper_observation_policy_eligible_count": 0,
        "paper_observation_policy_watch_count": 0,
        "paper_observation_policy_blocked_count": 0,
    }


def _observation_policy_fields(conn: Any, proactive_candidate_seed_id: str | None) -> dict[str, Any]:
    if not proactive_candidate_seed_id or not _table_exists(conn, "paper_observation_policy_reviews"):
        return {
            "paper_observation_policy_review_id": None,
            "paper_observation_policy_state": "NOT_REVIEWED",
            "observation_allowed_by_policy": False,
            "observation_policy_blockers": [],
        }
    row = conn.execute(
        """
        SELECT paper_observation_policy_review_id, observation_policy_state,
               observation_allowed_by_policy, policy_blockers_json
        FROM paper_observation_policy_reviews
        WHERE proactive_candidate_seed_id=%s
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (proactive_candidate_seed_id,),
    ).fetchone()
    if not row:
        return {
            "paper_observation_policy_review_id": None,
            "paper_observation_policy_state": "NOT_REVIEWED",
            "observation_allowed_by_policy": False,
            "observation_policy_blockers": [],
        }
    return {
        "paper_observation_policy_review_id": row.get("paper_observation_policy_review_id"),
        "paper_observation_policy_state": row.get("observation_policy_state"),
        "observation_allowed_by_policy": bool(row.get("observation_allowed_by_policy")),
        "observation_policy_blockers": row.get("policy_blockers_json") or [],
    }


def _observation_policy_market_fields(conn: Any, market_id: str | None) -> dict[str, Any]:
    if not market_id or not _table_exists(conn, "paper_observation_policy_reviews"):
        return {
            "paper_observation_policy_review_count": 0,
            "paper_observation_policy_eligible_count": 0,
            "paper_observation_policy_watch_count": 0,
            "paper_observation_policy_blocked_count": 0,
        }
    row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE observation_policy_state='OBSERVATION_POLICY_ELIGIBLE') AS eligible,
               COUNT(*) FILTER (WHERE observation_policy_state='OBSERVATION_POLICY_WATCH') AS watch,
               COUNT(*) FILTER (WHERE observation_policy_state='OBSERVATION_POLICY_BLOCKED') AS blocked
        FROM paper_observation_policy_reviews
        WHERE market_id=%s
        """,
        (market_id,),
    ).fetchone()
    return {
        "paper_observation_policy_review_count": int((row or {}).get("total") or 0),
        "paper_observation_policy_eligible_count": int((row or {}).get("eligible") or 0),
        "paper_observation_policy_watch_count": int((row or {}).get("watch") or 0),
        "paper_observation_policy_blocked_count": int((row or {}).get("blocked") or 0),
    }


def _safety_counts(conn: Any) -> dict[str, int]:
    tables = (
        "paper_intents",
        "paper_orders",
        "paper_fills",
        "paper_positions",
        "live_orders",
        "positions",
        "shadow_orders",
        "fresh_candidate_seeds",
        "market_link_candidates",
        "paper_eligibility_candidates",
    )
    out: dict[str, int] = {}
    for table in tables:
        if _table_exists(conn, table):
            out[table] = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
        else:
            out[table] = 0
    return out


def _trading_mutation(before: dict[str, int], after: dict[str, int]) -> bool:
    watched = {"paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "positions", "shadow_orders", "fresh_candidate_seeds", "market_link_candidates"}
    return any(after.get(table, 0) != before.get(table, 0) for table in watched)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row.get("reg"))


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


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out

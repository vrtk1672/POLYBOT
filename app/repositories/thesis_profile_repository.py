from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.thesis_profiles import ThesisProfile, ThesisProfileRun


class ThesisProfileRepository:
    def list_runtime_coordinator_decisions(self, conn: Connection, *, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "coordinator_decisions"):
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    cd.*,
                    array_remove(array_agg(DISTINCT cdi.brain_output_id), NULL) AS source_brain_output_ids,
                    array_remove(array_agg(DISTINCT dep.dependency_id) FILTER (WHERE dep.dependency_type = 'signal'), NULL) AS dependency_signal_ids,
                    MAX(obs.id) AS orderbook_snapshot_id,
                    BOOL_OR(sml.signal_id IS NOT NULL) AS has_signal_market_binding
                FROM coordinator_decisions cd
                LEFT JOIN coordinator_decision_inputs cdi
                    ON cdi.coordinator_decision_id = cd.coordinator_decision_id
                LEFT JOIN brain_output_dependencies dep
                    ON dep.brain_output_id = cdi.brain_output_id
                LEFT JOIN signal_market_links sml
                    ON sml.signal_id = dep.dependency_id
                LEFT JOIN orderbook_snapshots obs
                    ON obs.market_id = cd.market_id
                   AND obs.snapshot_status = 'OK'
                   AND obs.is_stale = false
                   AND obs.collected_at >= now() - interval '120 seconds'
                WHERE cd.metadata_json->>'generated_by' = 'runtime'
                  AND cd.metadata_json->>'producer_name' = 'runtime_coordinator_adapter'
                  AND COALESCE(cd.metadata_json->>'is_runtime_generated', 'false') = 'true'
                  AND COALESCE(cd.metadata_json->>'is_dry_run_generated', 'false') = 'false'
                  AND cd.execution_allowed = false
                GROUP BY cd.id
                ORDER BY cd.created_at DESC, cd.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def upsert_profile(self, conn: Connection, profile: ThesisProfile) -> tuple[dict[str, Any], bool]:
        existing = conn.execute("SELECT 1 FROM thesis_profiles WHERE thesis_id = %s", (profile.thesis_id,)).fetchone()
        row = conn.execute(
            """
            INSERT INTO thesis_profiles (
                thesis_id, market_id, side, status, thesis_type, why_now, expected_move,
                confidence, evidence, missing_evidence, invalidation_rules, risk_notes,
                source_coordinator_decision_id, source_brain_output_ids, source_signal_ids,
                orderbook_snapshot_id, generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, paper_candidate_allowed, risk_required, exit_required,
                created_at, updated_at
            )
            VALUES (
                %(thesis_id)s, %(market_id)s, %(side)s, %(status)s, %(thesis_type)s,
                %(why_now)s, %(expected_move)s, %(confidence)s, %(evidence)s,
                %(missing_evidence)s, %(invalidation_rules)s, %(risk_notes)s,
                %(source_coordinator_decision_id)s, %(source_brain_output_ids)s,
                %(source_signal_ids)s, %(orderbook_snapshot_id)s, %(generated_by)s,
                %(producer_name)s, %(is_runtime_generated)s, %(is_dry_run_generated)s,
                FALSE, TRUE, TRUE, COALESCE(%(created_at)s, now()), now()
            )
            ON CONFLICT (thesis_id) DO UPDATE SET
                market_id = EXCLUDED.market_id,
                side = EXCLUDED.side,
                status = EXCLUDED.status,
                thesis_type = EXCLUDED.thesis_type,
                why_now = EXCLUDED.why_now,
                expected_move = EXCLUDED.expected_move,
                confidence = EXCLUDED.confidence,
                evidence = EXCLUDED.evidence,
                missing_evidence = EXCLUDED.missing_evidence,
                invalidation_rules = EXCLUDED.invalidation_rules,
                risk_notes = EXCLUDED.risk_notes,
                source_brain_output_ids = EXCLUDED.source_brain_output_ids,
                source_signal_ids = EXCLUDED.source_signal_ids,
                orderbook_snapshot_id = EXCLUDED.orderbook_snapshot_id,
                generated_by = EXCLUDED.generated_by,
                producer_name = EXCLUDED.producer_name,
                is_runtime_generated = EXCLUDED.is_runtime_generated,
                is_dry_run_generated = EXCLUDED.is_dry_run_generated,
                paper_candidate_allowed = FALSE,
                risk_required = TRUE,
                exit_required = TRUE,
                updated_at = now()
            RETURNING *
            """,
            _profile_params(profile),
        ).fetchone()
        return dict(row), existing is None

    def record_evidence_items(self, conn: Connection, profile: ThesisProfile) -> None:
        conn.execute("DELETE FROM thesis_profile_evidence_items WHERE thesis_id = %s", (profile.thesis_id,))
        for source_id in profile.source_brain_output_ids:
            self._insert_evidence(conn, profile, "BRAIN_OUTPUT", source_id, "brain_output")
        for source_id in profile.source_signal_ids:
            self._insert_evidence(conn, profile, "SIGNAL", source_id, "signal")
        if profile.source_coordinator_decision_id:
            self._insert_evidence(conn, profile, "COORDINATOR_DECISION", profile.source_coordinator_decision_id, "coordinator_decision")
        if profile.orderbook_snapshot_id is not None:
            self._insert_evidence(conn, profile, "ORDERBOOK_SNAPSHOT", str(profile.orderbook_snapshot_id), "orderbook_snapshot")

    def _insert_evidence(self, conn: Connection, profile: ThesisProfile, evidence_type: str, source_id: str, source_type: str) -> None:
        conn.execute(
            """
            INSERT INTO thesis_profile_evidence_items (
                thesis_id, evidence_type, source_id, source_type, confidence, evidence, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, now())
            """,
            (
                profile.thesis_id,
                evidence_type,
                source_id,
                source_type,
                profile.confidence,
                Jsonb(_jsonable(profile.evidence)),
            ),
        )

    def record_run(self, conn: Connection, run: ThesisProfileRun) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO thesis_profile_runs (
                run_id, status, coordinator_decisions_checked, eligible_decisions,
                thesis_profiles_created, thesis_profiles_updated, complete_thesis_count,
                incomplete_thesis_count, blocked_thesis_count, weak_thesis_count,
                missing_market_count, missing_orderbook_count, missing_binding_count,
                missing_evidence_count, paper_ready_before, paper_ready_after,
                orders_created, order_intents_created, fills_created, positions_created,
                live_actions_created, started_at, finished_at, error_summary, created_at
            )
            VALUES (
                %(run_id)s, %(status)s, %(coordinator_decisions_checked)s,
                %(eligible_decisions)s, %(thesis_profiles_created)s,
                %(thesis_profiles_updated)s, %(complete_thesis_count)s,
                %(incomplete_thesis_count)s, %(blocked_thesis_count)s,
                %(weak_thesis_count)s, %(missing_market_count)s,
                %(missing_orderbook_count)s, %(missing_binding_count)s,
                %(missing_evidence_count)s, FALSE, FALSE, 0, 0, 0, 0, 0,
                %(started_at)s, %(finished_at)s, %(error_summary)s, now()
            )
            RETURNING *
            """,
            run.model_dump(exclude={"mock_data", "profiles"}),
        ).fetchone()
        return dict(row)

    def latest_run(self, conn: Connection) -> dict[str, Any] | None:
        if not _table_exists(conn, "thesis_profile_runs"):
            return None
        row = conn.execute(
            "SELECT * FROM thesis_profile_runs ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def list_profiles(
        self,
        conn: Connection,
        *,
        limit: int,
        status: str | None = None,
        market_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = %s")
            params.append(status.upper())
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM thesis_profiles
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        ]

    def summary(self, conn: Connection, *, limit: int) -> dict[str, Any]:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total_thesis_profiles,
                COUNT(*) FILTER (WHERE status = 'COMPLETE') AS complete_thesis_profiles,
                COUNT(*) FILTER (WHERE status = 'INCOMPLETE') AS incomplete_thesis_profiles,
                COUNT(*) FILTER (WHERE status = 'BLOCKED') AS blocked_thesis_profiles,
                COUNT(*) FILTER (WHERE status = 'WEAK') AS weak_thesis_profiles,
                COUNT(*) FILTER (WHERE is_runtime_generated = true) AS runtime_thesis_profiles,
                COUNT(*) FILTER (WHERE is_dry_run_generated = true) AS dry_run_thesis_profiles,
                COUNT(*) FILTER (WHERE paper_candidate_allowed = true) AS paper_candidate_allowed_count,
                MAX(updated_at) AS latest_at
            FROM thesis_profiles
            """
        ).fetchone()
        missing = conn.execute(
            """
            SELECT item AS field, COUNT(*) AS count
            FROM thesis_profiles,
                 jsonb_array_elements_text(missing_evidence) AS item
            GROUP BY item
            ORDER BY count DESC, item ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        invalidation = conn.execute(
            """
            SELECT item AS rule, COUNT(*) AS count
            FROM thesis_profiles,
                 jsonb_array_elements_text(invalidation_rules) AS item
            GROUP BY item
            ORDER BY count DESC, item ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        risk_notes = conn.execute(
            """
            SELECT item AS risk_note, COUNT(*) AS count
            FROM thesis_profiles,
                 jsonb_array_elements_text(risk_notes) AS item
            GROUP BY item
            ORDER BY count DESC, item ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        latest_run = self.latest_run(conn)
        latest_profiles = self.list_profiles(conn, limit=limit)
        return {
            **dict(totals),
            "latest_run": latest_run,
            "latest_thesis_profiles": latest_profiles,
            "missing_evidence_summary": [dict(row) for row in missing],
            "invalidation_rule_summary": [dict(row) for row in invalidation],
            "risk_notes_summary": [dict(row) for row in risk_notes],
        }


def _profile_params(profile: ThesisProfile) -> dict[str, Any]:
    data = profile.model_dump()
    for key in ("evidence", "missing_evidence", "invalidation_rules", "risk_notes", "source_brain_output_ids", "source_signal_ids"):
        data[key] = Jsonb(_jsonable(data.get(key)))
    data["paper_candidate_allowed"] = False
    data["risk_required"] = True
    data["exit_required"] = True
    return data


def thesis_profile_from_row(row: dict[str, Any]) -> ThesisProfile:
    data = dict(row)
    data.pop("id", None)
    return ThesisProfile(**data)


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value if value is not None else {}, default=str))


def _table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])

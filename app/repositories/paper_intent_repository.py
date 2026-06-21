from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.paper_intents import NoTradeLedgerRecord, PaperIntent, PaperIntentRun
from app.services.paper_session import active_paper_session_id
from app.utils.json_safety import json_safe


class PaperIntentRepository:
    def list_candidates(self, conn: Connection, *, limit: int, include_dry_run: bool = False) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_eligibility_candidates"):
            return []
        dry_run_clause = "" if include_dry_run else "AND COALESCE(is_dry_run_generated, false) = false"
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM paper_eligibility_candidates
                WHERE COALESCE(is_runtime_generated, true) = true
                  {dry_run_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def upsert_paper_intent(self, conn: Connection, intent: PaperIntent) -> tuple[dict[str, Any], bool]:
        existing_by_eligibility = conn.execute(
            "SELECT * FROM paper_intents WHERE eligibility_id = %s",
            (intent.eligibility_id,),
        ).fetchone()
        if existing_by_eligibility:
            row = self._record_idempotent_existing_intent(conn, dict(existing_by_eligibility), intent)
            return row, False
        existing = conn.execute("SELECT 1 FROM paper_intents WHERE paper_intent_id = %s", (intent.paper_intent_id,)).fetchone()
        session_id = active_paper_session_id(conn) or "NO_ACTIVE_PAPER_SESSION"
        row = conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, coordinator_decision_id, market_id, side,
                price_basis, orderbook_snapshot_id, intended_price, max_slippage,
                confidence, intent_status, intent_type, intent_reason, evidence,
                blockers, paper_only, live, execution_allowed, order_intent_created,
                generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, paper_session_id, created_at, updated_at
            )
            VALUES (
                %(paper_intent_id)s, %(eligibility_id)s, %(thesis_id)s,
                %(risk_decision_id)s, %(exit_plan_id)s,
                %(coordinator_decision_id)s, %(market_id)s, %(side)s,
                %(price_basis)s, %(orderbook_snapshot_id)s, %(intended_price)s,
                %(max_slippage)s, %(confidence)s, %(intent_status)s,
                %(intent_type)s, %(intent_reason)s, %(evidence)s, %(blockers)s,
                TRUE, FALSE, FALSE, FALSE, %(generated_by)s, %(producer_name)s,
                %(is_runtime_generated)s, %(is_dry_run_generated)s, %(paper_session_id)s,
                COALESCE(%(created_at)s, now()), now()
            )
            ON CONFLICT (paper_intent_id) DO UPDATE SET
                eligibility_id = EXCLUDED.eligibility_id,
                thesis_id = EXCLUDED.thesis_id,
                risk_decision_id = EXCLUDED.risk_decision_id,
                exit_plan_id = EXCLUDED.exit_plan_id,
                coordinator_decision_id = EXCLUDED.coordinator_decision_id,
                market_id = EXCLUDED.market_id,
                side = EXCLUDED.side,
                price_basis = EXCLUDED.price_basis,
                orderbook_snapshot_id = EXCLUDED.orderbook_snapshot_id,
                intended_price = EXCLUDED.intended_price,
                max_slippage = EXCLUDED.max_slippage,
                confidence = EXCLUDED.confidence,
                intent_status = EXCLUDED.intent_status,
                intent_type = EXCLUDED.intent_type,
                intent_reason = EXCLUDED.intent_reason,
                evidence = EXCLUDED.evidence,
                blockers = EXCLUDED.blockers,
                paper_only = TRUE,
                live = FALSE,
                execution_allowed = FALSE,
                order_intent_created = FALSE,
                generated_by = EXCLUDED.generated_by,
                producer_name = EXCLUDED.producer_name,
                is_runtime_generated = EXCLUDED.is_runtime_generated,
                is_dry_run_generated = EXCLUDED.is_dry_run_generated,
                paper_session_id = COALESCE(paper_intents.paper_session_id, EXCLUDED.paper_session_id),
                updated_at = now()
            RETURNING *
            """,
            {**_paper_intent_params(intent), "paper_session_id": session_id},
        ).fetchone()
        return dict(row), existing is None

    def _record_idempotent_existing_intent(self, conn: Connection, existing: dict[str, Any], intent: PaperIntent) -> dict[str, Any]:
        session_id = active_paper_session_id(conn) or "NO_ACTIVE_PAPER_SESSION"
        evidence = _dict(existing.get("evidence"))
        previous = _dict(evidence.get("paper_intent_gate_idempotency"))
        count = int(previous.get("encounter_count") or 0) + 1
        evidence["paper_intent_gate_idempotency"] = {
            "duplicate_eligibility_encountered": True,
            "duplicate_crash_prevented": True,
            "skip_reason": "ALREADY_INTENT_EXISTS_FOR_ELIGIBILITY",
            "action_taken": (
                "REUSED_EXISTING_INTENT"
                if str(existing.get("paper_intent_id") or "") == intent.paper_intent_id
                else "SKIPPED_EXISTING_INTENT"
            ),
            "existing_intent_id": existing.get("paper_intent_id"),
            "incoming_intent_id": intent.paper_intent_id,
            "eligibility_id": intent.eligibility_id,
            "existing_paper_session_id": existing.get("paper_session_id"),
            "incoming_paper_session_id": session_id,
            "same_session": str(existing.get("paper_session_id") or "") == str(session_id),
            "bug_suspect": False,
            "encounter_count": count,
        }
        row = conn.execute(
            """
            UPDATE paper_intents
            SET evidence = %(evidence)s,
                updated_at = now()
            WHERE paper_intent_id = %(paper_intent_id)s
            RETURNING *
            """,
            {"paper_intent_id": existing["paper_intent_id"], "evidence": Jsonb(json_safe(evidence))},
        ).fetchone()
        return dict(row)

    def upsert_no_trade_record(self, conn: Connection, record: NoTradeLedgerRecord) -> tuple[dict[str, Any], bool]:
        existing = conn.execute("SELECT 1 FROM no_trade_log WHERE no_trade_id = %s", (record.no_trade_id,)).fetchone()
        row = conn.execute(
            """
            INSERT INTO no_trade_log (
                no_trade_id, market_id, side, candidate_engine, source_layer,
                source_run_id, source_record_id, decision_status, primary_reason,
                reasons_json, risk_flags_json, decision_confidence, data_confidence,
                insufficient_data, insufficient_data_reasons_json, explanation,
                eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                no_trade_reason, no_trade_category, blockers, missing_requirements,
                evidence, source_status, generated_by, producer_name,
                is_runtime_generated, is_dry_run_generated, created_at, updated_at
            )
            VALUES (
                %(no_trade_id)s, %(market_id)s, %(side)s, 'PAPER_INTENT_GATE',
                %(source_layer)s, %(source_run_id)s, %(source_record_id)s,
                'NO_TRADE', %(primary_reason)s, %(reasons_json)s, '[]'::jsonb,
                0, 0, %(insufficient_data)s, %(missing_requirements)s,
                %(explanation)s, %(eligibility_id)s, %(thesis_id)s,
                %(risk_decision_id)s, %(exit_plan_id)s, %(no_trade_reason)s,
                %(no_trade_category)s, %(blockers)s, %(missing_requirements)s,
                %(evidence)s, %(source_status)s, %(generated_by)s,
                %(producer_name)s, %(is_runtime_generated)s,
                %(is_dry_run_generated)s, COALESCE(%(created_at)s, now()), now()
            )
            ON CONFLICT (no_trade_id) DO UPDATE SET
                market_id = EXCLUDED.market_id,
                side = EXCLUDED.side,
                candidate_engine = EXCLUDED.candidate_engine,
                source_layer = EXCLUDED.source_layer,
                source_run_id = EXCLUDED.source_run_id,
                source_record_id = EXCLUDED.source_record_id,
                decision_status = EXCLUDED.decision_status,
                primary_reason = EXCLUDED.primary_reason,
                reasons_json = EXCLUDED.reasons_json,
                insufficient_data = EXCLUDED.insufficient_data,
                insufficient_data_reasons_json = EXCLUDED.insufficient_data_reasons_json,
                explanation = EXCLUDED.explanation,
                eligibility_id = EXCLUDED.eligibility_id,
                thesis_id = EXCLUDED.thesis_id,
                risk_decision_id = EXCLUDED.risk_decision_id,
                exit_plan_id = EXCLUDED.exit_plan_id,
                no_trade_reason = EXCLUDED.no_trade_reason,
                no_trade_category = EXCLUDED.no_trade_category,
                blockers = EXCLUDED.blockers,
                missing_requirements = EXCLUDED.missing_requirements,
                evidence = EXCLUDED.evidence,
                source_status = EXCLUDED.source_status,
                generated_by = EXCLUDED.generated_by,
                producer_name = EXCLUDED.producer_name,
                is_runtime_generated = EXCLUDED.is_runtime_generated,
                is_dry_run_generated = EXCLUDED.is_dry_run_generated,
                updated_at = now()
            RETURNING *
            """,
            _no_trade_params(record),
        ).fetchone()
        return dict(row), existing is None

    def record_run(self, conn: Connection, run: PaperIntentRun) -> dict[str, Any]:
        return dict(
            conn.execute(
                """
                INSERT INTO paper_intent_runs (
                    run_id, status, candidates_checked, eligible_candidates,
                    paper_intents_created, paper_intents_updated,
                    no_trade_records_created, no_trade_records_updated,
                    blocked_candidates, missing_eligibility_count,
                    accounted_candidates, unaccounted_candidates,
                    paper_ready_before, paper_ready_after, orders_created,
                    order_intents_created, fills_created, positions_created,
                    live_actions_created, started_at, finished_at,
                    error_summary, created_at
                )
                VALUES (
                    %(run_id)s, %(status)s, %(candidates_checked)s,
                    %(eligible_candidates)s, %(paper_intents_created)s,
                    %(paper_intents_updated)s, %(no_trade_records_created)s,
                    %(no_trade_records_updated)s, %(blocked_candidates)s,
                    %(missing_eligibility_count)s, %(accounted_candidates)s,
                    %(unaccounted_candidates)s, FALSE, FALSE, 0, 0, 0, 0, 0,
                    %(started_at)s, %(finished_at)s, %(error_summary)s, now()
                )
                RETURNING *
                """,
                run.model_dump(exclude={"mock_data", "paper_intents", "no_trade_records"}),
            ).fetchone()
        )

    def record_no_trade_run(self, conn: Connection, run: PaperIntentRun) -> dict[str, Any]:
        return dict(
            conn.execute(
                """
                INSERT INTO no_trade_runs (
                    run_id, status, candidates_checked, no_trade_records_created,
                    no_trade_records_updated, blocked_candidates,
                    unaccounted_candidates, paper_ready_before, paper_ready_after,
                    started_at, finished_at, error_summary, created_at
                )
                VALUES (
                    %(run_id)s, %(status)s, %(candidates_checked)s,
                    %(no_trade_records_created)s, %(no_trade_records_updated)s,
                    %(blocked_candidates)s, %(unaccounted_candidates)s,
                    FALSE, FALSE, %(started_at)s, %(finished_at)s,
                    %(error_summary)s, now()
                )
                RETURNING *
                """,
                run.model_dump(exclude={"mock_data", "paper_intents", "no_trade_records"}),
            ).fetchone()
        )

    def latest_run(self, conn: Connection) -> dict[str, Any] | None:
        if not _table_exists(conn, "paper_intent_runs"):
            return None
        row = conn.execute("SELECT * FROM paper_intent_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def latest_no_trade_run(self, conn: Connection) -> dict[str, Any] | None:
        if not _table_exists(conn, "no_trade_runs"):
            return None
        row = conn.execute("SELECT * FROM no_trade_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def list_intents(self, conn: Connection, *, limit: int, status: str | None = None, market_id: str | None = None) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_intents"):
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("intent_status = %s")
            params.append(status.upper())
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        params.append(limit)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return [
            dict(row)
            for row in conn.execute(
                f"SELECT * FROM paper_intents {where} ORDER BY created_at DESC, id DESC LIMIT %s",
                tuple(params),
            ).fetchall()
        ]

    def list_no_trade(self, conn: Connection, *, limit: int, category: str | None = None, market_id: str | None = None) -> list[dict[str, Any]]:
        if not _table_exists(conn, "no_trade_log"):
            return []
        if not _column_exists(conn, "no_trade_log", "eligibility_id"):
            return []
        clauses = ["source_layer = 'paper_intent_gate'"]
        params: list[Any] = []
        if category:
            clauses.append("no_trade_category = %s")
            params.append(category.upper())
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM no_trade_log
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        ]

    def summary(self, conn: Connection, *, limit: int) -> dict[str, Any]:
        candidates = _count_table(conn, "paper_eligibility_candidates")
        eligible = _count_where(conn, "paper_eligibility_candidates", "status = 'ELIGIBLE'")
        intents = _count_table(conn, "paper_intents")
        created_intents = _count_where(conn, "paper_intents", "intent_status = 'CREATED'")
        blocked_intents = _count_where(conn, "paper_intents", "intent_status = 'BLOCKED'")
        no_trade = _count_where(conn, "no_trade_log", "source_layer = 'paper_intent_gate'")
        accounted = self.accounted_count(conn)
        return {
            "latest_run": self.latest_run(conn),
            "candidates_checked": candidates,
            "eligible_candidates": eligible,
            "total_paper_intents": intents,
            "created_intents": created_intents,
            "blocked_intents": blocked_intents,
            "paper_only_true_count": _count_where(conn, "paper_intents", "paper_only = true"),
            "live_true_count": _count_where(conn, "paper_intents", "live = true"),
            "execution_allowed_count": _count_where(conn, "paper_intents", "execution_allowed = true"),
            "order_intent_created_count": _count_where(conn, "paper_intents", "order_intent_created = true"),
            "no_trade_records_created": no_trade,
            "accounted_candidates": accounted,
            "unaccounted_candidates": max(0, candidates - accounted),
            "paper_intent_gate_idempotency": _idempotency_summary(conn),
            "latest_intents": self.list_intents(conn, limit=limit),
        }

    def no_trade_summary(self, conn: Connection, *, limit: int) -> dict[str, Any]:
        if not _table_exists(conn, "no_trade_log") or not _column_exists(conn, "no_trade_log", "eligibility_id"):
            candidates = _count_table(conn, "paper_eligibility_candidates")
            accounted = self.accounted_count(conn)
            return {
                "latest_run": self.latest_no_trade_run(conn),
                "total_no_trade_records": 0,
                "counts_by_category": [],
                "top_no_trade_reasons": [],
                "blocked_candidates": _count_where(conn, "paper_eligibility_candidates", "status <> 'ELIGIBLE'"),
                "missing_requirements_summary": [],
                "unaccounted_candidates": max(0, candidates - accounted),
                "latest_no_trade": [],
            }
        total = _count_where(conn, "no_trade_log", "source_layer = 'paper_intent_gate'")
        categories = conn.execute(
            """
            SELECT COALESCE(no_trade_category, 'NO_ELIGIBLE_CANDIDATE') AS category, COUNT(*) AS count
            FROM no_trade_log
            WHERE source_layer = 'paper_intent_gate'
            GROUP BY COALESCE(no_trade_category, 'NO_ELIGIBLE_CANDIDATE')
            ORDER BY count DESC, category ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall() if _table_exists(conn, "no_trade_log") else []
        reasons = conn.execute(
            """
            SELECT COALESCE(no_trade_reason, primary_reason) AS reason, COUNT(*) AS count
            FROM no_trade_log
            WHERE source_layer = 'paper_intent_gate'
            GROUP BY COALESCE(no_trade_reason, primary_reason)
            ORDER BY count DESC, reason ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall() if _table_exists(conn, "no_trade_log") else []
        missing = conn.execute(
            """
            SELECT item AS missing_requirement, COUNT(*) AS count
            FROM no_trade_log, jsonb_array_elements_text(missing_requirements) AS item
            WHERE source_layer = 'paper_intent_gate'
            GROUP BY item
            ORDER BY count DESC, item ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall() if _table_exists(conn, "no_trade_log") else []
        candidates = _count_table(conn, "paper_eligibility_candidates")
        accounted = self.accounted_count(conn)
        return {
            "latest_run": self.latest_no_trade_run(conn),
            "total_no_trade_records": total,
            "counts_by_category": [dict(row) for row in categories],
            "top_no_trade_reasons": [dict(row) for row in reasons],
            "blocked_candidates": _count_where(conn, "paper_eligibility_candidates", "status <> 'ELIGIBLE'"),
            "missing_requirements_summary": [dict(row) for row in missing],
            "unaccounted_candidates": max(0, candidates - accounted),
            "latest_no_trade": self.list_no_trade(conn, limit=limit),
        }

    def accounted_count(self, conn: Connection) -> int:
        if not _table_exists(conn, "paper_eligibility_candidates"):
            return 0
        intent_clause = (
            """
            EXISTS (
                SELECT 1 FROM paper_intents pi
                WHERE pi.eligibility_id = pec.eligibility_id
            )
            """
            if _table_exists(conn, "paper_intents")
            else "FALSE"
        )
        no_trade_clause = (
            """
            OR EXISTS (
                SELECT 1 FROM no_trade_log nt
                WHERE nt.eligibility_id = pec.eligibility_id
                  AND nt.source_layer = 'paper_intent_gate'
            )
            """
            if _table_exists(conn, "no_trade_log") and _column_exists(conn, "no_trade_log", "eligibility_id")
            else ""
        )
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM paper_eligibility_candidates pec
            WHERE {intent_clause}
            {no_trade_clause}
            """
        ).fetchone()
        return int(row["count"] or 0)


def paper_intent_from_row(row: dict[str, Any]) -> PaperIntent:
    return PaperIntent(
        paper_intent_id=str(row["paper_intent_id"]),
        eligibility_id=str(row["eligibility_id"]),
        thesis_id=str(row["thesis_id"]),
        risk_decision_id=str(row["risk_decision_id"]),
        exit_plan_id=str(row["exit_plan_id"]),
        coordinator_decision_id=row.get("coordinator_decision_id"),
        market_id=str(row["market_id"]),
        side=str(row["side"]),
        price_basis=row.get("price_basis") or "ORDERBOOK_MID",
        orderbook_snapshot_id=int(row["orderbook_snapshot_id"]) if row.get("orderbook_snapshot_id") is not None else None,
        intended_price=_float_or_none(row.get("intended_price")),
        max_slippage=_float_or_none(row.get("max_slippage")),
        confidence=_float_or_none(row.get("confidence")),
        intent_status=row.get("intent_status") or "ERROR",
        intent_type=row.get("intent_type") or "PAPER_ENTRY_INTENT",
        intent_reason=row.get("intent_reason") or "",
        evidence=row.get("evidence") or {},
        blockers=_list(row.get("blockers")),
        paper_only=bool(row.get("paper_only")),
        live=bool(row.get("live")),
        execution_allowed=bool(row.get("execution_allowed")),
        order_intent_created=bool(row.get("order_intent_created")),
        generated_by=row.get("generated_by") or "runtime",
        producer_name=row.get("producer_name") or "paper_intent_gate",
        is_runtime_generated=bool(row.get("is_runtime_generated", True)),
        is_dry_run_generated=bool(row.get("is_dry_run_generated", False)),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def no_trade_record_from_row(row: dict[str, Any]) -> NoTradeLedgerRecord:
    return NoTradeLedgerRecord(
        no_trade_id=str(row["no_trade_id"]),
        eligibility_id=row.get("eligibility_id"),
        thesis_id=row.get("thesis_id"),
        risk_decision_id=row.get("risk_decision_id"),
        exit_plan_id=row.get("exit_plan_id"),
        market_id=row.get("market_id"),
        side=row.get("side"),
        no_trade_reason=row.get("no_trade_reason") or row.get("primary_reason") or "NO_ELIGIBLE_CANDIDATE",
        no_trade_category=row.get("no_trade_category") or "NO_ELIGIBLE_CANDIDATE",
        blockers=_list(row.get("blockers")),
        missing_requirements=_list(row.get("missing_requirements")),
        evidence=row.get("evidence") or {},
        source_status=row.get("source_status") or row.get("decision_status"),
        source_layer=row.get("source_layer") or "paper_intent_gate",
        generated_by=row.get("generated_by") or "runtime",
        producer_name=row.get("producer_name") or "no_trade_ledger",
        is_runtime_generated=bool(row.get("is_runtime_generated", True)),
        is_dry_run_generated=bool(row.get("is_dry_run_generated", False)),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _paper_intent_params(intent: PaperIntent) -> dict[str, Any]:
    data = intent.model_dump()
    data["evidence"] = Jsonb(json_safe(data["evidence"]))
    data["blockers"] = Jsonb(json_safe(data["blockers"]))
    return data


def _no_trade_params(record: NoTradeLedgerRecord) -> dict[str, Any]:
    data = record.model_dump()
    blockers = data["blockers"]
    missing = data["missing_requirements"]
    reasons = [{"reason": item.lower(), "source_layer": "paper_intent_gate", "hard_block": True} for item in blockers or missing or [record.no_trade_reason]]
    data.update(
        {
            "source_run_id": None,
            "source_record_id": record.eligibility_id,
            "primary_reason": record.no_trade_reason.lower(),
            "reasons_json": Jsonb(json_safe(reasons)),
            "insufficient_data": bool(missing),
            "explanation": f"Paper Intent Gate recorded NO_TRADE because {record.no_trade_reason}.",
        }
    )
    data["blockers"] = Jsonb(json_safe(blockers))
    data["missing_requirements"] = Jsonb(json_safe(missing))
    data["evidence"] = Jsonb(json_safe(data["evidence"]))
    return data


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None]
        except json.JSONDecodeError:
            return [value]
    return [str(value)]


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _count_table(conn: Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _count_where(conn: Connection, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def _idempotency_summary(conn: Connection) -> dict[str, Any]:
    if not _table_exists(conn, "paper_intents"):
        return {
            "duplicate_eligibility_encountered": 0,
            "existing_intent_reused": 0,
            "duplicate_skipped_safely": 0,
            "duplicate_crash_prevented": False,
            "latest": None,
        }
    row = conn.execute(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE COALESCE((evidence->'paper_intent_gate_idempotency'->>'duplicate_eligibility_encountered')::boolean, false)
            ) AS duplicate_eligibility_encountered,
            COUNT(*) FILTER (
                WHERE evidence->'paper_intent_gate_idempotency'->>'action_taken' = 'REUSED_EXISTING_INTENT'
            ) AS existing_intent_reused,
            COUNT(*) FILTER (
                WHERE evidence->'paper_intent_gate_idempotency'->>'action_taken' = 'SKIPPED_EXISTING_INTENT'
            ) AS duplicate_skipped_safely
        FROM paper_intents
        """
    ).fetchone()
    latest = conn.execute(
        """
        SELECT paper_intent_id, eligibility_id, paper_session_id,
               evidence->'paper_intent_gate_idempotency' AS idempotency
        FROM paper_intents
        WHERE COALESCE((evidence->'paper_intent_gate_idempotency'->>'duplicate_eligibility_encountered')::boolean, false)
        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
        LIMIT 1
        """
    ).fetchone()
    encountered = int(row["duplicate_eligibility_encountered"] or 0) if row else 0
    return {
        "duplicate_eligibility_encountered": encountered,
        "existing_intent_reused": int(row["existing_intent_reused"] or 0) if row else 0,
        "duplicate_skipped_safely": int(row["duplicate_skipped_safely"] or 0) if row else 0,
        "duplicate_crash_prevented": encountered > 0,
        "latest": dict(latest) if latest else None,
    }


def _table_exists(conn: Connection, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _column_exists(conn: Connection, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = ANY (current_schemas(false))
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return bool(row)

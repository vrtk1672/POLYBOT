from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.exit_foundation import ExitFoundationPlan, ExitFoundationRun


class ExitFoundationRepository:
    def list_runtime_risk_decisions(self, conn: Connection, *, limit: int, include_blocked: bool) -> list[dict[str, Any]]:
        if not _table_exists(conn, "risk_decisions"):
            return []
        decision_clause = "" if include_blocked else "AND rd.decision NOT IN ('BLOCK', 'ERROR')"
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    rd.*,
                    tp.side AS thesis_side,
                    tp.status AS thesis_status,
                    tp.missing_evidence AS thesis_missing_evidence,
                    tp.invalidation_rules AS thesis_invalidation_rules,
                    obs.mid_price AS orderbook_mid_price,
                    obs.best_bid AS orderbook_best_bid,
                    obs.best_ask AS orderbook_best_ask,
                    obs.spread AS orderbook_spread,
                    obs.liquidity_score AS orderbook_liquidity_score,
                    obs.is_stale AS orderbook_is_stale,
                    obs.snapshot_status AS orderbook_snapshot_status
                FROM risk_decisions rd
                LEFT JOIN thesis_profiles tp
                    ON tp.thesis_id = rd.thesis_id
                LEFT JOIN orderbook_snapshots obs
                    ON obs.id = rd.orderbook_snapshot_id
                WHERE rd.is_runtime_generated = true
                  AND rd.is_dry_run_generated = false
                  {decision_clause}
                ORDER BY rd.updated_at DESC NULLS LAST, rd.created_at DESC, rd.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def upsert_plan(self, conn: Connection, plan: ExitFoundationPlan) -> tuple[dict[str, Any], bool]:
        existing = conn.execute("SELECT 1 FROM exit_plans WHERE exit_plan_id = %s", (plan.exit_plan_id,)).fetchone()
        row = conn.execute(
            """
            INSERT INTO exit_plans (
                exit_plan_id, market_id, side, engine, risk_gate_run_id,
                entry_price, entry_size, target_exit, stop_loss, max_hold_seconds,
                invalidation_rule_json, liquidity_exit_check_json, emergency_exit_json,
                exit_mode, plan_status, created_from, data_confidence,
                insufficient_data, insufficient_data_reasons_json,
                thesis_id, risk_decision_ref, status, exit_type, invalidation_rules,
                emergency_exit_rules, liquidity_exit_check, time_exit_check,
                missing_exit_evidence, blockers, warnings, source_risk_status,
                source_risk_score, orderbook_snapshot_id, paper_intent_allowed,
                paper_exit_ready, execution_allowed, generated_by, producer_name,
                is_runtime_generated, is_dry_run_generated, created_at, updated_at
            )
            VALUES (
                %(exit_plan_id)s, %(market_id)s, %(side)s, 'EXIT_FOUNDATION',
                %(risk_decision_id)s, 0, 0, %(target_exit)s, %(stop_loss)s,
                %(max_hold_seconds)s, %(invalidation_rule_json)s,
                %(liquidity_exit_check_json)s, %(emergency_exit_json)s,
                'PAPER_SIM_EXIT', %(plan_status)s, 'exit_foundation',
                %(data_confidence)s, %(insufficient_data)s,
                %(insufficient_data_reasons_json)s, %(thesis_id)s,
                %(risk_decision_id)s, %(status)s, %(exit_type)s,
                %(invalidation_rules)s, %(emergency_exit_rules)s,
                %(liquidity_exit_check)s, %(time_exit_check)s,
                %(missing_exit_evidence)s, %(blockers)s, %(warnings)s,
                %(source_risk_status)s, %(source_risk_score)s,
                %(orderbook_snapshot_id)s, FALSE, %(paper_exit_ready)s, FALSE,
                %(generated_by)s, %(producer_name)s,
                %(is_runtime_generated)s, %(is_dry_run_generated)s,
                COALESCE(%(created_at)s, now()), now()
            )
            ON CONFLICT (exit_plan_id) DO UPDATE SET
                market_id = EXCLUDED.market_id,
                side = EXCLUDED.side,
                target_exit = EXCLUDED.target_exit,
                stop_loss = EXCLUDED.stop_loss,
                max_hold_seconds = EXCLUDED.max_hold_seconds,
                invalidation_rule_json = EXCLUDED.invalidation_rule_json,
                liquidity_exit_check_json = EXCLUDED.liquidity_exit_check_json,
                emergency_exit_json = EXCLUDED.emergency_exit_json,
                plan_status = EXCLUDED.plan_status,
                data_confidence = EXCLUDED.data_confidence,
                insufficient_data = EXCLUDED.insufficient_data,
                insufficient_data_reasons_json = EXCLUDED.insufficient_data_reasons_json,
                thesis_id = EXCLUDED.thesis_id,
                risk_decision_ref = EXCLUDED.risk_decision_ref,
                status = EXCLUDED.status,
                exit_type = EXCLUDED.exit_type,
                invalidation_rules = EXCLUDED.invalidation_rules,
                emergency_exit_rules = EXCLUDED.emergency_exit_rules,
                liquidity_exit_check = EXCLUDED.liquidity_exit_check,
                time_exit_check = EXCLUDED.time_exit_check,
                missing_exit_evidence = EXCLUDED.missing_exit_evidence,
                blockers = EXCLUDED.blockers,
                warnings = EXCLUDED.warnings,
                source_risk_status = EXCLUDED.source_risk_status,
                source_risk_score = EXCLUDED.source_risk_score,
                orderbook_snapshot_id = EXCLUDED.orderbook_snapshot_id,
                paper_intent_allowed = FALSE,
                paper_exit_ready = EXCLUDED.paper_exit_ready,
                execution_allowed = FALSE,
                generated_by = EXCLUDED.generated_by,
                producer_name = EXCLUDED.producer_name,
                is_runtime_generated = EXCLUDED.is_runtime_generated,
                is_dry_run_generated = EXCLUDED.is_dry_run_generated,
                updated_at = now()
            RETURNING *
            """,
            _plan_params(plan),
        ).fetchone()
        return dict(row), existing is None

    def record_rules(self, conn: Connection, plan: ExitFoundationPlan) -> None:
        if not _table_exists(conn, "exit_plan_rules"):
            return
        conn.execute("DELETE FROM exit_plan_rules WHERE exit_plan_id = %s", (plan.exit_plan_id,))
        rule_payloads = {
            "INVALIDATION": plan.invalidation_rules,
            "EMERGENCY": plan.emergency_exit_rules,
            "LIQUIDITY": plan.liquidity_exit_check,
            "TIME": plan.time_exit_check,
        }
        for rule_type, parameters in rule_payloads.items():
            conn.execute(
                """
                INSERT INTO exit_plan_rules (exit_plan_id, rule_type, rule_status, parameters, created_at)
                VALUES (%s, %s, %s, %s, now())
                """,
                (
                    plan.exit_plan_id,
                    rule_type,
                    "BLOCKED" if plan.status == "BLOCKED" else "ACTIVE",
                    Jsonb(parameters),
                ),
            )

    def record_run(self, conn: Connection, run: ExitFoundationRun) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO exit_plan_runs (
                run_id, status, risk_decisions_checked, exit_plans_created,
                exit_plans_updated, complete_exit_count, incomplete_exit_count,
                blocked_exit_count, missing_market_count, missing_orderbook_count,
                missing_side_count, missing_risk_approval_count, paper_ready_before,
                paper_ready_after, orders_created, order_intents_created, fills_created,
                positions_created, live_actions_created, started_at, finished_at,
                error_summary, created_at
            )
            VALUES (
                %(run_id)s, %(status)s, %(risk_decisions_checked)s,
                %(exit_plans_created)s, %(exit_plans_updated)s,
                %(complete_exit_count)s, %(incomplete_exit_count)s,
                %(blocked_exit_count)s, %(missing_market_count)s,
                %(missing_orderbook_count)s, %(missing_side_count)s,
                %(missing_risk_approval_count)s, FALSE, FALSE, 0, 0, 0, 0, 0,
                %(started_at)s, %(finished_at)s, %(error_summary)s, now()
            )
            RETURNING *
            """,
            run.model_dump(exclude={"mock_data", "plans"}),
        ).fetchone()
        return dict(row)

    def latest_run(self, conn: Connection) -> dict[str, Any] | None:
        if not _table_exists(conn, "exit_plan_runs"):
            return None
        row = conn.execute("SELECT * FROM exit_plan_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def list_plans(
        self,
        conn: Connection,
        *,
        limit: int,
        status: str | None = None,
        market_id: str | None = None,
        risk_decision_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not _table_exists(conn, "exit_plans"):
            return []
        clauses = ["created_from = 'exit_foundation'"]
        params: list[Any] = []
        if status:
            clauses.append("status = %s")
            params.append(status.upper())
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        if risk_decision_id:
            clauses.append("risk_decision_ref = %s")
            params.append(risk_decision_id)
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM exit_plans
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        ]

    def summary(self, conn: Connection, *, limit: int) -> dict[str, Any]:
        if not _table_exists(conn, "exit_plans"):
            return _empty_summary()
        totals = conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE created_from = 'exit_foundation') AS total_exit_plans,
                COUNT(*) FILTER (WHERE created_from = 'exit_foundation' AND status = 'COMPLETE') AS complete_exit_plans,
                COUNT(*) FILTER (WHERE created_from = 'exit_foundation' AND status = 'INCOMPLETE') AS incomplete_exit_plans,
                COUNT(*) FILTER (WHERE created_from = 'exit_foundation' AND status = 'BLOCKED') AS blocked_exit_plans,
                COUNT(*) FILTER (WHERE created_from = 'exit_foundation' AND paper_exit_ready = true) AS paper_exit_ready_count,
                COUNT(*) FILTER (WHERE created_from = 'exit_foundation' AND paper_intent_allowed = true) AS paper_intent_allowed_count,
                COUNT(*) FILTER (WHERE created_from = 'exit_foundation' AND execution_allowed = true) AS execution_allowed_count,
                COUNT(*) FILTER (WHERE created_from = 'exit_foundation' AND target_exit IS NOT NULL) AS target_exit_count,
                COUNT(*) FILTER (WHERE created_from = 'exit_foundation' AND stop_loss IS NOT NULL) AS stop_loss_count,
                COUNT(*) FILTER (WHERE created_from = 'exit_foundation' AND jsonb_array_length(emergency_exit_rules) > 0) AS emergency_exit_rules_count,
                COUNT(*) FILTER (WHERE created_from = 'exit_foundation' AND liquidity_exit_check <> '{}'::jsonb) AS liquidity_exit_check_count
            FROM exit_plans
            """
        ).fetchone()
        blockers = conn.execute(
            """
            SELECT item AS blocker, COUNT(*) AS count
            FROM exit_plans,
                 jsonb_array_elements_text(blockers) AS item
            WHERE created_from = 'exit_foundation'
            GROUP BY item
            ORDER BY count DESC, item ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        missing = conn.execute(
            """
            SELECT item AS missing_evidence, COUNT(*) AS count
            FROM exit_plans,
                 jsonb_array_elements_text(missing_exit_evidence) AS item
            WHERE created_from = 'exit_foundation'
            GROUP BY item
            ORDER BY count DESC, item ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        invalidation = conn.execute(
            """
            SELECT item AS rule, COUNT(*) AS count
            FROM exit_plans,
                 jsonb_array_elements_text(invalidation_rules) AS item
            WHERE created_from = 'exit_foundation'
            GROUP BY item
            ORDER BY count DESC, item ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        emergency = conn.execute(
            """
            SELECT item AS rule, COUNT(*) AS count
            FROM exit_plans,
                 jsonb_array_elements_text(emergency_exit_rules) AS item
            WHERE created_from = 'exit_foundation'
            GROUP BY item
            ORDER BY count DESC, item ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        latest_run = self.latest_run(conn)
        return {
            **dict(totals),
            "top_exit_blockers": [dict(row) for row in blockers],
            "missing_exit_evidence_summary": [dict(row) for row in missing],
            "invalidation_rule_summary": [dict(row) for row in invalidation],
            "emergency_exit_summary": [dict(row) for row in emergency],
            "latest_run": latest_run,
            "latest_exit_plans": self.list_plans(conn, limit=limit),
        }


def exit_plan_from_row(row: dict[str, Any]) -> ExitFoundationPlan:
    return ExitFoundationPlan(
        exit_plan_id=str(row["exit_plan_id"]),
        thesis_id=row.get("thesis_id"),
        risk_decision_id=row.get("risk_decision_ref"),
        market_id=row.get("market_id"),
        side=row.get("side"),
        status=row.get("status") or "ERROR",
        exit_type=row.get("exit_type") or "EMERGENCY_ONLY_EXIT",
        target_exit=float(row["target_exit"]) if row.get("target_exit") is not None else None,
        stop_loss=float(row["stop_loss"]) if row.get("stop_loss") is not None else None,
        max_hold_seconds=int(row.get("max_hold_seconds") or 3600),
        invalidation_rules=_list(row.get("invalidation_rules")),
        emergency_exit_rules=_list(row.get("emergency_exit_rules")),
        liquidity_exit_check=row.get("liquidity_exit_check") or {},
        time_exit_check=row.get("time_exit_check") or {},
        missing_exit_evidence=_list(row.get("missing_exit_evidence")),
        blockers=_list(row.get("blockers")),
        warnings=_list(row.get("warnings")),
        source_risk_status=row.get("source_risk_status"),
        source_risk_score=float(row["source_risk_score"]) if row.get("source_risk_score") is not None else None,
        orderbook_snapshot_id=int(row["orderbook_snapshot_id"]) if row.get("orderbook_snapshot_id") is not None else None,
        paper_intent_allowed=bool(row.get("paper_intent_allowed")),
        paper_exit_ready=bool(row.get("paper_exit_ready")),
        execution_allowed=bool(row.get("execution_allowed")),
        generated_by=row.get("generated_by") or "runtime",
        producer_name=row.get("producer_name") or "exit_foundation",
        is_runtime_generated=bool(row.get("is_runtime_generated", True)),
        is_dry_run_generated=bool(row.get("is_dry_run_generated", False)),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _plan_params(plan: ExitFoundationPlan) -> dict[str, Any]:
    data = plan.model_dump()
    data["risk_decision_id"] = plan.risk_decision_id
    data["plan_status"] = "INSUFFICIENT_DATA" if plan.status in {"INCOMPLETE", "BLOCKED"} else "ACTIVE"
    data["data_confidence"] = 0.35 if plan.status != "COMPLETE" else 0.85
    data["insufficient_data"] = plan.status != "COMPLETE"
    data["insufficient_data_reasons_json"] = Jsonb(plan.missing_exit_evidence or plan.blockers)
    data["invalidation_rule_json"] = Jsonb({"rules": plan.invalidation_rules})
    data["liquidity_exit_check_json"] = Jsonb(plan.liquidity_exit_check)
    data["emergency_exit_json"] = Jsonb({"rules": plan.emergency_exit_rules})
    for key in (
        "invalidation_rules",
        "emergency_exit_rules",
        "liquidity_exit_check",
        "time_exit_check",
        "missing_exit_evidence",
        "blockers",
        "warnings",
    ):
        data[key] = Jsonb(data[key])
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


def _table_exists(conn: Connection, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _empty_summary() -> dict[str, Any]:
    return {
        "total_exit_plans": 0,
        "complete_exit_plans": 0,
        "incomplete_exit_plans": 0,
        "blocked_exit_plans": 0,
        "paper_exit_ready_count": 0,
        "paper_intent_allowed_count": 0,
        "execution_allowed_count": 0,
        "target_exit_count": 0,
        "stop_loss_count": 0,
        "emergency_exit_rules_count": 0,
        "liquidity_exit_check_count": 0,
        "top_exit_blockers": [],
        "missing_exit_evidence_summary": [],
        "invalidation_rule_summary": [],
        "emergency_exit_summary": [],
        "latest_run": None,
        "latest_exit_plans": [],
    }

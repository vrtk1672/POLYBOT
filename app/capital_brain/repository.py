from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class CapitalBrainRepository:
    def get_session(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mesh_sessions WHERE session_id = %s", (session_id,)).fetchone()
        return dict(row) if row else None

    def get_awareness(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mesh_shared_awareness WHERE session_id = %s", (session_id,)).fetchone()
        return dict(row) if row else None

    def get_account(self, conn: Connection, account_id: str = "paper_default") -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM paper_accounts WHERE account_id = %s", (account_id,)).fetchone()
        return dict(row) if row else None

    def latest_ledger(self, conn: Connection, account_id: str = "paper_default") -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM paper_capital_ledger
            WHERE account_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (account_id,),
        ).fetchone()
        return dict(row) if row else None

    def active_open_positions(self, conn: Connection) -> int:
        if not table_exists(conn, "paper_positions"):
            return 0
        return int(
            conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM paper_positions
                WHERE current_status = 'OPEN'
                  AND COALESCE(excluded_from_active_paper_truth, false) = false
                """
            ).fetchone()["count"]
            or 0
        )

    def position(self, conn: Connection, position_id: str | None) -> dict[str, Any] | None:
        if not position_id or not table_exists(conn, "paper_positions"):
            return None
        row = conn.execute(
            """
            SELECT *
            FROM paper_positions
            WHERE id::text = %s OR payload_json->>'paper_position_id' = %s
            ORDER BY updated_at DESC NULLS LAST, opened_at DESC NULLS LAST
            LIMIT 1
            """,
            (position_id, position_id),
        ).fetchone()
        return dict(row) if row else None

    def linked_events(self, conn: Connection, session_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        if not table_exists(conn, "mesh_session_events") or not table_exists(conn, "neural_events"):
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT e.*
                FROM mesh_session_events se
                JOIN neural_events e ON e.event_id = se.event_id
                WHERE se.session_id = %s
                ORDER BY se.linked_at DESC, se.id DESC
                LIMIT %s
                """,
                (session_id, limit),
            ).fetchall()
        ]

    def upsert_evaluation(self, conn: Connection, evaluation: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO capital_brain_evaluations (
                evaluation_id, session_id, market_id, candidate_id, position_id, account_id,
                available_balance, locked_balance, current_balance, open_exposure, daily_pnl,
                risk_per_trade_pct, max_position_size, max_daily_loss_pct, max_open_positions,
                max_total_open_exposure_pct, estimated_required_capital, estimated_max_loss,
                estimated_capital_lock_minutes, capital_efficiency_score, exposure_fit_score,
                balance_fit_score, decision, confidence, reason, missing_inputs_json,
                risk_flags_json, created_at
            )
            VALUES (
                %(evaluation_id)s, %(session_id)s, %(market_id)s, %(candidate_id)s,
                %(position_id)s, %(account_id)s, %(available_balance)s, %(locked_balance)s,
                %(current_balance)s, %(open_exposure)s, %(daily_pnl)s,
                %(risk_per_trade_pct)s, %(max_position_size)s, %(max_daily_loss_pct)s,
                %(max_open_positions)s, %(max_total_open_exposure_pct)s,
                %(estimated_required_capital)s, %(estimated_max_loss)s,
                %(estimated_capital_lock_minutes)s, %(capital_efficiency_score)s,
                %(exposure_fit_score)s, %(balance_fit_score)s, %(decision)s,
                %(confidence)s, %(reason)s, %(missing_inputs_json)s,
                %(risk_flags_json)s, now()
            )
            ON CONFLICT (session_id) DO UPDATE
            SET market_id = EXCLUDED.market_id,
                candidate_id = EXCLUDED.candidate_id,
                position_id = EXCLUDED.position_id,
                account_id = EXCLUDED.account_id,
                available_balance = EXCLUDED.available_balance,
                locked_balance = EXCLUDED.locked_balance,
                current_balance = EXCLUDED.current_balance,
                open_exposure = EXCLUDED.open_exposure,
                daily_pnl = EXCLUDED.daily_pnl,
                risk_per_trade_pct = EXCLUDED.risk_per_trade_pct,
                max_position_size = EXCLUDED.max_position_size,
                max_daily_loss_pct = EXCLUDED.max_daily_loss_pct,
                max_open_positions = EXCLUDED.max_open_positions,
                max_total_open_exposure_pct = EXCLUDED.max_total_open_exposure_pct,
                estimated_required_capital = EXCLUDED.estimated_required_capital,
                estimated_max_loss = EXCLUDED.estimated_max_loss,
                estimated_capital_lock_minutes = EXCLUDED.estimated_capital_lock_minutes,
                capital_efficiency_score = EXCLUDED.capital_efficiency_score,
                exposure_fit_score = EXCLUDED.exposure_fit_score,
                balance_fit_score = EXCLUDED.balance_fit_score,
                decision = EXCLUDED.decision,
                confidence = EXCLUDED.confidence,
                reason = EXCLUDED.reason,
                missing_inputs_json = EXCLUDED.missing_inputs_json,
                risk_flags_json = EXCLUDED.risk_flags_json,
                created_at = now()
            RETURNING *
            """,
            {
                **evaluation,
                "missing_inputs_json": Jsonb(evaluation["missing_inputs_json"]),
                "risk_flags_json": Jsonb(evaluation["risk_flags_json"]),
            },
        ).fetchone()
        assert row is not None
        conn.execute("DELETE FROM capital_brain_sources WHERE evaluation_id = %s", (row["evaluation_id"],))
        for source in sources:
            conn.execute(
                """
                INSERT INTO capital_brain_sources (
                    evaluation_id, session_id, source_domain, source_table,
                    source_record_id, contribution_summary
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (evaluation_id, source_domain, source_table, source_record_id) DO NOTHING
                """,
                (
                    row["evaluation_id"],
                    row["session_id"],
                    source["source_domain"],
                    source["source_table"],
                    source["source_record_id"],
                    source["contribution_summary"],
                ),
            )
        return dict(row)

    def latest_evaluation(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM capital_brain_evaluations
            WHERE session_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def dashboard_rows(self, conn: Connection, *, limit: int) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT e.*, s.session_type, s.title
                FROM capital_brain_evaluations e
                LEFT JOIN mesh_sessions s ON s.session_id = e.session_id
                ORDER BY e.created_at DESC, e.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def detail_by_evaluation(self, conn: Connection, evaluation_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM capital_brain_evaluations WHERE evaluation_id = %s", (evaluation_id,)).fetchone()
        if not row:
            return None
        return self.detail_for_row(conn, dict(row))

    def detail_by_session(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT * FROM capital_brain_evaluations WHERE session_id = %s ORDER BY created_at DESC, id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return self.detail_for_row(conn, dict(row))

    def detail_for_row(self, conn: Connection, evaluation: dict[str, Any]) -> dict[str, Any]:
        sources = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM capital_brain_sources
                WHERE evaluation_id = %s
                ORDER BY linked_at DESC, id DESC
                """,
                (evaluation["evaluation_id"],),
            ).fetchall()
        ]
        session = self.get_session(conn, str(evaluation["session_id"]))
        awareness = self.get_awareness(conn, str(evaluation["session_id"]))
        coordinator = None
        if table_exists(conn, "mesh_coordinator_decisions"):
            row = conn.execute(
                """
                SELECT *
                FROM mesh_coordinator_decisions
                WHERE session_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (evaluation["session_id"],),
            ).fetchone()
            coordinator = dict(row) if row else None
        return {
            "evaluation": evaluation,
            "sources": sources,
            "related_session": session,
            "related_awareness": awareness,
            "related_coordinator_decision": coordinator,
        }


def table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
    return row is not None and row["name"] is not None

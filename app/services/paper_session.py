from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.system_power import SystemPowerService
from app.utils.json_safety import json_safe

PAPER_LEDGER_TABLES = (
    "paper_intents",
    "paper_orders",
    "paper_fills",
    "paper_positions",
    "paper_position_closes",
    "paper_daily_pnl",
    "paper_capital_ledger",
    "paper_runs",
    "paper_signals",
    "paper_trade_ledger",
    "paper_order_events",
    "paper_position_events",
)
SESSION_COUNT_TABLES = (
    "paper_intents",
    "paper_orders",
    "paper_fills",
    "paper_positions",
    "paper_position_closes",
)
OPEN_POSITION_PREDICATE = "closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING') AND COALESCE(excluded_from_active_paper_truth,false)=false"


class PaperSessionService:
    """Official non-destructive paper session archive/reset surface."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        report_root: Path | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._report_root = report_root or Path("run_reports")

    def status(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "active_session": None, "current_session_counts": {}, "historical_totals": {}}
        with self._factory.connect() as conn:
            tables = _tables(conn)
            active = _active_session(conn) if "paper_sessions" in tables else None
            return json_safe(
                {
                    "status": "OK",
                    "source": "paper_session_service",
                    "active_session": active,
                    "current_session_counts": _session_counts(conn, tables, active["paper_session_id"] if active else None),
                    "current_session_pnl": _session_pnl(conn, tables, active["paper_session_id"] if active else None),
                    "current_session_account": _account(conn, tables),
                    "historical_totals": _historical_totals(conn, tables),
                    "previous_session_summary": _previous_session(conn, tables),
                    "reset_history": _reset_history(conn, tables, limit=10),
                }
            )

    def history(self, *, limit: int = 25) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "sessions": [], "resets": []}
        with self._factory.connect() as conn:
            tables = _tables(conn)
            sessions = _fetchall(
                conn,
                """
                SELECT *
                FROM paper_sessions
                ORDER BY started_at DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (limit,),
            ) if "paper_sessions" in tables else []
            return json_safe({"status": "OK", "sessions": sessions, "resets": _reset_history(conn, tables, limit=limit)})

    def reset(
        self,
        *,
        balance: Decimal | float | int | str = Decimal("1000"),
        defense_level: int | None = None,
        reason: str = "manual paper session reset",
        created_by: str = "polybot-cli",
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "errors": ["POLYBOT_DATABASE_URL is not configured"]}
        from app.services.paper_defense import defense_profile, normalize_defense_level

        requested_balance = _decimal(balance)
        if requested_balance <= 0:
            return {"status": "REJECTED", "errors": ["balance must be positive"]}
        requested_defense_level = normalize_defense_level(100 if defense_level is None else defense_level)
        profile = defense_profile(requested_defense_level)

        reset_id = f"paper_session_reset_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
        report_dir = self._report_root / reset_id
        report_dir.mkdir(parents=True, exist_ok=True)
        pre_status = self.status()
        _write_report(report_dir / "pre_reset_status.json", pre_status)

        stop_result = self._safe_stop_runtime(reason=reason, actor=created_by)
        errors: list[str] = []
        warnings: list[str] = []
        if not bool(stop_result.get("stopped")):
            warnings.append(f"runtime_stop_result={stop_result.get('status')}")

        with self._factory.connect() as conn, conn.transaction():
            tables = _tables(conn)
            safety = _live_shadow_safety(conn, tables)
            if not safety["safe"]:
                return {
                    "status": "REJECTED",
                    "reset_id": reset_id,
                    "errors": safety["errors"],
                    "report_dir": str(report_dir),
                    "stop_result": stop_result,
                }

            previous = _active_session(conn) if "paper_sessions" in tables else None
            if previous is None:
                previous = _create_legacy_session(conn, tables, created_by=created_by)
            previous_session_id = previous["paper_session_id"]
            _attach_null_rows(conn, tables, previous_session_id)
            previous_counts = _session_counts(conn, tables, previous_session_id)
            previous_pnl = _session_pnl(conn, tables, previous_session_id)
            open_before = _open_positions(conn, tables, previous_session_id)

            conn.execute(
                """
                INSERT INTO paper_session_resets (
                    reset_id, previous_session_id, requested_balance, status,
                    report_dir, previous_intents_count, previous_orders_count,
                    previous_fills_count, previous_positions_count,
                    previous_open_positions_count, previous_realized_pnl,
                    previous_unrealized_pnl, previous_net_pnl, errors_json,
                    warnings_json, created_by, metadata_json
                )
                VALUES (%s,%s,%s,'RUNNING',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    reset_id,
                    previous_session_id,
                    requested_balance,
                    str(report_dir),
                    previous_counts["paper_intents"],
                    previous_counts["paper_orders"],
                    previous_counts["paper_fills"],
                    previous_counts["paper_positions"],
                    open_before,
                    previous_pnl["realized"],
                    previous_pnl["unrealized"],
                    previous_pnl["net"],
                    Jsonb([]),
                    Jsonb(warnings),
                    created_by,
                    Jsonb({"reason": reason, "stop_result": json_safe(stop_result), "paper_defense": profile.to_dict()}),
                ),
            )

            closed_positions = _reset_close_open_positions(conn, tables, previous_session_id, reset_id)
            _archive_pending_intents(conn, tables, previous_session_id, reset_id)
            _archive_previous_session(conn, previous_session_id, reset_id=reset_id, report_dir=str(report_dir), reason=reason)
            new_session_id = f"paper_session_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
            _create_active_session(conn, new_session_id, balance=requested_balance, created_by=created_by, reset_id=reset_id, defense_level=requested_defense_level)
            _reset_paper_account(conn, tables, new_session_id, balance=requested_balance, reset_id=reset_id, defense_level=requested_defense_level)
            conn.execute(
                """
                UPDATE paper_session_resets
                SET new_session_id=%s,
                    status='COMPLETED',
                    reset_completed_at=now(),
                    errors_json=%s,
                    warnings_json=%s,
                    updated_at=now()
                WHERE reset_id=%s
                """,
                (new_session_id, Jsonb(errors), Jsonb(warnings), reset_id),
            )

        post_status = self.status()
        _write_report(report_dir / "post_reset_status.json", post_status)
        _write_report(
            report_dir / "paper_session_reset_result.json",
            {
                "status": "COMPLETED",
                "reset_id": reset_id,
                "previous_session_id": previous_session_id,
                "new_session_id": post_status.get("active_session", {}).get("paper_session_id"),
                "requested_balance": requested_balance,
                "defense_level": requested_defense_level,
                "defense_profile": profile.to_dict(),
                "closed_positions": closed_positions,
                "report_dir": str(report_dir),
                "stop_result": stop_result,
                "warnings": warnings,
                "errors": errors,
            },
        )
        return json_safe(
            {
                "status": "COMPLETED",
                "reset_id": reset_id,
                "previous_session_id": previous_session_id,
                "new_session_id": post_status.get("active_session", {}).get("paper_session_id"),
                "requested_balance": requested_balance,
                "defense_level": requested_defense_level,
                "defense_profile": profile.to_dict(),
                "closed_positions": closed_positions,
                "report_dir": str(report_dir),
                "current_session_counts": post_status.get("current_session_counts", {}),
                "historical_totals": post_status.get("historical_totals", {}),
                "active_session": post_status.get("active_session"),
                "stop_result": stop_result,
                "warnings": warnings,
                "errors": errors,
            }
        )

    def _safe_stop_runtime(self, *, actor: str, reason: str) -> dict[str, Any]:
        try:
            from app.control_center.action_contract import ControlCenterActionRequest
            from app.control_center.action_service import ControlCenterActionService

            envelope = ControlCenterActionService(connection_factory=self._factory).execute(
                "system-off",
                ControlCenterActionRequest(actor=actor, reason=f"paper session reset stop: {reason}"),
            )
            payload = envelope.to_api_dict() if hasattr(envelope, "to_api_dict") else envelope
            return {"stopped": True, "status": payload.get("status"), "payload": json_safe(payload)}
        except Exception as exc:
            try:
                result = self._system_power.turn_off(actor=actor, reason=f"paper session reset stop fallback: {reason}")
                return {"stopped": True, "status": "FALLBACK_SYSTEM_OFF", "payload": json_safe(result)}
            except Exception as fallback_exc:
                return {"stopped": False, "status": "STOP_FAILED", "error": f"{type(exc).__name__}: {exc}; fallback={type(fallback_exc).__name__}: {fallback_exc}"}


def active_paper_session_id(conn: Any) -> str | None:
    row = _active_session(conn)
    return str(row["paper_session_id"]) if row else None


def _tables(conn: Any) -> dict[str, set[str]]:
    rows = conn.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema=current_schema()
        """
    ).fetchall()
    out: dict[str, set[str]] = {}
    for row in rows:
        out.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    return out


def _active_session(conn: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_sessions"):
        return None
    row = conn.execute("SELECT * FROM paper_sessions WHERE status='ACTIVE' ORDER BY started_at DESC, id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _previous_session(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any] | None:
    if "paper_sessions" not in tables:
        return None
    row = conn.execute(
        """
        SELECT *
        FROM paper_sessions
        WHERE status <> 'ACTIVE'
        ORDER BY closed_at DESC NULLS LAST, started_at DESC NULLS LAST, id DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else None


def _session_counts(conn: Any, tables: dict[str, set[str]], session_id: str | None) -> dict[str, int]:
    out = {table: 0 for table in SESSION_COUNT_TABLES}
    out["open_paper_positions"] = 0
    if not session_id:
        return out
    for table in SESSION_COUNT_TABLES:
        if table in tables and "paper_session_id" in tables[table]:
            out[table] = _count_where(conn, table, "paper_session_id = %s", (session_id,))
    out["open_paper_positions"] = _open_positions(conn, tables, session_id)
    return out


def _historical_totals(conn: Any, tables: dict[str, set[str]]) -> dict[str, int]:
    out = {table: 0 for table in SESSION_COUNT_TABLES}
    out["open_paper_positions"] = 0
    for table in SESSION_COUNT_TABLES:
        if table in tables:
            out[table] = _count(conn, table)
    if "paper_positions" in tables:
        out["open_paper_positions"] = _count_where(conn, "paper_positions", OPEN_POSITION_PREDICATE)
    if "live_orders" in tables:
        out["live_orders"] = _count(conn, "live_orders")
    if "shadow_orders" in tables:
        out["shadow_orders"] = _count(conn, "shadow_orders")
    if "orders_v2" in tables:
        out["real_orders"] = _count(conn, "orders_v2")
    return out


def _session_pnl(conn: Any, tables: dict[str, set[str]], session_id: str | None) -> dict[str, Decimal]:
    zero = {"realized": Decimal("0"), "unrealized": Decimal("0"), "net": Decimal("0")}
    if not session_id:
        return zero
    realized = Decimal("0")
    unrealized = Decimal("0")
    if "paper_position_closes" in tables and "paper_session_id" in tables["paper_position_closes"]:
        realized = _sum_where(conn, "paper_position_closes", "realized_pnl", "paper_session_id = %s", (session_id,))
    if "paper_positions" in tables and "paper_session_id" in tables["paper_positions"]:
        unrealized = _sum_where(conn, "paper_positions", "unrealized", f"paper_session_id = %s AND {OPEN_POSITION_PREDICATE}", (session_id,))
    return {"realized": realized, "unrealized": unrealized, "net": realized + unrealized}


def _account(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any] | None:
    if "paper_accounts" not in tables:
        return None
    row = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default' ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _reset_history(conn: Any, tables: dict[str, set[str]], *, limit: int) -> list[dict[str, Any]]:
    if "paper_session_resets" not in tables:
        return []
    return _fetchall(conn, "SELECT * FROM paper_session_resets ORDER BY reset_started_at DESC, id DESC LIMIT %s", (limit,))


def _create_legacy_session(conn: Any, tables: dict[str, set[str]], *, created_by: str) -> dict[str, Any]:
    account = _account(conn, tables) or {}
    pnl = {
        "realized": _decimal(account.get("realized_pnl") or 0),
        "unrealized": _decimal(account.get("unrealized_pnl") or 0),
    }
    session_id = f"paper_session_legacy_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    row = conn.execute(
        """
        INSERT INTO paper_sessions (
            paper_session_id, session_name, starting_balance,
            current_balance_snapshot, realized_pnl, unrealized_pnl,
            net_pnl, status, started_at, created_by, metadata_json
        )
        VALUES (%s,'Legacy Paper Session',%s,%s,%s,%s,%s,'ACTIVE',now(),%s,%s)
        RETURNING *
        """,
        (
            session_id,
            _decimal(account.get("initial_balance") or 0),
            _decimal(account.get("current_balance") or 0),
            pnl["realized"],
            pnl["unrealized"],
            pnl["realized"] + pnl["unrealized"],
            created_by,
            Jsonb({"created_for_reset": True, "no_history_deleted": True}),
        ),
    ).fetchone()
    return dict(row)


def _create_active_session(conn: Any, session_id: str, *, balance: Decimal, created_by: str, reset_id: str, defense_level: int = 100) -> None:
    from app.services.paper_defense import defense_profile

    profile = defense_profile(defense_level)
    for ddl in (
        "ALTER TABLE paper_sessions ADD COLUMN IF NOT EXISTS defense_level INTEGER NOT NULL DEFAULT 100",
        "ALTER TABLE paper_sessions ADD COLUMN IF NOT EXISTS defense_profile_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE paper_sessions ADD COLUMN IF NOT EXISTS max_deployed_pct NUMERIC(8,4)",
        "ALTER TABLE paper_sessions ADD COLUMN IF NOT EXISTS max_single_trade_pct NUMERIC(8,4)",
        "ALTER TABLE paper_sessions ADD COLUMN IF NOT EXISTS session_learning_report_path TEXT",
    ):
        conn.execute(ddl)
    conn.execute(
        """
        INSERT INTO paper_sessions (
            paper_session_id, session_name, starting_balance,
            current_balance_snapshot, realized_pnl, unrealized_pnl,
            net_pnl, status, started_at, created_by, metadata_json,
            defense_level, defense_profile_snapshot, max_deployed_pct, max_single_trade_pct
        )
        VALUES (%s,'Fresh Paper Session',%s,%s,0,0,0,'ACTIVE',now(),%s,%s,%s,%s,%s,%s)
        """,
        (
            session_id,
            balance,
            balance,
            created_by,
            Jsonb({"reset_id": reset_id, "paper_only": True, "paper_defense": profile.to_dict()}),
            profile.defense_level,
            Jsonb(profile.to_dict()),
            profile.max_deployed_pct,
            profile.max_single_trade_pct,
        ),
    )


def _archive_previous_session(conn: Any, session_id: str, *, reset_id: str, report_dir: str, reason: str) -> None:
    conn.execute(
        """
        UPDATE paper_sessions
        SET status='RESET_CLOSED',
            closed_at=COALESCE(closed_at, now()),
            closed_reason=%s,
            reset_report_path=%s,
            metadata_json=COALESCE(metadata_json,'{}'::jsonb) || %s,
            updated_at=now()
        WHERE paper_session_id=%s
        """,
        (f"RESET_CLOSED: {reason}", report_dir, Jsonb({"reset_id": reset_id, "archived": True}), session_id),
    )


def _attach_null_rows(conn: Any, tables: dict[str, set[str]], session_id: str) -> None:
    for table in PAPER_LEDGER_TABLES:
        if table in tables and "paper_session_id" in tables[table]:
            conn.execute(f"UPDATE {table} SET paper_session_id=%s WHERE paper_session_id IS NULL", (session_id,))


def _reset_close_open_positions(conn: Any, tables: dict[str, set[str]], session_id: str, reset_id: str) -> int:
    if "paper_positions" not in tables:
        return 0
    rows = _fetchall(
        conn,
        f"""
        SELECT *
        FROM paper_positions
        WHERE paper_session_id=%s
          AND {OPEN_POSITION_PREDICATE}
        FOR UPDATE
        """,
        (session_id,),
    )
    for row in rows:
        entry = _decimal(row.get("avg_entry") or 0)
        mark = _decimal(row.get("mark_price") or row.get("avg_entry") or 0)
        qty = _decimal(row.get("size") or 0)
        realized = (mark - entry) * qty if entry > 0 and qty > 0 else _decimal(row.get("unrealized") or 0)
        close_id = f"reset_close_{reset_id}_{row['id']}"
        if "paper_position_closes" in tables:
            conn.execute(
                """
                INSERT INTO paper_position_closes (
                    close_id, position_id, trade_id, market_id, side,
                    entry_price, exit_price, quantity, realized_pnl,
                    realized_pnl_pct, exit_reason, price_basis,
                    source_exit_price, correlation_id, metadata_json,
                    paper_session_id, reset_id, created_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,'RESET_CLOSED','RESET_ARCHIVE',%s,%s,%s,%s,%s,now())
                ON CONFLICT (close_id) DO NOTHING
                """,
                (
                    close_id,
                    row["id"],
                    row.get("paper_run_id"),
                    row.get("market_id"),
                    row.get("intended_outcome"),
                    entry,
                    mark,
                    qty,
                    realized,
                    mark,
                    reset_id,
                    Jsonb({"reset_id": reset_id, "reset_closed": True, "previous_unrealized": str(row.get("unrealized") or 0)}),
                    session_id,
                    reset_id,
                ),
            )
        conn.execute(
            """
            UPDATE paper_positions
            SET current_status='RESET_CLOSED',
                closed_at=COALESCE(closed_at, now()),
                mark_price=%s,
                unrealized=0,
                realized=%s,
                excluded_from_active_paper_truth=true,
                reset_id=%s,
                payload_json=COALESCE(payload_json,'{}'::jsonb) || %s,
                updated_at=now()
            WHERE id=%s
            """,
            (
                mark,
                realized,
                reset_id,
                Jsonb({"reset_id": reset_id, "close_reason": "RESET_CLOSED", "excluded_from_new_session": True}),
                row["id"],
            ),
        )
    return len(rows)


def _archive_pending_intents(conn: Any, tables: dict[str, set[str]], session_id: str, reset_id: str) -> None:
    if "paper_intents" not in tables:
        return
    conn.execute(
        """
        UPDATE paper_intents
        SET intent_status='RESET_ARCHIVED',
            reset_id=%s,
            blockers=COALESCE(blockers,'[]'::jsonb) || '["RESET_ARCHIVED_PREVIOUS_SESSION"]'::jsonb,
            updated_at=now()
        WHERE paper_session_id=%s
          AND intent_status IN ('CREATED','READY','OPEN','PENDING','ENTER')
        """,
        (reset_id, session_id),
    )


def _reset_paper_account(conn: Any, tables: dict[str, set[str]], session_id: str, *, balance: Decimal, reset_id: str, defense_level: int = 100) -> None:
    if "paper_accounts" not in tables:
        return
    from app.services.paper_defense import defense_profile

    profile = defense_profile(defense_level)
    conn.execute(
        """
        INSERT INTO paper_accounts (
            account_id, name, currency, initial_balance, current_balance,
            available_balance, locked_balance, open_exposure, realized_pnl,
            unrealized_pnl, daily_pnl, risk_per_trade_pct,
            max_position_size, max_daily_loss_pct, max_open_positions,
            max_total_open_exposure_pct, status, metadata_json,
            paper_session_id, created_at, updated_at
        )
        VALUES (
            'paper_default','Default Paper Account','USD',%s,%s,%s,0,0,0,0,0,
            %s,GREATEST(%s * %s / 100.0, 1),5,%s,%s,'ACTIVE',%s,%s,now(),now()
        )
        ON CONFLICT (account_id) DO UPDATE SET
            initial_balance=EXCLUDED.initial_balance,
            current_balance=EXCLUDED.current_balance,
            available_balance=EXCLUDED.available_balance,
            locked_balance=0,
            open_exposure=0,
            realized_pnl=0,
            unrealized_pnl=0,
            daily_pnl=0,
            risk_per_trade_pct=EXCLUDED.risk_per_trade_pct,
            max_position_size=EXCLUDED.max_position_size,
            max_open_positions=EXCLUDED.max_open_positions,
            max_total_open_exposure_pct=EXCLUDED.max_total_open_exposure_pct,
            status='ACTIVE',
            paper_session_id=EXCLUDED.paper_session_id,
            metadata_json=COALESCE(paper_accounts.metadata_json,'{}'::jsonb) || EXCLUDED.metadata_json,
            updated_at=now()
        """,
        (
            balance,
            balance,
            balance,
            profile.max_single_trade_pct,
            balance,
            profile.max_single_trade_pct,
            profile.max_open_positions,
            profile.max_deployed_pct,
            Jsonb({"reset_id": reset_id, "paper_session_id": session_id, "paper_defense": profile.to_dict()}),
            session_id,
        ),
    )


def _live_shadow_safety(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    errors: list[str] = []
    for table in ("live_orders", "shadow_orders"):
        if table in tables and _count(conn, table) > 0:
            errors.append(f"{table.upper()}_PRESENT")
    return {"safe": not errors, "errors": errors}


def _open_positions(conn: Any, tables: dict[str, set[str]], session_id: str | None = None) -> int:
    if "paper_positions" not in tables:
        return 0
    if session_id and "paper_session_id" in tables["paper_positions"]:
        return _count_where(conn, "paper_positions", f"paper_session_id=%s AND {OPEN_POSITION_PREDICATE}", (session_id,))
    return _count_where(conn, "paper_positions", OPEN_POSITION_PREDICATE)


def _count(conn: Any, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _count_where(conn: Any, table: str, predicate: str, params: tuple[Any, ...] = ()) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {predicate}", params).fetchone()["count"] or 0)


def _sum_where(conn: Any, table: str, column: str, predicate: str, params: tuple[Any, ...] = ()) -> Decimal:
    row = conn.execute(f"SELECT COALESCE(SUM({column}),0) AS total FROM {table} WHERE {predicate}", params).fetchone()
    return _decimal(row["total"] if row else 0)


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or "0"))


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")

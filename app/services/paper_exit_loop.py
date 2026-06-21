from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.paper_capital import PaperCapitalService
from app.services.paper_session import active_paper_session_id
from app.services.system_power import SystemPowerService
from app.utils.json_safety import json_safe

FRESH_ORDERBOOK_SECONDS = 180
TAKE_PROFIT_REASON = "TAKE_PROFIT"
STOP_LOSS_REASON = "STOP_LOSS"
MAX_HOLD_REASON = "MAX_HOLD_TIME"


class PaperExitLoopService:
    """Close only existing open paper positions and derive paper PnL truth."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        paper_capital: PaperCapitalService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._paper_capital = paper_capital or PaperCapitalService(connection_factory=self._factory, system_power=self._system_power)

    def run_exit_loop(self, *, limit: int = 100, correlation_id: str | None = None) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"paper_exit_loop_{uuid4().hex}"
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        if system_power != "ON" or not bool(power.get("runtime_work_allowed")):
            return self._blocked_payload(run_id, system_power, started_at, "SYSTEM_POWER_OFF")
        if not self._factory.enabled:
            return self._empty_payload(run_id, system_power, started_at, "NO_OPEN_PAPER_POSITIONS")

        with self._factory.connect() as conn:
            open_count = _count_open_positions(conn)
        if open_count == 0:
            payload = self._empty_payload(run_id, system_power, started_at, "NO_OPEN_PAPER_POSITIONS")
            self._record_run(payload)
            return _json_safe(payload)

        if not self._governor.can_execute(RuntimeAction.CLOSE_POSITION):
            payload = self._blocked_payload(run_id, system_power, started_at, "STATE_GOVERNOR_BLOCKED_CLOSE_POSITION")
            payload["open_positions_checked"] = open_count
            self._record_run(payload)
            return _json_safe(payload)

        safety_before = self._safety_counts()
        closed = 0
        marked = 0
        blocked = 0
        no_exit_price = 0
        no_exit_condition = 0
        duplicate = 0
        realized_total = Decimal("0")
        errors: list[str] = []
        close_results: list[dict[str, Any]] = []

        with self._factory.connect() as conn, conn.transaction():
            positions = _list_open_positions(conn, limit=limit)
            for position in positions:
                try:
                    with conn.transaction():
                        decision = self._evaluate_position(conn, position)
                        if decision["status"] == "NO_EXIT_PRICE":
                            no_exit_price += 1
                            blocked += 1
                            self._mark_position(conn, position, decision, correlation_id=correlation_id)
                            continue
                        marked += 1
                        self._mark_position(conn, position, decision, correlation_id=correlation_id)
                        if decision["status"] == "HOLD":
                            no_exit_condition += 1
                            continue
                        if _close_exists(conn, str(position["id"])):
                            duplicate += 1
                            continue
                        close = self._close_position(conn, position, decision, correlation_id=correlation_id)
                        realized_total += Decimal(str(close["realized_pnl"]))
                        close_results.append(close)
                        closed += 1
                except Exception as exc:
                    blocked += 1
                    errors.append(f"{position.get('id')}:{type(exc).__name__}:{exc}")
            daily = self._refresh_daily_pnl(conn)
            orphan_count = _orphan_count(conn)

        safety_after = self._safety_counts()
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "system_power": system_power,
            "status": "DEGRADED" if errors else "OK",
            "open_positions_checked": len(positions),
            "closed_positions_count": closed,
            "marked_positions_count": marked,
            "blocked_positions_count": blocked,
            "no_exit_price_count": no_exit_price,
            "no_exit_condition_count": no_exit_condition,
            "duplicate_close_skipped_count": duplicate,
            "orphan_positions_count": orphan_count,
            "realized_pnl": float(realized_total),
            "unrealized_pnl": _float_or_none(daily.get("unrealized_pnl")),
            "paper_orders_delta": max(0, safety_after["paper_orders"] - safety_before["paper_orders"]),
            "paper_positions_delta": max(0, safety_after["paper_positions"] - safety_before["paper_positions"]),
            "real_orders_delta": max(0, safety_after["real_orders"] - safety_before["real_orders"]),
            "fills_delta": max(0, safety_after["fills"] - safety_before["fills"]),
            "live_orders_delta": max(0, safety_after["live_orders"] - safety_before["live_orders"]),
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "error_summary": "; ".join(errors) if errors else None,
            "metadata": {"closed_positions": close_results, "correlation_id": correlation_id, "daily_pnl": daily},
        }
        self._record_run(payload)
        return _json_safe(payload)

    def get_exits_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard("NO_OPEN_PAPER_POSITIONS")
        with self._factory.connect() as conn:
            open_positions = _count_open_positions(conn)
            closed_trades = _count_table(conn, "paper_position_closes")
            latest_run = _latest_run(conn)
            latest_close = _latest_close(conn)
            daily = _latest_daily(conn)
            orphan_count = _orphan_count(conn)
            stale_price_count = _stale_price_count(conn)
        safety_counts = self._safety_counts()
        latest_run = latest_run or {}
        status = "NO_OPEN_PAPER_POSITIONS" if open_positions == 0 and closed_trades == 0 else "OK"
        return {
            "mock_data": False,
            "status": status,
            "latest_run": latest_run,
            "open_paper_positions": open_positions,
            "closed_paper_trades": closed_trades,
            "pending_exit_checks": open_positions,
            "realized_pnl": _float_or_none((daily or {}).get("realized_pnl")) or 0.0,
            "unrealized_pnl": _float_or_none((daily or {}).get("unrealized_pnl")),
            "daily_pnl": daily,
            "latest_close_at": (latest_close or {}).get("created_at"),
            "latest_exit_reason": (latest_close or {}).get("exit_reason"),
            "orphan_positions_count": orphan_count,
            "pnl_source": "paper_position_closes+paper_positions",
            "stale_price_count": stale_price_count,
            "paper_orders_created": _int(latest_run.get("paper_orders_delta")),
            "paper_positions_created": _int(latest_run.get("paper_positions_delta")),
            "real_orders_created": _int(latest_run.get("real_orders_delta")),
            "fills_created": _int(latest_run.get("fills_delta")),
            "live_orders_created": _int(latest_run.get("live_orders_delta")),
            "real_orders_total": safety_counts["real_orders"],
            "live_orders_total": safety_counts["live_orders"],
            "real_orders": safety_counts["real_orders"],
            "live_orders": safety_counts["live_orders"],
            "paper_ready": False,
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def get_pnl_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard("NO_OPEN_PAPER_POSITIONS")
        with self._factory.connect() as conn, conn.transaction():
            daily = self._refresh_daily_pnl(conn)
            latest_run = _latest_run(conn)
            rows = _recent_daily(conn, limit=limit)
            open_positions = _count_open_positions(conn)
            closed_trades = _count_table(conn, "paper_position_closes")
            orphan_count = _orphan_count(conn)
        safety_counts = self._safety_counts()
        latest_run = latest_run or {}
        status = "NO_OPEN_PAPER_POSITIONS" if open_positions == 0 and closed_trades == 0 else "OK"
        return {
            "mock_data": False,
            "status": status,
            "latest_run": latest_run,
            "open_paper_positions": open_positions,
            "closed_paper_trades": closed_trades,
            "realized_pnl": _float_or_none(daily.get("realized_pnl")) or 0.0,
            "unrealized_pnl": _float_or_none(daily.get("unrealized_pnl")),
            "daily_pnl": daily,
            "daily_pnl_history": rows,
            "orphan_positions_count": orphan_count,
            "pnl_source": "derived_from_paper_trade_ledger_and_positions",
            "stale_price_count": _int(daily.get("stale_price_count")),
            "paper_orders_created": _int(latest_run.get("paper_orders_delta")),
            "paper_positions_created": _int(latest_run.get("paper_positions_delta")),
            "real_orders_created": _int(latest_run.get("real_orders_delta")),
            "fills_created": _int(latest_run.get("fills_delta")),
            "live_orders_created": _int(latest_run.get("live_orders_delta")),
            "real_orders_total": safety_counts["real_orders"],
            "live_orders_total": safety_counts["live_orders"],
            "real_orders": safety_counts["real_orders"],
            "live_orders": safety_counts["live_orders"],
            "paper_ready": False,
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _evaluate_position(self, conn: Any, position: dict[str, Any]) -> dict[str, Any]:
        side = str(position["intended_outcome"]).upper()
        mark = _latest_mark(conn, market_id=str(position["market_id"]), side=side)
        if mark is None:
            return {"status": "NO_EXIT_PRICE", "exit_price": None, "exit_reason": "NO_EXIT_PRICE", "price_basis": "UNAVAILABLE", "source_exit_price": "missing_fresh_orderbook"}
        entry = Decimal(str(position["avg_entry"]))
        quantity = Decimal(str(position["size"]))
        unrealized = (mark["price"] - entry) * quantity
        exit_plan = _latest_exit_plan(conn, market_id=str(position["market_id"]), side=side)
        reason = None
        if exit_plan:
            target = _decimal_or_none(exit_plan.get("target_exit"))
            stop = _decimal_or_none(exit_plan.get("stop_loss"))
            max_hold_seconds = _int(exit_plan.get("max_hold_seconds"))
            if target is not None and mark["price"] >= target:
                reason = TAKE_PROFIT_REASON
            elif stop is not None and mark["price"] <= stop:
                reason = STOP_LOSS_REASON
            elif max_hold_seconds > 0 and (datetime.now(UTC) - position["opened_at"]).total_seconds() >= max_hold_seconds:
                reason = MAX_HOLD_REASON
        return {
            "status": "CLOSE" if reason else "HOLD",
            "exit_reason": reason,
            "exit_price": mark["price"],
            "price_basis": "ORDERBOOK_MID",
            "source_exit_price": mark["source"],
            "orderbook_snapshot_id": mark["orderbook_snapshot_id"],
            "unrealized_pnl": unrealized,
            "exit_plan": exit_plan,
        }

    def _mark_position(self, conn: Any, position: dict[str, Any], decision: dict[str, Any], *, correlation_id: str | None) -> None:
        if decision.get("exit_price") is None:
            return
        conn.execute(
            """
            UPDATE paper_positions
            SET mark_price = %s,
                unrealized = %s,
                updated_at = now(),
                payload_json = jsonb_set(
                    COALESCE(payload_json, '{}'::jsonb),
                    '{paper_exit_loop}',
                    %s
                )
            WHERE id = %s
            """,
            (
                decision["exit_price"],
                decision["unrealized_pnl"],
                Jsonb({"last_checked_at": datetime.now(UTC).isoformat(), "correlation_id": correlation_id, "status": decision["status"]}),
                position["id"],
            ),
        )

    def _close_position(self, conn: Any, position: dict[str, Any], decision: dict[str, Any], *, correlation_id: str | None) -> dict[str, Any]:
        paper_session_id = str(position.get("paper_session_id") or active_paper_session_id(conn) or "NO_ACTIVE_PAPER_SESSION")
        entry = Decimal(str(position["avg_entry"]))
        exit_price = Decimal(str(decision["exit_price"]))
        quantity = Decimal(str(position["size"]))
        realized = (exit_price - entry) * quantity
        realized_pct = (realized / (entry * quantity)) if entry > 0 and quantity > 0 else None
        exit_plan = decision.get("exit_plan") or {}
        close_id = f"paper_close_{position['id']}"
        ledger_id = f"paper_ledger_close_{position['id']}"
        close = {
            "close_id": close_id,
            "position_id": position["id"],
            "trade_id": str(position["paper_run_id"]),
            "market_id": position["market_id"],
            "side": position["intended_outcome"],
            "entry_price": entry,
            "exit_price": exit_price,
            "quantity": quantity,
            "realized_pnl": realized,
            "realized_pnl_pct": realized_pct,
            "exit_reason": decision["exit_reason"],
            "price_basis": decision["price_basis"],
            "source_exit_price": decision["source_exit_price"],
            "exit_plan_id": exit_plan.get("exit_plan_id"),
            "risk_decision_id": exit_plan.get("risk_decision_ref") or exit_plan.get("risk_decision_id"),
            "correlation_id": correlation_id,
            "metadata_json": Jsonb({"orderbook_snapshot_id": decision.get("orderbook_snapshot_id"), "paper_only": True}),
            "paper_session_id": paper_session_id,
        }
        conn.execute(
            """
            INSERT INTO paper_position_closes (
                close_id, position_id, trade_id, market_id, side, entry_price,
                exit_price, quantity, realized_pnl, realized_pnl_pct, exit_reason,
                price_basis, source_exit_price, exit_plan_id, risk_decision_id,
                correlation_id, metadata_json, paper_session_id, created_at
            )
            VALUES (
                %(close_id)s, %(position_id)s, %(trade_id)s, %(market_id)s,
                %(side)s, %(entry_price)s, %(exit_price)s, %(quantity)s,
                %(realized_pnl)s, %(realized_pnl_pct)s, %(exit_reason)s,
                %(price_basis)s, %(source_exit_price)s, %(exit_plan_id)s,
                %(risk_decision_id)s, %(correlation_id)s, %(metadata_json)s,
                %(paper_session_id)s, now()
            )
            """,
            close,
        )
        conn.execute(
            """
            INSERT INTO paper_trade_ledger (
                ledger_id, position_id, event_type, market_id, side, amount,
                realized_pnl, unrealized_pnl, reason, correlation_id, metadata_json, created_at
            )
            VALUES (%s, %s, 'CLOSE', %s, %s, %s, %s, 0, %s, %s, %s, now())
            """,
            (
                ledger_id,
                position["id"],
                position["market_id"],
                position["intended_outcome"],
                quantity,
                realized,
                decision["exit_reason"],
                correlation_id,
                Jsonb({"close_id": close_id, "price_basis": decision["price_basis"], "paper_session_id": paper_session_id}),
            ),
        )
        conn.execute("UPDATE paper_trade_ledger SET paper_session_id=%s WHERE ledger_id=%s", (paper_session_id, ledger_id))
        conn.execute(
            """
            UPDATE paper_positions
            SET current_status = 'CLOSED',
                closed_at = now(),
                mark_price = %s,
                unrealized = 0,
                realized = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (exit_price, realized, position["id"]),
        )
        source_intent_id = None
        payload = position.get("payload_json") if isinstance(position.get("payload_json"), dict) else {}
        if isinstance(payload, dict):
            source_intent_id = payload.get("source_intent_id")
        if source_intent_id:
            conn.execute(
                """
                UPDATE paper_intents
                SET intent_status = 'CLOSED',
                    closed_at = COALESCE(closed_at, now()),
                    updated_at = now()
                WHERE paper_intent_id = %s
                """,
                (source_intent_id,),
            )
        capital_result = self._paper_capital.release_on_close(conn, close=close, position=position)
        if capital_result.get("status") != "RELEASED":
            raise RuntimeError(f"paper close capital release failed: {capital_result.get('status')}")
        conn.execute(
            """
            INSERT INTO paper_position_events (
                id, paper_position_id, event_at, event_type, reason_code,
                reason_text, payload_json, created_at
            )
            VALUES (%s, %s, now(), 'CLOSED', %s, %s, %s, now())
            """,
            (
                str(uuid4()),
                position["id"],
                str(decision["exit_reason"]).lower(),
                f"paper position closed by {decision['exit_reason']}",
                Jsonb({"close_id": close_id, "realized_pnl": float(realized), "exit_price": float(exit_price)}),
            ),
        )
        result = {key: _json_safe(value) for key, value in close.items() if key != "metadata_json"}
        result["capital_result"] = capital_result
        return result

    def _refresh_daily_pnl(self, conn: Any) -> dict[str, Any]:
        today = date.today()
        paper_session_id = active_paper_session_id(conn) or "NO_ACTIVE_PAPER_SESSION"
        closed = conn.execute(
            """
            SELECT
                COALESCE(SUM(realized_pnl), 0) AS realized_pnl,
                COALESCE(SUM(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS gross_profit,
                COALESCE(SUM(realized_pnl) FILTER (WHERE realized_pnl < 0), 0) AS gross_loss,
                COUNT(*) AS closed_trades_count,
                COUNT(*) FILTER (WHERE realized_pnl > 0) AS winning_trades_count,
                COUNT(*) FILTER (WHERE realized_pnl < 0) AS losing_trades_count
            FROM paper_position_closes
            WHERE created_at::date = %s
              AND (%s::text IS NULL OR paper_session_id = %s::text)
            """,
            (today, paper_session_id, paper_session_id),
        ).fetchone()
        open_row = conn.execute(
            """
            SELECT
                COUNT(*) AS open_positions_count,
                COALESCE(SUM(unrealized), 0) AS unrealized_pnl,
                COUNT(*) FILTER (WHERE mark_price IS NULL) AS stale_price_count
            FROM paper_positions
            WHERE closed_at IS NULL
              AND current_status IN ('OPEN', 'EXIT_PENDING')
              AND COALESCE(excluded_from_active_paper_truth, false) = false
              AND (%s::text IS NULL OR paper_session_id = %s::text)
            """
            ,
            (paper_session_id, paper_session_id),
        ).fetchone()
        realized = Decimal(str(closed["realized_pnl"] or 0))
        unrealized = Decimal(str(open_row["unrealized_pnl"] or 0))
        row = conn.execute(
            """
            INSERT INTO paper_daily_pnl (
                pnl_date, paper_session_id, realized_pnl, unrealized_pnl, net_pnl, gross_profit,
                gross_loss, closed_trades_count, open_positions_count,
                winning_trades_count, losing_trades_count, stale_price_count, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (paper_session_id, pnl_date) DO UPDATE SET
                realized_pnl = EXCLUDED.realized_pnl,
                unrealized_pnl = EXCLUDED.unrealized_pnl,
                net_pnl = EXCLUDED.net_pnl,
                gross_profit = EXCLUDED.gross_profit,
                gross_loss = EXCLUDED.gross_loss,
                closed_trades_count = EXCLUDED.closed_trades_count,
                open_positions_count = EXCLUDED.open_positions_count,
                winning_trades_count = EXCLUDED.winning_trades_count,
                losing_trades_count = EXCLUDED.losing_trades_count,
                stale_price_count = EXCLUDED.stale_price_count,
                updated_at = now()
            RETURNING *
            """,
            (
                today,
                paper_session_id,
                realized,
                unrealized,
                realized + unrealized,
                closed["gross_profit"],
                closed["gross_loss"],
                closed["closed_trades_count"],
                open_row["open_positions_count"],
                closed["winning_trades_count"],
                closed["losing_trades_count"],
                open_row["stale_price_count"],
            ),
        ).fetchone()
        return _json_safe(dict(row))

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "paper_exit_loop_runs"):
                return
            conn.execute(
                """
                INSERT INTO paper_exit_loop_runs (
                    run_id, system_power, status, open_positions_checked,
                    closed_positions_count, marked_positions_count,
                    blocked_positions_count, no_exit_price_count,
                    no_exit_condition_count, duplicate_close_skipped_count,
                    orphan_positions_count, realized_pnl, unrealized_pnl,
                    paper_orders_delta, paper_positions_delta, real_orders_delta,
                    fills_delta, live_orders_delta, started_at, finished_at,
                    error_summary, metadata_json, created_at
                )
                VALUES (
                    %(run_id)s, %(system_power)s, %(status)s,
                    %(open_positions_checked)s, %(closed_positions_count)s,
                    %(marked_positions_count)s, %(blocked_positions_count)s,
                    %(no_exit_price_count)s, %(no_exit_condition_count)s,
                    %(duplicate_close_skipped_count)s, %(orphan_positions_count)s,
                    %(realized_pnl)s, %(unrealized_pnl)s,
                    %(paper_orders_delta)s, %(paper_positions_delta)s,
                    %(real_orders_delta)s, %(fills_delta)s, %(live_orders_delta)s,
                    %(started_at)s, %(finished_at)s, %(error_summary)s,
                %(metadata_json)s, now()
            )
            """,
                {**payload, "metadata_json": Jsonb(_json_safe(payload.get("metadata") or {}))},
            )

    def _empty_payload(self, run_id: str, system_power: str, started_at: datetime, status: str) -> dict[str, Any]:
        safety = self._safety_counts()
        return {
            "mock_data": False,
            "run_id": run_id,
            "system_power": system_power,
            "status": status,
            "open_positions_checked": 0,
            "closed_positions_count": 0,
            "marked_positions_count": 0,
            "blocked_positions_count": 0,
            "no_exit_price_count": 0,
            "no_exit_condition_count": 0,
            "duplicate_close_skipped_count": 0,
            "orphan_positions_count": 0,
            "realized_pnl": 0,
            "unrealized_pnl": None,
            "paper_orders_delta": 0,
            "paper_positions_delta": 0,
            "real_orders_delta": 0,
            "fills_delta": 0,
            "live_orders_delta": 0,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "error_summary": None,
            "metadata": {"paper_orders": safety["paper_orders"], "paper_positions": safety["paper_positions"], "no_fake_pnl": True},
        }

    def _blocked_payload(self, run_id: str, system_power: str, started_at: datetime, reason: str) -> dict[str, Any]:
        payload = self._empty_payload(run_id, system_power, started_at, "BLOCKED")
        payload["blocked_reason"] = reason
        payload["metadata"]["blocked_reason"] = reason
        return _json_safe(payload)

    def _safety_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {"paper_orders": 0, "paper_positions": 0, "real_orders": 0, "fills": 0, "live_orders": 0}
        with self._factory.connect() as conn:
            return {
                "paper_orders": _count_table(conn, "paper_orders"),
                "paper_positions": _count_table(conn, "paper_positions"),
                "real_orders": _count_table(conn, "orders_v2"),
                "fills": _count_table(conn, "fills_v2") + _count_table(conn, "paper_fills"),
                "live_orders": _count_table(conn, "live_orders"),
            }


def _list_open_positions(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM paper_positions
            WHERE closed_at IS NULL
              AND current_status IN ('OPEN', 'EXIT_PENDING')
              AND COALESCE(excluded_from_active_paper_truth, false) = false
              AND size > 0
              AND avg_entry IS NOT NULL
            ORDER BY opened_at ASC, updated_at ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    ]


def _latest_mark(conn: Any, *, market_id: str, side: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, mid_price, collected_at
        FROM orderbook_snapshots
        WHERE market_id = %s
          AND side = %s
          AND mid_price IS NOT NULL
          AND is_stale = false
          AND snapshot_status IN ('OK', 'PARTIAL')
          AND collected_at >= now() - (%s || ' seconds')::interval
        ORDER BY collected_at DESC, id DESC
        LIMIT 1
        """,
        (market_id, side, FRESH_ORDERBOOK_SECONDS),
    ).fetchone()
    if not row:
        return None
    return {"price": Decimal(str(row["mid_price"])), "source": f"orderbook_snapshot:{row['id']}", "orderbook_snapshot_id": row["id"]}


def _latest_exit_plan(conn: Any, *, market_id: str, side: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM exit_plans
        WHERE market_id = %s
          AND side = %s
          AND created_from = 'exit_foundation'
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (market_id, side),
    ).fetchone()
    return dict(row) if row else None


def _close_exists(conn: Any, position_id: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM paper_position_closes WHERE position_id = %s", (position_id,)).fetchone())


def _count_open_positions(conn: Any) -> int:
    return _count_where(conn, "paper_positions", "closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING') AND COALESCE(excluded_from_active_paper_truth,false)=false")


def _orphan_count(conn: Any) -> int:
    if not _table_exists(conn, "paper_position_closes"):
        return 0
    missing_close = _count_where(
        conn,
        "paper_positions",
        "current_status = 'CLOSED' AND closed_at IS NOT NULL AND realized IS NOT NULL AND NOT EXISTS (SELECT 1 FROM paper_position_closes ppc WHERE ppc.position_id = paper_positions.id)",
    )
    missing_position = int(
        conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM paper_position_closes ppc
            LEFT JOIN paper_positions pp ON pp.id = ppc.position_id
            WHERE pp.id IS NULL
            """
        ).fetchone()["count"]
        or 0
    )
    return missing_close + missing_position


def _stale_price_count(conn: Any) -> int:
    return _count_where(conn, "paper_positions", "closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING') AND COALESCE(excluded_from_active_paper_truth,false)=false AND mark_price IS NULL")


def _latest_run(conn: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_exit_loop_runs"):
        return None
    row = conn.execute("SELECT * FROM paper_exit_loop_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
    return _json_safe(dict(row)) if row else None


def _latest_close(conn: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_position_closes"):
        return None
    row = conn.execute("SELECT * FROM paper_position_closes ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
    return _json_safe(dict(row)) if row else None


def _latest_daily(conn: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_daily_pnl"):
        return None
    row = conn.execute("SELECT * FROM paper_daily_pnl ORDER BY pnl_date DESC LIMIT 1").fetchone()
    return _json_safe(dict(row)) if row else None


def _recent_daily(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_daily_pnl"):
        return []
    return [_json_safe(dict(row)) for row in conn.execute("SELECT * FROM paper_daily_pnl ORDER BY pnl_date DESC LIMIT %s", (limit,)).fetchall()]


def _empty_dashboard(status: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "open_paper_positions": 0,
        "closed_paper_trades": 0,
        "realized_pnl": 0.0,
        "unrealized_pnl": None,
        "daily_pnl": None,
        "orphan_positions_count": 0,
        "pnl_source": "none",
        "stale_price_count": 0,
        "real_orders": 0,
        "live_orders": 0,
        "paper_ready": False,
        "last_updated": datetime.now(UTC).isoformat(),
    }


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_safe(value: Any) -> Any:
    return json_safe(value)

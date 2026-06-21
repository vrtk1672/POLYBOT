from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_session import active_paper_session_id
from app.services.system_power import SystemPowerService

DEFAULT_ACCOUNT_ID = "paper_default"
CAPITAL_LOCK_EVENTS = ("CAPITAL_LOCKED_ON_FILL", "CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL")
CAPITAL_RELEASE_EVENTS = ("CAPITAL_RELEASED_ON_CLOSE", "CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE")
REALIZED_PNL_EVENTS = ("REALIZED_PNL_APPLIED", "REALIZED_PNL_BACKFILLED_FROM_REAL_CLOSE")
MIN_RISK_CLAMP_NOTIONAL = Decimal("5.00")


@dataclass(frozen=True)
class CapitalCheck:
    allowed: bool
    blockers: list[str]
    notional: Decimal
    account_id: str = DEFAULT_ACCOUNT_ID


class PaperCapitalService:
    """Paper-only bankroll accounting for fills, closes, and capital guards."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        account_id: str = DEFAULT_ACCOUNT_ID,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._account_id = account_id

    def precheck_fill(
        self,
        conn: Any,
        *,
        paper_intent_id: str | None,
        fill_price: Decimal,
        quantity: Decimal,
        write_block: bool = False,
    ) -> CapitalCheck:
        if not _tables_ready(conn):
            return CapitalCheck(True, [], _notional(fill_price, quantity), self._account_id)

        account = _account_for_update(conn, self._account_id, lock=False)
        if not account:
            return CapitalCheck(False, ["PAPER_ACCOUNT_MISSING"], _notional(fill_price, quantity), self._account_id)

        notional = _notional(fill_price, quantity)
        blockers: list[str] = []
        if notional <= 0:
            blockers.append("INVALID_NOTIONAL")

        current_balance = _decimal(account["current_balance"])
        available = _decimal(account["available_balance"])
        max_position_size = _decimal(account["max_position_size"])
        max_risk_amount = current_balance * _decimal(account["risk_per_trade_pct"]) / Decimal("100")
        max_loss = _decimal(account["initial_balance"]) * _decimal(account["max_daily_loss_pct"]) / Decimal("100")
        daily_realized = _daily_realized_pnl(conn)
        active_open = _active_open_positions(conn)
        open_exposure = _active_open_exposure(conn)
        max_exposure = current_balance * _decimal(account["max_total_open_exposure_pct"]) / Decimal("100")

        if available < notional:
            blockers.append("INSUFFICIENT_PAPER_BALANCE")
        if notional > max_position_size:
            blockers.append("POSITION_SIZE_LIMIT")
        if notional > max_risk_amount:
            blockers.append("RISK_PER_TRADE_LIMIT")
        if daily_realized <= -max_loss:
            blockers.append("DAILY_LOSS_LIMIT")
        if active_open >= int(account["max_open_positions"] or 0):
            blockers.append("MAX_OPEN_POSITIONS")
        if open_exposure + notional > max_exposure:
            blockers.append("MAX_EXPOSURE_LIMIT")

        if blockers and write_block:
            for blocker in blockers:
                self._insert_guard_event(conn, account, blocker, paper_intent_id, notional)

        return CapitalCheck(not blockers, blockers, notional, self._account_id)

    def clamp_quantity_for_fill(
        self,
        conn: Any,
        *,
        paper_intent_id: str | None,
        fill_price: Decimal,
        quantity: Decimal,
        min_notional: Decimal = MIN_RISK_CLAMP_NOTIONAL,
    ) -> dict[str, Any]:
        """Clamp Paper quantity to current risk capacity when only size/risk caps block.

        This is intentionally Paper-only and does not soften balance, daily loss,
        max-open-position, exposure, or invalid-notional guards.
        """

        check = self.precheck_fill(
            conn,
            paper_intent_id=paper_intent_id,
            fill_price=fill_price,
            quantity=quantity,
            write_block=False,
        )
        if check.allowed:
            return {
                "allowed": True,
                "clamped": False,
                "quantity": quantity,
                "notional": check.notional,
                "blockers": [],
            }

        clampable = {"POSITION_SIZE_LIMIT", "RISK_PER_TRADE_LIMIT"}
        blockers = set(check.blockers)
        non_clampable = sorted(blockers - clampable)
        if non_clampable or not blockers <= clampable:
            return {
                "allowed": False,
                "clamped": False,
                "quantity": quantity,
                "notional": check.notional,
                "blockers": check.blockers,
                "non_clampable_blockers": non_clampable,
            }

        account = _account_for_update(conn, self._account_id, lock=False)
        if not account:
            return {
                "allowed": False,
                "clamped": False,
                "quantity": quantity,
                "notional": check.notional,
                "blockers": ["PAPER_ACCOUNT_MISSING"],
            }

        price = _decimal(fill_price)
        if price <= 0:
            return {
                "allowed": False,
                "clamped": False,
                "quantity": quantity,
                "notional": check.notional,
                "blockers": ["INVALID_NOTIONAL"],
            }

        current_balance = _decimal(account["current_balance"])
        available = _decimal(account["available_balance"])
        max_position_size = _decimal(account["max_position_size"])
        max_risk_amount = current_balance * _decimal(account["risk_per_trade_pct"]) / Decimal("100")
        max_exposure = current_balance * _decimal(account["max_total_open_exposure_pct"]) / Decimal("100")
        open_exposure = _active_open_exposure(conn)
        exposure_remaining = max(Decimal("0"), max_exposure - open_exposure)
        allowed_notional = min(available, max_position_size, max_risk_amount, exposure_remaining)

        if allowed_notional < min_notional:
            return {
                "allowed": False,
                "clamped": False,
                "quantity": quantity,
                "notional": check.notional,
                "blockers": [*check.blockers, "SIZE_BELOW_MIN_AFTER_RISK_CLAMP"],
                "allowed_notional": allowed_notional,
                "min_notional": min_notional,
            }

        adjusted_quantity = (allowed_notional / price).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
        adjusted_notional = _notional(price, adjusted_quantity)
        if adjusted_quantity <= 0 or adjusted_notional < min_notional:
            return {
                "allowed": False,
                "clamped": False,
                "quantity": quantity,
                "notional": check.notional,
                "blockers": [*check.blockers, "SIZE_BELOW_MIN_AFTER_RISK_CLAMP"],
                "allowed_notional": allowed_notional,
                "min_notional": min_notional,
            }

        return {
            "allowed": True,
            "clamped": True,
            "quantity": adjusted_quantity,
            "notional": adjusted_notional,
            "requested_quantity": quantity,
            "requested_notional": check.notional,
            "allowed_notional": allowed_notional,
            "blockers": [],
            "original_blockers": check.blockers,
            "clamp_reason": "RISK_CAPITAL_SIZE_CLAMP",
        }

    def lock_on_fill(
        self,
        conn: Any,
        *,
        paper_intent_id: str,
        paper_order_id: str,
        paper_fill_id: str,
        paper_position_id: str,
        fill_price: Decimal,
        quantity: Decimal,
        reason: str = "CAPITAL_LOCKED_ON_FILL",
        skip_precheck: bool = False,
    ) -> dict[str, Any]:
        self._require_system_on()
        if not _tables_ready(conn):
            return {"status": "CAPITAL_TABLES_MISSING", "locked": False}
        if _ledger_exists(conn, "CAPITAL_LOCKED_ON_FILL", paper_fill_id=paper_fill_id):
            return {"status": "ALREADY_LOCKED", "locked": False}

        account = _account_for_update(conn, self._account_id, lock=True)
        if not account:
            raise RuntimeError("paper account missing")

        if skip_precheck:
            notional = _notional(fill_price, quantity)
            if notional <= 0:
                raise RuntimeError("capital guard blocked fill: INVALID_NOTIONAL")
            if _decimal(account["available_balance"]) < notional:
                raise RuntimeError("capital guard blocked fill: INSUFFICIENT_PAPER_BALANCE")
        else:
            check = self.precheck_fill(
                conn,
                paper_intent_id=paper_intent_id,
                fill_price=fill_price,
                quantity=quantity,
                write_block=True,
            )
            if not check.allowed:
                raise RuntimeError(f"capital guard blocked fill: {','.join(check.blockers)}")
            notional = check.notional
        after_available = _decimal(account["available_balance"]) - notional
        after_locked = _decimal(account["locked_balance"]) + notional
        after_exposure = _decimal(account["open_exposure"]) + notional
        unrealized = _active_unrealized_pnl(conn)
        conn.execute(
            """
            UPDATE paper_accounts
            SET available_balance = %s,
                locked_balance = %s,
                open_exposure = %s,
                unrealized_pnl = %s,
                updated_at = now()
            WHERE account_id = %s
            """,
            (after_available, after_locked, after_exposure, unrealized, self._account_id),
        )
        ledger_id = f"paper_capital_lock_{paper_fill_id}"
        self._insert_ledger(
            conn,
            account,
            ledger_id=ledger_id,
            event_type="CAPITAL_LOCKED_ON_FILL",
            source_type="PAPER_FILL",
            source_id=paper_fill_id,
            paper_intent_id=paper_intent_id,
            paper_order_id=paper_order_id,
            paper_fill_id=paper_fill_id,
            paper_position_id=paper_position_id,
            amount=notional,
            balance_after=_decimal(account["current_balance"]),
            available_after=after_available,
            locked_after=after_locked,
            realized_pnl_delta=Decimal("0"),
            unrealized_pnl_snapshot=unrealized,
            reason=reason,
            metadata={"paper_only": True, "quantity": str(quantity), "fill_price": str(fill_price)},
        )
        return {"status": "LOCKED", "locked": True, "amount": _float(notional)}

    def release_on_close(
        self,
        conn: Any,
        *,
        close: dict[str, Any],
        position: dict[str, Any],
        reason: str = "CAPITAL_RELEASED_ON_CLOSE",
        release_event_type: str = "CAPITAL_RELEASED_ON_CLOSE",
        realized_event_type: str = "REALIZED_PNL_APPLIED",
    ) -> dict[str, Any]:
        self._require_system_on()
        return self._release_on_close_in_conn(
            conn,
            close=close,
            position=position,
            reason=reason,
            release_event_type=release_event_type,
            realized_event_type=realized_event_type,
            metadata={"paper_only": True},
        )

    def _release_on_close_in_conn(
        self,
        conn: Any,
        *,
        close: dict[str, Any],
        position: dict[str, Any],
        reason: str,
        release_event_type: str,
        realized_event_type: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if not _tables_ready(conn):
            return {"status": "CAPITAL_TABLES_MISSING", "released": False}
        close_id = str(close["close_id"])

        release_exists = _ledger_exists_any(conn, CAPITAL_RELEASE_EVENTS, paper_close_id=close_id)
        realized_exists = _ledger_exists_any(conn, REALIZED_PNL_EVENTS, paper_close_id=close_id)
        if release_exists and realized_exists:
            return {"status": "ALREADY_RELEASED", "released": False, "realized_applied": False}

        lock_row = _latest_lock_row(conn, str(position["id"]))
        paper_fill_id = _payload_value(position, "paper_fill_id") or (str(lock_row["paper_fill_id"]) if lock_row and lock_row.get("paper_fill_id") else None)
        if not lock_row:
            return {"status": "NO_CAPITAL_LOCK_FOUND", "released": False}

        account = _account_for_update(conn, self._account_id, lock=True)
        if not account:
            raise RuntimeError("paper account missing")

        released = Decimal("0") if release_exists else _active_locked_notional(conn, str(position["id"]))
        if not release_exists and released <= 0:
            return {"status": "NO_ACTIVE_CAPITAL_LOCK_FOUND", "released": False}
        realized = _decimal(close.get("realized_pnl"))
        realized_delta = Decimal("0") if realized_exists else realized
        after_balance = _decimal(account["current_balance"]) + realized_delta
        after_available = _decimal(account["available_balance"]) + released + realized_delta
        after_locked = _decimal(account["locked_balance"]) - released
        after_exposure = _decimal(account["open_exposure"]) - released
        realized_total = _decimal(account["realized_pnl"]) + realized_delta
        daily = _daily_realized_pnl(conn)
        unrealized = _active_unrealized_pnl(conn)
        conn.execute(
            """
            UPDATE paper_accounts
            SET current_balance = %s,
                available_balance = %s,
                locked_balance = %s,
                open_exposure = %s,
                realized_pnl = %s,
                unrealized_pnl = %s,
                daily_pnl = %s,
                updated_at = now()
            WHERE account_id = %s
            """,
            (after_balance, after_available, after_locked, after_exposure, realized_total, unrealized, daily, self._account_id),
        )
        if not release_exists:
            self._insert_ledger(
                conn,
                account,
                ledger_id=f"paper_capital_release_{close_id}" if release_event_type == "CAPITAL_RELEASED_ON_CLOSE" else f"paper_capital_backfill_release_{close_id}",
                event_type=release_event_type,
                source_type="PAPER_CLOSE",
                source_id=close_id,
                paper_intent_id=_payload_value(position, "source_intent_id"),
                paper_order_id=_payload_value(position, "paper_order_id"),
                paper_fill_id=paper_fill_id,
                paper_position_id=str(position["id"]),
                paper_close_id=close_id,
                amount=released,
                balance_after=after_balance,
                available_after=after_available,
                locked_after=after_locked,
                realized_pnl_delta=Decimal("0"),
                unrealized_pnl_snapshot=unrealized,
                reason=reason,
                metadata={**metadata, "realized_pnl": str(realized)},
            )
        if not realized_exists:
            self._insert_ledger(
                conn,
                account,
                ledger_id=f"paper_capital_realized_{close_id}" if realized_event_type == "REALIZED_PNL_APPLIED" else f"paper_capital_backfill_realized_{close_id}",
                event_type=realized_event_type,
                source_type="PAPER_CLOSE",
                source_id=close_id,
                paper_intent_id=_payload_value(position, "source_intent_id"),
                paper_order_id=_payload_value(position, "paper_order_id"),
                paper_fill_id=paper_fill_id,
                paper_position_id=str(position["id"]),
                paper_close_id=close_id,
                amount=realized,
                balance_after=after_balance,
                available_after=after_available,
                locked_after=after_locked,
                realized_pnl_delta=realized_delta,
                unrealized_pnl_snapshot=unrealized,
                reason=realized_event_type,
                metadata=metadata,
            )
        return {
            "status": "RELEASED",
            "released": not release_exists,
            "realized_applied": not realized_exists,
            "amount": _float(released),
            "realized_pnl": _float(realized_delta),
        }

    def refresh_unrealized(self, conn: Any | None = None) -> dict[str, Any]:
        if conn is not None:
            return self._refresh_unrealized_in_conn(conn)
        with self._factory.connect() as own_conn, own_conn.transaction():
            return self._refresh_unrealized_in_conn(own_conn)

    def get_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return {"mock_data": False, "generated_at": generated_at, "status": "DATABASE_UNAVAILABLE"}
        with self._factory.connect() as conn:
            if not _tables_ready(conn):
                return {"mock_data": False, "generated_at": generated_at, "status": "CAPITAL_TABLES_MISSING"}
            account = _account_for_update(conn, self._account_id, lock=False)
            if not account:
                return {"mock_data": False, "generated_at": generated_at, "status": "PAPER_ACCOUNT_MISSING"}
            reconciliation = self.reconcile(conn=conn)
            latest_events = [
                _json_safe(dict(row))
                for row in conn.execute(
                    """
                    SELECT *
                    FROM paper_capital_ledger
                    WHERE account_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (self._account_id, limit),
                ).fetchall()
            ]
            active_guards = _active_guards(conn, self._account_id)
            quarantined = _count_where(conn, "paper_positions", "COALESCE(excluded_from_active_paper_truth,false)=true OR current_status='QUARANTINED'")
            active_open = _active_open_positions(conn)
            safety = _safety_counts(conn)
        return _json_safe(
            {
                "mock_data": False,
                "generated_at": generated_at,
                "account_id": account["account_id"],
                "currency": account["currency"],
                "initial_balance": _float(account["initial_balance"]),
                "current_balance": _float(account["current_balance"]),
                "available_balance": _float(account["available_balance"]),
                "locked_balance": _float(account["locked_balance"]),
                "open_exposure": _float(account["open_exposure"]),
                "realized_pnl": _float(account["realized_pnl"]),
                "unrealized_pnl": _float(account["unrealized_pnl"]),
                "daily_pnl": _float(account["daily_pnl"]),
                "risk_per_trade_pct": _float(account["risk_per_trade_pct"]),
                "max_position_size": _float(account["max_position_size"]),
                "max_daily_loss_pct": _float(account["max_daily_loss_pct"]),
                "max_open_positions": int(account["max_open_positions"]),
                "max_total_open_exposure_pct": _float(account["max_total_open_exposure_pct"]),
                "active_open_positions": active_open,
                "quarantined_positions_excluded": quarantined,
                "capital_status": "OK" if reconciliation["capital_reconciliation_status"] == "OK" else "RED",
                "active_guards": active_guards,
                "latest_ledger_events": latest_events,
                "reconciliation_status": reconciliation["capital_reconciliation_status"],
                "capital_reconciliation_status": reconciliation["capital_reconciliation_status"],
                "reconciliation_errors": reconciliation["reconciliation_errors"],
                "expected_locked_balance": reconciliation.get("expected_locked_balance"),
                "actual_locked_balance": reconciliation.get("actual_locked_balance"),
                "expected_open_exposure": reconciliation.get("expected_open_exposure"),
                "actual_open_exposure": reconciliation.get("actual_open_exposure"),
                "open_positions_without_lock": reconciliation.get("open_positions_without_lock", []),
                "locks_without_open_position": reconciliation.get("locks_without_open_position", []),
                "closed_positions_with_active_lock": reconciliation.get("closed_positions_with_active_lock", []),
                "closes_without_release": reconciliation.get("closes_without_release", []),
                "closes_without_realized_pnl_applied": reconciliation.get("closes_without_realized_pnl_applied", []),
                "duplicate_releases": reconciliation.get("duplicate_releases", []),
                "realized_pnl_double_apply_count": reconciliation.get("realized_pnl_double_apply_count", 0),
                "duplicate_realized_pnl_apply_count": reconciliation.get("realized_pnl_double_apply_count", 0),
                "warnings": reconciliation["reconciliation_errors"],
                "live_orders": safety["live_orders"],
                "orders_v2": safety["orders_v2"],
                "fills_v2": safety["fills_v2"],
                "canonical_positions": safety["canonical_positions"],
            }
        )

    def reconcile(self, *, conn: Any | None = None) -> dict[str, Any]:
        if conn is not None:
            return self._reconcile_in_conn(conn)
        with self._factory.connect() as own_conn:
            return self._reconcile_in_conn(own_conn)

    def backfill_missing_open_position_locks_from_real_fills(self, *, actor: str = "codex") -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "backfilled": 0, "positions": []}
        with self._factory.connect() as conn, conn.transaction():
            if not _tables_ready(conn):
                return {"status": "CAPITAL_TABLES_MISSING", "backfilled": 0, "positions": []}
            account = _account_for_update(conn, self._account_id, lock=True)
            if not account:
                return {"status": "PAPER_ACCOUNT_MISSING", "backfilled": 0, "positions": []}
            rows = _open_positions_without_active_lock(conn)
            repaired: list[dict[str, Any]] = []
            for row in rows:
                fill_id = _payload_value(row, "paper_fill_id")
                order_id = _payload_value(row, "paper_order_id")
                intent_id = _payload_value(row, "source_intent_id")
                fill = _fetch_fill(conn, fill_id)
                if not fill or str(fill.get("paper_order_id")) != str(order_id):
                    continue
                notional = _notional(row["avg_entry"], row["size"])
                if notional <= 0:
                    continue
                account = _account_for_update(conn, self._account_id, lock=True)
                after_available = _decimal(account["available_balance"]) - notional
                after_locked = _decimal(account["locked_balance"]) + notional
                after_exposure = _decimal(account["open_exposure"]) + notional
                if after_available < 0:
                    continue
                unrealized = _active_unrealized_pnl(conn)
                conn.execute(
                    """
                    UPDATE paper_accounts
                    SET available_balance = %s,
                        locked_balance = %s,
                        open_exposure = %s,
                        unrealized_pnl = %s,
                        updated_at = now()
                    WHERE account_id = %s
                    """,
                    (after_available, after_locked, after_exposure, unrealized, self._account_id),
                )
                self._insert_ledger(
                    conn,
                    account,
                    ledger_id=f"paper_capital_backfill_lock_{row['id']}",
                    event_type="CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL",
                    source_type="PAPER_FILL",
                    source_id=fill_id,
                    paper_intent_id=intent_id,
                    paper_order_id=order_id,
                    paper_fill_id=fill_id,
                    paper_position_id=str(row["id"]),
                    amount=notional,
                    balance_after=_decimal(account["current_balance"]),
                    available_after=after_available,
                    locked_after=after_locked,
                    realized_pnl_delta=Decimal("0"),
                    unrealized_pnl_snapshot=unrealized,
                    reason="CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL",
                    metadata={
                        "paper_only": True,
                        "repair": True,
                        "actor": actor,
                        "source": "real_open_position_and_real_fill",
                        "quantity": str(row["size"]),
                        "fill_price": str(row["avg_entry"]),
                    },
                )
                repaired.append({"paper_position_id": str(row["id"]), "paper_fill_id": fill_id, "amount": _float(notional)})
            reconciliation = self._reconcile_in_conn(conn)
            return {"status": "OK", "backfilled": len(repaired), "positions": repaired, "reconciliation": reconciliation}

    def backfill_missing_close_releases_from_real_closes(self, *, actor: str = "codex") -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "backfilled": 0, "positions": []}
        with self._factory.connect() as conn, conn.transaction():
            if not _tables_ready(conn):
                return {"status": "CAPITAL_TABLES_MISSING", "backfilled": 0, "positions": []}
            repaired: list[dict[str, Any]] = []
            for row in _closed_positions_with_active_lock(conn):
                position = _fetch_position(conn, str(row["paper_position_id"]))
                close = _fetch_close(conn, str(row["paper_position_id"]))
                if not position or not close:
                    continue
                fill_id = _payload_value(position, "paper_fill_id")
                fill = _fetch_fill(conn, fill_id)
                if not fill:
                    continue
                close_id = str(close["close_id"])
                result = self._release_on_close_in_conn(
                    conn,
                    close=close,
                    position=position,
                    reason="CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE",
                    release_event_type="CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE",
                    realized_event_type="REALIZED_PNL_BACKFILLED_FROM_REAL_CLOSE",
                    metadata={
                        "paper_only": True,
                        "repair": True,
                        "actor": actor,
                        "source": "real_close_position_fill_and_lock",
                        "paper_position_id": str(position["id"]),
                        "paper_close_id": close_id,
                        "paper_fill_id": fill_id,
                    },
                )
                if result.get("status") == "RELEASED":
                    repaired.append(
                        {
                            "paper_position_id": str(position["id"]),
                            "paper_close_id": close_id,
                            "paper_fill_id": fill_id,
                            "released": result.get("amount"),
                            "realized_pnl_applied": result.get("realized_pnl"),
                        }
                    )
            reconciliation = self._reconcile_in_conn(conn)
            return {"status": "OK", "backfilled": len(repaired), "positions": repaired, "reconciliation": reconciliation}

    def _refresh_unrealized_in_conn(self, conn: Any) -> dict[str, Any]:
        self._require_system_on()
        if not _tables_ready(conn):
            return {"status": "CAPITAL_TABLES_MISSING"}
        account = _account_for_update(conn, self._account_id, lock=True)
        unrealized = _active_unrealized_pnl(conn)
        daily = _daily_realized_pnl(conn)
        conn.execute(
            "UPDATE paper_accounts SET unrealized_pnl=%s, daily_pnl=%s, updated_at=now() WHERE account_id=%s",
            (unrealized, daily, self._account_id),
        )
        self._insert_ledger(
            conn,
            account,
            ledger_id=f"paper_capital_unrealized_mark_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}",
            event_type="UNREALIZED_PNL_MARK",
            source_type="PAPER_POSITIONS",
            source_id="active_open_positions",
            amount=unrealized,
            balance_after=_decimal(account["current_balance"]),
            available_after=_decimal(account["available_balance"]),
            locked_after=_decimal(account["locked_balance"]),
            realized_pnl_delta=Decimal("0"),
            unrealized_pnl_snapshot=unrealized,
            reason="UNREALIZED_PNL_MARK",
            metadata={"paper_only": True},
        )
        return {"status": "OK", "unrealized_pnl": _float(unrealized), "daily_pnl": _float(daily)}

    def _reconcile_in_conn(self, conn: Any) -> dict[str, Any]:
        if not _tables_ready(conn):
            return {"capital_reconciliation_status": "RED", "reconciliation_errors": ["CAPITAL_TABLES_MISSING"]}
        account = _account_for_update(conn, self._account_id, lock=False)
        if not account:
            return {"capital_reconciliation_status": "RED", "reconciliation_errors": ["PAPER_ACCOUNT_MISSING"]}
        errors: list[str] = []
        applied = _realized_applied(conn, self._account_id)
        expected_current = _decimal(account["initial_balance"]) + applied
        if abs(_decimal(account["current_balance"]) - expected_current) > Decimal("0.000001"):
            errors.append("CURRENT_BALANCE_MISMATCH")
        if abs((_decimal(account["available_balance"]) + _decimal(account["locked_balance"])) - _decimal(account["current_balance"])) > Decimal("0.000001"):
            errors.append("AVAILABLE_LOCKED_BALANCE_MISMATCH")
        active_notional = _active_open_exposure(conn)
        diagnostics = _capital_diagnostics(conn, self._account_id)
        if abs(_decimal(account["open_exposure"]) - active_notional) > Decimal("0.000001"):
            errors.append("OPEN_EXPOSURE_MISMATCH")
        if abs(_decimal(account["locked_balance"]) - diagnostics["expected_locked_balance"]) > Decimal("0.000001"):
            errors.append("LOCKED_BALANCE_MISMATCH")
        if diagnostics["open_positions_without_lock"]:
            errors.append("OPEN_POSITION_WITHOUT_ACTIVE_LOCK")
        if diagnostics["locks_without_open_position"]:
            errors.append("LOCK_WITHOUT_OPEN_POSITION")
        if diagnostics["closes_without_release"]:
            errors.append("CLOSE_WITHOUT_CAPITAL_RELEASE")
        if diagnostics["closes_without_realized_pnl_applied"]:
            errors.append("CLOSE_WITHOUT_REALIZED_PNL_APPLIED")
        if diagnostics["duplicate_releases"]:
            errors.append("DUPLICATE_CAPITAL_RELEASE")
        if diagnostics["realized_pnl_double_apply_count"]:
            errors.append("REALIZED_PNL_DOUBLE_APPLIED")
        if _decimal(account["locked_balance"]) < 0 or _decimal(account["available_balance"]) < 0 or _decimal(account["current_balance"]) < 0:
            errors.append("NEGATIVE_BALANCE")
        return {
            "capital_reconciliation_status": "RED" if errors else "OK",
            "reconciliation_errors": errors,
            "expected_current_balance": _float(expected_current),
            "active_open_exposure": _float(active_notional),
            "expected_locked_balance": _float(diagnostics["expected_locked_balance"]),
            "actual_locked_balance": _float(account["locked_balance"]),
            "expected_open_exposure": _float(active_notional),
            "actual_open_exposure": _float(account["open_exposure"]),
            "open_positions_without_lock": diagnostics["open_positions_without_lock"],
            "locks_without_open_position": diagnostics["locks_without_open_position"],
            "closed_positions_with_active_lock": diagnostics["closed_positions_with_active_lock"],
            "closes_without_release": diagnostics["closes_without_release"],
            "closes_without_realized_pnl_applied": diagnostics["closes_without_realized_pnl_applied"],
            "duplicate_releases": diagnostics["duplicate_releases"],
            "realized_pnl_double_apply_count": diagnostics["realized_pnl_double_apply_count"],
            "duplicate_realized_pnl_apply_count": diagnostics["realized_pnl_double_apply_count"],
        }

    def _insert_guard_event(self, conn: Any, account: dict[str, Any], blocker: str, paper_intent_id: str | None, notional: Decimal) -> None:
        event_type = {
            "INSUFFICIENT_PAPER_BALANCE": "INSUFFICIENT_BALANCE_BLOCK",
            "POSITION_SIZE_LIMIT": "RISK_LIMIT_BLOCK",
            "RISK_PER_TRADE_LIMIT": "RISK_LIMIT_BLOCK",
            "DAILY_LOSS_LIMIT": "DAILY_LOSS_GUARD_TRIGGERED",
            "MAX_OPEN_POSITIONS": "MAX_OPEN_POSITIONS_BLOCK",
            "MAX_EXPOSURE_LIMIT": "MAX_EXPOSURE_BLOCK",
        }.get(blocker, "RISK_LIMIT_BLOCK")
        ledger_id = f"paper_capital_guard_{event_type.lower()}_{paper_intent_id or 'unknown'}"
        self._insert_ledger(
            conn,
            account,
            ledger_id=ledger_id,
            event_type=event_type,
            source_type="PAPER_INTENT",
            source_id=paper_intent_id,
            paper_intent_id=paper_intent_id,
            amount=notional,
            balance_after=_decimal(account["current_balance"]),
            available_after=_decimal(account["available_balance"]),
            locked_after=_decimal(account["locked_balance"]),
            realized_pnl_delta=Decimal("0"),
            unrealized_pnl_snapshot=_decimal(account["unrealized_pnl"]),
            reason=blocker,
            metadata={"paper_only": True},
        )

    def _insert_ledger(
        self,
        conn: Any,
        account: dict[str, Any],
        *,
        ledger_id: str,
        event_type: str,
        source_type: str,
        source_id: str | None = None,
        paper_intent_id: str | None = None,
        paper_order_id: str | None = None,
        paper_fill_id: str | None = None,
        paper_position_id: str | None = None,
        paper_close_id: str | None = None,
        amount: Decimal,
        balance_after: Decimal,
        available_after: Decimal,
        locked_after: Decimal,
        realized_pnl_delta: Decimal,
        unrealized_pnl_snapshot: Decimal | None,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        paper_session_id = active_paper_session_id(conn) or "NO_ACTIVE_PAPER_SESSION"
        conn.execute(
            """
            INSERT INTO paper_capital_ledger (
                ledger_id, account_id, event_type, source_type, source_id,
                paper_intent_id, paper_order_id, paper_fill_id, paper_position_id,
                paper_close_id, amount, balance_before, balance_after,
                available_before, available_after, locked_before, locked_after,
                realized_pnl_delta, unrealized_pnl_snapshot, reason, metadata_json,
                paper_session_id, created_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s,
                now()
            )
            ON CONFLICT (ledger_id) DO NOTHING
            """,
            (
                ledger_id,
                self._account_id,
                event_type,
                source_type,
                source_id,
                paper_intent_id,
                paper_order_id,
                paper_fill_id,
                paper_position_id,
                paper_close_id,
                amount,
                _decimal(account["current_balance"]),
                balance_after,
                _decimal(account["available_balance"]),
                available_after,
                _decimal(account["locked_balance"]),
                locked_after,
                realized_pnl_delta,
                unrealized_pnl_snapshot,
                reason,
                Jsonb(_json_safe(metadata)),
                paper_session_id,
            ),
        )

    def _require_system_on(self) -> None:
        power = self._system_power.get_power_state()
        if str(power.get("power") or "OFF").upper() != "ON" or not bool(power.get("runtime_work_allowed")):
            raise RuntimeError("SYSTEM_POWER_OFF")


def _tables_ready(conn: Any) -> bool:
    return _table_exists(conn, "paper_accounts") and _table_exists(conn, "paper_capital_ledger")


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return bool(row)


def _account_for_update(conn: Any, account_id: str, *, lock: bool) -> dict[str, Any] | None:
    suffix = " FOR UPDATE" if lock else ""
    row = conn.execute(f"SELECT * FROM paper_accounts WHERE account_id = %s{suffix}", (account_id,)).fetchone()
    return dict(row) if row else None


def _ledger_exists(conn: Any, event_type: str, *, paper_fill_id: str | None = None, paper_close_id: str | None = None) -> bool:
    if paper_fill_id is not None:
        row = conn.execute(
            "SELECT 1 FROM paper_capital_ledger WHERE event_type=%s AND paper_fill_id=%s LIMIT 1",
            (event_type, paper_fill_id),
        ).fetchone()
        return bool(row)
    if paper_close_id is not None:
        row = conn.execute(
            "SELECT 1 FROM paper_capital_ledger WHERE event_type=%s AND paper_close_id=%s LIMIT 1",
            (event_type, paper_close_id),
        ).fetchone()
        return bool(row)
    return False


def _ledger_exists_any(conn: Any, event_types: tuple[str, ...], *, paper_close_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM paper_capital_ledger WHERE event_type = ANY(%s) AND paper_close_id = %s LIMIT 1",
        (list(event_types), paper_close_id),
    ).fetchone()
    return bool(row)


def _latest_lock_row(conn: Any, paper_position_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM paper_capital_ledger
        WHERE paper_position_id = %s
          AND event_type = ANY(%s)
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (paper_position_id, list(CAPITAL_LOCK_EVENTS)),
    ).fetchone()
    return dict(row) if row else None


def _active_locked_notional(conn: Any, paper_position_id: str) -> Decimal:
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(amount) FILTER (WHERE event_type = ANY(%s)), 0) AS locked,
            COALESCE(SUM(amount) FILTER (WHERE event_type = ANY(%s)), 0) AS released
        FROM paper_capital_ledger
        WHERE paper_position_id = %s
        """,
        (list(CAPITAL_LOCK_EVENTS), list(CAPITAL_RELEASE_EVENTS), paper_position_id),
    ).fetchone()
    return _decimal(row["locked"]) - _decimal(row["released"])


def _open_positions_without_active_lock(conn: Any) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_positions"):
        return []
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT pp.*
            FROM paper_positions pp
            WHERE pp.closed_at IS NULL
              AND pp.current_status IN ('OPEN', 'EXIT_PENDING')
              AND COALESCE(pp.excluded_from_active_paper_truth, false) = false
              AND COALESCE(pp.avg_entry, 0) > 0
              AND COALESCE(pp.size, 0) > 0
              AND (
                  SELECT
                      COALESCE(SUM(pcl.amount) FILTER (WHERE pcl.event_type = ANY(%s)), 0)
                      - COALESCE(SUM(pcl.amount) FILTER (WHERE pcl.event_type = ANY(%s)), 0)
                  FROM paper_capital_ledger pcl
                  WHERE pcl.paper_position_id = pp.id::text
              ) <= 0
            ORDER BY pp.opened_at ASC, pp.id ASC
            """,
            (list(CAPITAL_LOCK_EVENTS), list(CAPITAL_RELEASE_EVENTS)),
        ).fetchall()
    ]


def _fetch_fill(conn: Any, paper_fill_id: str | None) -> dict[str, Any] | None:
    if not paper_fill_id or not _table_exists(conn, "paper_fills"):
        return None
    row = conn.execute("SELECT * FROM paper_fills WHERE paper_fill_id = %s", (paper_fill_id,)).fetchone()
    return dict(row) if row else None


def _fetch_position(conn: Any, paper_position_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_positions"):
        return None
    row = conn.execute("SELECT * FROM paper_positions WHERE id::text = %s", (paper_position_id,)).fetchone()
    return dict(row) if row else None


def _fetch_close(conn: Any, paper_position_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_position_closes"):
        return None
    row = conn.execute("SELECT * FROM paper_position_closes WHERE position_id::text = %s ORDER BY created_at DESC, id DESC LIMIT 1", (paper_position_id,)).fetchone()
    return dict(row) if row else None


def _closed_positions_with_active_lock(conn: Any, account_id: str = DEFAULT_ACCOUNT_ID) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_positions") or not _table_exists(conn, "paper_capital_ledger"):
        return []
    return [
        dict(row)
        for row in conn.execute(
            """
            WITH capital AS (
                SELECT
                    paper_position_id,
                    COALESCE(SUM(amount) FILTER (WHERE event_type = ANY(%s)), 0) AS locked,
                    COALESCE(SUM(amount) FILTER (WHERE event_type = ANY(%s)), 0) AS released
                FROM paper_capital_ledger
                WHERE account_id = %s
                  AND paper_position_id IS NOT NULL
                GROUP BY paper_position_id
            )
            SELECT pp.id::text AS paper_position_id,
                   pp.market_id,
                   pp.intended_outcome AS side,
                   COALESCE(c.locked, 0) - COALESCE(c.released, 0) AS active_lock
            FROM paper_positions pp
            JOIN capital c ON c.paper_position_id = pp.id::text
            WHERE c.locked - c.released > 0
              AND (
                  pp.closed_at IS NOT NULL
                  OR pp.current_status NOT IN ('OPEN', 'EXIT_PENDING')
                  OR COALESCE(pp.excluded_from_active_paper_truth, false) = true
              )
            ORDER BY pp.closed_at DESC NULLS LAST, pp.id ASC
            """,
            (list(CAPITAL_LOCK_EVENTS), list(CAPITAL_RELEASE_EVENTS), account_id),
        ).fetchall()
    ]


def _capital_diagnostics(conn: Any, account_id: str) -> dict[str, Any]:
    open_rows = conn.execute(
        """
        WITH capital AS (
            SELECT
                paper_position_id,
                COALESCE(SUM(amount) FILTER (WHERE event_type = ANY(%s)), 0) AS locked,
                COALESCE(SUM(amount) FILTER (WHERE event_type = ANY(%s)), 0) AS released
            FROM paper_capital_ledger
            WHERE account_id = %s
              AND paper_position_id IS NOT NULL
            GROUP BY paper_position_id
        )
        SELECT pp.id::text AS paper_position_id,
               pp.market_id,
               pp.intended_outcome AS side,
               pp.avg_entry * pp.size AS expected_notional,
               COALESCE(c.locked, 0) - COALESCE(c.released, 0) AS active_lock
        FROM paper_positions pp
        LEFT JOIN capital c ON c.paper_position_id = pp.id::text
        WHERE pp.closed_at IS NULL
          AND pp.current_status IN ('OPEN', 'EXIT_PENDING')
          AND COALESCE(pp.excluded_from_active_paper_truth, false) = false
        ORDER BY pp.opened_at ASC, pp.id ASC
        """,
        (list(CAPITAL_LOCK_EVENTS), list(CAPITAL_RELEASE_EVENTS), account_id),
    ).fetchall()
    expected_locked = sum((_decimal(row["active_lock"]) for row in open_rows), Decimal("0"))
    open_without_lock = [
        {
            "paper_position_id": str(row["paper_position_id"]),
            "market_id": row["market_id"],
            "side": row["side"],
            "expected_notional": _float(row["expected_notional"]),
            "active_lock": _float(row["active_lock"]),
        }
        for row in open_rows
        if _decimal(row["active_lock"]) <= 0
    ]
    locks_without_open = [
        {
            "paper_position_id": str(row["paper_position_id"]),
            "active_lock": _float(row["active_lock"]),
        }
        for row in conn.execute(
            """
            WITH capital AS (
                SELECT
                    paper_position_id,
                    COALESCE(SUM(amount) FILTER (WHERE event_type = ANY(%s)), 0) AS locked,
                    COALESCE(SUM(amount) FILTER (WHERE event_type = ANY(%s)), 0) AS released
                FROM paper_capital_ledger
                WHERE account_id = %s
                  AND paper_position_id IS NOT NULL
                GROUP BY paper_position_id
            )
            SELECT c.paper_position_id, c.locked - c.released AS active_lock
            FROM capital c
            LEFT JOIN paper_positions pp ON pp.id::text = c.paper_position_id
            WHERE c.locked - c.released > 0
              AND (
                  pp.id IS NULL
                  OR pp.closed_at IS NOT NULL
                  OR pp.current_status NOT IN ('OPEN', 'EXIT_PENDING')
                  OR COALESCE(pp.excluded_from_active_paper_truth, false) = true
              )
            ORDER BY c.paper_position_id
            """,
            (list(CAPITAL_LOCK_EVENTS), list(CAPITAL_RELEASE_EVENTS), account_id),
        ).fetchall()
    ]
    duplicate_releases = [
        {"paper_position_id": str(row["paper_position_id"]), "release_count": int(row["release_count"])}
        for row in conn.execute(
            """
            SELECT paper_position_id, COUNT(*) AS release_count
            FROM paper_capital_ledger
            WHERE account_id = %s
              AND event_type = ANY(%s)
              AND paper_position_id IS NOT NULL
            GROUP BY paper_position_id
            HAVING COUNT(*) > 1
            ORDER BY paper_position_id
            """,
            (account_id, list(CAPITAL_RELEASE_EVENTS)),
        ).fetchall()
    ]
    realized_double = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT paper_close_id
            FROM paper_capital_ledger
            WHERE account_id = %s
              AND event_type = ANY(%s)
              AND paper_close_id IS NOT NULL
            GROUP BY paper_close_id
            HAVING COUNT(*) > 1
        ) duplicates
        """,
        (account_id, list(REALIZED_PNL_EVENTS)),
    ).fetchone()
    closes_without_release = [
        {"paper_position_id": str(row["position_id"]), "paper_close_id": str(row["close_id"])}
        for row in conn.execute(
            """
            SELECT ppc.position_id, ppc.close_id
            FROM paper_position_closes ppc
            WHERE EXISTS (
                SELECT 1 FROM paper_capital_ledger lock_pcl
                WHERE lock_pcl.account_id = %s
                  AND lock_pcl.paper_position_id = ppc.position_id::text
                  AND lock_pcl.event_type = ANY(%s)
            )
              AND NOT EXISTS (
                SELECT 1 FROM paper_capital_ledger pcl
                WHERE pcl.account_id = %s
                  AND pcl.paper_close_id = ppc.close_id
                  AND pcl.event_type = ANY(%s)
            )
            ORDER BY ppc.created_at DESC, ppc.id DESC
            """,
            (account_id, list(CAPITAL_LOCK_EVENTS), account_id, list(CAPITAL_RELEASE_EVENTS)),
        ).fetchall()
    ]
    closes_without_realized = [
        {"paper_position_id": str(row["position_id"]), "paper_close_id": str(row["close_id"])}
        for row in conn.execute(
            """
            SELECT ppc.position_id, ppc.close_id
            FROM paper_position_closes ppc
            WHERE EXISTS (
                SELECT 1 FROM paper_capital_ledger lock_pcl
                WHERE lock_pcl.account_id = %s
                  AND lock_pcl.paper_position_id = ppc.position_id::text
                  AND lock_pcl.event_type = ANY(%s)
            )
              AND NOT EXISTS (
                SELECT 1 FROM paper_capital_ledger pcl
                WHERE pcl.account_id = %s
                  AND pcl.paper_close_id = ppc.close_id
                  AND pcl.event_type = ANY(%s)
            )
            ORDER BY ppc.created_at DESC, ppc.id DESC
            """,
            (account_id, list(CAPITAL_LOCK_EVENTS), account_id, list(REALIZED_PNL_EVENTS)),
        ).fetchall()
    ]
    return {
        "expected_locked_balance": max(Decimal("0"), expected_locked),
        "open_positions_without_lock": open_without_lock,
        "locks_without_open_position": locks_without_open,
        "closed_positions_with_active_lock": _closed_positions_with_active_lock(conn, account_id),
        "closes_without_release": closes_without_release,
        "closes_without_realized_pnl_applied": closes_without_realized,
        "duplicate_releases": duplicate_releases,
        "realized_pnl_double_apply_count": int(realized_double["count"] or 0),
    }


def _notional(fill_price: Decimal, quantity: Decimal) -> Decimal:
    return _decimal(fill_price) * _decimal(quantity)


def _daily_realized_pnl(conn: Any) -> Decimal:
    if not _table_exists(conn, "paper_position_closes"):
        return Decimal("0")
    session_id = active_paper_session_id(conn)
    if session_id and _column_exists(conn, "paper_position_closes", "paper_session_id"):
        row = conn.execute(
            """
            SELECT COALESCE(SUM(realized_pnl), 0) AS value
            FROM paper_position_closes
            WHERE created_at::date = %s
              AND paper_session_id = %s
            """,
            (date.today(), session_id),
        ).fetchone()
        return _decimal(row["value"])
    row = conn.execute(
        "SELECT COALESCE(SUM(realized_pnl), 0) AS value FROM paper_position_closes WHERE created_at::date = %s",
        (date.today(),),
    ).fetchone()
    return _decimal(row["value"])


def _realized_applied(conn: Any, account_id: str) -> Decimal:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(realized_pnl_delta), 0) AS value
        FROM paper_capital_ledger
        WHERE account_id = %s AND event_type = ANY(%s)
        """,
        (account_id, list(REALIZED_PNL_EVENTS)),
    ).fetchone()
    return _decimal(row["value"])


def _active_open_positions(conn: Any) -> int:
    return _count_where(
        conn,
        "paper_positions",
        "closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING') AND COALESCE(excluded_from_active_paper_truth,false)=false",
    )


def _active_open_exposure(conn: Any) -> Decimal:
    if not _table_exists(conn, "paper_positions"):
        return Decimal("0")
    row = conn.execute(
        """
        SELECT COALESCE(SUM(COALESCE(avg_entry, 0) * COALESCE(size, 0)), 0) AS value
        FROM paper_positions
        WHERE closed_at IS NULL
          AND current_status IN ('OPEN', 'EXIT_PENDING')
          AND COALESCE(excluded_from_active_paper_truth, false) = false
        """
    ).fetchone()
    return _decimal(row["value"])


def _active_unrealized_pnl(conn: Any) -> Decimal:
    if not _table_exists(conn, "paper_positions"):
        return Decimal("0")
    row = conn.execute(
        """
        SELECT COALESCE(SUM(COALESCE(unrealized, 0)), 0) AS value
        FROM paper_positions
        WHERE closed_at IS NULL
          AND current_status IN ('OPEN', 'EXIT_PENDING')
          AND COALESCE(excluded_from_active_paper_truth, false) = false
        """
    ).fetchone()
    return _decimal(row["value"])


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def _payload_value(row: dict[str, Any], key: str) -> str | None:
    payload = row.get("payload_json")
    if isinstance(payload, dict) and payload.get(key) not in (None, ""):
        return str(payload[key])
    return None


def _active_guards(conn: Any, account_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT reason
        FROM paper_capital_ledger
        WHERE account_id = %s
          AND event_type IN (
              'DAILY_LOSS_GUARD_TRIGGERED',
              'RISK_LIMIT_BLOCK',
              'INSUFFICIENT_BALANCE_BLOCK',
              'MAX_OPEN_POSITIONS_BLOCK',
              'MAX_EXPOSURE_BLOCK'
          )
          AND created_at >= now() - interval '24 hours'
        ORDER BY reason ASC
        """,
        (account_id,),
    ).fetchall()
    return [str(row["reason"]) for row in rows]


def _safety_counts(conn: Any) -> dict[str, int]:
    return {
        "live_orders": _count_where(conn, "live_orders", "TRUE"),
        "orders_v2": _count_where(conn, "orders_v2", "TRUE"),
        "fills_v2": _count_where(conn, "fills_v2", "TRUE"),
        "canonical_positions": _count_where(conn, "positions", "TRUE"),
    }


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _float(value: Any) -> float:
    return float(_decimal(value))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.capital_brain.repository import CapitalBrainRepository, table_exists
from app.capital_brain.types import CapitalDecision
from app.db.connection import DatabaseConnectionFactory
from app.services.capital_efficiency import CapitalEfficiencyService
from app.services.exit_hold_reasoning import ExitHoldReasoningService
from app.services.payout_odds import PayoutOddsService
from app.services.trade_lifecycle import TradeLifecycleService
from app.services.system_power import SystemPowerService


class CapitalBrainBlocked(RuntimeError):
    pass


class CapitalBrainService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: CapitalBrainRepository | None = None,
        system_power: SystemPowerService | None = None,
        account_id: str = "paper_default",
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or CapitalBrainRepository()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._account_id = account_id

    def evaluate_session(self, session_id: str) -> dict[str, Any]:
        self._assert_system_on()
        with self._factory.connect() as conn, conn.transaction():
            return self.evaluate_session_with_conn(conn, session_id)

    def evaluate_active_sessions(self, *, limit: int = 100) -> dict[str, Any]:
        self._assert_system_on()
        evaluated = 0
        with self._factory.connect() as conn, conn.transaction():
            if not self._tables_ready(conn):
                return {"mock_data": False, "status": "MISSING_TABLES", "sessions_evaluated": 0}
            rows = conn.execute(
                """
                SELECT session_id
                FROM mesh_shared_awareness
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            for row in rows:
                result = self.evaluate_session_with_conn(conn, str(row["session_id"]))
                evaluated += int(result.get("status") == "OK")
        return {"mock_data": False, "status": "OK", "sessions_evaluated": evaluated}

    def evaluate_session_with_conn(self, conn: Any, session_id: str) -> dict[str, Any]:
        if not self._tables_ready(conn):
            return {"mock_data": False, "status": "MISSING_TABLES", "session_id": session_id}
        session = self._repository.get_session(conn, session_id)
        awareness = self._repository.get_awareness(conn, session_id)
        if not session or not awareness:
            return {"mock_data": False, "status": "AWARENESS_NOT_FOUND", "session_id": session_id}
        account = self._repository.get_account(conn, self._account_id)
        ledger = self._repository.latest_ledger(conn, self._account_id) if account else None
        events = self._repository.linked_events(conn, session_id)
        active_open = self._repository.active_open_positions(conn)
        position = self._repository.position(conn, session.get("position_id"))
        evaluation, sources = self._build_evaluation(
            session=session,
            awareness=awareness,
            account=account,
            ledger=ledger,
            events=events,
            active_open=active_open,
            position=position,
        )
        row = self._repository.upsert_evaluation(conn, evaluation, sources)
        return {
            "mock_data": False,
            "status": "OK",
            "session_id": session_id,
            "evaluation_id": row["evaluation_id"],
            "decision": row["decision"],
            "confidence": row["confidence"],
        }

    def dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard("DB_UNAVAILABLE")
        with self._factory.connect() as conn:
            if not table_exists(conn, "capital_brain_evaluations"):
                return _empty_dashboard("MISSING_TABLES")
            latest = self._repository.dashboard_rows(conn, limit=limit)
            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(AVG(capital_efficiency_score), 0) AS avg_efficiency,
                    COUNT(*) FILTER (WHERE decision = 'CAPITAL_SUPPORT') AS support_count,
                    COUNT(*) FILTER (WHERE decision = 'CAPITAL_WATCH') AS watch_count,
                    COUNT(*) FILTER (WHERE decision = 'CAPITAL_BLOCK') AS block_count,
                    COUNT(*) FILTER (WHERE decision = 'CAPITAL_RELEASE_REVIEW') AS release_count,
                    COUNT(*) FILTER (WHERE decision = 'CAPITAL_INSUFFICIENT_DATA') AS insufficient_count
                FROM capital_brain_evaluations
                """
            ).fetchone()
            by_decision = conn.execute(
                """
                SELECT decision, COUNT(*) AS count
                FROM capital_brain_evaluations
                GROUP BY decision
                ORDER BY count DESC, decision
                """
            ).fetchall()
            account = self._repository.get_account(conn, self._account_id)
            payout_odds = PayoutOddsService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
            exit_hold = ExitHoldReasoningService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
            capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
            trade_lifecycle = TradeLifecycleService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
            constraints = []
            if latest:
                constraints = [
                    {"evaluation_id": row["evaluation_id"], "session_id": row["session_id"], "decision": row["decision"], "risk_flags": row.get("risk_flags_json") or []}
                    for row in latest
                    if row.get("decision") in {CapitalDecision.BLOCK.value, CapitalDecision.WATCH.value, CapitalDecision.RELEASE_REVIEW.value}
                ]
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": datetime.now(UTC).isoformat(),
                "total_evaluations": int(totals["total"] or 0),
                "decisions_by_type": {str(row["decision"]): int(row["count"] or 0) for row in by_decision},
                "capital_support_count": int(totals["support_count"] or 0),
                "capital_watch_count": int(totals["watch_count"] or 0),
                "capital_block_count": int(totals["block_count"] or 0),
                "release_review_count": int(totals["release_count"] or 0),
                "insufficient_data_count": int(totals["insufficient_count"] or 0),
                "avg_capital_efficiency_score": round(float(totals["avg_efficiency"] or 0), 4),
                "available_balance": _float(account.get("available_balance")) if account else None,
                "locked_balance": _float(account.get("locked_balance")) if account else None,
                "open_exposure": _float(account.get("open_exposure")) if account else None,
                "latest_evaluations": [_json_safe(row) for row in latest],
                "active_constraints": _json_safe(constraints),
                "payout_odds_visibility": payout_odds,
                "payout_odds_observational_only": True,
                "exit_hold_visibility": exit_hold,
                "exit_hold_observational_only": True,
                "capital_efficiency_visibility": capital_efficiency,
                "capital_efficiency_observational_only": True,
                "trade_lifecycle_visibility": trade_lifecycle,
                "trade_lifecycle_observational_only": True,
            }
        )

    def detail(self, evaluation_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DB_UNAVAILABLE", "evaluation_id": evaluation_id}
        with self._factory.connect() as conn:
            if not table_exists(conn, "capital_brain_evaluations"):
                return {"mock_data": False, "status": "MISSING_TABLES", "evaluation_id": evaluation_id}
            payload = self._repository.detail_by_evaluation(conn, evaluation_id)
            payout_odds = None
            if payload:
                ev = payload.get("evaluation") if isinstance(payload.get("evaluation"), dict) else payload
                payout_odds = PayoutOddsService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(ev.get("market_id")) if ev.get("market_id") else None,
                    position_id=str(ev.get("position_id")) if ev.get("position_id") else None,
                )
                exit_hold = ExitHoldReasoningService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(ev.get("market_id")) if ev.get("market_id") else None,
                    position_id=str(ev.get("position_id")) if ev.get("position_id") else None,
                )
                capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(ev.get("market_id")) if ev.get("market_id") else None,
                    position_id=str(ev.get("position_id")) if ev.get("position_id") else None,
                )
                trade_lifecycle = TradeLifecycleService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(ev.get("market_id")) if ev.get("market_id") else None,
                    position_id=str(ev.get("position_id")) if ev.get("position_id") else None,
                    candidate_id=str(ev.get("candidate_id")) if ev.get("candidate_id") else None,
                )
            else:
                exit_hold = None
                capital_efficiency = None
                trade_lifecycle = None
        if payload is None:
            return {"mock_data": False, "status": "NOT_FOUND", "evaluation_id": evaluation_id}
        payload["payout_odds_visibility"] = payout_odds
        payload["payout_odds_observational_only"] = True
        payload["exit_hold_visibility"] = exit_hold
        payload["exit_hold_observational_only"] = True
        payload["capital_efficiency_visibility"] = capital_efficiency
        payload["capital_efficiency_observational_only"] = True
        payload["trade_lifecycle_visibility"] = trade_lifecycle
        payload["trade_lifecycle_observational_only"] = True
        payload.update({"mock_data": False, "status": "OK", "generated_at": datetime.now(UTC).isoformat()})
        return _json_safe(payload)

    def latest_for_session(self, session_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DB_UNAVAILABLE", "session_id": session_id}
        with self._factory.connect() as conn:
            if not table_exists(conn, "capital_brain_evaluations"):
                return {"mock_data": False, "status": "MISSING_TABLES", "session_id": session_id}
            payload = self._repository.detail_by_session(conn, session_id)
            payout_odds = None
            if payload:
                ev = payload.get("evaluation") if isinstance(payload.get("evaluation"), dict) else payload
                payout_odds = PayoutOddsService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(ev.get("market_id")) if ev.get("market_id") else None,
                    position_id=str(ev.get("position_id")) if ev.get("position_id") else None,
                )
                exit_hold = ExitHoldReasoningService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(ev.get("market_id")) if ev.get("market_id") else None,
                    position_id=str(ev.get("position_id")) if ev.get("position_id") else None,
                )
                capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(ev.get("market_id")) if ev.get("market_id") else None,
                    position_id=str(ev.get("position_id")) if ev.get("position_id") else None,
                )
                trade_lifecycle = TradeLifecycleService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(ev.get("market_id")) if ev.get("market_id") else None,
                    position_id=str(ev.get("position_id")) if ev.get("position_id") else None,
                    candidate_id=str(ev.get("candidate_id")) if ev.get("candidate_id") else None,
                )
            else:
                exit_hold = None
                capital_efficiency = None
                trade_lifecycle = None
        if payload is None:
            return {"mock_data": False, "status": "NOT_FOUND", "session_id": session_id}
        payload["payout_odds_visibility"] = payout_odds
        payload["payout_odds_observational_only"] = True
        payload["exit_hold_visibility"] = exit_hold
        payload["exit_hold_observational_only"] = True
        payload["capital_efficiency_visibility"] = capital_efficiency
        payload["capital_efficiency_observational_only"] = True
        payload["trade_lifecycle_visibility"] = trade_lifecycle
        payload["trade_lifecycle_observational_only"] = True
        payload.update({"mock_data": False, "status": "OK", "generated_at": datetime.now(UTC).isoformat()})
        return _json_safe(payload)

    def _build_evaluation(
        self,
        *,
        session: dict[str, Any],
        awareness: dict[str, Any],
        account: dict[str, Any] | None,
        ledger: dict[str, Any] | None,
        events: list[dict[str, Any]],
        active_open: int,
        position: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        sources = [
            {
                "source_domain": "AWARENESS",
                "source_table": "mesh_shared_awareness",
                "source_record_id": str(awareness["awareness_id"]),
                "contribution_summary": "shared awareness context for upstream capital evaluation",
            }
        ]
        missing: list[str] = []
        flags: list[str] = []
        if not account:
            missing.append("paper_accounts.paper_default")
            return self._evaluation_row(
                session=session,
                account=None,
                decision=CapitalDecision.INSUFFICIENT_DATA,
                confidence=Decimal("0.20"),
                reason="Paper account state is missing; Capital Brain cannot evaluate upstream constraints.",
                missing=missing,
                flags=flags,
                estimated_required=Decimal("0"),
            ), sources

        sources.append(
            {
                "source_domain": "CAPITAL",
                "source_table": "paper_accounts",
                "source_record_id": str(account["account_id"]),
                "contribution_summary": "paper account balances and capital limits",
            }
        )
        if ledger:
            sources.append(
                {
                    "source_domain": "CAPITAL_LEDGER",
                    "source_table": "paper_capital_ledger",
                    "source_record_id": str(ledger["ledger_id"]),
                    "contribution_summary": f"latest paper capital ledger event={ledger.get('event_type')}",
                }
            )
        if position:
            sources.append(
                {
                    "source_domain": "POSITION",
                    "source_table": "paper_positions",
                    "source_record_id": str(position["id"]),
                    "contribution_summary": "paper position context for capital release review",
                }
            )

        available = _decimal(account.get("available_balance"))
        current = _decimal(account.get("current_balance"))
        open_exposure = _decimal(account.get("open_exposure"))
        daily_pnl = _decimal(account.get("daily_pnl"))
        max_position = _decimal(account.get("max_position_size"))
        risk_pct = _decimal(account.get("risk_per_trade_pct"))
        max_daily_loss_pct = _decimal(account.get("max_daily_loss_pct"))
        max_open_positions = int(account.get("max_open_positions") or 0)
        max_total_open_exposure_pct = _decimal(account.get("max_total_open_exposure_pct"))
        estimated_required, estimated_loss, lock_minutes = _estimate_requirements(events, account)
        balance_fit = _fit_score(available, estimated_required)
        max_exposure = current * max_total_open_exposure_pct / Decimal("100") if current > 0 else Decimal("0")
        exposure_after = open_exposure + estimated_required
        exposure_fit = _fit_score(max_exposure, exposure_after) if max_exposure > 0 else Decimal("0")
        efficiency = _efficiency_score(
            awareness=awareness,
            balance_fit=balance_fit,
            exposure_fit=exposure_fit,
            estimated_required=estimated_required,
            current=current,
            lock_minutes=lock_minutes,
        )
        decision = CapitalDecision.SUPPORT
        reason = "Capital Brain supports upstream review; balance, exposure, and limits fit the session."

        position_session = bool(session.get("position_id")) or session.get("session_type") == "POSITION_SESSION"
        if position_session:
            has_position_context = bool(position) or _state_present(awareness, "position_state_json")
            if not has_position_context:
                decision = CapitalDecision.INSUFFICIENT_DATA
                reason = "Position session lacks source-backed position context."
                missing.append("POSITION")
            else:
                adverse = _adverse_position_context(awareness)
                profitable = _profitable_position_context(awareness, position)
                if profitable and adverse:
                    decision = CapitalDecision.RELEASE_REVIEW
                    reason = "Position has profit context and adverse risk/exit signals; release review recommended."
                    flags.extend(["PROFITABLE_ADVERSE_POSITION", "RELEASE_REVIEW"])
                elif adverse:
                    decision = CapitalDecision.RELEASE_REVIEW
                    reason = "Position risk or exit context worsened; release review recommended."
                    flags.append("ADVERSE_POSITION_CONTEXT")
                else:
                    decision = CapitalDecision.WATCH
                    reason = "Position capital remains under observation; no release trigger was found."
            return self._evaluation_row(
                session=session,
                account=account,
                decision=decision,
                confidence=Decimal("0.70") if decision != CapitalDecision.INSUFFICIENT_DATA else Decimal("0.35"),
                reason=reason,
                missing=missing,
                flags=flags,
                estimated_required=estimated_required,
                estimated_loss=estimated_loss,
                lock_minutes=lock_minutes,
                efficiency=efficiency,
                exposure_fit=exposure_fit,
                balance_fit=balance_fit,
            ), sources

        daily_loss_limit = _decimal(account.get("initial_balance")) * max_daily_loss_pct / Decimal("100")
        capital_summary = str((awareness.get("capital_state_json") or {}).get("summary") or "").upper()
        if available <= 0 or "AVAILABLE=0" in capital_summary or "AVAILABLE=0.0" in capital_summary:
            decision = CapitalDecision.BLOCK
            reason = "Available paper capital is zero or negative."
            flags.append("NO_AVAILABLE_CAPITAL")
        elif estimated_required > available:
            decision = CapitalDecision.BLOCK
            reason = "Estimated required capital exceeds available balance."
            flags.append("REQUIRED_GT_AVAILABLE")
        elif estimated_required > max_position:
            decision = CapitalDecision.BLOCK
            reason = "Estimated required capital exceeds max position size."
            flags.append("MAX_POSITION_SIZE_EXCEEDED")
        elif daily_pnl <= -daily_loss_limit and daily_loss_limit > 0:
            decision = CapitalDecision.BLOCK
            reason = "Daily loss guard is active."
            flags.append("DAILY_LOSS_GUARD")
        elif active_open >= max_open_positions and max_open_positions >= 0:
            decision = CapitalDecision.BLOCK
            reason = "Max open paper positions has been reached."
            flags.append("MAX_OPEN_POSITIONS")
        elif max_exposure > 0 and exposure_after > max_exposure:
            decision = CapitalDecision.BLOCK
            reason = "Open exposure would exceed max total open exposure."
            flags.append("MAX_EXPOSURE_LIMIT")
        elif max_exposure > 0 and exposure_after > (max_exposure * Decimal("0.80")):
            decision = CapitalDecision.WATCH
            reason = "Open exposure is near the configured max exposure limit."
            flags.append("HIGH_EXPOSURE")
        elif _long_lock_poor_fees(awareness, lock_minutes):
            decision = CapitalDecision.WATCH
            reason = "Estimated capital lock is long while fee/edge context is poor or missing."
            flags.append("LONG_LOCK_POOR_FEES")
        elif _poor_liquidity(awareness):
            decision = CapitalDecision.WATCH
            reason = "Liquidity context is poor or stale; capital should watch instead of support."
            flags.append("POOR_LIQUIDITY")
        elif efficiency < Decimal("0.45"):
            decision = CapitalDecision.WATCH
            reason = "Capital efficiency is weak for this session."
            flags.append("LOW_CAPITAL_EFFICIENCY")

        confidence = Decimal("0.78") if decision == CapitalDecision.SUPPORT else Decimal("0.72") if decision == CapitalDecision.BLOCK else Decimal("0.62")
        return self._evaluation_row(
            session=session,
            account=account,
            decision=decision,
            confidence=confidence,
            reason=reason,
            missing=missing,
            flags=flags,
            estimated_required=estimated_required,
            estimated_loss=estimated_loss,
            lock_minutes=lock_minutes,
            efficiency=efficiency,
            exposure_fit=exposure_fit,
            balance_fit=balance_fit,
        ), sources

    def _evaluation_row(
        self,
        *,
        session: dict[str, Any],
        account: dict[str, Any] | None,
        decision: CapitalDecision,
        confidence: Decimal,
        reason: str,
        missing: list[str],
        flags: list[str],
        estimated_required: Decimal,
        estimated_loss: Decimal | None = None,
        lock_minutes: int | None = None,
        efficiency: Decimal | None = None,
        exposure_fit: Decimal | None = None,
        balance_fit: Decimal | None = None,
    ) -> dict[str, Any]:
        current = _decimal(account.get("current_balance")) if account else None
        return {
            "evaluation_id": f"capital_eval_{session['session_id']}",
            "session_id": session["session_id"],
            "market_id": session.get("market_id"),
            "candidate_id": session.get("candidate_id"),
            "position_id": session.get("position_id"),
            "account_id": account.get("account_id") if account else None,
            "available_balance": _decimal(account.get("available_balance")) if account else None,
            "locked_balance": _decimal(account.get("locked_balance")) if account else None,
            "current_balance": current,
            "open_exposure": _decimal(account.get("open_exposure")) if account else None,
            "daily_pnl": _decimal(account.get("daily_pnl")) if account else None,
            "risk_per_trade_pct": _decimal(account.get("risk_per_trade_pct")) if account else None,
            "max_position_size": _decimal(account.get("max_position_size")) if account else None,
            "max_daily_loss_pct": _decimal(account.get("max_daily_loss_pct")) if account else None,
            "max_open_positions": int(account.get("max_open_positions")) if account and account.get("max_open_positions") is not None else None,
            "max_total_open_exposure_pct": _decimal(account.get("max_total_open_exposure_pct")) if account else None,
            "estimated_required_capital": estimated_required,
            "estimated_max_loss": estimated_loss if estimated_loss is not None else estimated_required,
            "estimated_capital_lock_minutes": lock_minutes,
            "capital_efficiency_score": efficiency if efficiency is not None else Decimal("0"),
            "exposure_fit_score": exposure_fit if exposure_fit is not None else Decimal("0"),
            "balance_fit_score": balance_fit if balance_fit is not None else Decimal("0"),
            "decision": decision.value,
            "confidence": confidence,
            "reason": reason,
            "missing_inputs_json": missing,
            "risk_flags_json": flags,
        }

    def _tables_ready(self, conn: Any) -> bool:
        return all(
            table_exists(conn, table)
            for table in (
                "capital_brain_evaluations",
                "capital_brain_sources",
                "mesh_sessions",
                "mesh_shared_awareness",
                "paper_accounts",
            )
        )

    def _assert_system_on(self) -> None:
        power = self._system_power.get_power_state()
        if str(power.get("power") or "OFF").upper() != "ON" or not power.get("runtime_work_allowed"):
            raise CapitalBrainBlocked("SYSTEM_POWER_OFF")


def _estimate_requirements(events: list[dict[str, Any]], account: dict[str, Any]) -> tuple[Decimal, Decimal, int | None]:
    required: Decimal | None = None
    max_loss: Decimal | None = None
    lock_minutes: int | None = None
    for event in events:
        payload = event.get("payload_json") or {}
        if required is None:
            required = _payload_decimal(payload, "estimated_required_capital") or _payload_decimal(payload, "required_capital") or _payload_decimal(payload, "notional")
        if max_loss is None:
            max_loss = _payload_decimal(payload, "estimated_max_loss") or _payload_decimal(payload, "max_loss")
        if lock_minutes is None:
            raw_lock = payload.get("estimated_capital_lock_minutes") or payload.get("lock_minutes")
            try:
                lock_minutes = int(raw_lock) if raw_lock is not None else None
            except (TypeError, ValueError):
                lock_minutes = None
    current = _decimal(account.get("current_balance"))
    risk_pct = _decimal(account.get("risk_per_trade_pct"))
    risk_amount = current * risk_pct / Decimal("100")
    if required is None or required <= 0:
        required = min(_decimal(account.get("max_position_size")), risk_amount) if risk_amount > 0 else Decimal("0")
    if max_loss is None:
        max_loss = required
    return required.quantize(Decimal("0.00000001")), max_loss.quantize(Decimal("0.00000001")), lock_minutes


def _payload_decimal(payload: dict[str, Any], key: str) -> Decimal | None:
    if key not in payload:
        return None
    value = _decimal(payload.get(key))
    return value if value > 0 else None


def _efficiency_score(
    *,
    awareness: dict[str, Any],
    balance_fit: Decimal,
    exposure_fit: Decimal,
    estimated_required: Decimal,
    current: Decimal,
    lock_minutes: int | None,
) -> Decimal:
    score = (balance_fit * Decimal("0.35")) + (exposure_fit * Decimal("0.35"))
    size_fit = Decimal("1") - min(Decimal("1"), estimated_required / current) if current > 0 else Decimal("0")
    score += size_fit * Decimal("0.15")
    score += Decimal("0.10") if not _poor_liquidity(awareness) else Decimal("0")
    score += Decimal("0.05") if not _long_lock_poor_fees(awareness, lock_minutes) else Decimal("0")
    return _clamp(score)


def _fit_score(capacity: Decimal, required: Decimal) -> Decimal:
    if capacity <= 0:
        return Decimal("0")
    if required <= 0:
        return Decimal("1")
    return _clamp(Decimal("1") - (required / capacity))


def _state_present(awareness: dict[str, Any], column: str) -> bool:
    state = awareness.get(column) or {}
    return int(state.get("source_count") or 0) > 0 and str(state.get("status") or "MISSING") != "MISSING"


def _adverse_position_context(awareness: dict[str, Any]) -> bool:
    text = " ".join(
        str((awareness.get(column) or {}).get("summary") or "")
        for column in ("risk_state_json", "exit_state_json", "position_state_json")
    ).upper()
    return any(token in text for token in ("ADVERSE", "WORSEN", "EXIT_REQUIRED", "BLOCK", "CAUTION", "DANGER"))


def _profitable_position_context(awareness: dict[str, Any], position: dict[str, Any] | None) -> bool:
    if position and _decimal(position.get("unrealized")) + _decimal(position.get("realized")) > 0:
        return True
    text = " ".join(str((awareness.get(column) or {}).get("summary") or "") for column in ("pnl_state_json", "position_state_json")).upper()
    return any(token in text for token in ("PROFIT", "POSITIVE", "PNL=+"))


def _long_lock_poor_fees(awareness: dict[str, Any], lock_minutes: int | None) -> bool:
    if not lock_minutes or lock_minutes < 240:
        return False
    fees = awareness.get("fees_state_json") or {}
    summary = str(fees.get("summary") or "").upper()
    status = str(fees.get("status") or "MISSING")
    return status in {"MISSING", "STALE"} or any(token in summary for token in ("POOR", "HIGH", "NEGATIVE", "ERASE"))


def _poor_liquidity(awareness: dict[str, Any]) -> bool:
    liquidity = awareness.get("liquidity_state_json") or {}
    summary = str(liquidity.get("summary") or "").upper()
    status = str(liquidity.get("status") or "MISSING")
    return status == "STALE" or any(token in summary for token in ("POOR", "LOW", "THIN", "STALE"))


def _decimal(value: Any) -> Decimal:
    try:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _float(value: Any) -> float:
    return float(_decimal(value))


def _clamp(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), value)).quantize(Decimal("0.0001"))


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
        "total_evaluations": 0,
        "decisions_by_type": {},
        "capital_support_count": 0,
        "capital_watch_count": 0,
        "capital_block_count": 0,
        "release_review_count": 0,
        "insufficient_data_count": 0,
        "avg_capital_efficiency_score": 0,
        "available_balance": None,
        "locked_balance": None,
        "open_exposure": None,
        "latest_evaluations": [],
        "active_constraints": [],
    }

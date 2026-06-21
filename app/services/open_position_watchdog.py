from __future__ import annotations

import os
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.mesh_sessions.service import MeshSessionService
from app.neural_bus.contracts import NeuralEvent
from app.neural_bus.repository import NeuralEventRepository
from app.neural_bus.types import NeuralEventType
from app.position_awareness.repository import PositionAwarenessRepository
from app.position_awareness.service import PositionAwarenessService
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.security.redaction import redact_secrets
from app.services.capital_efficiency import CapitalEfficiencyService
from app.services.fresh_market_identity import SECURITY_GOVERNANCE_STATUS
from app.services.source_status import DEFAULT_CLOB_BASE_URL
from app.services.system_power import SystemPowerService
from app.services.trusted_orderbook import FRESHNESS_SECONDS


PNL_ABS_THRESHOLD = Decimal("0.01")
PNL_REL_THRESHOLD = Decimal("0.01")
SPREAD_ABS_THRESHOLD = Decimal("0.005")
SPREAD_REL_THRESHOLD = Decimal("0.20")
LIQUIDITY_ABS_THRESHOLD = Decimal("0.10")
LIQUIDITY_REL_THRESHOLD = Decimal("0.25")


class OpenPositionWatchdogService:
    """Locks actual entry tokens and watches open paper positions without trading authority."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        clob_client: Any | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._clob = clob_client or _WatchdogHttpClient()
        self._snapshotter = OrderbookSnapshotter(connection_factory=self._factory)
        self._orderbooks = OrderbookSnapshotRepository()
        self._events = NeuralEventRepository()
        self._mesh = MeshSessionService(connection_factory=self._factory)
        self._position_repo = PositionAwarenessRepository()
        self._position_awareness = PositionAwarenessService(connection_factory=self._factory)

    def run(
        self,
        *,
        cycle_id: str | None = None,
        limit: int = 25,
        dry_run: bool = False,
        max_seconds: int = 30,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"open_position_watchdog_{uuid4().hex}"
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        if system_power != "ON" or not bool(power.get("runtime_work_allowed")):
            payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, dry_run, "SYSTEM_POWER_OFF")
            self._record_run(payload)
            return _json_safe(payload)
        if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
            payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, dry_run, "STATE_GOVERNOR_BLOCKED_INTELLIGENCE")
            self._record_run(payload)
            return _json_safe(payload)

        before = self._counts()
        safety_before = self._safety_counts()
        blockers: Counter[str] = Counter()
        errors: list[str] = []
        positions_checked = 0
        locks_created = 0
        orderbooks_refreshed = 0
        pnl_changed = 0
        spread_widened = 0
        liquidity_dropped = 0
        token_unavailable = 0
        exit_review = 0
        hold_review = 0
        events_published = 0
        deadline = time.perf_counter() + max(1, max_seconds)

        with self._factory.connect() as conn:
            with conn.transaction():
                positions = self._list_open_positions(conn, limit=limit)
                if not positions:
                    blockers["NO_OPEN_POSITIONS"] += 1
                for position in positions:
                    if time.perf_counter() >= deadline:
                        blockers["MAX_SECONDS_EXHAUSTED"] += 1
                        break
                    positions_checked += 1
                    try:
                        if dry_run:
                            blockers["DRY_RUN_NOT_MUTATED"] += 1
                            continue
                        lock_result = self._ensure_position_token_lock(conn, run_id=run_id, position=position)
                        if lock_result.get("created"):
                            locks_created += 1
                        if lock_result.get("status") != "ACTIVE":
                            blockers[str(lock_result.get("status") or "MISSING_POSITION_TOKEN")] += 1
                            continue
                        trace, event_types = self._poll_position_lock(conn, run_id=run_id, position=position, lock=lock_result["lock"])
                        blockers[trace.get("reason") or "OK"] += 1
                        for event_type in event_types:
                            if event_type == NeuralEventType.POSITION_ORDERBOOK_REFRESHED.value:
                                orderbooks_refreshed += 1
                            elif event_type == NeuralEventType.PNL_CHANGED.value:
                                pnl_changed += 1
                            elif event_type == NeuralEventType.POSITION_EXIT_RISK.value:
                                spread_widened += int(bool(trace.get("metadata_json", {}).get("spread_widened")))
                                liquidity_dropped += int(bool(trace.get("metadata_json", {}).get("liquidity_dropped")))
                            elif event_type == NeuralEventType.TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION.value:
                                token_unavailable += 1
                            elif event_type == NeuralEventType.EXIT_REVIEW.value:
                                exit_review += 1
                            elif event_type == NeuralEventType.HOLD_REVIEW.value:
                                hold_review += 1
                        events_published += len(event_types)
                    except Exception as exc:
                        errors.append(_error_summary(position.get("id"), exc))
                        blockers["ERROR"] += 1
            conn.commit()

        after = self._counts()
        safety_after = self._safety_counts()
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "system_power": system_power,
            "status": "DEGRADED" if errors else "OK",
            "dry_run": dry_run,
            "positions_checked": positions_checked,
            "locks_created": locks_created,
            "orderbooks_refreshed": orderbooks_refreshed,
            "pnl_changed_count": pnl_changed,
            "spread_widened_count": spread_widened,
            "liquidity_dropped_count": liquidity_dropped,
            "token_unavailable_count": token_unavailable,
            "exit_review_count": exit_review,
            "hold_review_count": hold_review,
            "events_published": events_published,
            "errors_count": len(errors),
            "blocker_counts": dict(blockers),
            "safety_counts_before": safety_before,
            "safety_counts_after": safety_after,
            "live_orders_delta": max(0, safety_after["live_orders"] - safety_before["live_orders"]),
            "real_orders_delta": max(0, safety_after["orders_v2"] - safety_before["orders_v2"]),
            "metadata": {
                "phase": "position_token_lock_open_position_watchdog",
                "bounded_polling": True,
                "max_seconds": max_seconds,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "no_trading_authority": True,
                "no_position_close_authority": True,
                "before": before,
                "after": after,
            },
            "error_message": "; ".join(errors[:10]) if errors else None,
            "before": before,
            "after": after,
            "latest_traces": self._latest_traces(limit=20),
        }
        self._record_run(payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 100) -> dict[str, Any]:
        counts = self._counts()
        latest = self._latest_run()
        with self._factory.connect() as conn:
            capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
        return {
            "mock_data": False,
            "status": "OK",
            "open_positions": counts["open_positions"],
            "token_locks": counts["token_locks"],
            "missing_token_locks": counts["missing_token_locks"],
            "latest_run": latest,
            "positions_checked": int((latest or {}).get("positions_checked") or 0),
            "locks_created": int((latest or {}).get("locks_created") or 0),
            "orderbooks_refreshed": counts["POSITION_ORDERBOOK_REFRESHED"],
            "pnl_changed_count": counts["PNL_CHANGED"],
            "spread_widened_count": counts["POSITION_EXIT_RISK"],
            "liquidity_dropped_count": counts["POSITION_EXIT_RISK"],
            "token_unavailable_count": counts["TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION"],
            "exit_review_count": counts["EXIT_REVIEW"],
            "hold_review_count": counts["HOLD_REVIEW"],
            "latest_reactions": self._latest_reactions(limit=limit),
            "latest_traces": self._latest_traces(limit=limit),
            "capital_efficiency_visibility": capital_efficiency,
            "capital_efficiency_observational_only": True,
            "security_governance_status": SECURITY_GOVERNANCE_STATUS,
            "safety_counts": self._safety_counts(),
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def get_position_detail(self, paper_position_id: str, *, limit: int = 100) -> dict[str, Any]:
        with self._factory.connect() as conn:
            position = self._get_position(conn, paper_position_id)
            lock = self._get_lock(conn, paper_position_id)
            snapshot = None
            if lock and lock.get("token_id") and _table_exists(conn, "orderbook_snapshots"):
                snapshot = conn.execute(
                    """
                    SELECT *
                    FROM orderbook_snapshots
                    WHERE token_id=%s
                    ORDER BY collected_at DESC, id DESC
                    LIMIT 1
                    """,
                    (lock["token_id"],),
                ).fetchone()
            reactions = self._latest_reactions(limit=limit, paper_position_id=paper_position_id)
            traces = self._latest_traces(limit=limit, paper_position_id=paper_position_id)
            awareness = None
            if _table_exists(conn, "position_awareness"):
                awareness = conn.execute(
                    "SELECT * FROM position_awareness WHERE position_id=%s ORDER BY updated_at DESC LIMIT 1",
                    (paper_position_id,),
                ).fetchone()
            capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).observational_summary_for_market(conn, position_id=paper_position_id, limit=limit)
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK" if position else "POSITION_NOT_FOUND",
                "paper_position_id": paper_position_id,
                "position": dict(position) if position else None,
                "token_lock": dict(lock) if lock else None,
                "latest_orderbook_snapshot": dict(snapshot) if snapshot else None,
                "latest_reactions": reactions,
                "latest_traces": traces,
                "position_awareness": dict(awareness) if awareness else None,
                "capital_efficiency_visibility": capital_efficiency,
                "capital_efficiency_observational_only": True,
                "source_links": {
                    "position_table": "paper_positions",
                    "lock_table": "position_token_locks",
                    "trace_table": "open_position_watchdog_traces",
                },
            }
        )

    def _ensure_position_token_lock(self, conn: Any, *, run_id: str, position: dict[str, Any]) -> dict[str, Any]:
        position_id = str(position["id"])
        existing = self._get_lock(conn, position_id)
        if existing and existing.get("status") == "ACTIVE":
            drift = self._token_identity_drift(conn, existing)
            if drift:
                self._insert_trace(conn, run_id=run_id, position=position, lock=existing, clob_status="NOT_ATTEMPTED", reaction_type=NeuralEventType.TOKEN_IDENTITY_DRIFT_REVIEW.value, severity="CRITICAL", reason="TOKEN_IDENTITY_DRIFT_REVIEW", metadata={"current_expected_token_id": drift})
                self._publish_position_event(conn, position=position, trace_id=None, event_type=NeuralEventType.TOKEN_IDENTITY_DRIFT_REVIEW.value, lock=existing, payload={"current_expected_token_id": drift, "locked_token_id": existing.get("token_id")})
                return {"status": "TOKEN_IDENTITY_DRIFT_REVIEW", "lock": existing, "created": False}
            return {"status": "ACTIVE", "lock": existing, "created": False}

        derived = self._derive_lock(conn, position)
        if derived.get("status") != "ACTIVE":
            lock = self._upsert_missing_lock(conn, position=position, reason=str(derived.get("status") or "MISSING_POSITION_TOKEN"))
            trace = self._insert_trace(conn, run_id=run_id, position=position, lock=lock, clob_status="NOT_ATTEMPTED", reaction_type=NeuralEventType.MISSING_POSITION_TOKEN.value, severity="CRITICAL", reason=str(derived.get("status") or "MISSING_POSITION_TOKEN"), metadata=derived)
            self._publish_position_event(conn, position=position, trace_id=trace["id"], event_type=NeuralEventType.MISSING_POSITION_TOKEN.value, lock=lock, payload={"reason": derived.get("status"), "read_only": True})
            return {"status": "MISSING_POSITION_TOKEN", "lock": lock, "created": False}

        lock = self._upsert_active_lock(conn, derived)
        session = self._position_repo.ensure_position_session(conn, position)
        trace = self._insert_trace(conn, run_id=run_id, position=position, lock=lock, clob_status="NOT_ATTEMPTED", reaction_type="POSITION_TOKEN_LOCKED", severity="INFO", reason="POSITION_TOKEN_LOCKED", metadata={"session_id": session["session_id"]})
        self._insert_position_reaction(conn, position=position, session_id=str(session["session_id"]), reaction_type="POSITION_ORDERBOOK_REFRESHED", source_event_id=f"open_position_watchdog_traces:{trace['id']}", source_domain="POSITION", severity="INFO", summary=f"Locked token {lock.get('token_id')} for paper position {position_id}.")
        return {"status": "ACTIVE", "lock": lock, "created": existing is None}

    def _poll_position_lock(self, conn: Any, *, run_id: str, position: dict[str, Any], lock: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        clob = self._fetch_book(str(lock["token_id"]))
        if clob["status"] != "OK":
            trace = self._insert_trace(conn, run_id=run_id, position=position, lock=lock, clob_status=str(clob["status"]), reaction_type=NeuralEventType.TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION.value, severity="CRITICAL", reason=str(clob["status"]), metadata=clob)
            events = [NeuralEventType.TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION.value, NeuralEventType.POSITION_EXIT_RISK.value, NeuralEventType.EXIT_REVIEW.value]
            published = self._publish_events(conn, position=position, lock=lock, trace=trace, event_types=events)
            self._refresh_position_awareness(conn, position)
            return trace, published
        reason = self._validate_book(clob, lock)
        if reason:
            trace = self._insert_trace(conn, run_id=run_id, position=position, lock=lock, clob_status="REJECTED", reaction_type=NeuralEventType.TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION.value, severity="CRITICAL", reason=reason, metadata=clob)
            events = [NeuralEventType.TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION.value, NeuralEventType.POSITION_EXIT_RISK.value, NeuralEventType.EXIT_REVIEW.value]
            published = self._publish_events(conn, position=position, lock=lock, trace=trace, event_types=events)
            self._refresh_position_awareness(conn, position)
            return trace, published

        snapshot_id, metrics = self._persist_snapshot(conn, raw=clob["raw"], lock=lock, run_id=run_id)
        current_price = _decimal(metrics.get("best_bid"))
        current_pnl = _estimate_pnl(position, current_price)
        previous_pnl = _decimal(position.get("unrealized"))
        metadata = {
            **metrics,
            "spread_widened": _worsened(lock.get("last_spread"), metrics.get("spread"), abs_threshold=SPREAD_ABS_THRESHOLD, rel_threshold=SPREAD_REL_THRESHOLD),
            "liquidity_dropped": _dropped(lock.get("last_liquidity_score"), metrics.get("liquidity_score"), abs_threshold=LIQUIDITY_ABS_THRESHOLD, rel_threshold=LIQUIDITY_REL_THRESHOLD),
            "best_bid_missing": current_price is None,
        }
        event_types = [NeuralEventType.POSITION_ORDERBOOK_REFRESHED.value]
        if _pnl_changed(previous_pnl, current_pnl):
            event_types.append(NeuralEventType.PNL_CHANGED.value)
        if metadata["spread_widened"] or metadata["liquidity_dropped"] or metadata["best_bid_missing"]:
            event_types.append(NeuralEventType.POSITION_EXIT_RISK.value)
            event_types.append(NeuralEventType.EXIT_REVIEW.value)
        elif current_pnl is not None and current_pnl > 0 and current_price is not None:
            event_types.append(NeuralEventType.EXIT_REVIEW.value)
        else:
            event_types.append(NeuralEventType.HOLD_REVIEW.value)

        reaction_type = event_types[-1]
        severity = "WARN" if reaction_type in {NeuralEventType.POSITION_EXIT_RISK.value, NeuralEventType.EXIT_REVIEW.value} else "INFO"
        trace = self._insert_trace(
            conn,
            run_id=run_id,
            position=position,
            lock=lock,
            clob_status="OK",
            snapshot_id=snapshot_id,
            previous_price=position.get("mark_price"),
            current_price=current_price,
            previous_pnl=previous_pnl,
            current_pnl=current_pnl,
            previous_spread=lock.get("last_spread"),
            current_spread=metrics.get("spread"),
            previous_liquidity=lock.get("last_liquidity_score"),
            current_liquidity=metrics.get("liquidity_score"),
            reaction_type=reaction_type,
            severity=severity,
            reason=None,
            metadata=metadata,
        )
        published = self._publish_events(conn, position=position, lock=lock, trace=trace, event_types=event_types)
        self._update_lock_success(conn, lock, metrics=metrics, snapshot_id=snapshot_id)
        self._refresh_position_awareness(conn, position)
        return trace, published

    def _derive_lock(self, conn: Any, position: dict[str, Any]) -> dict[str, Any]:
        payload = position.get("payload_json") if isinstance(position.get("payload_json"), dict) else {}
        fill_ref = _clean(payload.get("paper_fill_id") or payload.get("fill_id"))
        fill = None
        if fill_ref and _table_exists(conn, "paper_fills"):
            fill = conn.execute("SELECT * FROM paper_fills WHERE paper_fill_id=%s ORDER BY created_at DESC, id DESC LIMIT 1", (fill_ref,)).fetchone()
        if fill is None and _table_exists(conn, "paper_fills"):
            rows = conn.execute(
                """
                SELECT *
                FROM paper_fills
                WHERE market_id=%s
                  AND side=%s
                  AND ABS(COALESCE(quantity,0) - COALESCE(%s,0)) < 0.000001
                  AND ABS(COALESCE(fill_price,0) - COALESCE(%s,0)) < 0.000001
                ORDER BY created_at DESC, id DESC
                LIMIT 2
                """,
                (position.get("market_id"), position.get("intended_outcome"), position.get("size"), position.get("avg_entry")),
            ).fetchall()
            if len(rows) == 1:
                fill = rows[0]
            elif len(rows) > 1:
                return {"status": "AMBIGUOUS_POSITION_FILL"}
        if fill is None:
            return {"status": "MISSING_POSITION_FILL"}
        fill = dict(fill)
        snapshot = None
        if fill.get("orderbook_snapshot_id") and _table_exists(conn, "orderbook_snapshots"):
            snapshot = conn.execute("SELECT * FROM orderbook_snapshots WHERE id=%s OR orderbook_snapshot_id=%s ORDER BY id DESC LIMIT 1", (fill.get("orderbook_snapshot_id"), str(fill.get("orderbook_snapshot_id")))).fetchone()
        if snapshot is None:
            return {"status": "MISSING_ENTRY_ORDERBOOK_SNAPSHOT", "fill_id": fill.get("paper_fill_id")}
        snapshot = dict(snapshot)
        token_id = _clean(snapshot.get("token_id"))
        if not token_id:
            return {"status": "MISSING_POSITION_TOKEN", "fill_id": fill.get("paper_fill_id"), "snapshot_id": snapshot.get("id")}
        condition_id = _clean((snapshot.get("raw_orderbook_json") or {}).get("market") if isinstance(snapshot.get("raw_orderbook_json"), dict) else None)
        if not condition_id:
            condition_id = self._condition_for_market(conn, str(position.get("market_id") or fill.get("market_id") or ""))
        side = _clean(fill.get("side") or snapshot.get("side") or position.get("intended_outcome"))
        return {
            "status": "ACTIVE",
            "lock_id": f"position_token_lock_{position['id']}",
            "paper_position_id": str(position["id"]),
            "market_id": _clean(position.get("market_id") or fill.get("market_id") or snapshot.get("market_id")),
            "condition_id": condition_id,
            "side": side,
            "token_id": token_id,
            "entry_order_id": str(fill.get("paper_order_id") or "") or None,
            "entry_fill_id": str(fill.get("paper_fill_id") or "") or None,
            "entry_orderbook_snapshot_id": int(snapshot["id"]),
            "source": "paper_fill_orderbook_snapshot",
            "metadata_json": {
                "fill_table_id": fill.get("id"),
                "orderbook_snapshot_id": snapshot.get("orderbook_snapshot_id"),
                "derived_from_actual_entry_fill": True,
            },
        }

    def _fetch_book(self, token_id: str) -> dict[str, Any]:
        endpoint = f"{(os.getenv('POLYMARKET_CLOB_HOST') or DEFAULT_CLOB_BASE_URL).rstrip('/')}/book"
        started = time.perf_counter()
        try:
            raw, latency_ms = self._clob.get_json(endpoint, params={"token_id": token_id})
        except httpx.HTTPStatusError as exc:
            body = redact_secrets(exc.response.text or "")[:240]
            status = "TOKEN_NOT_FOUND" if exc.response.status_code == 404 else "CLOB_ENDPOINT_ERROR"
            return {"status": status, "latency_ms": int((time.perf_counter() - started) * 1000), "error_summary": body}
        except Exception as exc:
            text = redact_secrets(str(exc))[:240]
            status = "TOKEN_NOT_FOUND" if "token" in text.lower() and "not" in text.lower() else "CLOB_ENDPOINT_ERROR"
            return {"status": status, "latency_ms": int((time.perf_counter() - started) * 1000), "error_summary": text}
        latency = latency_ms if latency_ms is not None else int((time.perf_counter() - started) * 1000)
        if not isinstance(raw, dict) or not raw:
            return {"status": "CLOB_NO_BOOK", "latency_ms": latency}
        bids = raw.get("bids") or raw.get("buy") or []
        asks = raw.get("asks") or raw.get("sell") or []
        if not bids or not asks:
            return {"status": "EMPTY_BOOK", "latency_ms": latency, "raw": raw, "asset_id": raw.get("asset_id"), "market": raw.get("market")}
        return {"status": "OK", "latency_ms": latency, "raw": raw, "asset_id": raw.get("asset_id"), "market": raw.get("market")}

    def _validate_book(self, clob: dict[str, Any], lock: dict[str, Any]) -> str | None:
        raw = clob.get("raw") or {}
        if _clean(raw.get("asset_id") or clob.get("asset_id")) != str(lock["token_id"]):
            return "ASSET_ID_MISMATCH"
        condition_id = _clean(lock.get("condition_id"))
        if condition_id and _clean(raw.get("market") or clob.get("market")) != condition_id:
            return "CONDITION_ID_MISMATCH"
        return None

    def _persist_snapshot(self, conn: Any, *, raw: dict[str, Any], lock: dict[str, Any], run_id: str) -> tuple[int | None, dict[str, Any]]:
        snapshot = self._snapshotter.normalize_orderbook(
            raw,
            market_id=str(lock["market_id"]),
            token_id=str(lock["token_id"]),
            side=str(lock["side"]),
            source="open_position_watchdog",
            correlation_id=run_id,
            raw_payload_ref=f"clob:/book:{lock['token_id']}:{datetime.now(UTC).isoformat()}",
            collected_at=datetime.now(UTC),
            freshness_window_seconds=FRESHNESS_SECONDS,
        )
        self._orderbooks.append_snapshot(conn, snapshot)
        row = conn.execute("SELECT * FROM orderbook_snapshots WHERE orderbook_snapshot_id=%s", (snapshot.orderbook_snapshot_id,)).fetchone()
        return (
            int(row["id"]) if row else None,
            {
                "snapshot_ref": snapshot.orderbook_snapshot_id,
                "best_bid": snapshot.best_bid,
                "best_ask": snapshot.best_ask,
                "spread": snapshot.spread,
                "liquidity_score": snapshot.liquidity_score,
            },
        )

    def _publish_events(self, conn: Any, *, position: dict[str, Any], lock: dict[str, Any], trace: dict[str, Any], event_types: list[str]) -> list[str]:
        published: list[str] = []
        for event_type in dict.fromkeys(event_types):
            row = self._publish_position_event(conn, position=position, trace_id=trace["id"], event_type=event_type, lock=lock, payload={
                "paper_position_id": str(position["id"]),
                "token_id": lock.get("token_id"),
                "market_id": lock.get("market_id"),
                "condition_id": lock.get("condition_id"),
                "side": lock.get("side"),
                "snapshot_id": trace.get("snapshot_id"),
                "previous_price": trace.get("previous_price"),
                "current_price": trace.get("current_price"),
                "previous_pnl": trace.get("previous_pnl"),
                "current_pnl": trace.get("current_pnl"),
                "previous_spread": trace.get("previous_spread"),
                "current_spread": trace.get("current_spread"),
                "previous_liquidity_score": trace.get("previous_liquidity_score"),
                "current_liquidity_score": trace.get("current_liquidity_score"),
                "reason": trace.get("reason"),
                "read_only": True,
                "no_exit_execution": True,
            })
            if row:
                conn.execute("UPDATE open_position_watchdog_traces SET event_id=%s WHERE id=%s AND event_id IS NULL", (row["event_id"], trace["id"]))
            published.append(event_type)
        return published

    def _publish_position_event(self, conn: Any, *, position: dict[str, Any], trace_id: int | None, event_type: str, lock: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        event = NeuralEvent(
            event_type=event_type,
            correlation_id=str(payload.get("run_id") or lock.get("lock_id") or position["id"]),
            market_id=lock.get("market_id") or position.get("market_id"),
            position_id=str(position["id"]),
            source_component="Open Position Watchdog",
            source_type="CLOB_READ_ONLY" if event_type not in {NeuralEventType.MISSING_POSITION_TOKEN.value, NeuralEventType.TOKEN_IDENTITY_DRIFT_REVIEW.value} else "PAPER_POSITION",
            priority=3,
            payload_json=payload,
            source_table="open_position_watchdog_traces" if trace_id else "position_token_locks",
            source_record_id=str(trace_id or lock.get("id") or lock.get("lock_id")),
            metadata_json={"source_backed": True, "no_trading_authority": True, "no_exit_execution": True},
        )
        row = self._events.append_event(conn, event)
        self._mesh.resolve_event_with_conn(conn, row)
        return row

    def _insert_position_reaction_for_event(self, conn: Any, *, position: dict[str, Any], event: dict[str, Any], event_type: str) -> None:
        session = self._position_repo.ensure_position_session(conn, position)
        mapping = {
            NeuralEventType.POSITION_ORDERBOOK_REFRESHED.value: ("POSITION_ORDERBOOK_REFRESHED", "ORDERBOOK", "INFO", "POSITION_ORDERBOOK_REFRESHED for open position token."),
            NeuralEventType.PNL_CHANGED.value: ("PNL_RISING", "PNL", "INFO", "Open position PnL changed."),
            NeuralEventType.POSITION_EXIT_RISK.value: ("POSITION_EXIT_RISK", "EXIT", "WARN", "POSITION_EXIT_RISK from open position watchdog."),
            NeuralEventType.TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION.value: ("TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION", "ORDERBOOK", "CRITICAL", "Open position token book unavailable."),
            NeuralEventType.EXIT_REVIEW.value: ("EXIT_REVIEW", "EXIT", "WARN", "EXIT_REVIEW requested by watchdog; no exit executed."),
            NeuralEventType.HOLD_REVIEW.value: ("HOLD_REVIEW", "EXIT", "INFO", "HOLD_REVIEW from watchdog; no action forced."),
            NeuralEventType.TOKEN_IDENTITY_DRIFT_REVIEW.value: ("TOKEN_IDENTITY_DRIFT_REVIEW", "RISK", "CRITICAL", "Token identity drift requires review."),
            NeuralEventType.MISSING_POSITION_TOKEN.value: ("MISSING_POSITION_TOKEN", "POSITION", "CRITICAL", "Position token missing from deterministic entry truth."),
        }
        reaction_type, domain, severity, summary = mapping.get(event_type, ("NO_REACTION", "POSITION", "INFO", event_type))
        self._insert_position_reaction(conn, position=position, session_id=str(session["session_id"]), reaction_type=reaction_type, source_event_id=str(event["event_id"]), source_domain=domain, severity=severity, summary=summary)

    def _insert_position_reaction(self, conn: Any, *, position: dict[str, Any], session_id: str, reaction_type: str, source_event_id: str, source_domain: str, severity: str, summary: str) -> None:
        conn.execute(
            """
            INSERT INTO position_reactions (
                reaction_id, position_id, session_id, reaction_type,
                source_event_id, source_domain, source_component, severity, summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'Open Position Watchdog', %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (f"open_position_watchdog_{position['id']}_{reaction_type}_{_slug(source_event_id)}", str(position["id"]), session_id, reaction_type, source_event_id, source_domain, severity, summary),
        )

    def _insert_trace(self, conn: Any, *, run_id: str, position: dict[str, Any], lock: dict[str, Any] | None, clob_status: str, reaction_type: str | None, severity: str | None, reason: str | None, metadata: dict[str, Any] | None = None, snapshot_id: int | None = None, previous_price: Any = None, current_price: Any = None, previous_pnl: Any = None, current_pnl: Any = None, previous_spread: Any = None, current_spread: Any = None, previous_liquidity: Any = None, current_liquidity: Any = None) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO open_position_watchdog_traces (
                run_id, paper_position_id, lock_id, token_id, market_id, condition_id, side,
                previous_price, current_price, previous_pnl, current_pnl,
                previous_spread, current_spread, previous_liquidity_score,
                current_liquidity_score, snapshot_id, clob_status, reaction_type,
                severity, reason, metadata_json
            )
            VALUES (
                %(run_id)s, %(paper_position_id)s, %(lock_id)s, %(token_id)s,
                %(market_id)s, %(condition_id)s, %(side)s, %(previous_price)s,
                %(current_price)s, %(previous_pnl)s, %(current_pnl)s,
                %(previous_spread)s, %(current_spread)s,
                %(previous_liquidity_score)s, %(current_liquidity_score)s,
                %(snapshot_id)s, %(clob_status)s, %(reaction_type)s, %(severity)s,
                %(reason)s, %(metadata_json)s
            )
            RETURNING *
            """,
            {
                "run_id": run_id,
                "paper_position_id": str(position["id"]),
                "lock_id": (lock or {}).get("lock_id"),
                "token_id": (lock or {}).get("token_id"),
                "market_id": (lock or {}).get("market_id") or position.get("market_id"),
                "condition_id": (lock or {}).get("condition_id"),
                "side": (lock or {}).get("side") or position.get("intended_outcome"),
                "previous_price": previous_price,
                "current_price": current_price,
                "previous_pnl": previous_pnl,
                "current_pnl": current_pnl,
                "previous_spread": previous_spread,
                "current_spread": current_spread,
                "previous_liquidity_score": previous_liquidity,
                "current_liquidity_score": current_liquidity,
                "snapshot_id": snapshot_id,
                "clob_status": clob_status,
                "reaction_type": reaction_type,
                "severity": severity,
                "reason": reason,
                "metadata_json": Jsonb(_json_safe(metadata or {})),
            },
        ).fetchone()
        return _json_safe(dict(row))

    def _upsert_active_lock(self, conn: Any, payload: dict[str, Any]) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO position_token_locks (
                lock_id, paper_position_id, market_id, condition_id, side, token_id,
                entry_order_id, entry_fill_id, entry_orderbook_snapshot_id, source,
                status, metadata_json
            )
            VALUES (
                %(lock_id)s, %(paper_position_id)s, %(market_id)s,
                %(condition_id)s, %(side)s, %(token_id)s, %(entry_order_id)s,
                %(entry_fill_id)s, %(entry_orderbook_snapshot_id)s, %(source)s,
                'ACTIVE', %(metadata_json)s
            )
            ON CONFLICT (paper_position_id) DO UPDATE
            SET market_id=EXCLUDED.market_id,
                condition_id=EXCLUDED.condition_id,
                side=EXCLUDED.side,
                token_id=EXCLUDED.token_id,
                entry_order_id=EXCLUDED.entry_order_id,
                entry_fill_id=EXCLUDED.entry_fill_id,
                entry_orderbook_snapshot_id=EXCLUDED.entry_orderbook_snapshot_id,
                source=EXCLUDED.source,
                status='ACTIVE',
                last_verified_at=position_token_locks.last_verified_at,
                metadata_json=position_token_locks.metadata_json || EXCLUDED.metadata_json
            RETURNING *
            """,
            {**payload, "metadata_json": Jsonb(payload.get("metadata_json") or {})},
        ).fetchone()
        return _json_safe(dict(row))

    def _upsert_missing_lock(self, conn: Any, *, position: dict[str, Any], reason: str) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO position_token_locks (
                lock_id, paper_position_id, market_id, side, source, status,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, 'paper_fill_orderbook_snapshot', 'MISSING_POSITION_TOKEN', %s)
            ON CONFLICT (paper_position_id) DO UPDATE
            SET status='MISSING_POSITION_TOKEN',
                metadata_json=position_token_locks.metadata_json || EXCLUDED.metadata_json
            RETURNING *
            """,
            (f"position_token_lock_{position['id']}", str(position["id"]), position.get("market_id"), position.get("intended_outcome"), Jsonb({"reason": reason})),
        ).fetchone()
        return _json_safe(dict(row))

    def _update_lock_success(self, conn: Any, lock: dict[str, Any], *, metrics: dict[str, Any], snapshot_id: int | None) -> None:
        conn.execute(
            """
            UPDATE position_token_locks
            SET last_verified_at=now(),
                metadata_json=COALESCE(metadata_json,'{}'::jsonb) || %s
            WHERE lock_id=%s
            """,
            (Jsonb({"last_snapshot_id": snapshot_id, "last_best_bid": metrics.get("best_bid"), "last_best_ask": metrics.get("best_ask"), "last_spread": metrics.get("spread"), "last_liquidity_score": metrics.get("liquidity_score")}), lock["lock_id"]),
        )

    def _refresh_position_awareness(self, conn: Any, position: dict[str, Any]) -> None:
        session = self._position_repo.ensure_position_session(conn, position)
        self._position_awareness.refresh_session_with_conn(conn, str(session["session_id"]))

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "open_position_watchdog_runs"):
                return
            conn.execute(
                """
                INSERT INTO open_position_watchdog_runs (
                    run_id, cycle_id, started_at, finished_at, system_power, status,
                    dry_run, positions_checked, locks_created, orderbooks_refreshed,
                    pnl_changed_count, spread_widened_count, liquidity_dropped_count,
                    token_unavailable_count, exit_review_count, hold_review_count,
                    events_published, errors_count, blocker_counts_json,
                    safety_counts_before_json, safety_counts_after_json,
                    live_orders_delta, real_orders_delta, metadata_json, error_message
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(started_at)s, %(finished_at)s,
                    %(system_power)s, %(status)s, %(dry_run)s,
                    %(positions_checked)s, %(locks_created)s,
                    %(orderbooks_refreshed)s, %(pnl_changed_count)s,
                    %(spread_widened_count)s, %(liquidity_dropped_count)s,
                    %(token_unavailable_count)s, %(exit_review_count)s,
                    %(hold_review_count)s, %(events_published)s,
                    %(errors_count)s, %(blocker_counts_json)s,
                    %(safety_counts_before_json)s, %(safety_counts_after_json)s,
                    %(live_orders_delta)s, %(real_orders_delta)s, %(metadata_json)s,
                    %(error_message)s
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                {
                    **payload,
                    "blocker_counts_json": Jsonb(_json_safe(payload.get("blocker_counts") or {})),
                    "safety_counts_before_json": Jsonb(_json_safe(payload.get("safety_counts_before") or {})),
                    "safety_counts_after_json": Jsonb(_json_safe(payload.get("safety_counts_after") or {})),
                    "metadata_json": Jsonb(_json_safe(payload.get("metadata") or {})),
                },
            )

    def _blocked_payload(self, run_id: str, cycle_id: str | None, system_power: str, started_at: datetime, dry_run: bool, reason: str) -> dict[str, Any]:
        safety = self._safety_counts()
        counts = self._counts()
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "system_power": system_power,
            "status": "BLOCKED",
            "dry_run": dry_run,
            "positions_checked": 0,
            "locks_created": 0,
            "orderbooks_refreshed": 0,
            "pnl_changed_count": 0,
            "spread_widened_count": 0,
            "liquidity_dropped_count": 0,
            "token_unavailable_count": 0,
            "exit_review_count": 0,
            "hold_review_count": 0,
            "events_published": 0,
            "errors_count": 0,
            "blocker_counts": {reason: 1},
            "safety_counts_before": safety,
            "safety_counts_after": safety,
            "live_orders_delta": 0,
            "real_orders_delta": 0,
            "metadata": {"reason": reason, "counts": counts, "security_governance_status": SECURITY_GOVERNANCE_STATUS},
            "error_message": reason,
            "before": counts,
            "after": counts,
            "latest_traces": [],
        }

    def _list_open_positions(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_positions"):
            return []
        rows = conn.execute(
            """
            SELECT *
            FROM paper_positions
            WHERE current_status IN ('OPEN', 'EXIT_PENDING')
              AND closed_at IS NULL
              AND COALESCE(excluded_from_active_paper_truth, false) = false
            ORDER BY updated_at DESC NULLS LAST, opened_at DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _get_position(self, conn: Any, paper_position_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "paper_positions"):
            return None
        row = conn.execute("SELECT * FROM paper_positions WHERE id::text=%s LIMIT 1", (paper_position_id,)).fetchone()
        return dict(row) if row else None

    def _get_lock(self, conn: Any, paper_position_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "position_token_locks"):
            return None
        row = conn.execute("SELECT * FROM position_token_locks WHERE paper_position_id=%s LIMIT 1", (paper_position_id,)).fetchone()
        if not row:
            return None
        payload = _json_safe(dict(row))
        metadata = payload.get("metadata_json") if isinstance(payload.get("metadata_json"), dict) else {}
        for key in ("last_snapshot_id", "last_best_bid", "last_best_ask", "last_spread", "last_liquidity_score"):
            if key in metadata and payload.get(key) is None:
                payload[key] = metadata[key]
        return payload

    def _condition_for_market(self, conn: Any, market_id: str) -> str | None:
        if not market_id:
            return None
        for table in ("markets_v2", "live_orderbook_watchlist"):
            if _table_exists(conn, table):
                row = conn.execute(f"SELECT condition_id FROM {table} WHERE market_id=%s AND condition_id IS NOT NULL ORDER BY 1 LIMIT 1", (market_id,)).fetchone()
                if row and _clean(row.get("condition_id")):
                    return str(row["condition_id"])
        return None

    def _token_identity_drift(self, conn: Any, lock: dict[str, Any]) -> str | None:
        if not _table_exists(conn, "live_orderbook_watchlist"):
            return None
        row = conn.execute(
            """
            SELECT token_id
            FROM live_orderbook_watchlist
            WHERE market_id=%s AND side=%s AND status='ACTIVE'
            ORDER BY last_success_at DESC NULLS LAST, updated_at DESC
            LIMIT 1
            """,
            (lock.get("market_id"), lock.get("side")),
        ).fetchone()
        if row and _clean(row.get("token_id")) and str(row["token_id"]) != str(lock.get("token_id")):
            return str(row["token_id"])
        return None

    def _latest_run(self) -> dict[str, Any] | None:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "open_position_watchdog_runs"):
                return None
            row = conn.execute("SELECT * FROM open_position_watchdog_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _latest_traces(self, *, limit: int, paper_position_id: str | None = None) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "open_position_watchdog_traces"):
                return []
            where = "WHERE paper_position_id=%s" if paper_position_id else ""
            params: list[Any] = [paper_position_id] if paper_position_id else []
            params.append(limit)
            rows = conn.execute(
                f"""
                SELECT *
                FROM open_position_watchdog_traces
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _latest_reactions(self, *, limit: int, paper_position_id: str | None = None) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "position_reactions"):
                return []
            where = "WHERE position_id=%s AND source_component='Open Position Watchdog'" if paper_position_id else "WHERE source_component='Open Position Watchdog'"
            params: list[Any] = [paper_position_id] if paper_position_id else []
            params.append(limit)
            rows = conn.execute(
                f"""
                SELECT *
                FROM position_reactions
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _counts(self) -> dict[str, int]:
        with self._factory.connect() as conn:
            return {
                "open_positions": _count_where(conn, "paper_positions", "current_status IN ('OPEN','EXIT_PENDING') AND closed_at IS NULL AND COALESCE(excluded_from_active_paper_truth,false)=false"),
                "closed_positions": _count_where(conn, "paper_positions", "closed_at IS NOT NULL OR current_status='CLOSED'"),
                "quarantined_legacy_positions": _count_where(conn, "paper_positions", "COALESCE(excluded_from_active_paper_truth,false)=true OR current_status='QUARANTINED'"),
                "token_locks": _count_where(conn, "position_token_locks", "status='ACTIVE'"),
                "missing_token_locks": _count_where(conn, "position_token_locks", "status='MISSING_POSITION_TOKEN'"),
                "watchdog_runs": _count_table(conn, "open_position_watchdog_runs"),
                "watchdog_traces": _count_table(conn, "open_position_watchdog_traces"),
                "position_reactions": _count_where(conn, "position_reactions", "source_component='Open Position Watchdog'"),
                "POSITION_ORDERBOOK_REFRESHED": _count_where(conn, "neural_events", "event_type='POSITION_ORDERBOOK_REFRESHED' AND source_component='Open Position Watchdog'"),
                "PNL_CHANGED": _count_where(conn, "neural_events", "event_type='PNL_CHANGED' AND source_component='Open Position Watchdog'"),
                "POSITION_EXIT_RISK": _count_where(conn, "neural_events", "event_type='POSITION_EXIT_RISK' AND source_component='Open Position Watchdog'"),
                "TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION": _count_where(conn, "neural_events", "event_type='TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION' AND source_component='Open Position Watchdog'"),
                "EXIT_REVIEW": _count_where(conn, "neural_events", "event_type='EXIT_REVIEW' AND source_component='Open Position Watchdog'"),
                "HOLD_REVIEW": _count_where(conn, "neural_events", "event_type='HOLD_REVIEW' AND source_component='Open Position Watchdog'"),
                "position_awareness": _count_table(conn, "position_awareness"),
                "mesh_sessions": _count_table(conn, "mesh_sessions"),
                "shared_awareness": _count_table(conn, "mesh_shared_awareness"),
                "brain_opinions": _count_table(conn, "mesh_brain_opinions"),
                "coordinator_decisions": _count_table(conn, "mesh_coordinator_decisions"),
                **self._safety_counts(conn),
            }

    def _safety_counts(self, conn: Any | None = None) -> dict[str, int]:
        if conn is not None:
            return _safety_counts(conn)
        with self._factory.connect() as local:
            return _safety_counts(local)


class _WatchdogHttpClient:
    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[Any, int]:
        started = time.perf_counter()
        with httpx.Client(timeout=12.0, headers={"User-Agent": "POLYBOT-open-position-watchdog/1.0"}) as client:
            response = client.get(url, params=params)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def _safety_counts(conn: Any) -> dict[str, int]:
    return {
        "live_orders": _count_table(conn, "live_orders"),
        "paper_intents": _count_table(conn, "paper_intents"),
        "paper_orders": _count_table(conn, "paper_orders"),
        "paper_fills": _count_table(conn, "paper_fills"),
        "paper_positions": _count_table(conn, "paper_positions"),
        "paper_position_closes": _count_table(conn, "paper_position_closes"),
        "paper_capital_ledger": _count_table(conn, "paper_capital_ledger"),
        "orders_v2": _count_table(conn, "orders_v2"),
        "fills_v2": _count_table(conn, "fills_v2"),
        "canonical_positions": _count_table(conn, "positions"),
    }


def _estimate_pnl(position: dict[str, Any], current_price: Decimal | None) -> Decimal | None:
    entry = _decimal(position.get("avg_entry"))
    size = _decimal(position.get("size"))
    if entry is None or size is None or current_price is None:
        return None
    return (current_price - entry) * size


def _pnl_changed(previous: Decimal | None, current: Decimal | None) -> bool:
    if previous is None or current is None:
        return current is not None
    delta = abs(current - previous)
    if delta >= PNL_ABS_THRESHOLD:
        return True
    base = abs(previous)
    return base > 0 and delta / base >= PNL_REL_THRESHOLD


def _worsened(old: Any, new: Any, *, abs_threshold: Decimal, rel_threshold: Decimal) -> bool:
    old_dec = _decimal(old)
    new_dec = _decimal(new)
    if old_dec is None or new_dec is None:
        return False
    return new_dec > old_dec and _decimal_changed(old_dec, new_dec, abs_threshold=abs_threshold, rel_threshold=rel_threshold)


def _dropped(old: Any, new: Any, *, abs_threshold: Decimal, rel_threshold: Decimal) -> bool:
    old_dec = _decimal(old)
    new_dec = _decimal(new)
    if old_dec is None or new_dec is None:
        return False
    return new_dec < old_dec and _decimal_changed(old_dec, new_dec, abs_threshold=abs_threshold, rel_threshold=rel_threshold)


def _decimal_changed(old: Decimal, new: Decimal, *, abs_threshold: Decimal, rel_threshold: Decimal) -> bool:
    delta = abs(new - old)
    if delta >= abs_threshold:
        return True
    base = abs(old)
    return base > 0 and delta / base >= rel_threshold


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value).lower())[:120]


def _error_summary(identifier: Any, exc: Exception) -> str:
    return redact_secrets(f"{identifier}: {type(exc).__name__}: {exc}")[:300]


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value

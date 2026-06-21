from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository
from app.services.open_position_watchdog import OpenPositionWatchdogService
from app.services.system_power import SystemPowerService


class _FakeCLOB:
    def __init__(self, payloads: dict[str, Any]) -> None:
        self.payloads = payloads
        self.calls: list[dict[str, Any]] = []

    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[dict[str, object], int]:
        token_id = str((params or {}).get("token_id"))
        self.calls.append({"url": url, "params": dict(params or {})})
        payload = self.payloads.get(token_id)
        if isinstance(payload, Exception):
            raise payload
        if payload is None:
            raise RuntimeError("token not found")
        return payload, 5


def _book(*, token: str, condition: str, bid: str = "0.56", ask: str = "0.57", bid_size: str = "1000", ask_size: str = "1000") -> dict[str, object]:
    return {
        "market": condition,
        "asset_id": token,
        "bids": [{"price": bid, "size": bid_size}],
        "asks": [{"price": ask, "size": ask_size}],
    }


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "open_position_watchdog_traces",
            "open_position_watchdog_runs",
            "position_token_locks",
            "position_context_sources",
            "position_reactions",
            "position_awareness",
            "mesh_coordinator_decisions",
            "mesh_brain_opinions",
            "mesh_shared_awareness",
            "mesh_awareness_sources",
            "mesh_session_events",
            "mesh_session_participants",
            "mesh_sessions",
            "neural_events",
            "live_orderbook_watchlist",
            "paper_fills",
            "paper_orders",
            "paper_signals",
            "paper_intents",
            "paper_positions",
            "paper_runs",
            "orderbook_snapshots",
            "markets_v2",
            "live_orders",
            "orders_v2",
            "fills_v2",
            "positions",
            "system_power_transitions",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")
    SystemPowerService().turn_on(actor="test", reason="open-position-watchdog-prepare")


def _insert_open_position(
    slug: str,
    *,
    token: str | None = "__AUTO__",
    condition: str | None = None,
    status: str = "OPEN",
    excluded: bool = False,
    previous_unrealized: str = "0.00",
) -> dict[str, str]:
    run_id = str(uuid4())
    signal_id = str(uuid4())
    order_id = str(uuid4())
    position_id = str(uuid4())
    market_id = f"position-market-{slug}"
    condition_id = condition or f"condition-{slug}"
    token_id = f"900000000000000000000000000000000000000000000000000000000000{abs(hash(slug)) % 1000000:06d}" if token == "__AUTO__" else (token or "")
    intent_id = f"paper_intent_{slug}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (market_id, condition_id, question, slug, accepting_orders, closed, archived, active, raw_market_json)
            VALUES (%s, %s, %s, %s, true, false, false, true, '{}'::jsonb)
            """,
            (market_id, condition_id, f"Question {slug}?", f"slug-{slug}"),
        )
        snapshot = OrderbookSnapshotter().normalize_orderbook(
            _book(token=token_id, condition=condition_id, bid="0.49", ask="0.50"),
            market_id=market_id,
            token_id=token_id,
            side="YES",
            source="test_entry",
        )
        if token is None:
            snapshot.token_id = None
        OrderbookSnapshotRepository().append_snapshot(conn, snapshot)
        snapshot_row = conn.execute("SELECT id FROM orderbook_snapshots WHERE orderbook_snapshot_id=%s", (snapshot.orderbook_snapshot_id,)).fetchone()
        snapshot_id = int(snapshot_row["id"])
        conn.execute("INSERT INTO paper_runs (id, mode, started_at, status, metadata_json) VALUES (%s, 'PAPER', now(), 'COMPLETED', '{}'::jsonb)", (run_id,))
        conn.execute(
            """
            INSERT INTO paper_signals (
                id, paper_run_id, market_id, signal_type, intended_outcome, guard_result,
                reason_code, reason_text, payload_json
            )
            VALUES (%s, %s, %s, 'WOULD_ENTER', 'YES', 'PASS', 'test', 'test', '{}'::jsonb)
            """,
            (signal_id, run_id, market_id),
        )
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, market_id, side, price_basis, orderbook_snapshot_id,
                intended_price, intent_status, intent_type, intent_reason
            )
            VALUES (%s, %s, 'thesis', 'risk', 'exit', %s, 'YES', 'BEST_ASK', %s, 0.50, 'CREATED', 'PAPER_ENTRY_INTENT', 'test')
            """,
            (intent_id, f"eligibility_{slug}", market_id, snapshot_id),
        )
        conn.execute(
            """
            INSERT INTO paper_orders (
                id, paper_run_id, paper_signal_id, market_id, intended_outcome,
                action, intended_price, intended_size, notional, status,
                fill_ratio, filled_size, remaining_size, avg_fill_price,
                min_size_check_passed, payload_json
            )
            VALUES (%s, %s, %s, %s, 'YES', 'BUY', 0.50, 10, 5, 'FILLED', 1, 10, 0, 0.50, true, '{}'::jsonb)
            """,
            (order_id, run_id, signal_id, market_id),
        )
        fill_id = f"paper_fill_{slug}"
        conn.execute(
            """
            INSERT INTO paper_fills (
                paper_fill_id, paper_order_id, source_intent_id, market_id, side,
                fill_price, quantity, price_basis, orderbook_snapshot_id, metadata_json
            )
            VALUES (%s, %s, %s, %s, 'YES', 0.50, 10, 'BEST_ASK', %s, '{}'::jsonb)
            """,
            (fill_id, order_id, intent_id, market_id, snapshot_id),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry,
                mark_price, unrealized, realized, current_status, thesis_state,
                invalidation_state, opened_at, updated_at, closed_at, payload_json,
                excluded_from_active_paper_truth
            )
            VALUES (
                %s, %s, %s, 'YES', 10, 0.50, 0.50, %s, 0, %s,
                'VALID', 'NONE', now(), now(), NULL, %s, %s
            )
            """,
            (position_id, run_id, market_id, previous_unrealized, status, Jsonb({"paper_fill_id": fill_id}), excluded),
        )
    return {"position_id": position_id, "market_id": market_id, "condition_id": condition_id, "token_id": token_id}


def _count(table: str, where: str = "true") -> int:
    with DatabaseConnectionFactory().connect() as conn:
        return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def _rows(table: str) -> list[dict[str, Any]]:
    with DatabaseConnectionFactory().connect() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]


def test_open_position_creates_token_lock_from_fill_orderbook_truth(postgres_test_schema) -> None:
    _prepare()
    ids = _insert_open_position("lock")
    service = OpenPositionWatchdogService(clob_client=_FakeCLOB({ids["token_id"]: _book(token=ids["token_id"], condition=ids["condition_id"])}))

    result = service.run(limit=1, max_seconds=10)

    assert result["errors_count"] == 0, result.get("error_message")
    assert result["locks_created"] == 1, result
    assert _count("position_token_locks", f"paper_position_id='{ids['position_id']}' AND token_id='{ids['token_id']}' AND status='ACTIVE'") == 1, (result, _rows("position_token_locks"), _rows("open_position_watchdog_traces"))
    assert service.get_dashboard_summary()["mock_data"] is False


def test_missing_token_does_not_create_fake_lock(postgres_test_schema) -> None:
    _prepare()
    _insert_open_position("missing", token=None)

    result = OpenPositionWatchdogService(clob_client=_FakeCLOB({})).run(limit=1, max_seconds=10)

    assert result["blocker_counts"].get("MISSING_POSITION_TOKEN") == 1
    assert _count("position_token_locks", "status='ACTIVE'") == 0
    assert _count("neural_events", "event_type='MISSING_POSITION_TOKEN'") == 1


def test_closed_and_quarantined_positions_are_not_watched(postgres_test_schema) -> None:
    _prepare()
    closed = _insert_open_position("closed", status="CLOSED")
    quarantined = _insert_open_position("quarantine", status="QUARANTINED", excluded=True)

    result = OpenPositionWatchdogService(clob_client=_FakeCLOB({})).run(limit=5, max_seconds=10)

    assert result["positions_checked"] == 0
    assert result["blocker_counts"] == {"NO_OPEN_POSITIONS": 1}
    assert _count("position_token_locks", f"paper_position_id IN ('{closed['position_id']}','{quarantined['position_id']}')") == 0


def test_valid_position_book_publishes_refresh_pnl_and_exit_review(postgres_test_schema) -> None:
    _prepare()
    ids = _insert_open_position("refresh", previous_unrealized="0.00")
    result = OpenPositionWatchdogService(
        clob_client=_FakeCLOB({ids["token_id"]: _book(token=ids["token_id"], condition=ids["condition_id"], bid="0.62", ask="0.63")})
    ).run(limit=1, max_seconds=10)

    assert result["orderbooks_refreshed"] == 1
    assert result["pnl_changed_count"] == 1
    assert result["exit_review_count"] == 1
    assert _count("orderbook_snapshots", "source='open_position_watchdog'") == 1
    assert _count("neural_events", "event_type='POSITION_ORDERBOOK_REFRESHED' AND source_component='Open Position Watchdog'") == 1
    assert _count("neural_events", "event_type='PNL_CHANGED' AND source_component='Open Position Watchdog'") == 1
    assert _count("position_awareness") == 1
    assert _count("mesh_session_events", "source_component='Open Position Watchdog'") >= 1
    assert _count("position_reactions", "source_component='Open Position Watchdog' AND reaction_type='EXIT_REVIEW'") == 1


def test_spread_widened_and_liquidity_drop_emit_exit_risk(postgres_test_schema) -> None:
    _prepare()
    ids = _insert_open_position("risk")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO position_token_locks (
                lock_id, paper_position_id, market_id, condition_id, side,
                token_id, status, metadata_json
            )
            VALUES (%s, %s, %s, %s, 'YES', %s, 'ACTIVE', %s)
            """,
            (
                f"position_token_lock_{ids['position_id']}",
                ids["position_id"],
                ids["market_id"],
                ids["condition_id"],
                ids["token_id"],
                Jsonb({"last_spread": 0.001, "last_liquidity_score": 0.9}),
            ),
        )

    result = OpenPositionWatchdogService(
        clob_client=_FakeCLOB({ids["token_id"]: _book(token=ids["token_id"], condition=ids["condition_id"], bid="0.40", ask="0.50", bid_size="1", ask_size="1")})
    ).run(limit=1, max_seconds=10)

    assert result["spread_widened_count"] == 1
    assert result["liquidity_dropped_count"] == 1
    assert result["exit_review_count"] == 1
    assert _count("neural_events", "event_type='POSITION_EXIT_RISK' AND source_component='Open Position Watchdog'") == 1


def test_token_unavailable_emits_position_risk_without_fake_book(postgres_test_schema) -> None:
    _prepare()
    ids = _insert_open_position("unavailable")

    result = OpenPositionWatchdogService(clob_client=_FakeCLOB({})).run(limit=1, max_seconds=10)

    assert result["token_unavailable_count"] == 1
    assert result["exit_review_count"] == 1
    assert _count("orderbook_snapshots", "source='open_position_watchdog'") == 0
    assert _count("neural_events", "event_type='TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION' AND source_component='Open Position Watchdog'") == 1


def test_stable_position_emits_hold_review(postgres_test_schema) -> None:
    _prepare()
    ids = _insert_open_position("hold", previous_unrealized="0.00")

    result = OpenPositionWatchdogService(
        clob_client=_FakeCLOB({ids["token_id"]: _book(token=ids["token_id"], condition=ids["condition_id"], bid="0.50", ask="0.51")})
    ).run(limit=1, max_seconds=10)

    assert result["hold_review_count"] == 1
    assert _count("neural_events", "event_type='HOLD_REVIEW' AND source_component='Open Position Watchdog'") == 1


def test_token_identity_drift_does_not_overwrite_lock(postgres_test_schema) -> None:
    _prepare()
    ids = _insert_open_position("drift")
    drift_token = ids["token_id"] + "999"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO position_token_locks (
                lock_id, paper_position_id, market_id, condition_id, side,
                token_id, status, metadata_json
            )
            VALUES (%s, %s, %s, %s, 'YES', %s, 'ACTIVE', '{}'::jsonb)
            """,
            (f"position_token_lock_{ids['position_id']}", ids["position_id"], ids["market_id"], ids["condition_id"], ids["token_id"]),
        )
        conn.execute(
            """
            INSERT INTO live_orderbook_watchlist (
                watch_id, market_id, condition_id, side, token_id, source_type,
                source_id, priority, status
            )
            VALUES (%s, %s, %s, 'YES', %s, 'test', 'drift', 1, 'ACTIVE')
            """,
            (f"live_watch_{ids['market_id']}_YES_{drift_token}", ids["market_id"], ids["condition_id"], drift_token),
        )

    result = OpenPositionWatchdogService(clob_client=_FakeCLOB({})).run(limit=1, max_seconds=10)

    assert result["blocker_counts"].get("TOKEN_IDENTITY_DRIFT_REVIEW") == 1
    assert _count("position_token_locks", f"paper_position_id='{ids['position_id']}' AND token_id='{ids['token_id']}'") == 1
    assert _count("neural_events", "event_type='TOKEN_IDENTITY_DRIFT_REVIEW'") == 1


def test_system_off_blocks_watchdog_and_no_trading_mutation(postgres_test_schema) -> None:
    _prepare()
    ids = _insert_open_position("off")
    before = {table: _count(table) for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2", "positions")}
    SystemPowerService().turn_off(actor="test", reason="watchdog-off")

    result = OpenPositionWatchdogService(clob_client=_FakeCLOB({ids["token_id"]: _book(token=ids["token_id"], condition=ids["condition_id"])})).run(limit=1)

    after = {table: _count(table) for table in before}
    assert result["status"] == "BLOCKED"
    assert result["blocker_counts"] == {"SYSTEM_POWER_OFF": 1}
    assert before == after

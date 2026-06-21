from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.decision_ledger_repository import DecisionLedgerRepository
from app.repositories.paper_order_events_repository import PaperOrderEventsRepository
from app.repositories.paper_orders_repository import PaperOrdersRepository
from app.repositories.paper_position_events_repository import PaperPositionEventsRepository
from app.repositories.paper_positions_repository import PaperPositionsRepository
from app.repositories.paper_runs_repository import PaperRunsRepository
from app.repositories.paper_signals_repository import PaperSignalsRepository
from app.repositories.shadow_order_events_repository import ShadowOrderEventsRepository
from app.repositories.shadow_orders_repository import ShadowOrdersRepository
from app.repositories.shadow_position_events_repository import ShadowPositionEventsRepository
from app.repositories.shadow_positions_repository import ShadowPositionsRepository
from app.repositories.shadow_runs_repository import ShadowRunsRepository


class PaperQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = PaperRunsRepository()
        self._signals = PaperSignalsRepository()
        self._decisions = DecisionLedgerRepository()
        self._orders = PaperOrdersRepository()
        self._order_events = PaperOrderEventsRepository()
        self._positions = PaperPositionsRepository()
        self._position_events = PaperPositionEventsRepository()
        self._shadow_runs = ShadowRunsRepository()
        self._shadow_orders = ShadowOrdersRepository()
        self._shadow_order_events = ShadowOrderEventsRepository()
        self._shadow_positions = ShadowPositionsRepository()
        self._shadow_position_events = ShadowPositionEventsRepository()

    def get_paper_run_summary(self, paper_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            paper_run = self._runs.get_by_id(conn, paper_run_id)
            if paper_run is None:
                return None
            signals = self._signals.list_for_run(conn, paper_run_id)
        return {
            "paper_run": dict(paper_run),
            "signal_counts": {
                "would_enter": sum(1 for row in signals if row["signal_type"] == "WOULD_ENTER"),
                "would_skip": sum(1 for row in signals if row["signal_type"] == "WOULD_SKIP"),
                "would_block": sum(1 for row in signals if row["signal_type"] == "WOULD_BLOCK"),
                "no_action": sum(1 for row in signals if row["signal_type"] == "NO_ACTION"),
            },
            "execution_counts": {
                "paper_orders": sum(1 for _ in self.list_open_paper_orders(paper_run_id)),
                "paper_positions": sum(1 for _ in self.list_open_paper_positions(paper_run_id)),
            },
        }

    def list_paper_signals_for_run(self, paper_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._signals.list_for_run(conn, paper_run_id)
        return [dict(row) for row in rows]

    def get_paper_signal_details(self, paper_signal_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            row = self._signals.get_by_id(conn, paper_signal_id)
        return dict(row) if row is not None else None

    def compare_cycle_decision_to_paper_signal(self, paper_signal_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            signal = self._signals.get_by_id(conn, paper_signal_id)
            if signal is None:
                return None
            decision = None
            if signal["cycle_id"] is not None:
                decision = self._decisions.get_for_cycle_market(
                    conn,
                    cycle_id=str(signal["cycle_id"]),
                    market_id=str(signal["market_id"]),
                )
        return {
            "paper_signal": dict(signal),
            "decision": dict(decision) if decision is not None else None,
        }

    def get_paper_order_history(
        self,
        *,
        paper_run_id: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object]:
        if not paper_run_id and not market_id:
            raise ValueError("paper_run_id or market_id is required")
        with self._factory.connect() as conn:
            if paper_run_id:
                orders = self._orders.list_for_run(conn, paper_run_id)
            else:
                orders = self._orders.list_for_market(conn, market_id or "")
            events = []
            for order in orders:
                events.extend(self._order_events.list_for_order(conn, str(order["id"])))
        events.sort(key=lambda row: (row["event_at"], row["created_at"]))
        return {
            "orders": [dict(row) for row in orders],
            "events": [dict(row) for row in events],
        }

    def get_paper_position_lifecycle(self, paper_position_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            position = self._positions.get_by_id(conn, paper_position_id)
            if position is None:
                return None
            events = self._position_events.list_for_position(conn, paper_position_id)
        return {
            "position": dict(position),
            "events": [dict(row) for row in events],
        }

    def get_execution_aware_paper_run_summary(self, paper_run_id: str) -> dict[str, object] | None:
        summary = self.get_paper_run_summary(paper_run_id)
        if summary is None:
            return None
        order_history = self.get_paper_order_history(paper_run_id=paper_run_id)
        summary["order_status_counts"] = {
            "created": sum(1 for row in order_history["orders"] if row["status"] == "CREATED"),
            "open": sum(1 for row in order_history["orders"] if row["status"] == "OPEN"),
            "partially_filled": sum(1 for row in order_history["orders"] if row["status"] == "PARTIALLY_FILLED"),
            "filled": sum(1 for row in order_history["orders"] if row["status"] == "FILLED"),
            "blocked_min_size": sum(1 for row in order_history["orders"] if row["status"] == "BLOCKED_MIN_SIZE"),
            "expired": sum(1 for row in order_history["orders"] if row["status"] == "EXPIRED"),
        }
        return summary

    def list_open_paper_orders(self, paper_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._orders.list_open_for_run(conn, paper_run_id)
        return [dict(row) for row in rows]

    def list_open_paper_positions(self, paper_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._positions.list_open_for_run(conn, paper_run_id)
        return [dict(row) for row in rows]

    def get_shadow_run_summary(self, shadow_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            shadow_run = self._shadow_runs.get_by_id(conn, shadow_run_id)
            if shadow_run is None:
                return None
            orders = self._shadow_orders.list_for_run(conn, shadow_run_id)
            positions = self._shadow_positions.list_for_run(conn, shadow_run_id)
        return {
            "shadow_run": dict(shadow_run),
            "order_counts": {
                "blocked": sum(
                    1
                    for row in orders
                    if row["status"] in {"BLOCKED", "WOULD_REJECT", "BLOCKED_BY_RISK", "BLOCKED_BY_CONFIG", "INVALID_REQUEST"}
                ),
                "would_submit": sum(1 for row in orders if row["status"] == "WOULD_SUBMIT"),
            },
            "position_counts": {
                "pending_submission": sum(1 for row in positions if row["current_status"] == "PENDING_SUBMISSION"),
            },
        }

    def list_shadow_orders_for_run(self, shadow_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._shadow_orders.list_for_run(conn, shadow_run_id)
        return [dict(row) for row in rows]

    def get_shadow_order_details(self, shadow_order_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            order = self._shadow_orders.get_by_id(conn, shadow_order_id)
            if order is None:
                return None
            events = self._shadow_order_events.list_for_order(conn, shadow_order_id)
        return {
            "shadow_order": dict(order),
            "events": [dict(row) for row in events],
        }

    def get_shadow_position_lifecycle(self, shadow_position_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            position = self._shadow_positions.get_by_id(conn, shadow_position_id)
            if position is None:
                return None
            events = self._shadow_position_events.list_for_position(conn, shadow_position_id)
        return {
            "shadow_position": dict(position),
            "events": [dict(row) for row in events],
        }

    def compare_shadow_order_to_paper_order_or_signal(self, shadow_order_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            order = self._shadow_orders.get_by_id(conn, shadow_order_id)
            if order is None:
                return None
            paper_signals = []
            paper_orders = []
            if order["cycle_id"] is not None:
                paper_signals = conn.execute(
                    """
                    SELECT *
                    FROM paper_signals
                    WHERE cycle_id = %s AND market_id = %s
                    ORDER BY created_at ASC
                    """,
                    (order["cycle_id"], order["market_id"]),
                ).fetchall()
                paper_orders = conn.execute(
                    """
                    SELECT po.*
                    FROM paper_orders po
                    JOIN paper_signals ps ON ps.id = po.paper_signal_id
                    WHERE po.cycle_id = %s AND po.market_id = %s
                    ORDER BY po.created_at ASC
                    """,
                    (order["cycle_id"], order["market_id"]),
                ).fetchall()
        return {
            "shadow_order": dict(order),
            "paper_signals": [dict(row) for row in paper_signals],
            "paper_orders": [dict(row) for row in paper_orders],
        }

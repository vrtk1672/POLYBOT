from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.cycle_repository import CycleRepository
from app.repositories.decision_ledger_repository import DecisionLedgerRepository
from app.repositories.live_orders_repository import LiveOrdersRepository
from app.repositories.market_snapshots_repository import MarketSnapshotsRepository
from app.repositories.order_status_history_repository import OrderStatusHistoryRepository
from app.repositories.position_events_repository import PositionEventsRepository
from app.repositories.positions_repository import PositionsRepository
from app.repositories.ranking_snapshots_repository import RankingSnapshotsRepository
from app.repositories.rejection_ledger_repository import RejectionLedgerRepository
from app.repositories.run_artifacts_repository import RunArtifactsRepository


class Phase1QueryService:
    def __init__(
        self,
        connection_factory: DatabaseConnectionFactory | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._cycles = CycleRepository()
        self._markets = MarketSnapshotsRepository()
        self._rankings = RankingSnapshotsRepository()
        self._decisions = DecisionLedgerRepository()
        self._rejections = RejectionLedgerRepository()
        self._artifacts = RunArtifactsRepository()
        self._orders = LiveOrdersRepository()
        self._order_history = OrderStatusHistoryRepository()
        self._positions = PositionsRepository()
        self._position_events = PositionEventsRepository()

    def get_cycle_summary(self, cycle_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            cycle = self._cycles.get_cycle(conn, cycle_id)
            if cycle is None:
                return None
            artifacts = self._artifacts.list_for_cycle(conn, cycle_id)
        return {
            "cycle": dict(cycle),
            "selected_market_id": (
                str(cycle["selected_market_id"])
                if cycle["selected_market_id"] is not None
                else None
            ),
            "artifact_count": len(artifacts),
            "artifacts": [_serialize_artifact(row) for row in artifacts],
        }

    def get_cycle_rejections(self, cycle_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._rejections.list_for_cycle(conn, cycle_id)
        return [_serialize_rejection(row) for row in rows]

    def get_market_decision_details(
        self,
        cycle_id: str,
        market_id: str,
    ) -> dict[str, object]:
        with self._factory.connect() as conn:
            market_snapshot = self._markets.get_for_cycle_market(conn, cycle_id=cycle_id, market_id=market_id)
            ranking_snapshot = self._rankings.get_for_cycle_market(conn, cycle_id=cycle_id, market_id=market_id)
            decision = self._decisions.get_for_cycle_market(conn, cycle_id=cycle_id, market_id=market_id)
            rejections = self._rejections.list_for_cycle_market(conn, cycle_id=cycle_id, market_id=market_id)
            artifacts = self._artifacts.list_for_cycle_market(conn, cycle_id=cycle_id, market_id=market_id)
        return {
            "cycle_id": cycle_id,
            "market_id": market_id,
            "market_snapshot": dict(market_snapshot) if market_snapshot else None,
            "ranking_snapshot": dict(ranking_snapshot) if ranking_snapshot else None,
            "decision": dict(decision) if decision else None,
            "rejections": [_serialize_rejection(row) for row in rejections],
            "artifacts": [_serialize_artifact(row) for row in artifacts],
        }

    def get_market_order_history(self, market_id: str) -> dict[str, object]:
        with self._factory.connect() as conn:
            orders = self._orders.list_for_market(conn, market_id)
            history_rows = []
            for order in orders:
                history_rows.extend(self._order_history.list_for_order(conn, str(order["id"])))
        history_rows.sort(key=lambda row: (row["event_at"], row["created_at"]))
        return {
            "market_id": market_id,
            "orders": [dict(row) for row in orders],
            "status_history": [dict(row) for row in history_rows],
        }

    def get_position_lifecycle(self, position_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            position = self._positions.get_by_id(conn, position_id)
            if position is None:
                return None
            events = self._position_events.list_for_position(conn, position_id)
        return {
            "position": dict(position),
            "events": [dict(row) for row in events],
        }


def _serialize_artifact(row: dict[str, object]) -> dict[str, object]:
    return {
        "artifact_id": str(row["id"]),
        "artifact_type": row["artifact_type"],
        "artifact_scope": row["artifact_scope"],
        "path": row["path"],
        "checksum": row["checksum"],
        "metadata_json": dict(row["metadata_json"]) if isinstance(row.get("metadata_json"), dict) else {},
        "created_at": row["created_at"],
    }


def _serialize_rejection(row: dict[str, object]) -> dict[str, object]:
    return {
        "rejection_id": str(row["id"]),
        "market_id": row["market_id"],
        "stage": row["stage"],
        "reason_code": row["reason_code"],
        "reason_text": row["reason_text"],
        "payload": dict(row["payload"]) if isinstance(row.get("payload"), dict) else {},
        "created_at": row["created_at"],
    }

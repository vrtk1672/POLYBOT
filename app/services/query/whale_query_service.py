from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.whale_events_repository import WhaleEventsRepository
from app.repositories.whale_registry_repository import WhaleRegistryRepository
from app.repositories.whale_scan_runs_repository import WhaleScanRunsRepository


class WhaleQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = WhaleScanRunsRepository()
        self._events = WhaleEventsRepository()
        self._registry = WhaleRegistryRepository()

    def get_whale_scan_run_summary(self, whale_scan_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, whale_scan_run_id)
            if run is None:
                return None
            rows = self._events.list_for_run(conn, whale_scan_run_id)

        direction_counts: dict[str, int] = {}
        market_counts: dict[str, int] = {}
        for row in rows:
            direction = str(row["event_direction_class"])
            direction_counts[direction] = direction_counts.get(direction, 0) + 1
            market = str(row["market_id"])
            market_counts[market] = market_counts.get(market, 0) + 1

        return {
            "run": dict(run),
            "event_count": len(rows),
            "direction_counts": direction_counts,
            "market_counts": market_counts,
        }

    def list_whale_events_for_run(self, whale_scan_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._events.list_for_run(conn, whale_scan_run_id)
        return [dict(row) for row in rows]

    def get_whale_event_details(self, whale_event_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            row = self._events.get_by_id(conn, whale_event_id)
        return dict(row) if row is not None else None

    def list_whale_events_for_wallet(self, wallet_address: str, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._events.list_for_wallet(conn, wallet_address, limit)
        return [dict(row) for row in rows]

    def get_whale_registry_entry(self, wallet_address: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            row = self._registry.get_by_wallet(conn, wallet_address)
        return dict(row) if row is not None else None

    def list_active_whale_registry(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._registry.list_active(conn, limit)
        return [dict(row) for row in rows]

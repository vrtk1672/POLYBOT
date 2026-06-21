from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.whale_profile_runs_repository import WhaleProfileRunsRepository
from app.repositories.whale_profiles_repository import WhaleProfilesRepository
from app.repositories.whale_registry_repository import WhaleRegistryRepository


class WhaleProfileQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = WhaleProfileRunsRepository()
        self._profiles = WhaleProfilesRepository()
        self._registry = WhaleRegistryRepository()

    def get_whale_profile_run_summary(self, whale_profile_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, whale_profile_run_id)
            if run is None:
                return None
            rows = self._profiles.list_for_run(conn, whale_profile_run_id)

        status_counts: dict[str, int] = {}
        for row in rows:
            status = str(row["profile_status"])
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "run": dict(run),
            "profile_count": len(rows),
            "status_counts": status_counts,
        }

    def list_whale_profiles_for_run(self, whale_profile_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._profiles.list_for_run(conn, whale_profile_run_id)
        return [dict(row) for row in rows]

    def get_whale_profile_details(
        self,
        *,
        whale_profile_id: str | None = None,
        wallet_address: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if whale_profile_id is not None:
                row = self._profiles.get_by_id(conn, whale_profile_id)
            elif wallet_address is not None:
                row = self._profiles.get_latest_by_wallet(conn, wallet_address)
            else:
                raise ValueError("whale_profile_id or wallet_address is required")
        return dict(row) if row is not None else None

    def list_top_whale_profiles(self, limit: int = 10, order_by: str = "follow_value_baseline") -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._profiles.list_top_profiles(conn, limit, order_by)
        return [dict(row) for row in rows]

    def compare_whale_profile_to_registry(self, wallet_address: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            profile = self._profiles.get_latest_by_wallet(conn, wallet_address)
            registry = self._registry.get_by_wallet(conn, wallet_address)
        if profile is None and registry is None:
            return None
        return {
            "profile": dict(profile) if profile is not None else None,
            "registry": dict(registry) if registry is not None else None,
        }

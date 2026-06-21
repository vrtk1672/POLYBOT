from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.whale_categories_repository import WhaleCategoriesRepository
from app.repositories.whale_category_runs_repository import WhaleCategoryRunsRepository
from app.repositories.whale_profiles_repository import WhaleProfilesRepository


class WhaleCategoryQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = WhaleCategoryRunsRepository()
        self._categories = WhaleCategoriesRepository()
        self._profiles = WhaleProfilesRepository()

    def get_whale_category_run_summary(self, whale_category_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, whale_category_run_id)
            if run is None:
                return None
            rows = self._categories.list_for_run(conn, whale_category_run_id)

        primary_counts: dict[str, int] = {}
        for row in rows:
            category = str(row["primary_category"])
            primary_counts[category] = primary_counts.get(category, 0) + 1

        return {
            "run": dict(run),
            "category_count": len(rows),
            "primary_counts": primary_counts,
        }

    def list_whale_categories_for_run(self, whale_category_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._categories.list_for_run(conn, whale_category_run_id)
        return [dict(row) for row in rows]

    def get_whale_category_details(
        self,
        *,
        whale_category_id: str | None = None,
        wallet_address: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if whale_category_id is not None:
                row = self._categories.get_by_id(conn, whale_category_id)
            elif wallet_address is not None:
                row = self._categories.get_latest_by_wallet(conn, wallet_address)
            else:
                raise ValueError("whale_category_id or wallet_address is required")
        return dict(row) if row is not None else None

    def list_whale_categories_by_primary(self, primary_category: str, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._categories.list_by_primary(conn, primary_category, limit)
        return [dict(row) for row in rows]

    def compare_whale_category_to_profile(self, wallet_address: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            category = self._categories.get_latest_by_wallet(conn, wallet_address)
            profile = self._profiles.get_latest_by_wallet(conn, wallet_address)
        if category is None and profile is None:
            return None
        return {
            "category": dict(category) if category is not None else None,
            "profile": dict(profile) if profile is not None else None,
        }

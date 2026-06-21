from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.exit_advisory_records_repository import ExitAdvisoryRecordsRepository
from app.repositories.exit_advisory_runs_repository import ExitAdvisoryRunsRepository
from app.repositories.invalidation_policy_records_repository import InvalidationPolicyRecordsRepository
from app.repositories.live_orders_repository import LiveOrdersRepository
from app.repositories.paper_orders_repository import PaperOrdersRepository
from app.repositories.paper_positions_repository import PaperPositionsRepository
from app.repositories.positions_repository import PositionsRepository
from app.repositories.shadow_orders_repository import ShadowOrdersRepository
from app.repositories.shadow_positions_repository import ShadowPositionsRepository


class ExitAdvisoryQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = ExitAdvisoryRunsRepository()
        self._records = ExitAdvisoryRecordsRepository()
        self._policy_records = InvalidationPolicyRecordsRepository()
        self._paper_positions = PaperPositionsRepository()
        self._paper_orders = PaperOrdersRepository()
        self._shadow_positions = ShadowPositionsRepository()
        self._shadow_orders = ShadowOrdersRepository()
        self._live_positions = PositionsRepository()
        self._live_orders = LiveOrdersRepository()

    def get_exit_advisory_run_summary(self, exit_advisory_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, exit_advisory_run_id)
            if run is None:
                return None
            rows = self._records.list_for_run(conn, exit_advisory_run_id)

        action_counts: dict[str, int] = {}
        priority_counts: dict[str, int] = {}
        for row in rows:
            action_key = str(row["advisory_action_class"])
            priority_key = str(row["advisory_priority_class"])
            action_counts[action_key] = action_counts.get(action_key, 0) + 1
            priority_counts[priority_key] = priority_counts.get(priority_key, 0) + 1

        return {
            "run": dict(run),
            "record_count": len(rows),
            "action_counts": action_counts,
            "priority_counts": priority_counts,
        }

    def list_exit_advisory_records_for_run(self, exit_advisory_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._records.list_for_run(conn, exit_advisory_run_id)
        return [dict(row) for row in rows]

    def get_exit_advisory_record_details(
        self,
        *,
        exit_advisory_record_id: str | None = None,
        market_id: str | None = None,
        exposure_type: str | None = None,
        exposure_ref_id: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if exit_advisory_record_id is not None:
                row = self._records.get_by_id(conn, exit_advisory_record_id)
            elif exposure_type is not None and exposure_ref_id is not None:
                row = self._records.get_latest_for_exposure(
                    conn,
                    exposure_type=exposure_type,
                    exposure_ref_id=exposure_ref_id,
                )
            elif market_id is not None:
                row = self._records.get_latest_by_market(conn, market_id)
            else:
                raise ValueError("exit_advisory_record_id, market_id, or exposure_type+exposure_ref_id is required")
        return dict(row) if row is not None else None

    def list_critical_exit_advisories(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._records.list_critical(conn, limit)
        return [dict(row) for row in rows]

    def compare_exit_advisory_to_policy_context(self, market_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            policy = self._policy_records.get_latest_by_market(conn, market_id)
            advisories = self._records.list_for_market(conn, market_id)
            paper_positions = self._paper_positions.list_for_market(conn, market_id)
            paper_orders = self._paper_orders.list_for_market(conn, market_id)
            shadow_positions = self._shadow_positions.list_for_market(conn, market_id)
            shadow_orders = self._shadow_orders.list_for_market(conn, market_id)
            live_positions = self._live_positions.list_for_market(conn, market_id)
            live_orders = self._live_orders.list_for_market(conn, market_id)

        if (
            policy is None
            and not advisories
            and not paper_positions
            and not paper_orders
            and not shadow_positions
            and not shadow_orders
            and not live_positions
            and not live_orders
        ):
            return None

        return {
            "invalidation_policy_record": dict(policy) if policy is not None else None,
            "exit_advisory_records": [dict(row) for row in advisories],
            "paper_positions": [dict(row) for row in paper_positions],
            "paper_orders": [dict(row) for row in paper_orders],
            "shadow_positions": [dict(row) for row in shadow_positions],
            "shadow_orders": [dict(row) for row in shadow_orders],
            "live_positions": [dict(row) for row in live_positions],
            "live_orders": [dict(row) for row in live_orders],
        }

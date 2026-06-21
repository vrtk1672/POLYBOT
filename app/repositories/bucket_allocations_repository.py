from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.bucket_allocation import BucketAllocationContract


class BucketAllocationsRepository:
    def insert(self, conn: Connection, allocation: BucketAllocationContract) -> None:
        conn.execute(
            """
            INSERT INTO bucket_allocations (
                id, bucket_allocation_run_id, market_id, trade_classification_id,
                primary_trade_type, assigned_bucket_class, bucket_target_fraction,
                bucket_cap_fraction, deployment_fraction, occupancy_status,
                deployability_class, allocation_reason_codes_json, allocation_reason_text,
                explanation_json, allocator_version
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
            """,
            (
                allocation.id,
                allocation.bucket_allocation_run_id,
                allocation.market_id,
                allocation.trade_classification_id,
                allocation.primary_trade_type,
                allocation.assigned_bucket_class,
                allocation.bucket_target_fraction,
                allocation.bucket_cap_fraction,
                allocation.deployment_fraction,
                allocation.occupancy_status,
                allocation.deployability_class,
                Jsonb(allocation.allocation_reason_codes_json),
                allocation.allocation_reason_text,
                Jsonb(allocation.explanation_json),
                allocation.allocator_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM bucket_allocations
            WHERE bucket_allocation_run_id = %s
            ORDER BY deployment_fraction DESC, created_at DESC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, bucket_allocation_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM bucket_allocations
            WHERE id = %s
            LIMIT 1
            """,
            (bucket_allocation_id,),
        ).fetchone()

    def get_latest_by_market(self, conn: Connection, market_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM bucket_allocations
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()

    def list_by_bucket(self, conn: Connection, assigned_bucket_class: str, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM bucket_allocations
            WHERE assigned_bucket_class = %s
            ORDER BY deployment_fraction DESC, created_at DESC
            LIMIT %s
            """,
            (assigned_bucket_class, limit),
        ).fetchall()

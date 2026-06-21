from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.data_foundation.data_completeness import DataCompletenessComputer
from app.db.connection import DatabaseConnectionFactory
from app.repositories.fee_snapshot_repository import FeeSnapshotRepository
from app.repositories.liquidity_snapshot_repository import LiquiditySnapshotRepository
from app.repositories.market_family_repository import MarketFamilyRepository
from app.repositories.market_registry_repository import MarketRegistryRepository
from app.repositories.market_rules_repository import MarketRulesRepository
from app.repositories.market_snapshot_v2_repository import MarketSnapshotV2Repository
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    output: dict[str, Any] = {}
    for key, value in dict(row).items():
        if hasattr(value, "isoformat"):
            output[key] = value.isoformat()
        else:
            output[key] = value
    return output


def create_data_foundation_router(*, connection_factory: DatabaseConnectionFactory | None = None) -> APIRouter:
    router = APIRouter(prefix="/data", tags=["data-foundation"])
    factory = connection_factory or DatabaseConnectionFactory()
    markets = MarketRegistryRepository()
    rules_repo = MarketRulesRepository()
    snapshots = MarketSnapshotV2Repository()
    orderbooks = OrderbookSnapshotRepository()
    liquidity_repo = LiquiditySnapshotRepository()
    fee_repo = FeeSnapshotRepository()
    family_repo = MarketFamilyRepository()
    completeness = DataCompletenessComputer()

    @router.get("/markets")
    async def list_markets(
        active: bool | None = None,
        closed: bool | None = None,
        market_family: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        if not factory.enabled:
            return {"markets": [], "count": 0, "filters": {"active": active, "closed": closed, "market_family": market_family}}
        with factory.connect() as conn:
            rows = markets.list_markets(conn, active=active, closed=closed, market_family=market_family, limit=limit)
        return {"markets": [_serialize(row) for row in rows], "count": len(rows), "filters": {"active": active, "closed": closed, "market_family": market_family}}

    @router.get("/markets/{market_id}")
    async def get_market(market_id: str) -> dict[str, Any]:
        if not factory.enabled:
            raise HTTPException(status_code=404, detail="market not found")
        with factory.connect() as conn:
            market = markets.get_market(conn, market_id)
            if market is None:
                raise HTTPException(status_code=404, detail="market not found")
            rules = rules_repo.get_rules(conn, market_id)
            latest_snapshot = snapshots.get_latest_snapshot(conn, market_id)
            orderbook = orderbooks.get_latest_snapshot(conn, market_id)
            liquidity = liquidity_repo.get_latest_snapshot(conn, market_id)
            fees = fee_repo.get_latest_snapshot(conn, market_id)
        score = completeness.compute_data_completeness(
            market=market,
            rules=rules,
            latest_snapshot=latest_snapshot,
            orderbook=orderbook,
            liquidity=liquidity,
            fees=fees,
        )
        return {
            "market": _serialize(market),
            "latest_rules": _serialize(rules),
            "latest_snapshot": _serialize(latest_snapshot),
            "latest_orderbook": _serialize(orderbook),
            "latest_liquidity": _serialize(liquidity),
            "latest_fees": _serialize(fees),
            "data_completeness": score.to_dict(),
        }

    @router.get("/markets/{market_id}/snapshots")
    async def market_snapshots(market_id: str, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        if not factory.enabled:
            return {"snapshots": []}
        with factory.connect() as conn:
            rows = snapshots.list_recent_snapshots(conn, market_id, limit)
        return {"snapshots": [_serialize(row) for row in rows], "count": len(rows)}

    @router.get("/markets/{market_id}/orderbook/latest")
    async def latest_orderbook(market_id: str) -> dict[str, Any]:
        if not factory.enabled:
            raise HTTPException(status_code=404, detail="orderbook not found")
        with factory.connect() as conn:
            row = orderbooks.get_latest_snapshot(conn, market_id)
        if row is None:
            raise HTTPException(status_code=404, detail="orderbook not found")
        return {"orderbook": _serialize(row)}

    @router.get("/coverage")
    async def coverage() -> dict[str, Any]:
        if not factory.enabled:
            return _empty_coverage()
        with factory.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_markets,
                    COUNT(*) FILTER (WHERE active = true) AS active_markets,
                    COUNT(*) FILTER (WHERE accepting_orders = true AND closed = false) AS tradable_markets,
                    COUNT(*) FILTER (WHERE closed = true) AS closed_markets
                FROM markets_v2
                """
            ).fetchone()
            coverage_row = conn.execute(
                """
                SELECT
                    (SELECT COUNT(DISTINCT market_id) FROM market_rules WHERE rules_text IS NOT NULL AND rules_text <> '') AS markets_with_rules,
                    (SELECT COUNT(DISTINCT market_id) FROM orderbook_snapshots) AS markets_with_orderbook,
                    (SELECT COUNT(DISTINCT market_id) FROM liquidity_snapshots) AS markets_with_liquidity,
                    (SELECT COUNT(*) FROM market_snapshots_v2 WHERE stale = true) AS stale_markets,
                    (SELECT AVG(data_completeness_score) FROM market_snapshots_v2) AS average_data_completeness,
                    (SELECT MAX(snapshot_at) FROM market_snapshots_v2) AS last_market_snapshot_at,
                    (SELECT MAX(snapshot_at) FROM orderbook_snapshots) AS last_orderbook_snapshot_at
                """
            ).fetchone()
        total = int(row["total_markets"] or 0)
        return {
            "total_markets": total,
            "active_markets": int(row["active_markets"] or 0),
            "tradable_markets": int(row["tradable_markets"] or 0),
            "markets_with_rules": int(coverage_row["markets_with_rules"] or 0),
            "markets_with_orderbook": int(coverage_row["markets_with_orderbook"] or 0),
            "markets_with_liquidity": int(coverage_row["markets_with_liquidity"] or 0),
            "orderbook_coverage_pct": _pct(coverage_row["markets_with_orderbook"], total),
            "rules_coverage_pct": _pct(coverage_row["markets_with_rules"], total),
            "liquidity_coverage_pct": _pct(coverage_row["markets_with_liquidity"], total),
            "stale_markets": int(coverage_row["stale_markets"] or 0),
            "closed_markets": int(row["closed_markets"] or 0),
            "average_data_completeness": float(coverage_row["average_data_completeness"] or 0),
            "last_market_snapshot_at": _iso(coverage_row["last_market_snapshot_at"]),
            "last_orderbook_snapshot_at": _iso(coverage_row["last_orderbook_snapshot_at"]),
        }

    @router.get("/families")
    async def families() -> dict[str, Any]:
        if not factory.enabled:
            return {"families": [], "count": 0}
        with factory.connect() as conn:
            rows = family_repo.list_families(conn)
        return {"families": [_serialize(row) for row in rows], "count": len(rows)}

    return router


def _pct(value: object, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((float(value or 0) / total) * 100, 2)


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _empty_coverage() -> dict[str, Any]:
    return {
        "total_markets": 0,
        "active_markets": 0,
        "tradable_markets": 0,
        "markets_with_rules": 0,
        "markets_with_orderbook": 0,
        "markets_with_liquidity": 0,
        "orderbook_coverage_pct": 0.0,
        "rules_coverage_pct": 0.0,
        "liquidity_coverage_pct": 0.0,
        "stale_markets": 0,
        "closed_markets": 0,
        "average_data_completeness": 0.0,
        "last_market_snapshot_at": None,
        "last_orderbook_snapshot_at": None,
    }
